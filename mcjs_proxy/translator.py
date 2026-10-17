"""Protocol translation layer: connects EaglercraftX-family browser clients to real
vanilla Minecraft 1.8 servers.

The difference between a vanilla server and a browser client is confined to
"the very beginning of the connection":

    browser client                        vanilla server
    --------------                        --------------
    1. private handshake (version      ->  (cannot make sense of it,
       negotiation / login / finish)       drops the connection)
    2. vanilla 1.8.8 game data after   <-> vanilla 1.8.8 game data

So this module:
* answers step 1 -- it plays an EaglercraftX server towards the client;
* at the same time plays a vanilla 1.8.8 client towards the server (vanilla
  handshake + login start; offline mode is enough);
* translates the login result from the server into the client's
  "allow login / finish login";
* then moves game data in both directions, patching up the places where the two
  sides differ:
    - framing: vanilla TCP is a byte stream of [VarInt length][body], while the
      browser client uses "one WebSocket frame = one bare packet (id + content)"
      with neither length prefix nor compression, so every packet has to be sent
      as its own frame and every frame has to be wrapped back into one packet;
    - compression: the server may enable compression while the client never
      compresses (its setCompressionTreshold throws
      CompressionNotSupportedException outright), so the proxy
      decompresses/recompresses and never forwards Set Compression to the
      client;
    - game data the server sends before the handshake completes is buffered and
      released to the client after "finish login";
    - client-specific "EAG|..." plugin messages and 0xEE-prefixed injected
      message frames are dropped -- vanilla servers do not understand them.

All protocol formats come from the EaglercraftX server implementation
(lax1dude/eaglerxserver) and the client u53 socket-layer sources.
"""

from __future__ import annotations

import json
import os
import threading

from . import crypto, eagler, vanilla
from .i18n import tr
from .logger import NullLogger

# Human-readable names for the common packet ids, used in log lines.
PACKET_NAMES = {
    (vanilla.LOGIN_DISCONNECT, 'login'): 'LoginDisconnect',
    (vanilla.LOGIN_ENCRYPTION_REQUEST, 'login'): 'EncryptionRequest',
    (vanilla.LOGIN_SUCCESS, 'login'): 'LoginSuccess',
    (vanilla.LOGIN_SET_COMPRESSION, 'login'): 'SetCompression',
    (vanilla.PLAY_KEEP_ALIVE, 'play'): 'KeepAlive',
    (vanilla.PLAY_JOIN_GAME, 'play'): 'JoinGame',
    (0x02, 'play'): 'ChatMessage',
    (0x08, 'play'): 'PlayerPositionAndLook',
    (0x21, 'play'): 'ChunkData',
    (0x26, 'play'): 'MapChunkBulk',
    (vanilla.PLAY_PLUGIN_MESSAGE, 'play'): 'PluginMessage',
    (vanilla.PLAY_DISCONNECT, 'play'): 'Disconnect',
    (vanilla.CLIENT_PLUGIN_MESSAGE, 'play'): 'PluginMessage',
}


def packet_name(packet_id: int, state: str) -> str:
    return PACKET_NAMES.get((packet_id, state), '0x%02x' % packet_id)


def note(text: str) -> str:
    """Tag a text meant for the player with this proxy's own prefix, so that it
    stays distinguishable from whatever the server says."""
    return tr('translator.prefix') + text


def chat_to_text(raw) -> str:
    """Flatten a chat component (JSON) into plain text."""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        parts = []
        text = raw.get('text')
        if isinstance(text, str):
            parts.append(text)
        translate = raw.get('translate')
        if isinstance(translate, str) and not parts:
            parts.append(translate)
        extra = raw.get('extra')
        if isinstance(extra, list):
            parts.append(''.join(chat_to_text(item) for item in extra))
        return ''.join(parts)
    if isinstance(raw, list):
        return ''.join(chat_to_text(item) for item in raw)
    return ''


def uuid_from_string(text: str) -> bytes | None:
    value = text.replace('-', '').strip()
    if len(value) != 32:
        return None
    try:
        return bytes.fromhex(value)
    except ValueError:
        return None


class EaglerTranslator:
    """Per-connection EaglercraftX <-> vanilla translation state machine."""

    def __init__(self, target_host: str, target_port: int, log=None, tag: str = '',
                 send_client=None, send_backend=None, request_close=None,
                 brand: str = 'MCJS-Proxy', brand_version: str = '1.0',
                 spoof_brand: str = ''):
        self.target_host = target_host
        self.target_port = int(target_port)
        self.log = log or NullLogger()
        self.tag = tag
        self.brand = brand
        self.brand_version = brand_version
        # Client identification spoof: the MC|Brand value sent to the target server
        # after login; empty means "do not send one"
        self.spoof_brand = (spoof_brand or '').strip()
        self._send_client = send_client or (lambda data: None)
        self._send_backend = send_backend or (lambda data: None)
        self._request_close = request_close or (lambda reason: None)

        self.phase = 'client_version'     # client_version -> request_login -> backend_login
                                          # -> allow_sent -> play / closed
        self.client_version: eagler.ClientVersion | None = None
        self.handshake_protocol = 0
        self.mc_protocol = eagler.SUPPORTED_MC_PROTOCOLS[-1]
        self.username = ''
        self.uuid = b''
        self.client_finished = False      # has the client sent "finish login" yet?
        self.login_done = False           # has the backend login succeeded yet?
        self.close_reason = ''

        # The client direction uses no Decoder/Encoder: there, one frame is one bare
        # packet -- see feed_client/feed_server
        self.server_decoder = vanilla.Decoder(0)
        self.server_encoder = vanilla.Encoder(0)
        self.server_decrypt: crypto.AesCfb8 | None = None   # target server -> proxy (AES)
        self.server_encrypt: crypto.AesCfb8 | None = None   # proxy -> target server (AES)
        self.pending_to_client: list[bytes] = []            # game frames buffered while the
                                                            # handshake completes (one packet per frame)
        self._lock = threading.Lock()

        self.packets_to_server = 0
        self.packets_to_client = 0
        self._seen_client_ids: set[tuple[int, str]] = set()
        self._seen_server_ids: set[tuple[int, str]] = set()

    # ---------- Public API: the two directions ----------
    def feed_client(self, data: bytes) -> bytes:
        """Feed in one WebSocket frame from the client; return the bytes to write
        to the backend server.

        Note: on the client side one frame is one bare packet (id + content) with
        neither a length prefix nor compression, so a whole frame is treated as a
        single packet here.
        """
        if not data or self.phase == 'closed':
            return b''
        with self._lock:
            if self.phase == 'play':
                out = self._client_play(data)
            elif self.phase == 'client_version':
                out = self._handle_client_version(data)
            else:
                out = self._handle_handshake_packet(data)
            return self._encode_for_backend(out)

    def feed_server(self, data: bytes) -> list[bytes]:
        """Feed in the byte stream from the backend server; return the WebSocket
        frames to send to the client.

        The result is a *list of frames* rather than one blob: the client requires
        exactly one packet per frame, so every packet has to be sent as its own
        frame and the caller must send them one by one.
        """
        if not data or self.phase == 'closed':
            return []
        with self._lock:
            if self.server_decrypt is not None:
                data = self.server_decrypt.decrypt(data)
            self.server_decoder.push(data)
            frames: list[bytes] = []
            while True:
                try:
                    packet = self.server_decoder.next_packet()
                except vanilla.ProtocolError as exc:
                    self._fail(tr('translator.error.backend_parse_failed', error=exc))
                    return frames
                if packet is None:
                    return frames
                self.packets_to_client += 1
                if not self.login_done:
                    self._handle_login_packet(packet, frames)
                else:
                    self._handle_play_packet(packet, frames)
                if self.phase == 'closed':
                    return frames

    def _encode_for_backend(self, data: bytes) -> bytes:
        """Before writing to the backend server: wrap in AES once encryption is on."""
        if not data:
            return b''
        if self.server_encrypt is not None:
            data = self.server_encrypt.encrypt(data)
        return data

    # ---------- Client: first packet ----------
    def _handle_client_version(self, data: bytes) -> bytes:
        version = eagler.parse_client_version(data)
        if version is None:
            self._fail(tr('translator.error.unrecognized_client_version'))
            return b''
        self.client_version = version
        self.log.info('%s %s' % (self.tag, tr(
            'translator.log.client_handshake', detail=version.describe())))

        picked = eagler.select_protocols(version)
        if picked is None:
            message = tr('translator.error.unsupported_mc_protocol',
                         protocols=(version.mc_protocols or ['?']))
            if not version.handshake_protocols:
                message = tr('translator.error.handshake_v1_too_old')
            self.log.warn('%s %s' % (self.tag, message))
            self._send(eagler.pack_version_mismatch(
                eagler.SUPPORTED_HANDSHAKE_PROTOCOLS, min(eagler.SUPPORTED_MC_PROTOCOLS),
                max(eagler.SUPPORTED_MC_PROTOCOLS), 'Outdated Client'))
            # A version-mismatch packet has already been sent; no extra error packet
            self._fail(message, notify_client=False)
            return b''

        self.handshake_protocol, self.mc_protocol = picked
        self.phase = 'request_login'
        self._send(eagler.pack_server_version(
            self.handshake_protocol, self.mc_protocol, self.brand, self.brand_version))
        self.log.info('%s %s' % (self.tag, tr(
            'translator.log.protocols_selected',
            handshake=self.handshake_protocol, mc=self.mc_protocol)))
        return b''

    # ---------- Client: login request / finish login ----------
    def _handle_handshake_packet(self, data: bytes) -> bytes:
        packet_id = data[0]
        if packet_id == eagler.PROTOCOL_CLIENT_REQUEST_LOGIN:
            if self.phase != 'request_login':
                self._fail(tr('translator.error.duplicate_login_request'))
                return b''
            try:
                request = eagler.parse_request_login(data, self.handshake_protocol)
            except eagler.HandshakeError as exc:
                self._fail(tr('translator.error.login_request_parse_failed', error=exc))
                return b''
            return self._begin_backend_login(request)
        if packet_id == eagler.PROTOCOL_CLIENT_PROFILE_DATA:
            self.log.debug('%s %s' % (self.tag, tr(
                'translator.log.ignore_profile_data', size=len(data))))
            return b''
        if packet_id == eagler.PROTOCOL_CLIENT_FINISH_LOGIN:
            if len(data) != 1:
                self._fail(tr('translator.error.finish_login_malformed'))
                return b''
            self.client_finished = True
            self.log.debug('%s %s' % (self.tag, tr('translator.log.client_finished_login')))
            self._maybe_finish_login()
            return b''
        self._fail(tr('translator.error.unexpected_handshake_packet', packet_id=packet_id))
        return b''

    def _begin_backend_login(self, request: eagler.LoginRequest) -> bytes:
        raw_name = (request.username or '').strip()
        if not raw_name and self.client_version is not None:
            # Some browser clients (MCJS, observed in practice) send an empty name in
            # the login request; the real name sits in the authUsername field of the
            # handshake packet and is preferred here, so that not everyone ends up
            # sharing the same fallback name.
            candidate = self.client_version.auth_username.decode('utf-8', 'replace').strip()
            if eagler.USERNAME_PATTERN.match(candidate):
                raw_name = candidate
                self.log.info('%s %s' % (self.tag, tr(
                    'translator.log.empty_username_fallback', name=candidate)))
        username = eagler.sanitize_username(raw_name)
        if username != raw_name:
            self.log.warn('%s %s' % (self.tag, tr(
                'translator.log.username_sanitized', raw=raw_name, clean=username)))
        self.username = username
        self.uuid = eagler.offline_uuid(username)
        self.log.info('%s %s' % (self.tag, tr('translator.log.login_request',
                                              detail=request.describe())))
        self.phase = 'backend_login'

        # Vanilla handshake packet (next state = login) + login-start packet
        address = self.target_host.encode('utf-8')
        handshake = vanilla.pack(0x00, (
            vanilla.write_varint(self.mc_protocol)
            + vanilla.write_varint(len(address)) + address
            + int(self.target_port).to_bytes(2, 'big')
            + vanilla.write_varint(2)))
        login_start = vanilla.pack(0x00, (
            vanilla.write_varint(len(username.encode('utf-8')))
            + username.encode('utf-8')))
        self.log.info('%s %s' % (self.tag, tr(
            'translator.log.vanilla_login_sent',
            username=username, protocol=self.mc_protocol)))
        return handshake + login_start

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
            # The client parses this body as JSON and the kick reason the target
            # server provides is already JSON, so it is forwarded as-is
            self._send(eagler.pack_deny_login(raw or tr('translator.kick_fallback'),
                                              self.handshake_protocol))
            self._fail(denied, notify_client=False)
            return
        if packet_id == vanilla.LOGIN_ENCRYPTION_REQUEST:
            self._handle_encryption_request(packet)
            return
        if packet_id == vanilla.LOGIN_SUCCESS:
            self._handle_login_success(packet, frames)
            return
        self.log.warn('%s %s' % (self.tag, tr(
            'translator.log.unexpected_login_packet',
            packet=packet_name(packet_id, 'login'))))

    def _handle_encryption_request(self, packet: vanilla.Packet) -> None:
        """Complete the encryption handshake on behalf of the client.

        An encryption request does not imply a premium account: many servers
        (especially ones that "look like" premium) merely want the link
        encrypted and never actually check the session with Mojang, so offline
        names are let in all the same. This step is therefore done in the
        client's place: a random shared secret is encrypted with the server's
        public key and sent back, after which both directions use AES-128-CFB8.
        If the server really does validate, it will send a kick reason
        afterwards, and that text is forwarded to the client verbatim.
        """
        if not crypto.available():
            message = tr('translator.error.aes_missing')
            self.log.warn('%s %s' % (self.tag, message))
            self._send(eagler.pack_error(eagler.ERROR_CUSTOM_MESSAGE, note(message),
                                         self.handshake_protocol))
            self._fail(message, notify_client=False)
            return
        try:
            pos = 0
            server_id, pos = vanilla.read_string(packet.body, pos)
            length, pos = vanilla.read_varint(packet.body, pos)
            key_der = packet.body[pos:pos + length]
            pos += length
            length, pos = vanilla.read_varint(packet.body, pos)
            token = packet.body[pos:pos + length]
        except vanilla.ProtocolError as exc:
            self._fail(tr('translator.error.encryption_request_parse_failed', error=exc))
            return
        if not key_der or not token:
            self._fail(tr('translator.error.encryption_request_empty'))
            return
        try:
            secret = os.urandom(16)
            enc_secret = crypto.rsa_encrypt(key_der, secret)
            enc_token = crypto.rsa_encrypt(key_der, token)
        except Exception as exc:                     # bad public key or a library error
            message = tr('translator.error.encryption_handshake_failed', error=exc)
            self.log.warn('%s %s' % (self.tag, message))
            self._send(eagler.pack_error(eagler.ERROR_CUSTOM_MESSAGE, note(message),
                                         self.handshake_protocol))
            self._fail(message, notify_client=False)
            return
        body = (vanilla.write_varint(len(enc_secret)) + enc_secret
                + vanilla.write_varint(len(enc_token)) + enc_token)
        payload = vanilla.write_varint(vanilla.LOGIN_ENCRYPTION_RESPONSE) + body
        # This one is plaintext (encryption starts only once the server has received
        # it), so it is sent directly and does not go through _encode_for_backend
        self._send_backend(self.server_encoder.frame(payload))
        self.server_decrypt = crypto.AesCfb8(secret, secret)
        self.server_encrypt = crypto.AesCfb8(secret, secret)
        self.log.info('%s %s' % (self.tag, tr(
            'translator.log.encryption_done', server_id=server_id,
            secret=secret.hex()[:8], backend=crypto.backend_name())))

    def _handle_login_success(self, packet: vanilla.Packet, frames: list[bytes]) -> None:
        try:
            uuid_text, pos = vanilla.read_string(packet.body, 0)
            name, _ = vanilla.read_string(packet.body, pos)
        except vanilla.ProtocolError:
            self._fail(tr('translator.error.login_success_parse_failed'))
            return
        uuid_bytes = uuid_from_string(uuid_text) or self.uuid
        if name and eagler.USERNAME_PATTERN.match(name):
            self.username = name
            if uuid_from_string(uuid_text) is None:
                uuid_bytes = eagler.offline_uuid(name)
        self.uuid = uuid_bytes
        self.login_done = True
        self.phase = 'allow_sent'
        self.log.info('%s %s' % (self.tag, tr(
            'translator.log.backend_login_ok', username=self.username, uuid=uuid_text)))
        self._send(eagler.pack_allow_login(self.username, self.uuid, self.handshake_protocol))
        self._maybe_finish_login()

    # ---------- Backend: play phase ----------
    def _handle_play_packet(self, packet: vanilla.Packet, frames: list[bytes]) -> None:
        if packet.packet_id == vanilla.PLAY_DISCONNECT:
            reason = self._chat_text(packet.body)
            if reason:
                self.log.warn('%s %s' % (self.tag, tr(
                    'translator.log.backend_disconnect', reason=reason)))
            self.close_reason = reason or self.close_reason
        self._note_packet(packet.packet_id, 'play', to_client=True)
        # The client wants "one bare packet per frame", so packet id + content is
        # sent as one frame directly
        if self.phase == 'play':
            frames.append(packet.payload)
        else:
            # The client has not finished the handshake yet; buffer the game data
            # (still one packet per frame)
            self.pending_to_client.append(packet.payload)

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
        if packet_id == vanilla.CLIENT_PLUGIN_MESSAGE:
            channel = self._plugin_channel(data[at:])
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

    def _announce_brand(self) -> None:
        """After login, declare a spoofed client brand to the target server per config.

        A vanilla client would not send this message itself, and plugins on the
        server side (anti-cheat, statistics, ...) take the "client identification"
        they see mostly from MC|Brand, so a vanilla-style value is supplied here
        per config to keep the target server from recognizing this as a browser
        client through some other channel.
        """
        if not self.spoof_brand:
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
        try:
            return chat_to_text(json.loads(raw)) or raw
        except ValueError:
            return raw

    def _chat_text(self, body: bytes) -> str:
        return self._flatten_chat(self._chat_raw(body))

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
        same teardown path as an internal failure."""
        self._fail(reason, notify_client)

    def _fail(self, reason: str, notify_client: bool = True) -> None:
        if self.phase == 'closed':
            return
        self.phase = 'closed'
        self.close_reason = reason
        if notify_client:
            try:
                self._send(eagler.pack_error(eagler.ERROR_CUSTOM_MESSAGE, note(reason),
                                             max(self.handshake_protocol, 3)))
            except Exception:      # a failed notification must not break teardown
                pass
        self._request_close(reason)
