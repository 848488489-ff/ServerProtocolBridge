"""Bridge lifecycle: construction, the connect handshake, the WebSocket receive loop, the first-message timeout and connection diagnostics.  Split from proxy.py for file size.

Method bodies are unchanged; they are methods of Bridge, reached
through ``self``.
"""

import asyncio
import threading
import time
from . import (eagler, handshake, vanilla)
from .i18n import tr
from .proxy import (CLOSE_GRACE, CONNECT_FAIL_WAIT, FIRST_MESSAGE_WAIT, RECV_SIZE, _SessionClosed, _discard_future_result, _set_socket_options, describe_connect_error)
from .translator import note
from websockets.asyncio.server import ServerConnection
from websockets.exceptions import ConnectionClosed
class BridgeInit:
    """BridgeInit mixin for Bridge."""
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
        # _queue_to_client is the translator's send_client callback and runs in
        # the same worker threads as _queue_to_backend (login / transaction
        # replies).  _drain_outbox therefore needs the same copy-and-clear
        # discipline as _to_server: without the lock a frame appended between
        # the copy and the clear would be silently lost and the client would
        # hang in login or desync in play.
        self._outbox_lock = threading.Lock()
        self._close_after_flush = False
        self._ws_closed = False
        self._first_task: asyncio.Task | None = None
        self._handshake_timer: asyncio.TimerHandle | None = None

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

        # Connect to the target server, retrying a configured number of times
        # on a transient failure (DNS flakiness, a restarting backend) before
        # telling the player it is unreachable.
        retries = max(0, int(getattr(config, 'connect_retries', 0) or 0))
        delay = max(0.0, float(getattr(config, 'connect_retry_delay', 0) or 0))
        reader = writer = None
        last_exc: BaseException | None = None
        for attempt in range(retries + 1):
            if attempt:
                self.log.info(tr('proxy.log.connect_retry', id=self.id,
                                 attempt=attempt, host=host, port=port))
                await asyncio.sleep(delay)
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port, limit=RECV_SIZE),
                    timeout=max(1.0, float(config.connect_timeout)))
                break
            except Exception as exc:
                last_exc = exc
        if writer is None or reader is None:
            await self._report_connect_failure(
                host, port, last_exc or ConnectionError('connect failed'), first)
            return
        self.reader, self.writer = reader, writer
        _set_socket_options(writer)
        self.log.info(tr('proxy.log.connected', id=self.id, host=host, port=port))
        self._arm_handshake_timeout()

        # if the first packet is already in hand, handle it right away; otherwise
        # leave it to the pumps to keep waiting
        if first is not None:
            self._first_task = None
            await self._handle_incoming(first[0], first[1])
        tasks = [
            asyncio.create_task(self._pump_from_client(), name='spb-ws-%d' % self.id),
            asyncio.create_task(self._pump_from_server(), name='spb-tcp-%d' % self.id),
        ]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
    # ---------- handshake/login deadline ----------
    def _arm_handshake_timeout(self) -> None:
        """Arm the handshake/login deadline.

        A browser client that connects but never finishes the login (a stalled
        or hostile peer) would otherwise hold its socket open until the
        WebSocket heartbeat or the peer gives up.  When ``handshake_timeout``
        is set, such a session is dropped after that many seconds.
        """
        timeout = float(getattr(self.config, 'handshake_timeout', 0) or 0)
        if timeout <= 0 or self._handshake_timer is not None:
            return
        loop = self.loop or asyncio.get_running_loop()
        self._handshake_timer = loop.call_later(
            timeout, lambda: loop.create_task(self._handshake_timed_out()))

    def _disarm_handshake_timeout(self) -> None:
        """Cancel the handshake deadline once the login is finished."""
        timer = self._handshake_timer
        self._handshake_timer = None
        if timer is not None:
            try:
                timer.cancel()
            except Exception:
                pass

    async def _handshake_timed_out(self) -> None:
        """The deadline fired while the session was still handshaking/logging
        in: close it so a stalled peer cannot pin the connection forever."""
        self._handshake_timer = None
        translator = self.translator
        if (translator is not None and translator.login_done) or self.query_mode:
            return
        if not self.close_reason:
            self.close_reason = tr('proxy.reason.handshake_timeout')
            self.close_code = 1001
            self.close_text = 'handshake timeout'
            self.log.warn('#%d %s' % (self.id, self.close_reason))
        await self._close_ws()
        self._close_writer()
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
