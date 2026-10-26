"""Login-phase methods of EaglerTranslator, composed from focused mixins.

Dispatch over the backend's login packets and the wind-down into play live
here; each individual step is in a sibling translator_login_*.py file, one per
responsibility, so a file only has to explain one thing.
"""

from __future__ import annotations

from . import eagler, vanilla
from .i18n import tr
from .translator_chat import packet_name
from .translator_login_backend import LoginBackendMixin
from .translator_login_encryption import LoginEncryptionMixin
from .translator_login_handshake import LoginHandshakeMixin
from .translator_login_reply import LoginReplyMixin
from .translator_login_success import LoginSuccessMixin


class LoginMixin(LoginHandshakeMixin, LoginBackendMixin, LoginEncryptionMixin,
                 LoginSuccessMixin, LoginReplyMixin):
    """Everything the translation layer does while the backend is in login."""

    # ---------- Backend: login phase ----------
    def _handle_login_packet(self, packet: vanilla.Packet, frames: list[bytes]) -> None:
        packet_id = packet.packet_id
        if packet_id == vanilla.LOGIN_SET_COMPRESSION:
            threshold = 256
            try:
                threshold, _ = vanilla.read_varint(packet.body, 0)
            except vanilla.ProtocolError:
                pass
            self.server_decoder.threshold = threshold
            self.server_encoder.threshold = threshold
            self.log.debug('%s %s' % (self.tag, tr(
                'translator.log.compression_enabled', threshold=threshold)))
            return
        if packet_id == vanilla.LOGIN_DISCONNECT:
            raw = self._chat_raw(packet.body)
            reason = self._flatten_chat(raw)
            denied = tr('translator.denied_login',
                        reason=reason or tr('translator.empty_content'))
            self.log.warn('%s %s' % (self.tag, denied))
            fallback = tr('translator.kick_fallback')
            # Forward the reason in the mode that matches its content: a JSON
            # component stays JSON so jsonToComponent renders its colours, and
            # a legacy ``§`` string stays plain text so the renderer draws the
            # codes.  Nothing is flattened or converted in either direction.
            body, chat_json = eagler.chat_passthrough(raw, fallback)
            self._send(eagler.pack_deny_login(body, self.handshake_protocol,
                                              chat_json=chat_json))
            self._fail(denied, notify_client=False)
            return
        if packet_id == vanilla.LOGIN_ENCRYPTION_REQUEST:
            self._handle_encryption_request(packet)
            return
        if packet_id == vanilla.LOGIN_PLUGIN_REQUEST:
            self._decline_login_plugin_request(packet)
            return
        if packet_id == vanilla.LOGIN_COOKIE_REQUEST:
            self._decline_login_cookie_request(packet)
            return
        if packet_id == vanilla.LOGIN_SUCCESS:
            self._handle_login_success(packet, frames)
            return
        self.log.warn('%s %s' % (self.tag, tr(
            'translator.log.unexpected_login_packet',
            packet=packet_name(packet_id, 'login'))))

    # ---------- Winding down ----------
    def _maybe_finish_login(self) -> None:
        if self.phase != 'allow_sent' or not (self.client_finished and self.login_done):
            return
        self.phase = 'play'
        self._send(eagler.pack_finish_login())
        if self.pending_to_client:
            total = sum(len(frame) for frame in self.pending_to_client)
            self.log.debug('%s %s' % (self.tag, tr(
                'translator.log.flush_pending',
                count=len(self.pending_to_client), size=total)))
            for frame in self.pending_to_client:      # one packet per frame; send separately
                self._send(frame)
            self.pending_to_client.clear()
        self.log.info('%s %s' % (self.tag, tr('translator.log.translation_done')))
        self._announce_brand()
