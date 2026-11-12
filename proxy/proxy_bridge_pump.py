"""Bridge translator wiring: the pump tasks that move bytes between the browser WebSocket and the vanilla backend through the protocol translator.  Split from proxy.py for file size.

Method bodies are unchanged; they are methods of Bridge, reached
through ``self``.
"""

import asyncio
import base64
from . import (accounts, eagler, handshake)
from .i18n import tr
from .proxy import (CLOSE_GRACE, RECV_SIZE, _SessionClosed)
from .translator import EaglerTranslator
from .version import (SERVICE_NAME, VERSION)
from collections.abc import Callable
class BridgePump:
    """BridgePump mixin for Bridge."""
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
            config_ack=bool(getattr(config, 'config_ack', True)),
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
        with self._outbox_lock:
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
        with self._outbox_lock:
            if self._outbox:
                # same as _flush_to_server: must be cleared in place, or frames
                # the translation layer appends later would be lost.  The lock
                # makes the copy-and-clear atomic against _queue_to_client,
                # which runs in a worker thread while login is in flight.
                frames = list(self._outbox)
                self._outbox.clear()
            else:
                frames = []
        if frames:
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
    def _close_writer(self) -> None:
        writer, self.writer = self.writer, None
        if writer is not None:
            try:
                writer.close()
            except Exception:
                pass
