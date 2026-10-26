"""Bridge server-list query handling: query detection, the cached and live status replies, plain-socket login sniffing and packet decoding.  Split from proxy.py for file size.

Method bodies are unchanged; they are methods of Bridge, reached
through ``self``.
"""

import asyncio
import json
import time
from . import (vanilla, wsproto)
from .i18n import tr
from .proxy import (PLAIN_WATCH_BYTES, QUERY_IDLE_SECONDS, STATUS_TIMEOUT, _SessionClosed, describe_connect_error, motd_lines)
from .translator import (chat_to_text, note)
from .utils import human_bytes
from .version import SERVICE_NAME
class BridgeQuery:
    """BridgeQuery mixin for Bridge."""
    async def _serve_query(self, payload: bytes) -> None:
        """The browser client's "server list" query.

        Its ServerQueryImpl sends only one text frame, ``Accept: MOTD``, right
        after connecting, then waits for a JSON text frame. Without an answer it
        would keep showing "cannot connect to the server", so this answers
        locally with the target server's status.
        """
        self.query_mode = True
        await self._answer_query(payload)
        # Log after the reply: the client times this exchange as its ping, and
        # a synchronous console/file write must not sit in front of the answer.
        self.log.info(tr('proxy.log.query_received', id=self.id, scheme=self.scheme.upper(),
                         payload=payload[:80].decode('utf-8', 'replace')))
        deadline = time.time() + QUERY_IDLE_SECONDS
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                self.close_reason = tr('proxy.reason.query_idle_timeout')
                return
            try:
                item = await asyncio.wait_for(self._receive_one(), timeout=remaining)
            except asyncio.TimeoutError:
                self.close_reason = tr('proxy.reason.query_idle_timeout')
                return
            if item is None:
                return
            if item[1]:
                await self._answer_query(item[0])
            else:
                self.log.debug(tr('proxy.log.query_binary_ignored',
                                  id=self.id, size=len(item[0])))
    async def _answer_query(self, payload: bytes) -> None:
        wants = {item.strip().upper()
                 for item in payload.decode('utf-8', 'replace').partition(':')[2].split(',')
                 if item.strip()}
        self.log.debug(tr('proxy.log.query_wants', id=self.id,
                          wants=','.join(sorted(wants)) or tr('proxy.log.empty')))
        if wants and 'MOTD' not in wants:
            return
        route = self.server.resolve_route(self.path)
        # A cache hit is returned immediately; a miss performs one live status
        # query in a worker thread.  The old code answered a miss with a
        # placeholder, which made the client show "no MOTD" even though the
        # target was reachable.  Waiting for the first query is the only way to
        # return the real MOTD without sending a second, unsolicited answer.
        try:
            status = await asyncio.to_thread(
                self.server.status_for_query, route['host'], route['port'],
                STATUS_TIMEOUT)
        except Exception as exc:
            status = {
                'ok': False,
                'ms': None,
                'status': None,
                'error': describe_connect_error(exc),
                'time': time.time(),
            }
        data = self._build_query_response(status)
        try:
            await self.ws.send(json.dumps(data, ensure_ascii=False))
        except Exception as exc:
            self.log.debug(tr('proxy.log.query_send_failed', id=self.id, error=exc))
            raise _SessionClosed()
    def _chat_body(self, reason: str) -> bytes:
        """The chat component a Disconnect packet carries."""
        text = note(reason or tr('proxy.reason.service_stopped'))
        return vanilla.write_string(json.dumps({'text': text}, ensure_ascii=False))
    def _chat_packet(self, packet_id: int, reason: str) -> bytes:
        """One bare packet (id + body), the form the WebSocket side uses."""
        return vanilla.write_varint(packet_id) + self._chat_body(reason)
    def _watch_plain_login(self, data: bytes) -> None:
        """Follow the login stage of a plain (untranslated) session.

        Two packets matter: Set Compression (it changes the framing of everything
        after it) and Login Success (after it the client is in the game).  The
        answer is only used to pick a goodbye packet if the service stops later;
        the watcher steps aside for good once the game starts or the stream stops
        looking like the vanilla protocol.
        """
        if self.plain_watch_done:
            return
        if self._plain_down is None:
            self._plain_down = vanilla.Decoder(0)
        self._plain_down.push(data)
        while True:
            try:
                packet = self._plain_down.next_packet()
            except vanilla.ProtocolError:
                self._stop_plain_watch()
                return
            if packet is None:
                return
            if packet.packet_id == vanilla.LOGIN_SET_COMPRESSION:
                try:
                    threshold, _ = vanilla.read_varint(packet.body, 0)
                except vanilla.ProtocolError:
                    threshold = 0
                self.plain_compressed = True
                self._plain_down.threshold = max(1, threshold)
                if self._plain_up is not None:
                    self._plain_up.threshold = max(1, threshold)
            elif packet.packet_id == vanilla.LOGIN_SUCCESS:
                self.plain_playing = True
                self._stop_plain_watch()
                return
            elif packet.packet_id == vanilla.LOGIN_DISCONNECT:
                self._stop_plain_watch()
                return
            if self._plain_down.pending > PLAIN_WATCH_BYTES:
                self._stop_plain_watch()
                return
    def _watch_plain_login_sent(self, data: bytes) -> None:
        """Client side of _watch_plain_login: notice encryption being switched on.

        From that moment on no plaintext packet may go into the session, so a
        goodbye would be garbage and is left out.
        """
        if self.plain_watch_done or self.translator is not None or not data:
            return
        if self._plain_up is None:
            self._plain_up = vanilla.Decoder(0)
        self._plain_up.push(data)
        while True:
            try:
                packet = self._plain_up.next_packet()
            except vanilla.ProtocolError:
                self._stop_plain_watch()
                return
            if packet is None:
                return
            if packet.packet_id == vanilla.LOGIN_ENCRYPTION_RESPONSE:
                self.plain_encrypted = True
                self._stop_plain_watch()
                return
            if self._plain_up.pending > PLAIN_WATCH_BYTES:
                self._stop_plain_watch()
                return
    def _stop_plain_watch(self) -> None:
        self.plain_watch_done = True
        self._plain_down = None
        self._plain_up = None
    # ---------- server list query (Accept: MOTD) ----------
    @staticmethod
    def _is_query(payload: bytes) -> bool:
        return payload.lstrip()[:7].lower() == b'accept:'
    def _build_query_response(self, status: dict | None) -> dict:
        """Build the JSON that the client's ServerData.setMOTDFromQuery wants.

        Field meanings (from the client source):
            type/vers/brand/name/time/cracked  +  data{ motd[at most two lines],
            online, max, players, icon }
        data.players is what the list shows as "details" on hover.
        """
        config = self.config
        detail: list[str] = []
        motd: list[str] = []
        online = 0
        max_players = 0
        version_name = '1.8.8'
        raw = (status or {}).get('status') or {}
        query_error = str((status or {}).get('error') or '').strip()
        if raw:
            motd = motd_lines(raw.get('description'))
            version = raw.get('version') or {}
            version_name = str(version.get('name') or version_name)
            players = raw.get('players') or {}
            try:
                online = int(players.get('online') or 0)
                max_players = int(players.get('max') or 0)
            except (TypeError, ValueError):
                online = max_players = 0
            for item in (players.get('sample') or [])[:12]:
                name = chat_to_text(item.get('name') if isinstance(item, dict) else item).strip()
                if name:
                    detail.append(name)
        if not motd:
            motd = [tr('proxy.query.status_error', error=query_error)
                    if query_error else tr('proxy.query.no_motd')]
        brand = (config.server_brand or SERVICE_NAME).strip() or SERVICE_NAME
        # the "version" column in the client's list: use the configured value when
        # one is set, otherwise show the version name reported by the target server
        shown_version = (getattr(config, 'server_brand_version', '') or '').strip() or version_name
        return {
            'type': 'MOTD',
            'name': brand,
            'brand': brand,
            'vers': shown_version,
            'cracked': True,
            'time': int(time.time() * 1000),
            'data': {
                'motd': motd,
                'online': online,
                'max': max_players,
                'players': detail,
                'icon': False,
            },
        }
    def _decode_payload(self, payload: bytes, is_text: bool) -> bytes:
        if not is_text:
            return payload
        if not self.base64_mode:
            self.base64_mode = True
            self.log.warn(tr('proxy.log.base64_switch', id=self.id))
        data = wsproto.decode_base64_text(payload)
        if data is None:
            preview = payload[:100].decode('utf-8', 'replace')
            self.log.warn(tr('proxy.log.bad_base64', id=self.id,
                             size=len(payload), preview=preview))
            return b''
        self.log.debug(tr('proxy.log.base64_decoded', id=self.id,
                          size=len(payload), decoded=len(data)))
        return data
    # ---------- wind-down ----------
    async def _close_ws(self) -> None:
        if self._ws_closed:
            return
        self._ws_closed = True
        try:
            await self.ws.close(code=self.close_code, reason=self.close_text)
        except Exception:
            pass
    async def _cleanup(self) -> None:
        self._close_writer()
        translator = self.translator
        if translator is not None and translator.close_reason and not self.close_reason:
            self.close_reason = translator.close_reason
        await self._close_ws()
        if self.query_mode and not self.close_reason:
            self.close_reason = tr('proxy.reason.normal_close')
        self.log.info(tr('proxy.log.session_end', id=self.id,
                         seconds=time.time() - self.started_at,
                         reason=self.close_reason or tr('proxy.reason.normal_close'),
                         up=human_bytes(self.bytes_to_server),
                         down=human_bytes(self.bytes_to_client)))
        for hint in self._diagnose():
            self.log.warn('#%d %s' % (self.id, hint))
        self.server.forget(self)
    def _diagnose(self) -> list[str]:
        """Give one plausible cause when a connection ends abnormally, so the log
        does not end on a bare "connection ended"."""
        if self.translator is not None or self.query_mode:
            # the translation layer's log already explains the reason; no guessing needed
            return []
        hints: list[str] = []
        if self.target_sent_any:
            return hints
        info = self.handshake_info
        if info is None:
            return hints
        if info['next_state'] == 2:      # login
            hints.append(tr('proxy.diag.no_reply'))
            if info['address'] not in ('',) and self.endpoint:
                host = self.endpoint[0]
                if info['address'] not in host and ':' not in info['address']:
                    hints.append(tr('proxy.diag.address_mismatch',
                                    shown=info['address'], actual=host))
            hints.append(tr('proxy.diag.protocol_unsupported',
                            version=info['protocol']))
            hints.append(tr('proxy.diag.policy'))
        return hints
