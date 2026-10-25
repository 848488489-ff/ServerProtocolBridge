"""Forwarding core: bridges a local wss:// / ws:// WebSocket connection to the
target Minecraft server's TCP connection.

The HTTP and WebSocket layer is handled directly by the ``websockets`` library:
fragment reassembly, heartbeats (PING/PONG), subprotocol negotiation, the
closing handshake and frame size limits are all left to that implementation.
There is no ASGI layer and no FastAPI/uvicorn process in front of the game
traffic.  This module only does three things:

* move the messages coming from the client over to the target server's TCP
  connection verbatim, and the other way around;
* once the peer turns out to be a browser (EaglercraftX-family) client, hand it
  to translator.py for protocol translation;
* answer the browser client's server-list MOTD query locally (it sends the
  text frame ``Accept: MOTD``), otherwise it would keep showing "unable to
  connect".

On top of that the same listener serves a status page: opening
http://<listen address>:<ws port>/ in a browser shows the "current server
address", the target server status, the connection count and the traffic.
"""

from __future__ import annotations

import asyncio
import base64
import concurrent.futures
import json
import socket
import ssl
import threading
import time
from collections.abc import Callable

from websockets.asyncio.server import ServerConnection, serve
from websockets.datastructures import Headers
from websockets.exceptions import ConnectionClosed
from websockets.http11 import Request, Response

from . import accounts, certs, eagler, handshake, resolver, vanilla, wsproto
from .config import Config, parse_address
from .i18n import tr
from .logger import NullLogger
from .translator import EaglerTranslator, chat_to_legacy, chat_to_text, note
from .utils import human_bytes
from .version import SERVICE_NAME, VERSION

RECV_SIZE = 262144           # one TCP read often contains a whole burst of game packets
WS_MAX_QUEUE = 32            # incoming message queue: absorb bursts without backpressure
WS_WRITE_LIMIT = 262144      # outgoing high-water mark: do not pause on every small packet
CLOSE_GRACE = 0.35           # finish the closing words before disconnecting; give the client time to read them
PLAIN_WATCH_BYTES = 64 * 1024   # how far a plain session's login stage is watched before giving up on it
FIRST_MESSAGE_WAIT = 1.0     # how long to wait for the client's first message (tells list queries and game handshakes apart)
CONNECT_FAIL_WAIT = 1.0      # when the target is down, wait a bit longer for the client's first packet (we need its handshake version)
QUERY_IDLE_SECONDS = 300.0   # max idle time of a "server list" query connection
STATUS_TIMEOUT = 4.0         # timeout of a live target status query


class _SessionClosed(Exception):
    """This connection should wind down now (not a failure)."""


class _NoDelayServerConnection(ServerConnection):
    """Server connection that disables Nagle before the first game packet.

    Game packets are small and latency-sensitive; batching them in the kernel
    adds avoidable delay.  The TCP socket is only reachable from the transport,
    so this is done at connection setup rather than in the message handler.
    """

    def connection_made(self, transport) -> None:
        super().connection_made(transport)
        try:
            sock = transport.get_extra_info('socket')
            if sock is not None:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except (OSError, AttributeError):
            pass


def describe_connect_error(exc: BaseException) -> str:
    """Turn a connection failure into one sentence the player can understand."""
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return tr('proxy.error.timeout')
    if isinstance(exc, socket.gaierror):
        return tr('proxy.error.dns')
    if isinstance(exc, ConnectionRefusedError):
        return tr('proxy.error.refused')
    if isinstance(exc, OSError):
        mapping = {
            110: tr('proxy.error.timeout'),
            10060: tr('proxy.error.timeout'),
            111: tr('proxy.error.refused'),
            10061: tr('proxy.error.refused'),
            113: tr('proxy.error.unreachable'),
            101: tr('proxy.error.unreachable'),
            10051: tr('proxy.error.unreachable'),
            10065: tr('proxy.error.unreachable'),
        }
        text = mapping.get(getattr(exc, 'errno', None))
        if text:
            return text
    text = str(exc).strip()
    return text or exc.__class__.__name__


def motd_lines(raw, limit: int = 2, legacy: bool = True) -> list[str]:
    """Split the server's title screen into at most ``limit`` lines.

    The server-list query expects the legacy ``§`` colour codes in its MOTD
    strings; the status page and logs use ``legacy=False`` to get plain text.
    """
    text = chat_to_legacy(raw) if legacy else chat_to_text(raw)
    lines = [line.strip() for line in text.split('\n')]
    return [line for line in lines if line][:limit]


class Stats:
    def __init__(self):
        self._lock = threading.Lock()
        self.started_at = time.time()
        self.active = 0
        self.total = 0
        self.bytes_to_server = 0
        self.bytes_to_client = 0

    def add_bytes(self, to_server: int = 0, to_client: int = 0) -> None:
        with self._lock:
            self.bytes_to_server += to_server
            self.bytes_to_client += to_client

    def connection_opened(self) -> None:
        with self._lock:
            self.active += 1
            self.total += 1

    def connection_closed(self) -> None:
        with self._lock:
            if self.active > 0:
                self.active -= 1

    def snapshot(self) -> dict:
        with self._lock:
            return {
                'uptime': time.time() - self.started_at,
                'active': self.active,
                'total': self.total,
                'bytes_to_server': self.bytes_to_server,
                'bytes_to_client': self.bytes_to_client,
            }


def _discard_future_result(future: asyncio.Future | concurrent.futures.Future) -> None:
    """Drop a task/future result (handled elsewhere) but retrieve any exception, so
    no unhandled-exception warning is left behind.

    A cancelled one raises CancelledError from .exception(), and a future scheduled
    onto an event loop is cancelled when that loop shuts down, so the state is
    checked first -- otherwise the done callback itself blows up with "exception
    calling callback for <Future ... state=cancelled>" during a normal shutdown.
    """
    if not future.cancelled():
        future.exception()


def _set_socket_options(writer: asyncio.StreamWriter) -> None:
    sock = writer.get_extra_info('socket')
    if sock is None:
        return
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    except OSError:
        pass


class Bridge:
    """One WebSocket client connection <-> one target server TCP connection.

    Data flow:
        client --(WebSocket messages)--> Bridge --(TCP byte stream)--> target server
        target server --(TCP byte stream)--> Bridge --(one frame per packet)--> client

    The browser client's protocol translation layer wants to emit several packets
    for a single frame (the handshake packet plus buffered game packets), and each
    of those packets must occupy a WebSocket frame of its own. Payloads destined
    for the client are therefore queued first and sent frame by frame in order by
    _drain_outbox; bytes destined for the target server go through
    _flush_to_server the same way.
    """

    def __init__(self, server: 'ProxyServer', websocket: ServerConnection, path: str,
                 scheme: str, addr, log, subprotocol: str | None = None):
        self.server = server
        self.config = server.config
        self.log = log
        self.ws = websocket
        self.path = path
        self.scheme = scheme
        self.addr = addr
        self.subprotocol = subprotocol
        self.id = server.next_id()
        self.base64_mode = bool(subprotocol and subprotocol.lower() == 'base64')

        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.loop: asyncio.AbstractEventLoop | None = None

        self.started_at = time.time()
        self.close_reason = ''
        self.close_code = 1000
        self.close_text = 'session closed'
        self.bytes_to_server = 0
        self.bytes_to_client = 0
        self.frames_in = 0

        self.route_label = ''
        self.route_host = ''
        self.target_text = ''
        self.endpoint: tuple[str, int] | None = None

        self.handshake_seen = False          # whether the handshake packet at the start of the upstream has been parsed
        self._handshake_buffer = b''
        self.handshake_info: dict | None = None
        self.target_sent_any = False         # whether the target server has sent any data back
        self.protocol_checked = False        # whether the first upstream data frame was already checked for the client type
        self.query_mode = False              # this is only a server list query, not joining the game
        self.translator: EaglerTranslator | None = None
        # During login the translator may block in accounts.join_session(), so
        # its calls run in a worker thread.  Once the game is running the
        # translation is tiny and latency-sensitive; calling it on the event
        # loop avoids a thread-pool round trip (and its GIL contention) for
        # every packet.  ``_translator_inflight`` closes the race where one
        # pump is still in a worker while the other switches to the fast path.
        self._translator_direct = False
        self._translator_inflight = 0

        self._outbox: list[bytes] = []       # payloads to send to the client (one frame each)
        self._to_server: list[bytes] = []    # bytes to write to the target server
        # The translation layer may queue backend bytes from a worker thread
        # (login/transaction replies) while a pump drains the queue on the
        # event loop.  Copy-and-clear must be atomic with respect to appends,
        # otherwise a reply can be appended between the copy and the clear and
        # silently disappear.
        self._to_server_lock = threading.Lock()
        self._close_after_flush = False
        self._ws_closed = False
        self._first_task: asyncio.Task | None = None

        # Plain (untranslated) sessions: the login stage is followed just far
        # enough to know which goodbye packet would be legal if the service
        # stops later on.  Nothing is modified or held back on the way.
        self.plain_playing = False
        self.plain_compressed = False
        self.plain_encrypted = False
        self.plain_watch_done = False
        self._plain_down: vanilla.Decoder | None = None
        self._plain_up: vanilla.Decoder | None = None

    # ---------- lifecycle ----------
    async def run(self) -> None:
        self.loop = asyncio.get_running_loop()
        try:
            await self._handle()
        except (_SessionClosed, eagler.HandshakeError):
            pass
        except asyncio.CancelledError:
            self.close_reason = self.close_reason or tr('proxy.reason.service_stopped')
            raise
        except Exception as exc:  # one bad connection must not take the whole service down
            self.log.error(tr('proxy.log.connection_error', id=self.id, error=exc))
        finally:
            await self._cleanup()

    async def shutdown(self, reason: str) -> None:
        """Server-initiated disconnect (called while the listeners stop): say goodbye
        in the client's own protocol first, so it does not only see the cut."""
        if not self.close_reason:
            self.close_reason = reason
        self.close_code = 1001
        self.close_text = 'server stopping'
        if getattr(self.config, 'auto_exit', True):
            await self._say_goodbye(reason)
        await self._close_ws()
        self._close_writer()

    async def _say_goodbye(self, reason: str) -> None:
        """Tell the client the session is over before the socket closes.

        A raw close is what a game client shows as an ended data stream; a real
        disconnect packet lets it name the reason instead.  Only states this
        bridge can vouch for are used: the translation layer knows its phase, and
        a plain session is only answered while it is in the login stage or was
        seen starting the game.
        """
        if self._ws_closed:
            return
        translator = self.translator
        if translator is not None:
            try:
                if translator.login_done:
                    # Playing: the client speaks vanilla over the WebSocket, so a
                    # bare play Disconnect packet is what it expects.
                    await self._send_payload(self._chat_packet(vanilla.PLAY_DISCONNECT,
                                                               reason))
                else:
                    # Still in the login stages: there the client listens for the
                    # transport's own error packet.
                    translator.fail(reason)
                    await self._drain_outbox()
            except _SessionClosed:
                return
            self.log.debug(tr('proxy.log.goodbye_sent', id=self.id))
            await asyncio.sleep(CLOSE_GRACE)
            return
        if self.query_mode or self.plain_encrypted:
            # a server list query has nobody in the game, and into an encrypted
            # session a plaintext packet would only be garbage
            return
        info = self.handshake_info
        if not info or info.get('next_state') != 2:
            return
        try:
            if self.plain_playing:
                protocol = int(info.get('protocol') or 0)
                if protocol != 47:
                    # The play-phase disconnect packet moved around between
                    # versions; guessing would hand the client a packet it
                    # cannot read, so nothing is sent.
                    self.log.debug(tr('proxy.log.goodbye_skipped', id=self.id,
                                      protocol=protocol))
                    return
                encoder = vanilla.Encoder(1 if self.plain_compressed else 0)
                await self._send_payload(encoder.frame(
                    self._chat_packet(vanilla.PLAY_DISCONNECT, reason)))
            else:
                # Login stage: 0x00 means the same thing in every protocol version.
                await self._send_payload(vanilla.pack(vanilla.LOGIN_DISCONNECT,
                                                      self._chat_body(reason)))
        except _SessionClosed:
            return
        self.log.debug(tr('proxy.log.goodbye_sent', id=self.id))
        await asyncio.sleep(CLOSE_GRACE)

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

    async def _handle(self) -> None:
        config = self.config
        route = self.server.resolve_route(self.path)
        self.route_label = route['label']
        self.route_host = route['host']
        self.target_text = (route['source'] or config.target or '').strip()

        self.log.info(tr('proxy.log.accepted', id=self.id, scheme=self.scheme.upper(),
                         host=self.addr[0], port=self.addr[1],
                         source=route['source'], label=route['label']))

        first = await self._wait_first_message(FIRST_MESSAGE_WAIT)
        if first is not None and first[1] and self._is_query(first[0]):
            # "server list" query: answer locally, no need to connect to the target server
            await self._serve_query(first[0])
            return

        try:
            host, port = await asyncio.to_thread(
                self.server.resolve_endpoint, route['host'], route['port'])
        except Exception as exc:
            self.close_reason = tr('proxy.error.resolve_failed', error=exc)
            self.close_code = 1011
            self.log.warn('#%d %s' % (self.id, self.close_reason))
            return
        self.endpoint = (host, port)

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port, limit=RECV_SIZE),
                timeout=max(1.0, float(config.connect_timeout)))
        except Exception as exc:
            await self._report_connect_failure(host, port, exc, first)
            return
        self.reader, self.writer = reader, writer
        _set_socket_options(writer)
        self.log.info(tr('proxy.log.connected', id=self.id, host=host, port=port))

        # if the first packet is already in hand, handle it right away; otherwise
        # leave it to the pumps to keep waiting
        if first is not None:
            self._first_task = None
            await self._handle_incoming(first[0], first[1])
        tasks = [
            asyncio.create_task(self._pump_from_client(), name='mcjs-ws-%d' % self.id),
            asyncio.create_task(self._pump_from_server(), name='mcjs-tcp-%d' % self.id),
        ]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _receive_one(self) -> tuple[bytes, bool] | None:
        """Receive one message from the client, returning (payload, is_text);
        None when the peer disconnects."""
        try:
            message = await self.ws.recv()
        except ConnectionClosed:
            code = self.ws.close_code
            if not self.close_reason:
                self.close_reason = tr('proxy.reason.client_closed_code', code=code) \
                    if code else tr('proxy.reason.client_closed')
            self.close_code = 1001
            return None
        except Exception:
            return None
        if isinstance(message, str):
            return message.encode('utf-8'), True
        return message, False

    async def _wait_first_message(self, timeout: float) -> tuple[bytes, bool] | None:
        """Wait for the client's first message after it connects.

        The client always speaks first (game handshake / ``Accept: MOTD`` list
        query), so it is used to tell what this connection is for. A timeout is
        fine -- the read task stays around for the pumps, so no message is lost.
        """
        if self._first_task is None:
            self._first_task = asyncio.ensure_future(self._receive_one())
            self._first_task.add_done_callback(_discard_future_result)
        try:
            return await asyncio.wait_for(asyncio.shield(self._first_task), timeout=timeout)
        except asyncio.TimeoutError:
            return None
        except Exception:
            return None

    async def _report_connect_failure(self, host: str, port: int, exc: BaseException,
                                      first: tuple[bytes, bool] | None) -> None:
        """Target server unreachable: try to tell the player the reason directly
        instead of leaving them with a bare Connection Closed."""
        reason = describe_connect_error(exc)
        self.close_reason = tr('proxy.error.connect_failed', host=host, port=port, reason=reason)
        self.close_code = 1011
        self.close_text = 'cannot reach target'
        self.log.warn('#%d %s' % (self.id, self.close_reason))
        if first is None:
            first = await self._wait_first_message(CONNECT_FAIL_WAIT)
        self._first_task = None
        payload = first[0] if first else b''
        if not payload or eagler.parse_client_version(payload) is None:
            # not a browser client (or it has not started talking yet); closing
            # the connection is all we can do
            return
        message = note(tr('proxy.error.connect_note', host=host, port=port, reason=reason))
        try:
            await self.ws.send(
                eagler.pack_error_pre_version(eagler.ERROR_CUSTOM_MESSAGE, message))
            self.log.info(tr('proxy.log.failure_sent', id=self.id))
            await asyncio.sleep(CLOSE_GRACE)
        except Exception as exc2:
            self.log.debug(tr('proxy.log.failure_send_error', id=self.id, error=exc2))

    # ---------- server list query (Accept: MOTD) ----------
    @staticmethod
    def _is_query(payload: bytes) -> bool:
        return payload.lstrip()[:7].lower() == b'accept:'

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
                name = chat_to_legacy(item.get('name') if isinstance(item, dict) else item).strip()
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

    # ---------- client -> target server ----------
    async def _pump_from_client(self) -> None:
        pending, self._first_task = self._first_task, None
        while True:
            if pending is not None:
                item = await pending
                pending = None
            else:
                item = await self._receive_one()
            if item is None:
                self.close_reason = self.close_reason or tr('proxy.reason.client_closed')
                self.close_code = 1001
                return
            await self._handle_incoming(item[0], item[1])

    async def _handle_incoming(self, payload: bytes, is_text: bool) -> None:
        self.frames_in += 1
        if self.frames_in <= 4:      # the first frames matter for debugging; log them at debug level only
            self.log.debug(tr('proxy.log.frame_in', id=self.id, index=self.frames_in,
                              kind=tr('proxy.frame.text') if is_text else tr('proxy.frame.binary'),
                              size=len(payload), preview=handshake.hex_preview(payload)))
        if self.translator is not None and is_text:
            # browser clients only use binary frames for game data, so a text
            # frame means the peer is not one of them
            self.log.warn(tr('proxy.log.text_frame_closing', id=self.id))
            self.close_reason = tr('proxy.reason.text_frame_in_translate')
            self.close_code = 1003
            self.close_text = 'text frame not allowed'
            raise _SessionClosed()
        data = self._decode_payload(payload, is_text)
        if self.translator is not None:
            to_server = await self._feed_translator_client(data)
        else:
            if not self.protocol_checked and data:
                self.protocol_checked = True
                if (getattr(self.config, 'eagler_translate', True)
                        and eagler.parse_client_version(data) is not None):
                    self._start_translator()
                    data = self.translator.feed_client(data) if self.translator else data
            to_server = self._inspect_handshake(data)
        if to_server:
            self._watch_plain_login_sent(to_server)
            self._queue_to_backend(to_server)
        await self._flush_to_server()
        await self._drain_outbox()

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

    async def _feed_translator_client(self, data: bytes) -> bytes:
        translator = self.translator
        if translator is None:
            return data
        return await self._translator_call(translator.feed_client, data, translator)

    async def _feed_translator_server(self, data: bytes) -> list[bytes]:
        translator = self.translator
        if translator is None:
            return []
        return await self._translator_call(translator.feed_server, data, translator)

    async def _translator_call(self, func: Callable[[bytes], object], data: bytes,
                               translator: EaglerTranslator):
        """Run one translator direction on the cheapest safe execution path.

        Login can perform a blocking Microsoft session join, so it stays in a
        worker thread.  Play traffic is parsed packet by packet and must not pay
        a thread-pool hand-off per frame: that adds jitter, and the GIL is
        already released by the C parts that matter (TLS, AES, zlib).  The
        switch happens only after every in-flight worker call has returned, so
        the two pumps never race on the translator's state.
        """
        if self._translator_direct:
            return func(data)
        self._translator_inflight += 1
        completed = False
        try:
            result = await asyncio.to_thread(func, data)
            completed = True
            return result
        finally:
            self._translator_inflight -= 1
            if (completed and self._translator_inflight == 0
                    and translator.phase == 'play'
                    and translator.login_done):
                self._translator_direct = True

    def _start_translator(self) -> None:
        """The peer turned out to be a browser client: set up the protocol translation layer."""
        config = self.config
        host, port = self.endpoint if self.endpoint else (self.route_host or '', 25565)
        self.translator = EaglerTranslator(
            target_host=self.route_host or host,
            target_port=port,
            log=self.log,
            tag='#%d' % self.id,
            send_client=self._queue_to_client,
            send_backend=self._queue_to_backend,
            request_close=self._translator_close,
            brand=(config.server_brand or SERVICE_NAME).strip() or SERVICE_NAME,
            brand_version=(config.server_brand_version or '').strip() or VERSION,
            spoof_client=getattr(config, 'spoof_client', 'off'),
            spoof_brand=config.spoof_brand_value(),
            login_ack=bool(getattr(config, 'login_ack', True)),
            resource_pack_mode=getattr(config, 'resource_pack_mode', 'forward'),
            account=self._selected_account(),
        )
        self.log.info(tr('proxy.log.translator_enabled', id=self.id))

    def _selected_account(self):
        """The account selected in the settings, or None.

        accounts.json is read at connect time, so picking another account in
        the account manager applies to the very next client without restarting
        the service.  A broken store is logged and treated as "no account": it
        must never keep people from connecting.
        """
        selection = str(getattr(self.config, 'account_override', '') or '').strip()
        try:
            if selection:
                account = accounts.find_account(selection)
                if account is None:
                    self.log.warn(tr('proxy.log.account_not_found', name=selection))
                return account
            return accounts.active_account()
        except Exception as exc:               # unreadable file, bad JSON, ...
            self.log.warn(tr('proxy.log.account_load_failed', error=exc))
            return None

    def _queue_to_client(self, data: bytes) -> None:
        """Translator callback: queue one frame to be sent to the client (sent one
        by one, see _drain_outbox)."""
        self._outbox.append(data)

    def _queue_to_backend(self, data: bytes) -> None:
        """Queue a chunk of bytes for the target server (thread-safe)."""
        with self._to_server_lock:
            self._to_server.append(data)

    def _translator_close(self, reason: str) -> None:
        """The translator asks to wind down: let it send what it has to say first,
        wait a moment, and only then disconnect.

        Closing right away would often cut the client off before it has read *why*
        it was rejected.
        """
        if not self.close_reason:
            self.close_reason = reason
        self._close_after_flush = True

    def _inspect_handshake(self, data: bytes) -> bytes:
        """Parse the handshake packet at the start of the upstream once (for the
        log) and, when configured, rewrite the address inside it.

        A client may split the handshake packet across several sends, so this
        buffers until it is complete before forwarding; every other byte is
        forwarded verbatim -- no game data is ever modified.
        """
        if self.handshake_seen:
            return data
        buffer = self._handshake_buffer + data
        size = handshake.packet_size(buffer)
        if (size is not None and size <= 4096 and len(buffer) < size
                and handshake.looks_like_handshake(buffer)):
            self._handshake_buffer = buffer
            self.log.debug(tr('proxy.log.handshake_incomplete',
                              id=self.id, missing=size - len(buffer)))
            return b''
        self.handshake_seen = True
        self._handshake_buffer = b''
        info = handshake.parse_handshake(buffer)
        if info is None:
            self.log.debug(tr('proxy.log.not_handshake',
                              id=self.id, preview=handshake.hex_preview(buffer)))
            return buffer
        self.handshake_info = info
        self.log.info(tr('proxy.log.handshake',
                         id=self.id, info=handshake.describe_handshake(info)))
        if not getattr(self.config, 'rewrite_handshake_host', False) or not self.endpoint:
            return buffer
        host, port = self.endpoint
        rewritten = handshake.rewrite_handshake(buffer, host, port)
        if rewritten is None:
            self.log.warn(tr('proxy.log.rewrite_failed', id=self.id))
            return buffer
        if rewritten == buffer:
            return buffer
        self.log.info(tr('proxy.log.address_rewritten', id=self.id, host=host, port=port))
        return rewritten

    # ---------- target server -> client ----------
    async def _pump_from_server(self) -> None:
        reader = self.reader
        while True:
            data = await reader.read(RECV_SIZE)
            if not data:
                break
            self.target_sent_any = True
            self.bytes_to_client += len(data)
            self.server.stats.add_bytes(to_client=len(data))
            translator = self.translator
            if translator is not None:
                frames = await self._feed_translator_server(data)
                if translator.close_reason and not self.close_reason:
                    self.close_reason = translator.close_reason
                await self._send_payloads(frames)
                await self._flush_to_server()
                await self._drain_outbox()
            else:
                self._watch_plain_login(data)
                await self._send_payload(data)
        if not self.close_reason:
            self.close_reason = tr('proxy.reason.target_closed')
            self.close_code = 1000
        translator = self.translator
        if translator is not None and not translator.login_done:
            # closed by the peer during login: give the player a reason, otherwise
            # they would only see Connection Closed
            translator.fail(tr('proxy.error.login_stage_closed'))
        await self._flush_to_server()
        await self._drain_outbox()

    # ---------- send/receive queues ----------
    async def _flush_to_server(self) -> None:
        # Note: the list must be drained in place. The translation layer holds
        # _to_server.append as its callback; swapping the attribute for a fresh
        # list would send every later append into an orphaned list nobody reads,
        # and not a single byte would go out.
        with self._to_server_lock:
            if not self._to_server:
                return
            chunks = list(self._to_server)
            self._to_server.clear()
        writer = self.writer
        if writer is None:
            return
        total = sum(len(chunk) for chunk in chunks)
        try:
            for chunk in chunks:
                writer.write(chunk)
            await writer.drain()
        except (OSError, RuntimeError) as exc:
            self.close_reason = self.close_reason or tr('proxy.reason.send_to_target_failed',
                                                        error=exc)
            self.close_code = 1001
            raise _SessionClosed()
        self.bytes_to_server += total
        self.server.stats.add_bytes(to_server=total)

    async def _drain_outbox(self) -> None:
        if self._outbox:
            # same as _flush_to_server: must be cleared in place, or frames the
            # translation layer appends later would be lost
            frames = list(self._outbox)
            self._outbox.clear()
            await self._send_payloads(frames)
        if self._close_after_flush:
            self._close_after_flush = False
            await asyncio.sleep(CLOSE_GRACE)
            raise _SessionClosed()

    async def _send_payloads(self, frames: list[bytes]) -> None:
        """Send a run of payloads coming from the protocol translation layer: each packet must occupy its own WebSocket frame."""
        for frame in frames:
            if frame:
                await self._send_payload(frame)

    async def _send_payload(self, data: bytes) -> None:
        if not data or self._ws_closed:
            return
        try:
            if self.base64_mode:
                await self.ws.send(base64.b64encode(data).decode('ascii'))
            else:
                await self.ws.send(data)
        except Exception as exc:
            self.log.debug(tr('proxy.log.send_client_failed', id=self.id, error=exc))
            self.close_code = 1001
            raise _SessionClosed()

    # ---------- wind-down ----------
    async def _close_ws(self) -> None:
        if self._ws_closed:
            return
        self._ws_closed = True
        try:
            await self.ws.close(code=self.close_code, reason=self.close_text)
        except Exception:
            pass

    def _close_writer(self) -> None:
        writer, self.writer = self.writer, None
        if writer is not None:
            try:
                writer.close()
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


class ProxyServer:
    """WebSocket listeners + connection management + status page."""

    def __init__(self, config: Config, logger=None):
        self.config = config
        self.log = logger or NullLogger()
        self.stats = Stats()
        self.certificate: dict | None = None
        self.running = False
        self._servers: list[dict] = []
        self._connections: set[Bridge] = set()
        self._lock = threading.Lock()
        self._srv_cache: dict[str, tuple[str, int, float]] = {}
        self._status_cache: dict[str, dict] = {}
        self._status_refreshing: set[str] = set()
        self._status_warming: set[str] = set()
        self._id_counter = 0

    # ---------- public API ----------
    def next_id(self) -> int:
        with self._lock:
            self._id_counter += 1
            return self._id_counter

    def start(self) -> dict:
        config = self.config
        problems = config.validate()
        if problems:
            raise ValueError(tr('proxy.error.bad_config', problems='; '.join(problems)))

        ssl_context: ssl.SSLContext | None = None
        if config.tls_enabled:
            self.certificate = certs.ensure_certificate(
                config.resolved_cert_dir,
                common_name=config.cert_common_name or 'localhost',
                extra_names=config.cert_extra_names,
                days=int(config.cert_days),
                generator=config.cert_generator,
                regenerate=False,
                logger=self.log,
            )
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
            ssl_context.options |= ssl.OP_NO_COMPRESSION
            ssl_context.load_cert_chain(
                self.certificate['cert_path'], self.certificate['key_path'])

        listeners: list[str] = []
        self.running = True
        try:
            if config.tls_enabled and int(config.wss_port) > 0:
                listeners.append(self._start_listener(
                    int(config.wss_port), 'wss', ssl_context))
            if int(config.ws_port) > 0:
                listeners.append(self._start_listener(int(config.ws_port), 'ws', None))
        except Exception:
            self.running = False
            self._shutdown_servers()
            raise
        self.log.info(tr('proxy.log.listeners_ready', listeners=', '.join(listeners)))
        # Warm the server-list status cache off the event loop.  A cache hit
        # answers immediately; a cache miss waits for one live target query so
        # the client sees the real MOTD instead of a placeholder.  Prewarming
        # makes that wait unlikely for the first browser connection.
        if config.status_cache:
            addresses = [config.target]
            addresses.extend((config.routes or {}).values())
            for address in addresses:
                try:
                    host_name, target_port = parse_address(address)
                except (TypeError, ValueError):
                    continue
                self.warm_status_async(host_name, target_port)
        return self.describe()

    def stop(self) -> None:
        if not self.running:
            return
        self.running = False
        # let every connection wind down normally first (so the client still gets
        # its close frame), then stop the listeners
        with self._lock:
            bridges = list(self._connections)
        for bridge in bridges:
            loop = bridge.loop
            if loop is None or loop.is_closed():
                continue
            try:
                future = asyncio.run_coroutine_threadsafe(
                    bridge.shutdown(tr('proxy.reason.service_stopped')), loop)
                future.add_done_callback(_discard_future_result)
            except Exception:
                pass
        deadline = time.time() + 1.0
        while time.time() < deadline:
            with self._lock:
                if not self._connections:
                    break
            time.sleep(0.02)
        self._shutdown_servers()
        self.log.info(tr('proxy.log.stopped'))

    def describe(self) -> dict:
        config = self.config
        data = {
            'service': SERVICE_NAME,
            'app': tr('core.app_name'),
            'version': VERSION,
            'running': self.running,
            'target': config.describe_target(),
            'target_source': (config.target or '').strip(),
            'target_resolved': self._resolved_target(),
            'routes': dict(config.routes or {}),
            'use_srv': bool(config.use_srv),
            'listeners': config.listeners() if self.running else [],
            'wss_url': config.wss_url() if self.running else None,
            'server_brand': config.server_brand,
            'server_brand_version': config.server_brand_version or VERSION,
            'spoof_client': getattr(config, 'spoof_client', 'off'),
            'spoof_brand': config.spoof_brand_value(),
            'status_cache': bool(config.status_cache),
            'status_cache_ttl': int(config.status_cache_ttl),
            'certificate': None,
        }
        if self.certificate:
            data['certificate'] = {
                'path': self.certificate['cert_path'],
                'thumbprint': self.certificate['thumbprint'],
                'alt_names': list(self.certificate.get('alt_names', ())),
                'not_after': self.certificate.get('not_after', ''),
            }
        return data

    def status(self, path: str = '/', with_target: bool = False) -> dict:
        snapshot = self.stats.snapshot()
        data = self.describe()
        data.update({
            'path': path,
            'uptime_seconds': round(snapshot['uptime'], 1),
            'active_connections': snapshot['active'],
            'total_connections': snapshot['total'],
            'bytes_to_server': snapshot['bytes_to_server'],
            'bytes_to_client': snapshot['bytes_to_client'],
            'bytes_to_server_human': human_bytes(snapshot['bytes_to_server']),
            'bytes_to_client_human': human_bytes(snapshot['bytes_to_client']),
        })
        if with_target:
            host, port = self._resolve_for_status()
            if host:
                info = self.target_status(host, port, STATUS_TIMEOUT)
                status = info.get('status') or {}
                data['target_probe'] = {
                    'ok': bool(info.get('ok')),
                    'host': host,
                    'port': port,
                    'ping_ms': round(info['ms'], 1) if info.get('ms') else None,
                    'error': info.get('error', ''),
                    'motd': motd_lines(status.get('description'), legacy=False),
                    'version': (status.get('version') or {}).get('name', ''),
                    'players': status.get('players') or {},
                }
        return data

    def forget(self, bridge: Bridge) -> None:
        with self._lock:
            if bridge in self._connections:
                self._connections.discard(bridge)
                self.stats.connection_closed()

    # ---------- routing / target resolution ----------
    def resolve_route(self, path: str) -> dict:
        routes = self.config.routes or {}
        key = (path or '/').rstrip('/') or '/'
        candidates = [key, path or '/']
        if key != '/':
            candidates.append(key + '/')
        for candidate in candidates:
            if candidate in routes:
                try:
                    host, port = parse_address(routes[candidate])
                except ValueError as exc:
                    self.log.warn(tr('proxy.log.bad_route', path=candidate, error=exc))
                    break
                return {'label': tr('proxy.route.path', path=candidate),
                        'source': routes[candidate], 'host': host, 'port': port}
        host, port = parse_address(self.config.target)
        label = tr('proxy.route.default') if key == '/' \
            else tr('proxy.route.default_missing', path=path)
        return {'label': label, 'source': self.config.target, 'host': host, 'port': port}

    def resolve_endpoint(self, host: str, port: int | None) -> tuple[str, int]:
        if port:
            return host, int(port)
        now = time.time()
        cached = self._srv_cache.get(host)
        if cached and cached[2] > now:
            return cached[0], cached[1]
        resolved = resolver.resolve_target(host, None, logger=self.log, use_srv=self.config.use_srv)
        self._srv_cache[host] = (resolved[0], resolved[1], now + 300.0)
        return resolved

    def cached_endpoint(self, host: str, port: int | None) -> tuple[str, int] | None:
        """Return an endpoint only when no live DNS query is needed.

        The server-list answer is timed by the browser as ping, so callers on
        that path must not block on SRV/DNS.  An explicit port is always
        immediate; a bare hostname is returned only from the resolve cache.
        """
        if port:
            return host, int(port)
        cached = self._srv_cache.get(host)
        if cached and cached[2] > time.time():
            return cached[0], cached[1]
        return None

    def warm_status_async(self, host: str, port: int | None) -> None:
        """Resolve and refresh a target status in a daemon thread."""
        host = (host or '').strip()
        if not host:
            return
        token = '%s:%s' % (host, port or 0)
        with self._lock:
            if token in self._status_warming:
                return
            self._status_warming.add(token)

        def worker() -> None:
            try:
                resolved_host, resolved_port = self.resolve_endpoint(host, port)
                self._start_status_refresh(resolved_host, resolved_port)
            except Exception as exc:
                self.log.debug('status warm-up failed: %s' % exc)
            finally:
                with self._lock:
                    self._status_warming.discard(token)

        threading.Thread(target=worker, daemon=True, name='mcjs-status-warm').start()

    def _start_status_refresh(self, host: str, port: int,
                              timeout: float = STATUS_TIMEOUT) -> None:
        key = '%s:%d' % (host, int(port))
        with self._lock:
            if key in self._status_refreshing:
                return
            self._status_refreshing.add(key)

        def worker() -> None:
            try:
                result = resolver.query_status(host, int(port), timeout=timeout)
                result['time'] = time.time()
                if self.config.status_cache:
                    with self._lock:
                        self._status_cache[key] = result
            except Exception as exc:
                self.log.debug('status refresh failed: %s' % exc)
            finally:
                with self._lock:
                    self._status_refreshing.discard(key)

        threading.Thread(target=worker, daemon=True, name='mcjs-status').start()

    def _resolved_target(self) -> str:
        """Already-resolved target address (report the cache only, no live DNS lookup)."""
        try:
            host, port = parse_address(self.config.target)
        except ValueError:
            return ''
        if port:
            return '%s:%d' % (host, int(port))
        cached = self._srv_cache.get(host)
        if cached:
            return '%s:%d' % (cached[0], cached[1])
        return ''

    def _resolve_for_status(self, timeout: float = STATUS_TIMEOUT) -> tuple[str, int]:
        try:
            host, port = parse_address(self.config.target)
        except ValueError:
            return '', 0
        try:
            return self.resolve_endpoint(host, port)
        except Exception as exc:
            self.log.debug(tr('proxy.log.status_resolve_failed', error=exc))
            return host, int(port or 25565)

    def status_for_query(self, host: str, port: int | None,
                         timeout: float = STATUS_TIMEOUT) -> dict:
        """Return the status used for an ``Accept: MOTD`` answer.

        This runs in a worker thread.  With caching enabled a fresh result is
        returned immediately, a stale result is returned while a refresh runs
        in the background, and a miss performs one live query.  With caching
        disabled every call queries the target and nothing is stored.
        """
        resolved_host, resolved_port = self.resolve_endpoint(host, port)
        resolved_port = int(resolved_port)
        key = '%s:%d' % (resolved_host, resolved_port)
        if self.config.status_cache:
            now = time.time()
            with self._lock:
                cached = self._status_cache.get(key)
            if cached:
                if now - cached['time'] < int(self.config.status_cache_ttl):
                    return cached
                self._start_status_refresh(resolved_host, resolved_port, timeout)
                return cached
        result = resolver.query_status(resolved_host, resolved_port, timeout=timeout)
        result['time'] = time.time()
        if self.config.status_cache:
            with self._lock:
                self._status_cache[key] = result
        return result

    def target_status(self, host: str, port: int, timeout: float = STATUS_TIMEOUT,
                      max_age: float | None = None, wait: bool = True) -> dict:
        """Return the target server status.

        ``wait=True`` is for the status page: it may block for a fresh live
        query.  ``wait=False`` is the non-blocking variant: it returns a cached
        value immediately (even if stale) and refreshes it in the background,
        or returns a placeholder while the first refresh runs.
        """
        if max_age is None:
            max_age = float(self.config.status_cache_ttl)
        key = '%s:%d' % (host, int(port))
        now = time.time()
        cached_result = None
        needs_refresh = False
        if self.config.status_cache:
            with self._lock:
                cached = self._status_cache.get(key)
                if cached:
                    fresh = now - cached['time'] < max_age
                    if fresh or not wait:
                        cached_result = cached
                        needs_refresh = not fresh
        if cached_result is not None:
            if needs_refresh:
                self._start_status_refresh(host, int(port), timeout)
            return cached_result
        if not wait:
            if self.config.status_cache:
                self._start_status_refresh(host, int(port), timeout)
            return {
                'ok': False,
                'ms': None,
                'status': None,
                'error': '',
                'time': now,
                'refreshing': True,
            }
        result = resolver.query_status(host, int(port), timeout=timeout)
        result['time'] = time.time()
        if self.config.status_cache:
            with self._lock:
                self._status_cache[key] = result
        return result

    # ---------- HTTP / WebSocket transport ----------
    @staticmethod
    def _http_response(status: int, reason: str, body: bytes,
                       content_type: str = '') -> Response:
        headers = Headers()
        if content_type:
            headers['Content-Type'] = content_type
        headers['Content-Length'] = str(len(body))
        headers['Cache-Control'] = 'no-store'
        headers['X-Content-Type-Options'] = 'nosniff'
        # The status page is a diagnostic endpoint, not a browser application:
        # closing the connection keeps the response bounded and avoids keeping
        # idle HTTP sockets around on the game port.
        headers['Connection'] = 'close'
        return Response(status, reason, headers, body)

    async def _process_http(self, connection: ServerConnection,
                            request: Request) -> Response | None:
        """Serve diagnostic HTTP on the same port, hand WebSocket upgrades on.

        Returning None lets ``websockets`` complete the WebSocket handshake.
        Everything else is answered here without touching the game path.
        """
        if request.headers.get('Upgrade', '').lower() == 'websocket':
            return None

        path = (request.path or '/').split('?', 1)[0] or '/'
        # websockets 15 only parses GET handshake requests and has no method
        # attribute; 17 adds one.  Treat the absent attribute as GET.
        method = getattr(request, 'method', 'GET')
        head = method == 'HEAD'
        if method not in ('GET', 'HEAD'):
            return self._http_response(
                405, 'Method Not Allowed', b'',
                'text/plain; charset=utf-8')

        if path in ('/status', '/status.json'):
            body = json.dumps(self.status(path), ensure_ascii=False).encode('utf-8')
            return self._http_response(
                200, 'OK', b'' if head else body,
                'application/json; charset=utf-8')
        if path == '/favicon.ico':
            return self._http_response(204, 'No Content', b'')
        return self._http_response(
            404, 'Not Found', b'Not Found\n', 'text/plain; charset=utf-8')

    @staticmethod
    def _select_subprotocol(connection: ServerConnection,
                            subprotocols: list[str]) -> str | None:
        # Preserve the previous gateway's behaviour: use the first protocol the
        # client offered, so ``base64`` remains an explicit opt-in.
        return subprotocols[0] if subprotocols else None

    async def handle_websocket(self, connection: ServerConnection, scheme: str) -> None:
        request = connection.request
        path = ((request.path if request is not None else '/') or '/').split('?', 1)[0] or '/'
        if request is not None:
            # Some browser clients attach a Cookie header to the WebSocket
            # upgrade.  The Eagler protocol has no use for it and it must never
            # leak into a backend handshake or a log line, so drop it before
            # anything else can see it.
            try:
                del request.headers['Cookie']
            except KeyError:
                pass
        client = connection.remote_address or ('?', 0)
        addr = (client[0], client[1])
        bridge = Bridge(self, connection, path, scheme, addr, self.log,
                        connection.subprotocol)
        with self._lock:
            self._connections.add(bridge)
            self.stats.connection_opened()
        await bridge.run()

    # ---------- listeners ----------
    def _start_listener(self, port: int, scheme: str,
                        ssl_context: ssl.SSLContext | None) -> str:
        """Create the listening socket first (a busy port surfaces right away),
        then hand it to a dedicated ``websockets`` event loop.

        The socket is already listening, so client connections can arrive as
        soon as start() returns; the kernel queues them until the loop is up.
        """
        config = self.config
        host = config.listen_host or '127.0.0.1'
        family = socket.AF_INET6 if ':' in host else socket.AF_INET
        listener = socket.socket(family, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind((host, int(port)))
            listener.listen(128)
        except OSError as exc:
            listener.close()
            raise OSError(tr('proxy.error.listen_failed',
                             host=host, port=int(port), error=exc))

        entry = {
            'server': None,
            'loop': None,
            'serve_task': None,
            'thread': None,
            'listener': listener,
            'ready': threading.Event(),
            'error': None,
        }
        thread = threading.Thread(
            target=self._serve, args=(entry, scheme, ssl_context),
            daemon=True, name='mcjs-%s' % scheme)
        entry['thread'] = thread
        self._servers.append(entry)
        thread.start()
        # Waiting for the loop to install the server means a failure inside
        # the thread is raised from start() instead of disappearing into it.
        if not entry['ready'].wait(5.0):
            try:
                listener.close()
            except OSError:
                pass
            raise RuntimeError(tr('proxy.error.listener_failed', scheme=scheme))
        if entry['error'] is not None:
            thread.join(1.0)
            raise entry['error']
        display_host = host if host not in ('0.0.0.0', '') else '127.0.0.1'
        return '%s://%s:%d' % (scheme, display_host, int(port))

    def _serve(self, entry: dict, scheme: str,
               ssl_context: ssl.SSLContext | None) -> None:
        async def main() -> None:
            config = self.config
            heartbeat = max(0, int(config.heartbeat_sec))
            try:
                server = await serve(
                    lambda connection: self.handle_websocket(connection, scheme),
                    sock=entry['listener'],
                    ssl=ssl_context,
                    process_request=self._process_http,
                    select_subprotocol=self._select_subprotocol,
                    compression=None,       # avoid per-message latency and CPU
                    max_size=int(config.max_payload_bytes),
                    max_queue=WS_MAX_QUEUE,
                    write_limit=WS_WRITE_LIMIT,
                    ping_interval=float(heartbeat) if heartbeat else None,
                    ping_timeout=float(max(1, heartbeat)) * 2 if heartbeat else None,
                    close_timeout=2,
                    server_header='%s/%s' % (SERVICE_NAME, VERSION),
                    create_connection=_NoDelayServerConnection,
                )
            except BaseException as exc:
                entry['error'] = exc
                entry['ready'].set()
                return
            entry['server'] = server
            entry['loop'] = asyncio.get_running_loop()
            serve_task = asyncio.create_task(server.serve_forever())
            entry['serve_task'] = serve_task
            entry['ready'].set()
            try:
                await serve_task
            except asyncio.CancelledError:
                pass
            finally:
                server.close()
                await server.wait_closed()

        try:
            asyncio.run(main())
        except asyncio.CancelledError:
            pass
        except Exception:      # errors in a thread cannot be raised to the caller; record them
            import traceback
            traceback.print_exc()
            entry['error'] = entry['error'] or True

    def _shutdown_servers(self) -> None:
        servers = self._servers
        self._servers = []
        # Ask each loop to close its listener and terminate the remaining
        # connections.  Server.close() is thread-safe only through the loop.
        for entry in servers:
            loop = entry.get('loop')
            server = entry.get('server')
            serve_task = entry.get('serve_task')
            if loop is not None and server is not None and not loop.is_closed():
                try:
                    loop.call_soon_threadsafe(server.close)
                except RuntimeError:
                    pass
            if loop is not None and serve_task is not None and not loop.is_closed():
                # asyncio.Server.serve_forever() only returns when cancelled;
                # close() stops accepting but leaves the wait itself pending.
                try:
                    loop.call_soon_threadsafe(serve_task.cancel)
                except RuntimeError:
                    pass
        deadline = time.time() + 3.0
        for entry in servers:
            thread = entry.get('thread')
            if thread is not None:
                thread.join(max(0.1, deadline - time.time()))
        # A handler stuck in a blocking call would keep its loop alive; stop
        # the loop so the process can still exit cleanly.
        for entry in servers:
            thread = entry.get('thread')
            loop = entry.get('loop')
            if thread is not None and thread.is_alive() and loop is not None:
                try:
                    loop.call_soon_threadsafe(loop.stop)
                except RuntimeError:
                    pass
        for entry in servers:
            thread = entry.get('thread')
            if thread is not None:
                thread.join(2.0)
            listener = entry.get('listener')
            try:
                if listener is not None:
                    listener.close()
            except OSError:
                pass
