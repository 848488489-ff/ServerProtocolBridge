"""Client-to-backend play packets: re-framing and plugin-message filtering.

The client sends one bare packet per frame; the backend needs the vanilla
byte stream again, so each frame is wrapped and compressed by the threshold
the server announced.  Messages the vanilla side cannot use are dropped here.
"""

from __future__ import annotations

from . import vanilla
from .i18n import tr


class PlayClientMixin:
    def _client_play(self, data: bytes) -> bytes:
        """One frame from the client is a complete bare packet: no length prefix
        and no compression."""
        if len(data) > 1 and data[0] == vanilla.INJECTED_FRAME_MARKER:
            # Since v5, extensions such as skins travel in "injected message" frames;
            # that is not a vanilla packet and vanilla servers do not understand it
            self.log.debug('%s %s' % (self.tag, tr(
                'translator.log.drop_injected_frame', size=len(data))))
            return b''
        try:
            packet_id, at = vanilla.read_varint(data, 0)
        except vanilla.ProtocolError as exc:
            self._fail(tr('translator.error.client_parse_failed', error=exc))
            return b''
        self.packets_to_server += 1
        self._note_packet(packet_id, 'play', to_client=False)
        body = data[at:]
        if packet_id == vanilla.CLIENT_PLUGIN_MESSAGE:
            channel = self._plugin_channel(body)
            if channel.startswith(vanilla.EAGLER_CHANNEL_PREFIXES):
                self.log.debug('%s %s' % (self.tag, tr(
                    'translator.log.drop_plugin_message', channel=channel)))
                return b''
            if channel == 'MC|Brand' and self.spoof_brand:
                # The client identification is already spoofed per config; do not let
                # the client report its own value as well
                self.log.debug('%s %s' % (self.tag, tr(
                    'translator.log.drop_client_brand', brand=self.spoof_brand)))
                return b''
        # Wrap back into the vanilla byte stream: [length][packet id + content];
        # once the server has enabled compression, use its threshold
        return self.server_encoder.frame(data)

    def _plugin_channel(self, body: bytes) -> str:
        """Read the channel name of a plugin message ('' on a parse failure).

        Eaglercraft's private messages ("EAG|...") are unknown to vanilla
        servers and are dropped at the call site.
        """
        try:
            channel, _ = vanilla.read_string(body, 0)
        except vanilla.ProtocolError:
            return ''
        return channel
