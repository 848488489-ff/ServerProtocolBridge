"""Client-identity spoofing on the backend connection.

Server-side plugins (anti-cheat, statistics, ...) tell a browser client apart
mostly from the "client identification" packets a vanilla or modded client
sends after joining, so every fingerprint of the configured preset is
reproduced here.  Only 1.8 connections are spoofed: the packet ids and
channel names of other game versions are not guessed at.
"""

from __future__ import annotations

from . import vanilla
from .i18n import tr


class PlaySpoofMixin:
    def _announce_brand(self) -> None:
        """After login, declare the spoofed client identity to the target server."""
        if self.spoof_client == 'forge-1.8' and self.mc_protocol == 47:
            self._send_forge_registration()
        if not self.spoof_brand:
            return
        if self.mc_protocol != 47:
            # The plugin-message packet id and the brand channel name change
            # per game version; outside 1.8 nothing is fabricated here, and the
            # client's own packets pass through untouched
            return
        channel = b'MC|Brand'
        value = self.spoof_brand.encode('utf-8', 'replace')
        body = (vanilla.write_varint(len(channel)) + channel
                + vanilla.write_varint(len(value)) + value)
        # NOTE: frame() expects an *unframed* payload (packet id + content).
        # vanilla.pack() already prepends the outer length prefix, so use
        # write_varint here instead -- passing a packed packet to frame() would
        # double-frame it.
        payload = vanilla.write_varint(vanilla.CLIENT_PLUGIN_MESSAGE) + body
        self._send_backend(self._encode_for_backend(self.server_encoder.frame(payload)))
        self.log.info('%s %s' % (self.tag, tr(
            'translator.log.brand_spoofed', brand=self.spoof_brand)))

    def _send_forge_registration(self) -> None:
        """Send the channel registration a legacy Forge client (up to 1.12.2) sends.

        FMLHandshakeMessage.makeCustomChannelRegistration joins the built-in
        FML channels -- plus any mod channels, none here -- with NUL bytes and
        sends them as the payload of one "REGISTER" plugin message; the raw
        blob carries no length prefixes inside.  A vanilla server ignores the
        message, a modded one uses it to see which channels the client speaks.
        """
        channel = b'REGISTER'
        data = b'FML|HS\x00FML\x00FML|MP'
        body = vanilla.write_varint(len(channel)) + channel + data
        payload = vanilla.write_varint(vanilla.CLIENT_PLUGIN_MESSAGE) + body
        self._send_backend(self._encode_for_backend(self.server_encoder.frame(payload)))
        self.log.info('%s %s' % (self.tag, tr(
            'translator.log.forge_channels',
            channels=data.decode('ascii').replace('\x00', ', '))))
