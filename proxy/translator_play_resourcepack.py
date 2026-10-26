"""Resource pack prompts: what the proxy answers instead of the browser client.

Browser clients have no working resource pack flow, so the four configured
modes decide whether the prompt is passed through, accepted, declined, or
accepted without the client ever seeing it.
"""

from __future__ import annotations

from . import vanilla
from .i18n import tr


class PlayResourcePackMixin:
    def _handle_resource_pack_prompt(self, packet: vanilla.Packet, frames: list[bytes]) -> None:
        """Handle the server's resource pack prompt according to the configured mode.

        Modes (see config.py RESOURCE_PACK_MODES):
          forward -- pass the prompt through to the browser client unchanged;
                     the client decides and answers on its own.
          accept  -- answer ACCEPTED in the client's place, drop the prompt
                     from the downstream path.
          reject  -- answer DECLINED in the client's place, drop the prompt.
          spoof   -- answer ACCEPTED to trick the server into thinking the
                     client accepted, but never forward the prompt to the
                     browser client (the client never sees or needs to
                     download anything).
        """
        mode = self.resource_pack_mode
        self.log.info('%s %s' % (self.tag, tr(
            'translator.log.resource_pack_prompt', mode=mode)))

        if mode == 'forward':
            self._handle_resource_pack_prompt_forward_fallback(packet, frames)
            return

        if mode == 'accept':
            self._send_client_status(vanilla.CLIENT_STATUS_ACCEPTED)
            return

        if mode == 'reject':
            self._send_client_status(vanilla.CLIENT_STATUS_DECLINED)
            return

        if mode == 'spoof':
            # Pretend to accept, but never forward the prompt to the client
            self._send_client_status(vanilla.CLIENT_STATUS_ACCEPTED)
            return

        # Unknown mode: fall back to forward (safest)
        self.log.warn('%s %s' % (self.tag, tr(
            'translator.log.unknown_resource_pack_mode', mode=mode)))
        self._handle_resource_pack_prompt_forward_fallback(packet, frames)

    def _handle_resource_pack_prompt_forward_fallback(
            self, packet: vanilla.Packet, frames: list[bytes]) -> None:
        """Forward a resource pack prompt unchanged."""
        self._note_packet(packet.packet_id, 'play', to_client=True)
        if self.phase == 'play':
            frames.append(packet.payload)
        else:
            # The client has not finished the handshake yet; buffer the game data
            self.pending_to_client.append(packet.payload)

    def _send_client_status(self, status: int) -> None:
        """Send a Client Status packet (0x02) to the backend server.

        Status values: 0 = DECLINED, 1 = ACCEPTED, 2 = ACKNOWLEDGED.
        """
        payload = (vanilla.write_varint(vanilla.CLIENT_STATUS)
                   + vanilla.write_varint(status))
        self._send_backend(self._encode_for_backend(self.server_encoder.frame(payload)))
        self.log.info('%s %s' % (self.tag, tr(
            'translator.log.client_status_sent', status=status)))
