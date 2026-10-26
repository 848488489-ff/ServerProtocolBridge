"""Backend-to-client play packets: dispatch and disconnect forwarding.

Game packets the target server sends are already in the wire format the
browser client wants ("one bare packet per frame"), so most of what this
direction does is decide where a packet goes and keep the disconnect body
untouched.
"""

from __future__ import annotations

from . import vanilla
from .i18n import tr


class PlayBackendMixin:
    # ---------- Backend: play phase ----------
    def _handle_play_packet(self, packet: vanilla.Packet, frames: list[bytes]) -> None:
        if packet.packet_id == vanilla.PLAY_RESOURCE_PACK_SEND:
            self._handle_resource_pack_prompt(packet, frames)
            return
        if packet.packet_id == vanilla.PLAY_DISCONNECT:
            raw = self._chat_raw(packet.body)
            reason = self._flatten_chat(raw)
            if reason:
                self.log.warn('%s %s' % (self.tag, tr(
                    'translator.log.backend_disconnect', reason=reason)))
            self.close_reason = reason or self.close_reason
            # Forward the server's body verbatim: a JSON component is already
            # what the client's disconnect screen renders, and a legacy
            # ``§``-coded string is left untouched rather than being re-rolled
            # onto the 16-colour palette.
            if raw:
                body = raw
                packet = vanilla.Packet(
                    packet.packet_id,
                    vanilla.write_string(body),
                    vanilla.write_varint(packet.packet_id) + vanilla.write_string(body))
        self._note_packet(packet.packet_id, 'play', to_client=True)
        # The client wants "one bare packet per frame", so packet id + content is
        # sent as one frame directly
        if self.phase == 'play':
            frames.append(packet.payload)
        else:
            # The client has not finished the handshake yet; buffer the game data
            # (still one packet per frame)
            self.pending_to_client.append(packet.payload)
