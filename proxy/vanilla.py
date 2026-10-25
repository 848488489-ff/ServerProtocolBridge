"""Framing and compression of the vanilla Minecraft protocol (1.8, protocol
version 47) -- only the parts needed to relay packets.

**Vanilla TCP side** (the Decoder/Encoder of this module):
* compression off: [VarInt length][VarInt packet id][content]
* compression on : [VarInt length][VarInt uncompressed length][content]
    - uncompressed length == 0: the content is raw (packet id + data)
    - uncompressed length > 0 : the content is zlib-compressed (packet id + data)

**Browser clients (EaglercraftX) use a different convention on the WebSocket
side**, completely unlike TCP: one WebSocket frame = one complete packet
(packet id + content), with neither a length prefix nor compression. When
reading, the client takes the start of the frame as the packet id
(`input.readVarIntFromBuffer()` in WebSocketNetworkManager); when writing, it
puts `writeVarInt(packet id) + writePacketData()` into a single frame. The
reference server implementation WebSocketEaglerFrameCodec likewise pushes the
content of a BinaryWebSocketFrame into the pipeline as one packet and stuffs a
whole packet into one frame when sending.
So: one packet in the vanilla stream -> one bare frame; and one bare frame ->
one packet in the vanilla stream.

Sources: VanillaInitializer / WebSocketEaglerFrameCodec of the EaglercraftX
server (lax1dude/eaglerxserver), and WebSocketNetworkManager of the client u53.
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass

from .i18n import tr

MAX_PACKET_BYTES = 8 * 1024 * 1024

# Login-phase packet ids
LOGIN_DISCONNECT = 0x00
LOGIN_ENCRYPTION_REQUEST = 0x01
LOGIN_ENCRYPTION_RESPONSE = 0x01
LOGIN_SUCCESS = 0x02
LOGIN_SET_COMPRESSION = 0x03
# The ids below only exist since 1.13 / 1.20.5; answering them keeps a login
# from stalling on modded or forwarding-server targets (an answer is expected
# either way)
LOGIN_PLUGIN_REQUEST = 0x04     # clientbound (1.13+)
LOGIN_PLUGIN_RESPONSE = 0x02    # serverbound (1.13+)
LOGIN_COOKIE_REQUEST = 0x05     # clientbound (1.20.5+)
LOGIN_COOKIE_RESPONSE = 0x04    # serverbound (1.20.5+)

# 1.20.2 split login and play with a "configuration" phase: the server stays in
# the login state after Login Success until the client acknowledges it
LOGIN_ACKNOWLEDGED = 0x03       # serverbound (1.20.2+), no content

# Play-phase packet ids that matter to us (1.8.8)
PLAY_KEEP_ALIVE = 0x00
PLAY_JOIN_GAME = 0x01
PLAY_WINDOW_CONFIRMATION = 0x32  # server -> client
PLAY_RESOURCE_PACK_SEND = 0x48  # server -> client (hash, url)
PLAY_PLUGIN_MESSAGE = 0x3F      # server -> client
PLAY_DISCONNECT = 0x40
# Client -> server: the single "Client Status" packet carries the player's
# decision on the resource pack prompt.  In 1.8 the status byte is
# 0 = DECLINED, 1 = ACCEPTED, 2 = ACKNOWLEDGED (only for downloads started
# by the server, not for the initial prompt).
CLIENT_STATUS = 0x02
CLIENT_STATUS_DECLINED = 0
CLIENT_STATUS_ACCEPTED = 1
CLIENT_STATUS_ACKNOWLEDGED = 2

CLIENT_PLAYER = 0x03            # client -> server (on-ground flag only)
CLIENT_PLAYER_POSITION = 0x04
CLIENT_PLAYER_LOOK = 0x05
CLIENT_PLAYER_POSITION_LOOK = 0x06
CLIENT_HELD_ITEM_CHANGE = 0x09
CLIENT_CONFIRM_TRANSACTION = 0x0F
CLIENT_PLUGIN_MESSAGE = 0x17    # client -> server

# "Injected message" frames from the client (the path skins/extension messages
# take since v5) start with 0xEE and are not vanilla packets
INJECTED_FRAME_MARKER = 0xEE

# All of Eaglercraft's own extensions travel over plugin-message channels; these
# are the two prefixes
EAGLER_CHANNEL_PREFIXES = ('EAG|', 'eagler:')


class ProtocolError(Exception):
    """The byte stream does not follow the vanilla packet format."""


class NeedMoreData(ProtocolError):
    """Not enough data yet; keep receiving.

    A subclass of ProtocolError on purpose: when parsing an "already complete
    packet" and running out of bytes, the packet itself is truncated (malformed),
    so callers may handle it as a protocol error; only streaming parsers need to
    tell the two situations apart.
    """


def write_varint(value: int) -> bytes:
    if value < 0:
        value &= 0xFFFFFFFF
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def read_varint(data: bytes, pos: int = 0) -> tuple[int, int]:
    """Read a VarInt, returning (value, new position). Raises NeedMoreData when the data is short."""
    value = 0
    for index in range(5):
        if pos >= len(data):
            raise NeedMoreData()
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << (7 * index)
        if not byte & 0x80:
            return value, pos
    raise ProtocolError(tr('vanilla.error.varint_too_long'))


def read_string(data: bytes, pos: int = 0) -> tuple[str, int]:
    """Read a UTF-8 string prefixed with a VarInt length."""
    length, pos = read_varint(data, pos)
    if length < 0 or pos + length > len(data):
        raise NeedMoreData()
    return data[pos:pos + length].decode('utf-8', 'replace'), pos + length


def read_u16(data: bytes, pos: int = 0) -> tuple[int, int]:
    if pos + 2 > len(data):
        raise NeedMoreData()
    return int.from_bytes(data[pos:pos + 2], 'big'), pos + 2


def write_string(text: str) -> bytes:
    """Encode a string with its VarInt length prefix (the inverse of read_string)."""
    raw = str(text).encode('utf-8')
    return write_varint(len(raw)) + raw


def pack(packet_id: int, body: bytes = b'') -> bytes:
    """Build one complete uncompressed frame (length prefix + packet id + body)."""
    payload = write_varint(packet_id) + body
    return write_varint(len(payload)) + payload


@dataclass
class Packet:
    """A decoded vanilla packet."""

    packet_id: int
    body: bytes        # content after the packet id
    payload: bytes     # packet id + content (uncompressed form)


class Decoder:
    """Incrementally parse one direction of a byte stream.

    Note: the compression threshold can change in the middle of the stream (after
    the server sends Set Compression), so treating ``feed`` as a batch helper is
    not safe -- whenever a threshold change is possible, use ``push`` +
    ``next_packet`` one packet at a time so that an updated threshold applies to
    new packets immediately.
    """

    def __init__(self, threshold: int = 0):
        # A read from the target often contains many packets.  Keeping unread
        # bytes behind an offset avoids copying the tail of the buffer for every
        # packet (the old ``buffer = buffer[end:]`` was quadratic on a burst).
        self.buffer = bytearray()
        self._pos = 0
        self.threshold = threshold

    @property
    def pending(self) -> int:
        """Number of bytes that still belong to the current/next packet."""
        return len(self.buffer) - self._pos

    def push(self, data: bytes) -> None:
        if not data:
            return
        if self._pos:
            if self._pos >= len(self.buffer):
                self.buffer.clear()
            else:
                del self.buffer[:self._pos]
            self._pos = 0
        self.buffer.extend(data)

    def feed(self, data: bytes) -> list[Packet]:
        self.push(data)
        packets: list[Packet] = []
        while True:
            packet = self.next_packet()
            if packet is None:
                return packets
            packets.append(packet)

    def next_packet(self) -> Packet | None:
        """Take the next complete packet; return None when more data is needed
        (it stays in the buffer for the next call)."""
        buffer = self.buffer
        start = self._pos
        try:
            length, pos = read_varint(buffer, start)
        except NeedMoreData:
            return None
        if length <= 0 or length > MAX_PACKET_BYTES:
            raise ProtocolError(tr('vanilla.error.bad_packet_length', length=length))
        end = pos + length
        if len(buffer) < end:
            return None
        body = bytes(buffer[pos:end])
        self._pos = end
        if end == len(buffer):
            # The read is fully consumed: release it instead of carrying a dead
            # prefix until the next push.
            buffer.clear()
            self._pos = 0
        if self.threshold > 0:
            try:
                uncompressed, offset = read_varint(body, 0)
            except NeedMoreData:
                raise ProtocolError(tr('vanilla.error.missing_uncompressed_length'))
            payload = body[offset:]
            if uncompressed > 0:
                try:
                    payload = zlib.decompress(payload)
                except zlib.error as exc:
                    raise ProtocolError(tr('vanilla.error.zlib_failed', error=exc))
                if len(payload) != uncompressed:
                    raise ProtocolError(tr('vanilla.error.decompressed_length_mismatch',
                                           actual=len(payload), declared=uncompressed))
        else:
            payload = body
        try:
            packet_id, at = read_varint(payload, 0)
        except NeedMoreData:
            raise ProtocolError(tr('vanilla.error.missing_packet_id'))
        return Packet(packet_id, payload[at:], payload)


class Encoder:
    """Reframe packets with the negotiated compression threshold."""

    def __init__(self, threshold: int = 0):
        self.threshold = threshold

    def frame(self, payload: bytes) -> bytes:
        if self.threshold > 0:
            if len(payload) >= self.threshold:
                body = write_varint(len(payload)) + zlib.compress(payload)
            else:
                body = write_varint(0) + payload
        else:
            body = payload
        return write_varint(len(body)) + body
