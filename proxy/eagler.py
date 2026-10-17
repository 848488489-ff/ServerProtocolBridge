"""EaglercraftX 1.8 client handshake protocol (server-side implementation).

Browser clients (the EaglercraftX family) **do not send a vanilla handshake**:
they first send a handshake in their own protocol, in which the server completes
the "version negotiation -> request login -> allow login -> finish login" flow;
only after that does the connection switch to the vanilla 1.8.8 game data stream.
Vanilla servers cannot read any of it and simply close the connection, so an
intermediary layer is needed to answer this handshake for them.

Protocol details come from the EaglercraftX server implementation
(lax1dude/eaglerxserver, core/.../handshake and
core/.../pipeline/WebSocketEaglerInitialHandler) and match measured traffic
exactly:

    Client's first packet (37 bytes measured):
      01 02                     marker: 0x01 = EaglercraftX 1.8, 0x02 = handshake v2..v5
      00 03                     3 "supported handshake protocol versions" follow
      00 03 00 04 00 05         = 3, 4, 5
      00 01                     1 "supported Minecraft protocol version" follows
      00 2f                     = 47 = Minecraft 1.8.8
      0c "EaglercraftX"         client brand
      03 "u53"                  client version
      00                        clientAuth = false
      04 "nopp"                 authUsername (placeholder when authentication is off)

Every handshake packet is "one WebSocket frame = one packet" with no length
prefix, so parsing must consume exactly the whole frame.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field

from .i18n import tr

# Handshake packet types (HandshakePacketTypes)
PROTOCOL_CLIENT_VERSION = 0x01
PROTOCOL_SERVER_VERSION = 0x02
PROTOCOL_VERSION_MISMATCH = 0x03
PROTOCOL_CLIENT_REQUEST_LOGIN = 0x04
PROTOCOL_SERVER_ALLOW_LOGIN = 0x05
PROTOCOL_SERVER_DENY_LOGIN = 0x06
PROTOCOL_CLIENT_PROFILE_DATA = 0x07
PROTOCOL_CLIENT_FINISH_LOGIN = 0x08
PROTOCOL_SERVER_FINISH_LOGIN = 0x09
PROTOCOL_SERVER_REDIRECT_TO = 0x0A
PROTOCOL_SERVER_ERROR = 0xFF

# Server error codes
ERROR_UNKNOWN_PACKET = 0x01
ERROR_INVALID_PACKET = 0x02
ERROR_WRONG_PACKET = 0x03
ERROR_CUSTOM_MESSAGE = 0x08
ERROR_AUTHENTICATION_REQUIRED = 0x09

# We implement handshake protocols v2..v5; a client picks the highest one in its list
SUPPORTED_HANDSHAKE_PROTOCOLS = (2, 3, 4, 5)
# Browser clients only speak 1.8, so this is the only protocol version supported
SUPPORTED_MC_PROTOCOLS = (47,)

MARKER_CLASSIC = 0x01        # First byte: EaglercraftX 1.8
MARKER_MODERN = 0x02         # Second byte: v2..v5 handshake
MARKER_LEGACY = 0x01         # Second byte: v1 handshake

USERNAME_PATTERN = re.compile(r'^[A-Za-z0-9_]{3,16}$')
MAX_STRING = 255
MAX_LIST = 16


class HandshakeError(Exception):
    """The handshake data does not follow the protocol."""


# ---------- Helpers ----------

def _as_u16(value: int) -> bytes:
    return int(value).to_bytes(2, 'big')


def _read_u16(data: bytes, pos: int) -> tuple[int, int]:
    if pos + 2 > len(data):
        raise HandshakeError(tr('eagler.error.u16_out_of_range'))
    return int.from_bytes(data[pos:pos + 2], 'big'), pos + 2


def _write_string(text: str) -> bytes:
    encoded = text.encode('utf-8')
    if len(encoded) > MAX_STRING:
        encoded = encoded[:MAX_STRING]
    return bytes([len(encoded)]) + encoded


def _read_string(data: bytes, pos: int) -> tuple[str, int]:
    if pos >= len(data):
        raise HandshakeError(tr('eagler.error.string_length_out_of_range'))
    length = data[pos]
    start = pos + 1
    end = start + length
    if end > len(data):
        raise HandshakeError(tr('eagler.error.string_out_of_range'))
    return data[start:end].decode('utf-8', 'replace'), end


def _truncate_utf8(text: str, limit: int) -> str:
    """Truncate to a UTF-8 byte budget without splitting a multi-byte character."""
    encoded = text.encode('utf-8')
    if len(encoded) <= limit:
        return text
    return encoded[:limit].decode('utf-8', 'ignore')


def as_chat_json(raw: str, fallback: str = 'Kicked') -> str:
    """Turn a piece of text into chat-component JSON the client can parse.

    Since v3, the client parses the body of "deny login" and "custom error"
    packets as JSON (IChatComponent.Serializer.jsonToComponent); sending plain
    text makes it throw and show nothing but "Invalid packet received", wasting
    the kick reason the server gave. Kick reasons coming from vanilla servers
    are already valid JSON and pass through unchanged.
    """
    text = (raw or '').strip() or fallback
    try:
        parsed = json.loads(text)
    except ValueError:
        return json.dumps({'text': text}, ensure_ascii=False)
    if isinstance(parsed, (dict, list)):
        return text
    return json.dumps({'text': text}, ensure_ascii=False)


def offline_uuid(username: str) -> bytes:
    """Offline-mode UUID: matches Java's UUID.nameUUIDFromBytes("OfflinePlayer:"+name).

    Entity UUIDs on the server and locally are all computed this way, and all
    three sides must agree, otherwise the client treats the player as a stranger
    (name list / skins / entity ownership can all end up mismatched).
    """
    digest = bytearray(hashlib.md5(('OfflinePlayer:' + username).encode('utf-8')).digest())
    digest[6] = (digest[6] & 0x0F) | 0x30        # version 3 (name-based)
    digest[8] = (digest[8] & 0x3F) | 0x80        # IETF variant
    return bytes(digest)


# ---------- Client's first packet ----------

@dataclass
class ClientVersion:
    """Contents of the client's first data packet."""

    handshake_protocols: list[int] = field(default_factory=list)
    mc_protocols: list[int] = field(default_factory=list)
    brand: str = ''
    version: str = ''
    auth: bool = False
    auth_username: bytes = b''

    def describe(self) -> str:
        return tr('eagler.describe.client_version',
                  brand=self.brand or '?', version=self.version or '?',
                  handshake=self.handshake_protocols, mc=self.mc_protocols,
                  auth=tr('eagler.describe.auth_enabled' if self.auth
                          else 'eagler.describe.auth_disabled'))


def _looks_like_modern_marker(data: bytes) -> bool:
    return (len(data) >= 8 and data[0] == MARKER_CLASSIC
            and data[1] in (MARKER_MODERN, MARKER_LEGACY))


def parse_client_version(data: bytes) -> ClientVersion | None:
    """Parse the client's first packet; return None for formats we do not know
    (such traffic is forwarded as-is).

    The protocol contract is strict: the frame must be consumed exactly, and a
    single extra byte makes it invalid.
    """
    if not _looks_like_modern_marker(data):
        return None
    version = ClientVersion()
    try:
        pos = 2
        if data[1] == MARKER_LEGACY:
            # v1 client: u8 MC protocol, brand, version
            if pos >= len(data):
                raise HandshakeError(tr('eagler.error.v1_packet_incomplete'))
            version.mc_protocols = [data[pos]]
            pos += 1
            version.brand, pos = _read_string(data, pos)
            version.version, pos = _read_string(data, pos)
        else:
            count, pos = _read_u16(data, pos)
            if not 1 <= count <= MAX_LIST:
                raise HandshakeError(tr('eagler.error.bad_handshake_count', count=count))
            for _ in range(count):
                value, pos = _read_u16(data, pos)
                version.handshake_protocols.append(value)
            count, pos = _read_u16(data, pos)
            if not 1 <= count <= MAX_LIST:
                raise HandshakeError(tr('eagler.error.bad_mc_count', count=count))
            for _ in range(count):
                value, pos = _read_u16(data, pos)
                version.mc_protocols.append(value)
            version.brand, pos = _read_string(data, pos)
            version.version, pos = _read_string(data, pos)
            if pos >= len(data):
                raise HandshakeError(tr('eagler.error.missing_client_auth'))
            version.auth = bool(data[pos])
            pos += 1
            if pos >= len(data):
                raise HandshakeError(tr('eagler.error.missing_auth_username'))
            length = data[pos]
            pos += 1
            if pos + length > len(data):
                raise HandshakeError(tr('eagler.error.auth_username_out_of_range'))
            version.auth_username = data[pos:pos + length]
            pos += length
        if pos != len(data):
            raise HandshakeError(tr('eagler.error.trailing_bytes',
                                    count=len(data) - pos))
    except HandshakeError:
        return None
    return version


def select_protocols(client: ClientVersion) -> tuple[int, int] | None:
    """Pick the highest handshake and MC protocol versions both sides support."""
    handshake = [item for item in client.handshake_protocols
                 if item in SUPPORTED_HANDSHAKE_PROTOCOLS]
    mc = [item for item in client.mc_protocols if item in SUPPORTED_MC_PROTOCOLS]
    if not handshake or not mc:
        return None
    return max(handshake), max(mc)


# ---------- Server replies ----------

def pack_server_version(handshake_protocol: int, mc_protocol: int, brand: str,
                        version: str, auth_method: int = 0,
                        salt: bytes = b'', nickname_selection: bool = False) -> bytes:
    """Server version packet (0x02), matching sendPacketVersionNoAuth of HandshakerV2~V5."""
    out = bytearray([PROTOCOL_SERVER_VERSION])
    out += _as_u16(handshake_protocol)
    out += _as_u16(mc_protocol)
    out += _write_string(brand)
    out += _write_string(version)
    out.append(auth_method & 0xFF)
    out += _as_u16(len(salt))
    out += salt
    if handshake_protocol >= 4:
        out.append(1 if nickname_selection else 0)
    return bytes(out)


def pack_version_mismatch(handshake_protocols, mc_min: int, mc_max: int,
                          message: str) -> bytes:
    """Version mismatch packet (0x03)."""
    out = bytearray([PROTOCOL_VERSION_MISMATCH])
    out += _as_u16(len(handshake_protocols))
    for item in handshake_protocols:
        out += _as_u16(item)
    out += _as_u16(2)
    out += _as_u16(mc_min)
    out += _as_u16(mc_max)
    out += _write_string(message)
    return bytes(out)


def pack_allow_login(username: str, uuid_bytes: bytes, handshake_protocol: int,
                     capabilities: int = 0, capability_versions: bytes = b'',
                     ext_count: int = 0) -> bytes:
    """Allow login packet (0x05). Only v5 carries capability bits; v2..v4 are just name + UUID."""
    out = bytearray([PROTOCOL_SERVER_ALLOW_LOGIN])
    out += _write_string(username)
    if len(uuid_bytes) != 16:
        raise HandshakeError(tr('eagler.error.uuid_not_16_bytes'))
    out += uuid_bytes
    if handshake_protocol >= 5:
        out += _varint(capabilities)
        out += capability_versions
        out.append(ext_count & 0xFF)
    return bytes(out)


def pack_deny_login(message: str, handshake_protocol: int) -> bytes:
    """Deny login packet (0x06).

    From v3 on the length field is a u16 and the client parses the body as JSON
    (IChatComponent); below v3 the length is a u8 and the body is plain text.
    """
    out = bytearray([PROTOCOL_SERVER_DENY_LOGIN])
    if handshake_protocol >= 3:
        encoded = _truncate_utf8(as_chat_json(message), 65535).encode('utf-8')
        out += _as_u16(len(encoded))
    else:
        encoded = _truncate_utf8(message, 255).encode('utf-8')
        out.append(len(encoded))
    out += encoded
    return bytes(out)


def pack_error(code: int, message: str, handshake_protocol: int) -> bytes:
    """Error packet (0xFF).

    From v3 on the length field is a u16 (the client reads a u16), and the body
    of ERROR_CUSTOM_MESSAGE is parsed by jsonToComponent, so custom messages
    must be JSON; the client concatenates other error codes as plain text, which
    is therefore kept as-is. Below v3 the length is a u8 and the body is always
    plain text.
    """
    out = bytearray([PROTOCOL_SERVER_ERROR, code & 0xFF])
    if handshake_protocol >= 3:
        body = as_chat_json(message) if code == ERROR_CUSTOM_MESSAGE else message
        encoded = _truncate_utf8(body, 65535).encode('utf-8')
        out += _as_u16(len(encoded))
    else:
        encoded = _truncate_utf8(message, 255).encode('utf-8')
        out.append(len(encoded))
    out += encoded
    return bytes(out)


def pack_error_pre_version(code: int, message: str) -> bytes:
    """Pre-negotiation error packet (0xFF): the length field is a **u8** and the
    body is plain text.

    Right after the client sends its first packet and before it has received the
    server version packet, incoming traffic is handled by HandshakerHandler,
    which in this state only accepts 0x02 / 0x03 / 0xFF and reads 0xFF bodies as
    plain text (see handleServerError(packet, false)). Used to tell the player
    reasons like "the target server is unreachable" directly, instead of leaving
    them with a bare Connection Closed.
    """
    encoded = _truncate_utf8(message, 255).encode('utf-8')
    return bytes([PROTOCOL_SERVER_ERROR, code & 0xFF, len(encoded)]) + encoded


def pack_finish_login() -> bytes:
    """Server finish-login packet (0x09); vanilla game data follows."""
    return bytes([PROTOCOL_SERVER_FINISH_LOGIN])


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _read_varint(data: bytes, pos: int) -> tuple[int, int]:
    value = 0
    for index in range(5):
        if pos >= len(data):
            raise HandshakeError(tr('eagler.error.varint_out_of_range'))
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << (7 * index)
        if not byte & 0x80:
            return value, pos
    raise HandshakeError(tr('eagler.error.varint_too_long'))


# ---------- Client login request ----------

@dataclass
class LoginRequest:
    username: str = ''
    requested_server: str = ''
    password: bytes = b''
    cookie: bytes = b''
    capabilities: int = 0

    def describe(self) -> str:
        return tr('eagler.describe.login_request',
                  username=self.username, server=self.requested_server,
                  password=tr('eagler.describe.password_set' if self.password
                              else 'eagler.describe.password_unset'),
                  caps=self.capabilities)


def parse_request_login(data: bytes, handshake_protocol: int) -> LoginRequest:
    """Parse the login request packet (0x04); the fields differ per handshake version:
    v1~v3: name, server address, password
    v4    : plus cookie flag and contents
    v5    : plus capability bits and the extension capability table
    """
    if not data or data[0] != PROTOCOL_CLIENT_REQUEST_LOGIN:
        raise HandshakeError(tr('eagler.error.not_login_request'))
    pos = 1
    request = LoginRequest()
    request.username, pos = _read_string(data, pos)
    request.requested_server, pos = _read_string(data, pos)
    if pos >= len(data):
        raise HandshakeError(tr('eagler.error.missing_password_field'))
    length = data[pos]
    pos += 1
    if pos + length > len(data):
        raise HandshakeError(tr('eagler.error.password_out_of_range'))
    request.password = data[pos:pos + length]
    pos += length
    if handshake_protocol >= 4:
        if pos >= len(data):
            raise HandshakeError(tr('eagler.error.missing_cookie_flag'))
        enable_cookie = bool(data[pos])
        pos += 1
        if pos >= len(data):
            raise HandshakeError(tr('eagler.error.missing_cookie_length'))
        cookie_len = data[pos]
        pos += 1
        if enable_cookie:
            if pos + cookie_len > len(data):
                raise HandshakeError(tr('eagler.error.cookie_out_of_range'))
            request.cookie = data[pos:pos + cookie_len]
            pos += cookie_len
        elif cookie_len != 0:
            raise HandshakeError(tr('eagler.error.cookie_length_not_zero'))
    if handshake_protocol >= 5:
        request.capabilities, pos = _read_varint(data, pos)
        count = bin(request.capabilities).count('1')
        for _ in range(count):
            _, pos = _read_varint(data, pos)
        if pos >= len(data):
            raise HandshakeError(tr('eagler.error.missing_extension_count'))
        ext_count = data[pos]
        pos += 1
        if ext_count > 32:
            raise HandshakeError(tr('eagler.error.bad_extension_count', count=ext_count))
        for _ in range(ext_count):
            if pos + 16 > len(data):
                raise HandshakeError(tr('eagler.error.extension_uuid_out_of_range'))
            pos += 16
            _, pos = _read_varint(data, pos)
    if pos != len(data):
        raise HandshakeError(tr('eagler.error.login_trailing_bytes',
                                count=len(data) - pos))
    return request


def sanitize_username(username: str, fallback: str = 'MCJSEagler') -> str:
    """Target servers only accept [A-Za-z0-9_]{3,16}; anything else is replaced
    with a stable, usable name."""
    if USERNAME_PATTERN.match(username or ''):
        return username
    cleaned = re.sub(r'[^A-Za-z0-9_]', '', username or '')
    if len(cleaned) > 16:
        cleaned = cleaned[:16]
    if len(cleaned) < 3:
        cleaned = (cleaned + fallback)[:16]
    return cleaned
