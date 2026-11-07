"""Client-to-backend play packets: re-framing and plugin-message filtering.

The client sends one bare packet per frame; the backend needs the vanilla
byte stream again, so each frame is wrapped and compressed by the threshold
the server announced.  Messages the vanilla side cannot use are dropped here.

Client identity (the brand packet) is intercepted on every game version, not
just 1.8: the modern ``minecraft:brand`` packet is rewritten to the configured
spoof value instead of reaching the target server verbatim (a server that
applies client checks, or an anti-cheat, would otherwise see the browser's
identity).
"""

from __future__ import annotations

from . import vanilla
from .i18n import tr


class PlayClientMixin:
    def _client_play(self, data: bytes) -> bytes:
        """One frame from the client is a complete bare packet: no length prefix
        and no compression."""
        if len(data) > 1 and data[0] == vanilla.INJECTED_FRAME_MARKER:
            # Since v5, extensions such as skins travel in "injected message"
            # frames; that is not a vanilla packet and vanilla servers do not
            # understand it
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
        rewritten = self._maybe_rewrite_brand(data, packet_id, at)
        if rewritten is not None:
            return rewritten
        if self._looks_like_plugin_message(packet_id, body):
            channel = self._plugin_channel(body)
            if channel.startswith(vanilla.EAGLER_CHANNEL_PREFIXES):
                self.log.debug('%s %s' % (self.tag, tr(
                    'translator.log.drop_plugin_message', channel=channel)))
                return b''
            if channel == 'MC|Brand' and self.spoof_brand:
                # The client identification is already spoofed per config; do not
                # let the client report its own value as well
                self.log.debug('%s %s' % (self.tag, tr(
                    'translator.log.drop_client_brand', brand=self.spoof_brand)))
                return b''
        # Wrap back into the vanilla byte stream: [length][packet id + content];
        # once the server has enabled compression, use its threshold
        return self.server_encoder.frame(data)

    def _looks_like_plugin_message(self, packet_id: int, body: bytes) -> bool:
        """Plugin-message detection that does not depend on per-version packet ids.

        1.8 uses CLIENT_PLUGIN_MESSAGE; every other version carries its own
        custom-payload id, so the channel string itself is used as the signal:
        only when the id is a plausible custom-payload id AND the body starts
        with a decodable channel string is this treated as a plugin message.
        """
        if packet_id == vanilla.CLIENT_PLUGIN_MESSAGE:
            return True
        if packet_id not in vanilla.PLUGIN_MESSAGE_ID_RANGE or not body:
            return False
        try:
            vanilla.read_string(body, 0)
        except vanilla.ProtocolError:
            return False
        return True

    def _maybe_rewrite_brand(self, data: bytes, packet_id: int, at: int):
        """Rewrite the client's brand packet to the configured spoof value.

        Returns the replacement packet to send upstream, or None when this is
        not a brand packet (or there is nothing configured -- the packet then
        passes through untouched, which is the 'off' preset behaviour).
        """
        if not self.spoof_brand:
            return None
        body = data[at:]
        if not self._looks_like_plugin_message(packet_id, body):
            return None
        try:
            channel, pos = vanilla.read_string(body, 0)
        except vanilla.ProtocolError:
            return None
        if channel not in vanilla.BRAND_CHANNELS:
            return None
        try:
            vanilla.read_string(body, pos)
        except vanilla.ProtocolError:
            return None
        value_bytes = self.spoof_brand.encode('utf-8', 'replace')
        body = (vanilla.write_varint(len(channel.encode('utf-8')))
                + channel.encode('utf-8')
                + vanilla.write_varint(len(value_bytes)) + value_bytes)
        self._brand_rewritten = True
        self.log.info('%s %s' % (self.tag, tr(
            'translator.log.rewrite_brand', brand=self.spoof_brand)))
        return self.server_encoder.frame(vanilla.write_varint(packet_id) + body)

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
