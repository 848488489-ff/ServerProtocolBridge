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

from . import accounts, crypto, eagler, vanilla
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


_CHAT_KEYS = ('text', 'translate', 'extra', 'with', 'score', 'selector',
              'keybind', 'nbt', 'clickEvent', 'hoverEvent')


def _looks_like_chat_component(value) -> bool:
    """Whether a decoded JSON value is a Minecraft chat component.

    A kick reason is sometimes serialized twice, so the first ``json.loads``
    returns a string that still contains the actual component.  Plain player
    chat may also look like JSON, so only unwrap objects with component keys
    (or lists of component-ish values) to avoid turning a literal message such
    as ``{"foo": "bar"}`` into an empty string.
    """
    if isinstance(value, dict):
        return any(key in value for key in _CHAT_KEYS)
    if isinstance(value, list):
        return bool(value) and all(
            isinstance(item, (str, dict, list)) for item in value)
    return False


def _unwrap_chat_json(value, depth: int = 0):
    """Remove one or more JSON-string wrappers around a chat component."""
    if depth >= 8 or not isinstance(value, str):
        return value
    text = value.strip().lstrip('\ufeff')
    if not text or text[0] not in '{["':
        return value
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return value
    if isinstance(parsed, str):
        if parsed == value:
            return value
        return _unwrap_chat_json(parsed, depth + 1)
    if _looks_like_chat_component(parsed):
        return parsed
    return value


def chat_to_text(raw) -> str:
    """Flatten a chat component (JSON) into plain text.

    Handles the normal object form, arrays, nested ``extra`` arrays and the
    double-encoded strings some servers/proxies produce.
    """
    if isinstance(raw, str):
        raw = _unwrap_chat_json(raw)
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        parts = []
        text = raw.get('text')
        if isinstance(text, str):
            nested = _unwrap_chat_json(text)
            if isinstance(nested, (dict, list)):
                parts.append(chat_to_text(nested))
            else:
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


_LEGACY_COLOR_CODES = {
    'black': '0', 'dark_blue': '1', 'dark_green': '2', 'dark_aqua': '3',
    'dark_red': '4', 'dark_purple': '5', 'gold': '6', 'gray': '7',
    'dark_gray': '8', 'blue': '9', 'green': 'a', 'aqua': 'b', 'red': 'c',
    'light_purple': 'd', 'yellow': 'e', 'white': 'f',
}
_LEGACY_COLOR_RGB = {
    '0': (0, 0, 0), '1': (0, 0, 170), '2': (0, 170, 0), '3': (0, 170, 170),
    '4': (170, 0, 0), '5': (170, 0, 170), '6': (255, 170, 0),
    '7': (170, 170, 170), '8': (85, 85, 85), '9': (85, 85, 255),
    'a': (85, 255, 85), 'b': (85, 255, 255), 'c': (255, 85, 85),
    'd': (255, 85, 255), 'e': (255, 255, 85), 'f': (255, 255, 255),
}
_LEGACY_STYLE_CODES = (
    ('obfuscated', 'k'), ('bold', 'l'), ('strikethrough', 'm'),
    ('underlined', 'n'), ('italic', 'o'),
)
_LEGACY_COLOR_NAMES = {code: name for name, code in _LEGACY_COLOR_CODES.items()}
_LEGACY_STYLE_NAMES = {code: name for name, code in _LEGACY_STYLE_CODES}


def _legacy_color_code(value: str) -> str | None:
    """Map a chat-component colour name (or hex value) to a legacy code."""
    value = value.strip().lower()
    if value == 'reset':
        return ''
    if value in _LEGACY_COLOR_CODES:
        return _LEGACY_COLOR_CODES[value]
    if value.startswith('#') and len(value) in (4, 7):
        digits = value[1:]
        if len(digits) == 3:
            digits = ''.join(character * 2 for character in digits)
        try:
            red, green, blue = (int(digits[index:index + 2], 16)
                                for index in (0, 2, 4))
        except ValueError:
            return None
        # Legacy clients only understand the 16-colour palette.  Pick the
        # nearest entry instead of dropping the colour altogether.
        return min(_LEGACY_COLOR_RGB,
                   key=lambda code: sum(
                       (actual - target) ** 2
                       for actual, target in zip(
                           (red, green, blue), _LEGACY_COLOR_RGB[code])))
    return None


def _legacy_style(component: dict, parent: dict) -> dict:
    state = dict(parent)
    color = component.get('color')
    if isinstance(color, str):
        code = _legacy_color_code(color)
        if code == '':
            state = {}
        elif code:
            state['color'] = code
    for key, _code in _LEGACY_STYLE_CODES:
        if key in component and isinstance(component[key], bool):
            state[key] = component[key]
    return state


def _legacy_prefix(state: dict) -> str:
    codes = ''
    if state.get('color'):
        codes += '\u00a7' + state['color']
    codes += ''.join('\u00a7' + code for key, code in _LEGACY_STYLE_CODES
                     if state.get(key))
    return '\u00a7r' + codes


def _collect_legacy(raw, state: dict, out: list[tuple[str, dict]]) -> None:
    if isinstance(raw, str):
        if raw:
            out.append((raw, state))
        return
    if isinstance(raw, list):
        for item in raw:
            _collect_legacy(item, state, out)
        return
    if not isinstance(raw, dict):
        return
    state = _legacy_style(raw, state)
    text = raw.get('text')
    has_text = isinstance(text, str)
    if has_text:
        nested = _unwrap_chat_json(text)
        if isinstance(nested, (dict, list)):
            _collect_legacy(nested, state, out)
        elif text:
            out.append((text, state))
    translate = raw.get('translate')
    if isinstance(translate, str) and not has_text:
        out.append((translate, state))
    extra = raw.get('extra')
    if isinstance(extra, list):
        for item in extra:
            _collect_legacy(item, state, out)


def chat_to_legacy(raw) -> str:
    """Flatten a chat component into text with Minecraft legacy colour codes.

    The browser clients show disconnect and MOTD bodies as plain strings; JSON
    colour fields are therefore converted to the ``§`` codes their font
    renderer understands.  Plain strings that already contain ``§`` codes are
    returned unchanged.
    """
    if isinstance(raw, str):
        unwrapped = _unwrap_chat_json(raw)
        if isinstance(unwrapped, str):
            return unwrapped
        raw = unwrapped
    elif not isinstance(raw, (dict, list)):
        return ''
    segments: list[tuple[str, dict]] = []
    _collect_legacy(raw, {}, segments)
    parts: list[str] = []
    current: dict | None = None
    formatted = False
    for text, state in segments:
        if not text:
            continue
        notices = any(state.get(key) for key, _code in _LEGACY_STYLE_CODES)
        if current is None:
            if state.get('color') or notices:
                parts.append(_legacy_prefix(state))
                formatted = True
        elif state != current:
            codes = ''
            if state.get('color'):
                codes += '\u00a7' + state['color']
            codes += ''.join('\u00a7' + code for key, code in _LEGACY_STYLE_CODES
                             if state.get(key))
            parts.append('\u00a7r' + codes)
            formatted = True
        parts.append(text)
        current = state
    if formatted and current and (
            current.get('color') or any(current.get(key)
                                        for key, _code in _LEGACY_STYLE_CODES)):
        parts.append('\u00a7r')
    return ''.join(parts)


def _component_from_legacy(text: str) -> dict:
    """Turn a legacy ``§``-formatted string into one chat component.

    A component whose ``text`` still contains section-sign codes is rendered
    literally by several browser clients (the section sign becomes a missing
    glyph and the code letter stays visible).  Converting the codes to the
    JSON ``color`` / ``bold`` fields makes the same text render correctly in
    those clients.
    """
    segments: list[dict] = []
    state: dict = {}
    buffer: list[str] = []

    def flush() -> None:
        if not buffer:
            return
        part = {'text': ''.join(buffer)}
        if state.get('color'):
            part['color'] = state['color']
        for key, _code in _LEGACY_STYLE_CODES:
            if state.get(key):
                part[key] = True
        segments.append(part)
        buffer.clear()

    at = 0
    while at < len(text):
        character = text[at]
        if character == '\u00a7' and at + 1 < len(text):
            code = text[at + 1].lower()
            if code == 'r':
                flush()
                state.clear()
                at += 2
                continue
            if code in _LEGACY_COLOR_NAMES:
                flush()
                state['color'] = _LEGACY_COLOR_NAMES[code]
                at += 2
                continue
            if code in _LEGACY_STYLE_NAMES:
                flush()
                state[_LEGACY_STYLE_NAMES[code]] = True
                at += 2
                continue
        buffer.append(character)
        at += 1
    flush()
    if len(segments) == 1:
        return segments[0]
    if not segments:
        return {'text': ''}
    return {'text': '', 'extra': segments}


def chat_to_component_json(raw, fallback: str = 'Kicked') -> str:
    """Build a normalised JSON chat component with explicit colour fields.

    Server kick reasons arrive either as JSON components (often with colour
    fields) or as legacy ``§`` strings.  Both are first flattened to a legacy
    string, then converted back into a component whose colours are fields
    rather than inline section-sign codes, which is what the browser clients
    render on the disconnect screen.
    """
    legacy = chat_to_legacy(raw)
    if not legacy:
        legacy = fallback
    return json.dumps(_component_from_legacy(legacy), ensure_ascii=False)


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
                 brand: str = 'ServerProtocolBridge', brand_version: str = '1.0',
                 spoof_client: str = 'off', spoof_brand: str = '',
                 login_ack: bool = True, resource_pack_mode: str = 'forward', account=None):
        self.target_host = target_host
        self.target_port = int(target_port)
        self.log = log or NullLogger()
        self.tag = tag
        self.brand = brand
        self.brand_version = brand_version
        # Client identification spoof: the preset decides which handshake
        # fingerprints (FML marker / channel registration) are reproduced on
        # the upstream connection; the brand is the MC|Brand value sent to the
        # target server after login, and empty means "do not send one"
        self.spoof_client = (spoof_client or 'off').strip().lower()
        self.spoof_brand = (spoof_brand or '').strip()
        # Whether the 1.20.2+ login acknowledge is sent in the client's place
        # (see _handle_login_success); switchable because it is a guess about
        # what the browser client does, not part of the classic flow
        self.login_ack = bool(login_ack)
        # How to treat the server's resource pack prompt (see config.py).
        self.resource_pack_mode = (resource_pack_mode or 'forward').strip().lower()
        # The account selected in the settings (accounts.py), if any: it
        # dictates the name/UUID the target sees and, for authenticated kinds,
        # the session join done before the encryption answer
        self.account = account
        self._send_client = send_client or (lambda data: None)
        self._send_backend = send_backend or (lambda data: None)
        self._request_close = request_close or (lambda reason: None)

        self.phase = 'client_version'     # client_version -> request_login -> backend_login
                                          # -> allow_sent -> play / closed
        self.client_version: eagler.ClientVersion | None = None
        self.handshake_protocol = 0
        self.mc_protocol = eagler.DEFAULT_MC_PROTOCOL
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
            # Only the v1 handshake lands here: it carries no version list, so
            # there is nothing to negotiate from
            message = tr('translator.error.handshake_v1_too_old')
            self.log.warn('%s %s' % (self.tag, message))
            self._send(eagler.pack_version_mismatch(
                eagler.SUPPORTED_HANDSHAKE_PROTOCOLS, *eagler.MC_PROTOCOL_RANGE,
                'Outdated Client'))
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
            if request.cookie:
                self.log.debug('%s %s' % (self.tag, tr(
                    'translator.log.cookie_discarded', size=len(request.cookie))))
                request.cookie = b''
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
        account = self.account
        if account is not None and (account.username or '').strip():
            # An account is selected: it dictates the identity -- the exact
            # name and profile UUID a server that validates logins expects to
            # see together.  The name the client asked for is only used when
            # no account is set.
            username = account.username.strip()
            self.username = username
            self.uuid = account.uuid_bytes or eagler.offline_uuid(username)
            self.log.info('%s %s' % (self.tag, tr(
                'translator.log.account_selected', label=account.label,
                uuid=self.uuid.hex())))
        elif not raw_name and self.client_version is not None:
            # Some browser clients (MCJS, observed in practice) send an empty name in
            # the login request; the real name sits in the authUsername field of the
            # handshake packet and is preferred here, so that not everyone ends up
            # sharing the same fallback name.
            candidate = self.client_version.auth_username.decode('utf-8', 'replace').strip()
            if eagler.USERNAME_PATTERN.match(candidate):
                raw_name = candidate
                self.log.info('%s %s' % (self.tag, tr(
                    'translator.log.empty_username_fallback', name=candidate)))
        if not (self.username and self.uuid):
            username = eagler.sanitize_username(raw_name)
            if username != raw_name:
                self.log.warn('%s %s' % (self.tag, tr(
                    'translator.log.username_sanitized', raw=raw_name, clean=username)))
            self.username = username
            self.uuid = eagler.offline_uuid(username)
        username = self.username
        self.log.info('%s %s' % (self.tag, tr('translator.log.login_request',
                                              detail=request.describe())))
        self.phase = 'backend_login'

        # Vanilla handshake packet (next state = login) + login-start packet
        address = self.target_host.encode('utf-8')
        if self.spoof_client == 'forge-1.8' and self.mc_protocol == 47:
            # Legacy Forge clients append the FML marker to the address they put
            # into their handshake packet (see C00Handshake in the Forge patch
            # set); the remote end stores that marker as the connection's "this
            # is a modded client" flag.  The marker, the REGISTER channel list
            # and the brand are reproduced on 1.8 connections only: that is the
            # only generation whose packet numbers and channel names this proxy
            # knows by heart, and guessing others would put malformed packets
            # on the wire.
            address += b'\x00FML\x00'
        handshake = vanilla.pack(0x00, (
            vanilla.write_varint(self.mc_protocol)
            + vanilla.write_varint(len(address)) + address
            + int(self.target_port).to_bytes(2, 'big')
            + vanilla.write_varint(2)))
        name_bytes = username.encode('utf-8')
        login_start_body = vanilla.write_varint(len(name_bytes)) + name_bytes
        # Login Start gained optional (1.19) and then required (1.20.2) fields.
        # The target server parses the packet with its own version's layout, so
        # the fields it expects must be present: where they are optional the
        # "absent" flag is written, where the UUID is required ours is sent
        if self.mc_protocol >= 764:
            login_start_body += self.uuid
        elif self.mc_protocol >= 761:
            login_start_body += b'\x00'
        elif self.mc_protocol >= 760:
            login_start_body += b'\x00\x00'
        elif self.mc_protocol >= 759:
            login_start_body += b'\x00'
        login_start = vanilla.pack(0x00, login_start_body)
        self.log.info('%s %s' % (self.tag, tr(
            'translator.log.vanilla_login_sent',
            username=username, protocol=self.mc_protocol)))
        if self.spoof_client == 'forge-1.8' and self.mc_protocol == 47:
            self.log.info('%s %s' % (self.tag, tr('translator.log.forge_marker')))
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
            # The kick reason the target server provides is usually JSON.  The
            # log has already flattened it correctly, but several browser
            # clients (including some that advertise an EaglercraftX brand)
            # show the deny body as literal text.  Sending the component JSON
            # therefore produces a wall of JSON on the disconnect screen, so
            # always send the flattened reason.
            fallback = tr('translator.kick_fallback')
            # The modern EaglercraftX launcher displays the deny body as a
            # plain string (a JSON body is shown literally), while its font
            # renderer understands legacy colour codes.  Send the flattened
            # string with the § prefixes intact.
            body = chat_to_legacy(raw) or fallback
            self._send(eagler.pack_deny_login(body, self.handshake_protocol,
                                              chat_json=False))
            self._fail(denied, notify_client=False)
            return
        if packet_id == vanilla.LOGIN_ENCRYPTION_REQUEST:
            self._handle_encryption_request(packet)
            return
        if packet_id == vanilla.LOGIN_PLUGIN_REQUEST:
            self._decline_login_plugin_request(packet)
            return
        if packet_id == vanilla.LOGIN_COOKIE_REQUEST:
            self._decline_login_cookie_request(packet)
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
                                         self.handshake_protocol,
                                         chat_json=self._client_parses_chat_json()))
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
                                         self.handshake_protocol,
                                         chat_json=self._client_parses_chat_json()))
            self._fail(message, notify_client=False)
            return
        account = self.account
        if account is not None and account.joinable():
            # An authenticated account is selected and the server wants the
            # link encrypted: if it really validates logins, it will now ask
            # the session service about this join, so the join has to be
            # registered first -- in the client's place, because the browser
            # client cannot do that part (and this is the reason accounts
            # exist here at all).  Blocking by design: the caller runs the
            # translation layer off the event loop.
            try:
                accounts.join_session(account,
                                      accounts.join_hash(server_id, secret, key_der),
                                      log=self.log)
            except accounts.AccountError as exc:
                message = tr('translator.error.account_join_failed', error=exc)
                self.log.warn('%s %s' % (self.tag, message))
                self._send(eagler.pack_error(eagler.ERROR_CUSTOM_MESSAGE, note(message),
                                             self.handshake_protocol,
                                             chat_json=self._client_parses_chat_json()))
                self._fail(message, notify_client=False)
                return
            self.log.info('%s %s' % (self.tag, tr(
                'translator.log.account_joined', label=account.label)))
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
        if name and eagler.USERNAME_PATTERN.match(name):
            self.username = name
            if raw_uuid is None and uuid_from_string(uuid_text) is None:
                uuid_bytes = eagler.offline_uuid(name)
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
