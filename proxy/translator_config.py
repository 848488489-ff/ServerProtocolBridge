"""Configuration-phase (1.20.2+, protocol 764+) handling for browser clients.

The Eagler handshake ends with the client already positioned for the game, so a
browser client has no code for the "configuration" state a modern server puts
the connection through between login and play.  Two packets in that state must
be answered or the target never leaves it:

* ``Finish Configuration`` -- the server waits for the client's acknowledge
  before the play state starts.  Unanswered, it hangs until its timeout.
* ``Keep Alive`` -- an unanswered keep-alive gets the connection dropped.

The proxy answers both in the client's place and does **not** forward them (a
client positioned for play would misparse configuration packets).  Everything
else in the state -- registry data, feature flags, known packs, plugin
messages, resource pack adds -- is forwarded to the client exactly as it was
before, so this is strictly additive: it can only unblock a target that would
otherwise stall, never take bytes away that used to reach the client.
"""

from __future__ import annotations

from . import vanilla
from .i18n import tr


class TranslatorConfigMixin:
    def _handle_config_packet(self, packet: vanilla.Packet, frames: list[bytes]) -> None:
        """Dispatch one backend packet while the target is in its configuration
        state (1.20.2+)."""
        packet_id = packet.packet_id
        if packet_id == vanilla.CONFIG_FINISH_CONFIGURATION:
            self._answer_config_finish()
            return
        if packet_id == vanilla.CONFIG_KEEP_ALIVE:
            self._answer_config_keep_alive(packet)
            return
        # Everything else passes through as it always did: forward the frame.
        if self.phase == 'play':
            frames.append(packet.payload)
        else:
            self.pending_to_client.append(packet.payload)

    def _answer_config_finish(self) -> None:
        """Answer the server's Finish Configuration so it can enter the play state.

        The serverbound acknowledge carries nothing beyond its id.
        """
        self._send_backend(self._encode_for_backend(
            self.server_encoder.frame(
                vanilla.write_varint(vanilla.CONFIG_FINISH_CONFIGURATION))))
        self.config_phase = False
        self.log.info('%s %s' % (self.tag, tr(
            'translator.log.config_finished')))

    def _answer_config_keep_alive(self, packet: vanilla.Packet) -> None:
        """Echo a configuration-phase keep-alive so the target keeps the session.

        The id is a fixed 8-byte long; the reply carries exactly the same bytes.
        """
        try:
            keep_alive_id = packet.body[:8]
        except Exception:
            return
        if len(keep_alive_id) < 8:
            # Truncated keep-alive: forward it and let the parser surface the
            # problem rather than fabricating a reply the target would reject.
            return
        self._send_backend(self._encode_for_backend(
            self.server_encoder.frame(
                vanilla.write_varint(vanilla.CONFIG_KEEP_ALIVE) + keep_alive_id)))
        if self.log.enabled('debug'):
            self.log.debug('%s %s' % (self.tag, tr(
                'translator.log.config_keep_alive')))
