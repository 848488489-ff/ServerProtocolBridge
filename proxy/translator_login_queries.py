"""Backend login-phase requests the proxy answers in the client's place.

Modern servers ask the connecting client questions during login -- a plugin
request, a cookie request, a login acknowledgement.  Browser clients have no
code for any of them, so the proxy replies with "not understood" / "no cookie"
/ "acknowledged" to keep the handshake moving.
"""

from __future__ import annotations

from . import vanilla


class TranslatorLoginQueriesMixin:
    def _decline_login_plugin_request(self, packet: vanilla.Packet) -> None:
        """Answer a login plugin request (1.13+) with "not understood".

        A modded server, or one sitting behind a forwarding proxy, may ask the
        connecting client questions during login; an answer is expected either
        way, so staying silent would leave the login hanging until the server's
        timeout.
        """
        try:
            message_id, _ = vanilla.read_varint(packet.body, 0)
        except vanilla.ProtocolError:
            return
        payload = (vanilla.write_varint(vanilla.LOGIN_PLUGIN_RESPONSE)
                   + vanilla.write_varint(message_id) + b'\x00')
        self._send_backend(self._encode_for_backend(self.server_encoder.frame(payload)))

    def _decline_login_cookie_request(self, packet: vanilla.Packet) -> None:
        """Answer a login cookie request (1.20.5+) with "no cookie stored"."""
        try:
            key, _ = vanilla.read_string(packet.body, 0)
        except vanilla.ProtocolError:
            return
        payload = (vanilla.write_varint(vanilla.LOGIN_COOKIE_RESPONSE)
                   + vanilla.write_string(key) + b'\x00')
        self._send_backend(self._encode_for_backend(self.server_encoder.frame(payload)))

    def _acknowledge_login(self) -> None:
        """Acknowledge the login result (1.20.2+) in the client's place.

        The packet carries nothing beyond its id; see _handle_login_success for
        why the proxy has to send it instead of the browser client.
        """
        payload = vanilla.write_varint(vanilla.LOGIN_ACKNOWLEDGED)
        self._send_backend(self._encode_for_backend(self.server_encoder.frame(payload)))
