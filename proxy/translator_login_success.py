"""The vanilla login-success reply: accepting the identity the target picked.

The target server decides which name and UUID this connection is.  Whatever it
returns is what the client will be told to use, including non-ASCII names --
offline-mode servers hand the client's name back unchanged, and Chinese servers
hand Chinese names back.
"""

from __future__ import annotations

from . import eagler, vanilla
from .i18n import tr
from .translator_chat import uuid_from_string


class LoginSuccessMixin:
    def _handle_login_success(self, packet: vanilla.Packet, frames: list[bytes]) -> None:
        raw_uuid: bytes | None = None
        try:
            if self.mc_protocol >= 735:
                # Since 1.16 the UUID is 16 raw bytes; whatever follows the name
                # (profile properties since 1.19) is not needed here
                raw_uuid = packet.body[:16]
                name, _ = vanilla.read_string(packet.body, 16)
                text = raw_uuid.hex()
                uuid_text = '%s-%s-%s-%s-%s' % (
                    text[:8], text[8:12], text[12:16], text[16:20], text[20:])
            else:
                uuid_text, pos = vanilla.read_string(packet.body, 0)
                name, _ = vanilla.read_string(packet.body, pos)
        except vanilla.ProtocolError:
            self._fail(tr('translator.error.login_success_parse_failed'))
            return
        uuid_bytes = raw_uuid or uuid_from_string(uuid_text) or self.uuid
        # A name back from the target is trusted whether or not it is ASCII:
        # offline-mode servers routinely return the client's original name, and
        # Chinese servers return Chinese names, which the old ASCII gate silently
        # discarded and replaced with whatever the proxy had guessed.
        accepted = eagler.usable_name(name)
        if accepted:
            self.username = accepted
            if raw_uuid is None and uuid_from_string(uuid_text) is None:
                uuid_bytes = eagler.offline_uuid(accepted)
        self.uuid = uuid_bytes
        self.login_done = True
        self.phase = 'allow_sent'
        if self.login_ack and self.mc_protocol >= 764:
            # 1.20.2+ servers hold the connection in the login state until the
            # login result is acknowledged (the configuration phase only starts
            # afterwards).  A browser client never sends that acknowledge -- its
            # login phase ends with the EaglercraftX handshake -- and the first
            # thing it sends after the handshake is already configuration data,
            # which a target still waiting in the login state answers by
            # dropping the connection; so the proxy acknowledges on its behalf.
            # This is the "login acknowledge" switch in the settings.
            self._acknowledge_login()
        self.log.info('%s %s' % (self.tag, tr(
            'translator.log.backend_login_ok', username=self.username, uuid=uuid_text)))
        self._send(eagler.pack_allow_login(self.username, self.uuid, self.handshake_protocol))
        self._maybe_finish_login()
