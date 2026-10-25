"""Play-phase methods of EaglerTranslator, split out for file size."""

from __future__ import annotations
import json
import os
import threading
from . import accounts, crypto, eagler, vanilla
from .i18n import tr
from .logger import NullLogger

from .translator_chat import PACKET_NAMES, _CHAT_KEYS, _LEGACY_COLOR_CODES, _LEGACY_COLOR_NAMES, _LEGACY_COLOR_RGB, _LEGACY_STYLE_CODES, _LEGACY_STYLE_NAMES, _collect_legacy, _component_from_legacy, _legacy_color_code, _legacy_prefix, _legacy_style, _looks_like_chat_component, _unwrap_chat_json, chat_to_component_json, chat_to_legacy, chat_to_text, note, packet_name, uuid_from_string

class PlayMixin:
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
            # Do not forward the server's body verbatim.  Logs show the
            # flattened reason, but several browser clients display the packet
            # body literally, so a JSON component appears as raw JSON on the
            # disconnect screen.  Send the flattened text instead.
            if raw:
                fallback = tr('translator.kick_fallback')
                body = chat_to_legacy(raw) or fallback
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
            # Let the browser client handle it normally
            self._note_packet(packet.packet_id, 'play', to_client=True)
            if self.phase == 'play':
                frames.append(packet.payload)
            else:
                # The client has not finished the handshake yet; buffer the game data
                # (still one packet per frame)
                self.pending_to_client.append(packet.payload)
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
    def _handle_resource_pack_prompt_forward_fallback(self, packet: vanilla.Packet, frames: list[bytes]) -> None:
        """Forward a resource pack prompt when the mode is unrecognized."""
        self._note_packet(packet.packet_id, 'play', to_client=True)
        if self.phase == 'play':
            frames.append(packet.payload)
        else:
            self.pending_to_client.append(packet.payload)
    def _send_client_status(self, status: int) -> None:
        """Send a Client Status packet (0x02) to the backend server.

        Status values:
          0 = DECLINED
          1 = ACCEPTED
          2 = ACKNOWLEDGED
        """
        payload = vanilla.write_varint(vanilla.CLIENT_STATUS) + vanilla.write_varint(status)
        self._send_backend(self._encode_for_backend(self.server_encoder.frame(payload)))
        self.log.info('%s %s' % (self.tag, tr(
            'translator.log.client_status_sent', status=status)))
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
        """Read the channel name of a plugin message (an empty string when parsing
        fails).

        Eaglercraft's private messages ("EAG|...") are unknown to vanilla servers
        and have to be dropped at the call site.
        """
        try:
            channel, _ = vanilla.read_string(body, 0)
        except vanilla.ProtocolError:
            return ''
        return channel
    def _announce_brand(self) -> None:
        """After login, declare the spoofed client identity to the target server.

        A vanilla client sends neither a channel registration nor an FML
        marker, and server-side plugins (anti-cheat, statistics, ...) take the
        "client identification" they see mostly from exactly these packets, so
        every fingerprint of the chosen preset is reproduced here per config to
        keep the target server from recognizing this as a browser client
        through some other channel.  The fingerprints are reproduced on 1.8
        connections only: the packet ids and channel names of the other game
        versions are not guessed at (see _begin_backend_login).
        """
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
        # NOTE: frame() expects an *unframed* payload (packet id + content). vanilla.pack()
        # already prepends the outer length prefix, so use write_varint here instead --
        # passing a packed packet to frame() would double-frame it.
        payload = vanilla.write_varint(vanilla.CLIENT_PLUGIN_MESSAGE) + body
        self._send_backend(self._encode_for_backend(self.server_encoder.frame(payload)))
        self.log.info('%s %s' % (self.tag, tr(
            'translator.log.brand_spoofed', brand=self.spoof_brand)))
    def _send_forge_registration(self) -> None:
        """Send the channel registration a legacy Forge client (up to 1.12.2) sends after joining.

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
    def _chat_raw(self, body: bytes) -> str:
        """Read the raw body text of a chat component (usually JSON)."""
        try:
            text, _ = vanilla.read_string(body, 0)
        except vanilla.ProtocolError:
            return ''
        return text
    def _flatten_chat(self, raw: str) -> str:
        """Flatten a chat component JSON into plain text."""
        if not raw:
            return ''
        return chat_to_text(raw) or raw
    def _chat_text(self, body: bytes) -> str:
        return self._flatten_chat(self._chat_raw(body))
    def _client_parses_chat_json(self) -> bool:
        """Whether the client runs JSON chat bodies through jsonToComponent.

        EaglercraftX (and forks that keep its brand) do, for the deny-login
        reason and for custom error messages; other browser clients (Gaius,
        ...) display whatever arrives as literal text, so those get the
        flattened plain text instead of a raw JSON blob on the screen.
        """
        brand = self.client_version.brand if self.client_version else ''
        return brand.strip().lower().startswith('eaglercraft')
    def _note_packet(self, packet_id: int, state: str, to_client: bool) -> None:
        seen = self._seen_server_ids if to_client else self._seen_client_ids
        key = (packet_id, state)
        if key in seen or len(seen) > 60:
            return
        seen.add(key)
        direction = tr('translator.direction.downstream' if to_client
                       else 'translator.direction.upstream')
        self.log.debug('%s %s' % (self.tag, tr(
            'translator.log.first_packet', direction=direction,
            name=packet_name(packet_id, state), packet_id=packet_id)))
    def _send(self, data: bytes) -> None:
        if data:
            self._send_client(data)
    def fail(self, reason: str, notify_client: bool = True) -> None:
        """For the bridge layer: report a connection-level problem through the
        same teardown path as an internal failure.

        Takes the lock because the bridge may call this while a feed call is
        still running on a worker thread (see proxy.py's asyncio.to_thread).
        """
        with self._lock:
            self._fail(reason, notify_client)
    def _fail(self, reason: str, notify_client: bool = True) -> None:
        if self.phase == 'closed':
            return
        self.phase = 'closed'
        self.close_reason = reason
        if notify_client:
            try:
                self._send(eagler.pack_error(eagler.ERROR_CUSTOM_MESSAGE, note(reason),
                                             max(self.handshake_protocol, 3),
                                             chat_json=self._client_parses_chat_json()))
            except Exception:      # a failed notification must not break teardown
                pass
        self._request_close(reason)
