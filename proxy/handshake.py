"""Parsing of the Minecraft handshake packet and optional address rewriting.

The proxy itself does not process the protocol; this module only touches the
**first upstream packet** (the handshake) to do two things:

* parse the protocol version / server address the client typed / port / next
  state into the log -- when investigating "kicked right after connecting",
  this one line is usually the answer;
* when the user explicitly enables handshake address rewriting, replace the
  address inside the handshake with the real target domain -- browser-based
  clients tend to put the local address (127.0.0.1:8443) in there, and some
  servers validate it or route by domain, which shows up as "closed right
  after connecting".

When parsing fails (the data is not a handshake, was split across packets,
and so on) everything is forwarded untouched -- no guessing.
"""

from __future__ import annotations

from .i18n import tr

# Next State value -> translation key; resolved at call time because the
# active language can change while the program runs.
NEXT_STATE_KEYS = {
    1: 'handshake.state_status',
    2: 'handshake.state_login',
    3: 'handshake.state_transfer',
}


def next_state_name(state: int) -> str:
    """Human-readable name of a handshake Next State value, in the active language."""
    key = NEXT_STATE_KEYS.get(state)
    if key is None:
        return tr('handshake.state_unknown', state=state)
    return tr(key)


def read_varint(data: bytes, pos: int = 0) -> tuple[int, int]:
    """Read one VarInt; returns (value, new position)."""
    value = 0
    for index in range(5):
        if pos >= len(data):
            raise ValueError(tr('handshake.varint_incomplete'))
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << (7 * index)
        if not byte & 0x80:
            return value, pos
    raise ValueError(tr('handshake.varint_too_long'))


def write_varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def read_string(data: bytes, pos: int) -> tuple[str, int]:
    length, pos = read_varint(data, pos)
    text = data[pos:pos + length].decode('utf-8', 'replace')
    return text, pos + length


def packet_size(data: bytes) -> int | None:
    """Full length of the first packet (including its length prefix); None when there are too few bytes to read the prefix."""
    try:
        packet_length, pos = read_varint(data, 0)
    except ValueError:
        return None
    return packet_length + pos


def looks_like_handshake(data: bytes, max_packet: int = 2048,
                         max_protocol: int = 2000) -> bool:
    """Decide whether the start of the data looks like a handshake packet that has not fully arrived yet.

    Checking the length prefix alone is not enough -- the first byte of any
    game data could be read as a valid length and the buffer would be cached
    by mistake.  The packet id must be 0x00 and the protocol version and
    address length must be in a plausible range before the data is treated
    as an incomplete handshake.  If any check fails the function returns
    False (forward immediately).
    """
    try:
        packet_length, pos = read_varint(data, 0)
    except ValueError:
        return False
    if not 0 < packet_length <= max_packet or len(data) <= pos:
        return False
    try:
        packet_id, pos = read_varint(data, pos)
    except ValueError:
        return False
    if packet_id != 0x00:
        return False
    if len(data) <= pos:
        return True                       # there is a length and the packet id is 0, cache it as a handshake
    try:
        protocol, pos = read_varint(data, pos)
    except ValueError:
        return False
    if not 0 <= protocol <= max_protocol:
        return False
    if len(data) <= pos:
        return True
    try:
        address_length, _ = read_varint(data, pos)
    except ValueError:
        return False
    return 0 <= address_length <= 255


def hex_preview(data: bytes, limit: int = 64) -> str:
    """Hexadecimal preview for the log."""
    chunk = data[:limit]
    text = ' '.join('%02x' % byte for byte in chunk)
    if len(data) > limit:
        text += tr('handshake.hex_more', count=len(data))
    return text


def parse_handshake(data: bytes) -> dict | None:
    """Parse the upstream data as a handshake packet; None when it is not one or is incomplete."""
    try:
        packet_length, pos = read_varint(data, 0)
        if not 0 < packet_length <= len(data) - pos:
            return None
        packet_id, pos = read_varint(data, pos)
        if packet_id != 0x00:
            return None
        protocol, pos = read_varint(data, pos)
        address, pos = read_string(data, pos)
        if pos + 2 > len(data):
            return None
        port = int.from_bytes(data[pos:pos + 2], 'big')
        pos += 2
        next_state, pos = read_varint(data, pos)
    except (ValueError, IndexError):
        return None
    return {
        'packet_length': packet_length,
        'protocol': protocol,
        'address': address,
        'port': port,
        'next_state': next_state,
        'next_state_name': next_state_name(next_state),
        'consumed': pos,       # number of bytes the handshake occupies inside data
    }


def rewrite_handshake(data: bytes, address: str, port: int | None = None) -> bytes | None:
    """Replace the server address (and port) inside the handshake with new values.

    Returns the complete rewritten data (including any packets that follow);
    returns None when parsing fails, leaving it to the caller to decide
    whether to forward the data untouched.
    """
    try:
        packet_length, pos = read_varint(data, 0)
        if not 0 < packet_length <= len(data) - pos:
            return None
        packet_id, pos = read_varint(data, pos)
        if packet_id != 0x00:
            return None
        protocol, pos = read_varint(data, pos)
        _old_address, pos = read_string(data, pos)
        if pos + 2 > len(data):
            return None
        old_port = int.from_bytes(data[pos:pos + 2], 'big')
        pos += 2
        next_state, pos = read_varint(data, pos)
        rest = data[pos:]
        encoded = address.encode('utf-8')
        body = (write_varint(packet_id) + write_varint(protocol)
                + write_varint(len(encoded)) + encoded
                + (old_port if port is None else port).to_bytes(2, 'big')
                + write_varint(next_state))
        return write_varint(len(body)) + body + rest
    except (ValueError, IndexError):
        return None


def describe_handshake(info: dict) -> str:
    return tr('handshake.describe', protocol=info['protocol'], address=info['address'],
              port=info['port'], next_state=info['next_state_name'])
