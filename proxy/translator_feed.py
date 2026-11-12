"""The two feed directions: client frames in, server bytes in.

Both take the lock because the bridge layer runs the translation off the event
loop and a connection can be torn down at the same time (see proxy.py's
asyncio.to_thread).
"""

from __future__ import annotations

from . import vanilla
from .i18n import tr


class TranslatorFeedMixin:
    # ---------- Public API: the two directions ----------
    def feed_client(self, data: bytes) -> bytes:
        """Feed in one WebSocket frame from the client; return the bytes to write
        to the backend server.

        Note: on the client side one frame is one bare packet (id + content) with
        neither a length prefix nor compression, so a whole frame is treated as a
        single packet here.
        """
        if not data or self.phase == 'closed':
            return b''
        with self._lock:
            if self.phase == 'play':
                out = self._client_play(data)
            elif self.phase == 'client_version':
                out = self._handle_client_version(data)
            else:
                out = self._handle_handshake_packet(data)
            return self._encode_for_backend(out)

    def feed_server(self, data: bytes) -> list[bytes]:
        """Feed in the byte stream from the backend server; return the WebSocket
        frames to send to the client.

        The result is a *list of frames* rather than one blob: the client requires
        exactly one packet per frame, so every packet has to be sent as its own
        frame and the caller must send them one by one.
        """
        if not data or self.phase == 'closed':
            return []
        with self._lock:
            if self.server_decrypt is not None:
                data = self.server_decrypt.decrypt(data)
            self.server_decoder.push(data)
            frames: list[bytes] = []
            while True:
                try:
                    packet = self.server_decoder.next_packet()
                except vanilla.ProtocolError as exc:
                    self._fail(tr('translator.error.backend_parse_failed', error=exc))
                    return frames
                if packet is None:
                    return frames
                self.packets_to_client += 1
                if not self.login_done:
                    self._handle_login_packet(packet, frames)
                elif self.config_phase:
                    self._handle_config_packet(packet, frames)
                else:
                    self._handle_play_packet(packet, frames)
                if self.phase == 'closed':
                    return frames

    def _encode_for_backend(self, data: bytes) -> bytes:
        """Before writing to the backend server: wrap in AES once encryption is on."""
        if not data:
            return b''
        if self.server_encrypt is not None:
            data = self.server_encrypt.encrypt(data)
        return data
