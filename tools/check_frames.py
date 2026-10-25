"""Read proxy return data the way a real EaglercraftX client does, to verify "one frame = one vanilla packet".

Usage:
    py -X utf8 tools\\check_frames.py
    py -X utf8 tools\\check_frames.py --url wss://127.0.0.1:1000 --seconds 20

Why this tool exists: when the browser-side client reads WebSocket frames it takes the **first
byte of the frame as the packet id directly** -- frames carry neither the vanilla [VarInt packet
length] prefix nor compression. The proxy must therefore "send one packet per frame, and the frame
contains the bare packet". This tool strictly validates every returning frame against that rule:

* the packet id must be a valid id for the 1.8 clientbound direction;
* the packet body must be consumed exactly (no bytes left over, none missing);
* a Set Compression during the play phase counts as an immediate failure (the client does not
  support compression at all).

Any "unknown packet id" or "structure mismatch" means framing is broken again -- the client will
hang on the loading screen.

Exit code: 0 = everything valid; 1 = suspicious data found.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import ssl
import struct
import sys
import threading
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from proxy import eagler, vanilla, wsproto       # noqa: E402
from proxy.config import Config                   # noqa: E402


# ---------------------------------------------------------------- data reader



# clientbound (1.8.8) packet id -> (name, strict parser function)
# The parser must consume exactly the whole frame; any leftover bytes mean the framing is wrong
PARSERS = {
    0x00: ('KeepAlive', lambda r: r.varint()),
    0x01: ('JoinGame', lambda r: (r.i32(), r.u8(), r.i8(), r.u8(), r.u8(),
                                  r.string(), r.boolean())),
    0x02: ('ChatMessage', lambda r: (r.string(), r.u8())),
    0x03: ('TimeUpdate', lambda r: (r.i64(), r.i64())),
    0x05: ('SpawnPosition', lambda r: r.i64()),
    0x06: ('UpdateHealth', lambda r: (r.f32(), r.varint(), r.f32())),
    0x07: ('Respawn', lambda r: (r.i32(), r.u8(), r.u8(), r.string())),
    0x08: ('PlayerPositionAndLook', lambda r: (r.f64(), r.f64(), r.f64(),
                                               r.f32(), r.f32(), r.u8())),
    0x09: ('HeldItemChange', lambda r: r.i8()),
    0x0B: ('Animation', lambda r: (r.varint(), r.u8())),
    0x0D: ('CollectItem', lambda r: (r.varint(), r.varint(), r.varint())),
    0x12: ('EntityVelocity', lambda r: (r.varint(), r.i16(), r.i16(), r.i16())),
    0x13: ('DestroyEntities', lambda r: [r.varint() for _ in range(r.varint())]),
    0x14: ('Entity', lambda r: r.varint()),
    0x15: ('EntityRelativeMove', lambda r: (r.varint(), r.i8(), r.i8(), r.i8())),
    0x16: ('EntityLook', lambda r: (r.varint(), r.i8(), r.i8())),
    0x17: ('EntityLookAndRelativeMove', lambda r: (r.varint(), r.i8(), r.i8(), r.i8(),
                                                   r.i8(), r.i8())),
    0x18: ('EntityTeleport', lambda r: (r.varint(), r.i32(), r.i32(), r.i32(),
                                        r.i8(), r.i8(), r.boolean())),
    0x19: ('EntityHeadLook', lambda r: (r.varint(), r.i8())),
    0x1A: ('EntityStatus', lambda r: (r.i32(), r.i8())),
    0x1B: ('AttachEntity', lambda r: (r.i32(), r.i32(), r.boolean())),
    0x1D: ('EntityEffect', lambda r: (r.varint(), r.u8(), r.u8(), r.varint(), r.u8())),
    0x1E: ('RemoveEntityEffect', lambda r: (r.varint(), r.u8())),
    0x1F: ('SetExperience', lambda r: (r.f32(), r.varint(), r.varint())),
    0x20: ('EntityProperties', lambda r: _entity_properties(r)),
    0x21: ('ChunkData', lambda r: _chunk_data(r)),
    0x22: ('MultiBlockChange', lambda r: (r.i32(), r.i32(), r.u16(), r.rest())),
    0x23: ('BlockChange', lambda r: (r.i64(), r.varint())),
    0x25: ('BlockBreakAnimation', lambda r: (r.varint(), r.i64(), r.i8())),
    0x26: ('MapChunkBulk', lambda r: _map_chunk_bulk(r)),
    0x27: ('Explosion', lambda r: _explosion(r)),
    0x28: ('Effect', lambda r: (r.i32(), r.i64(), r.i32(), r.boolean())),
    0x29: ('SoundEffect', lambda r: (r.string(), r.i32(), r.i32(), r.i32(),
                                     r.f32(), r.f32())),
    0x2A: ('Particle', lambda r: _particle(r)),
    0x2B: ('ChangeGameState', lambda r: (r.u8(), r.f32())),
    0x2C: ('SpawnGlobalEntity', lambda r: (r.varint(), r.u8(), r.i32(), r.i32(), r.i32())),
    0x2D: ('OpenWindow', lambda r: (r.u8(), r.string(), r.string(), r.u8())),
    0x2E: ('CloseWindow', lambda r: r.u8()),
    0x31: ('WindowProperty', lambda r: (r.u8(), r.i16(), r.i16())),
    0x32: ('ConfirmTransaction', lambda r: (r.i8(), r.i16(), r.boolean())),
    0x33: ('UpdateSign', lambda r: (r.i64(), r.string(), r.string(), r.string(), r.string())),
    0x36: ('OpenSignEditor', lambda r: r.i64()),
    0x38: ('PlayerListItem', lambda r: _player_list_item(r)),
    0x39: ('PlayerAbilities', lambda r: (r.u8(), r.f32(), r.f32())),
    0x3B: ('ScoreboardObjective', lambda r: _scoreboard_objective(r)),
    0x3C: ('UpdateScore', lambda r: (r.string(), r.u8(), r.string(), r.varint())),
    0x3D: ('DisplayScoreboard', lambda r: (r.i8(), r.string())),
    0x3F: ('PluginMessage', lambda r: (r.string(), r.rest())),
    0x40: ('Disconnect', lambda r: r.string()),
    0x41: ('ServerDifficulty', lambda r: r.u8()),
    0x42: ('CombatEvent', lambda r: _combat_event(r)),
    0x43: ('Camera', lambda r: r.varint()),
    0x46: ('SetCompression', lambda r: r.varint()),
    0x47: ('PlayerListHeaderFooter', lambda r: (r.string(), r.string())),
    0x48: ('ResourcePackSend', lambda r: (r.string(), r.string())),
}

# valid ids whose structure is too verbose to parse here (NBT / metadata); only the id is checked
LOOSE_IDS = {
    0x04: 'EntityEquipment', 0x0A: 'UseBed', 0x0C: 'SpawnPlayer',
    0x0E: 'SpawnObject', 0x0F: 'SpawnMob', 0x10: 'SpawnPainting',
    0x11: 'SpawnExperienceOrb', 0x1C: 'EntityMetadata', 0x24: 'BlockAction',
    0x2F: 'SetSlot', 0x30: 'WindowItems', 0x31: 'WindowProperty',
    0x34: 'Map', 0x35: 'UpdateBlockEntity', 0x36: 'OpenSignEditor',
    0x37: 'Statistics', 0x3A: 'TabComplete', 0x3E: 'Teams',
    0x44: 'WorldBorder', 0x45: 'Title', 0x49: 'UpdateEntityNBT',
}

PLAY_MAX_ID = 0x49


















def check_frame(frame: bytes) -> tuple[str, str]:
    """Validate one frame; return (result, detail). result: ok / loose / bad."""
    if not frame:
        return 'bad', 'empty frame'
    try:
        packet_id, at = vanilla.read_varint(frame, 0)
    except vanilla.ProtocolError as exc:
        return 'bad', 'frame does not start with a valid packet id: %s' % exc
    if packet_id > PLAY_MAX_ID:
        return 'bad', ('packet id 0x%02x is beyond the 1.8 play range (max 0x49), '
                       'so the frame carries a length prefix' % packet_id)
    body = frame[at:]
    if packet_id in LOOSE_IDS:
        return 'loose', LOOSE_IDS[packet_id]
    entry = PARSERS.get(packet_id)
    if entry is None:
        return 'bad', 'packet id 0x%02x does not exist in the 1.8 clientbound direction' % packet_id
    name, parse = entry
    reader = Reader(body)
    try:
        parse(reader)
    except Exception as exc:
        return 'bad', '%s structure mismatch: %s' % (name, exc)
    if reader.left() != 0:
        return 'bad', ('%s parsed with %d bytes left (frame is %d bytes): %s'
                       % (name, reader.left(), len(frame), reader.rest()[:16].hex(' ')))
    return 'ok', name


# ---------------------------------------------------------------- minimal WebSocket client

class MiniWs:
    """Just enough WebSocket client (masks outgoing frames, reads server frames)."""

    def __init__(self, url: str, timeout: float = 10.0):
        parsed = urlparse(url)
        secure = parsed.scheme in ('wss', 'https')
        host = parsed.hostname or '127.0.0.1'
        port = parsed.port or (443 if secure else 80)
        path = parsed.path or '/'
        if parsed.query:
            path += '?' + parsed.query
        sock = socket.create_connection((host, port), timeout=timeout)
        if secure:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            sock = context.wrap_socket(sock, server_hostname=host)
        sock.settimeout(timeout)
        key = base64.b64encode(os.urandom(16)).decode('ascii')
        request = ('GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\n'
                   'Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n'
                   'Sec-WebSocket-Version: 13\r\n\r\n'
                   % (path, host, port, key))
        sock.sendall(request.encode('ascii'))
        head = b''
        while b'\r\n\r\n' not in head:
            chunk = sock.recv(4096)
            if not chunk:
                raise RuntimeError('connection closed during the WebSocket handshake')
            head += chunk
        first_line = head.split(b'\r\n', 1)[0].decode('latin-1')
        if '101' not in first_line:
            raise RuntimeError('WebSocket handshake failed: %s' % first_line)
        self.sock = sock
        self.decoder = wsproto.FrameDecoder()
        self.inbox: list[wsproto.Frame] = []
        self.closed: tuple[int, str] | None = None
        self.eof = False
        self._pending = head.split(b'\r\n\r\n', 1)[1]
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()

    def _reader(self) -> None:
        try:
            while True:
                chunk = self._pending or self.sock.recv(65536)
                self._pending = b''
                if not chunk:
                    self.eof = True
                    return
                for frame in self.decoder.feed(chunk):
                    with self._lock:
                        if frame.opcode == wsproto.OP_CLOSE:
                            self.closed = wsproto.parse_close_payload(frame.payload)
                        elif frame.opcode in (wsproto.OP_BINARY, wsproto.OP_TEXT):
                            self.inbox.append(frame)
        except (OSError, ssl.SSLError):
            self.eof = True

    def send(self, data: bytes) -> None:
        self.sock.sendall(wsproto.encode_frame(wsproto.OP_BINARY, data, mask=True))

    def recv(self, timeout: float = 5.0) -> bytes | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if self.inbox:
                    return self.inbox.pop(0).payload
            time.sleep(0.01)
        return None

    def close(self) -> None:
        try:
            self.sock.sendall(wsproto.encode_frame(
                wsproto.OP_CLOSE, wsproto.close_payload(1000, 'bye'), mask=True))
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


# ---------------------------------------------------------------- client handshake packets

def client_version_packet(username: str) -> bytes:
    out = bytearray([eagler.PROTOCOL_CLIENT_VERSION, 0x02])
    out += (3).to_bytes(2, 'big')                  # 3 handshake protocols supported
    for item in (3, 4, 5):
        out += item.to_bytes(2, 'big')
    out += (1).to_bytes(2, 'big') + (47).to_bytes(2, 'big')
    for text in ('EaglercraftX', 'u53'):
        out += bytes([len(text)]) + text.encode('ascii')
    out.append(0)                                  # no password
    out += bytes([len(username)]) + username.encode('ascii')
    return bytes(out)


def request_login_packet(username: str) -> bytes:
    out = bytearray([eagler.PROTOCOL_CLIENT_REQUEST_LOGIN])
    for field in (username.encode('ascii'), b'default', b''):
        out += bytes([len(field)]) + field
    out += bytes([0, 0])                           # no cookie
    out += eagler._varint(0)                       # standardCaps
    out.append(0)                                  # extCaps count
    return bytes(out)


def keep_alive_reply(packet_id_value: int) -> bytes:
    return vanilla.write_varint(vanilla.PLAY_KEEP_ALIVE) + vanilla.write_varint(packet_id_value)


def client_settings() -> bytes:
    locale = b'zh_CN'
    return (vanilla.write_varint(0x15)
            + vanilla.write_varint(len(locale)) + locale
            + bytes([8, 0, 1, 0x7F]))              # view distance / chat / colors / skin parts


def brand_plugin_message(brand: str = 'EaglercraftX') -> bytes:
    channel = b'MC|Brand'
    return (vanilla.write_varint(vanilla.CLIENT_PLUGIN_MESSAGE)
            + vanilla.write_varint(len(channel)) + channel
            + vanilla.write_varint(len(brand)) + brand.encode('ascii'))


# ---------------------------------------------------------------- main flow

def default_url() -> str:
    try:
        config = Config.load()
    except Exception:
        return 'wss://127.0.0.1:1000'
    if config.tls_enabled and int(config.wss_port) > 0:
        return 'wss://127.0.0.1:%d' % int(config.wss_port)
    if int(config.ws_port) > 0:
        return 'ws://127.0.0.1:%d' % int(config.ws_port)
    return 'wss://127.0.0.1:1000'


def main() -> int:
    parser = argparse.ArgumentParser(description='verify that proxy return data is "one frame per vanilla packet"')
    parser.add_argument('--url', default=None, help='proxy listen address (default: read from config.json)')
    parser.add_argument('--seconds', type=float, default=20.0, help='how long to capture (default 20 s)')
    parser.add_argument('--username', default='ProxyCheck', help='login name to use')
    parser.add_argument('--no-play', action='store_true', help='do not send play packets like a client')
    args = parser.parse_args()

    url = args.url or default_url()
    print('connecting to %s (username %s)' % (url, args.username))
    client = None
    last_error: Exception | None = None
    deadline = time.time() + 10.0
    while client is None and time.time() < deadline:
        try:
            client = MiniWs(url)
        except Exception as exc:          # the proxy may have just started, retry for a bit
            last_error = exc
            time.sleep(0.5)
    if client is None:
        print('cannot reach the proxy: %s' % last_error)
        print('(make sure the proxy is running and the address/port match)')
        return 1

    try:
        client.send(client_version_packet(args.username))
        frame = client.recv(8.0)
        if frame is None:
            print('no server version packet received')
            return 1
        if frame[0] != eagler.PROTOCOL_SERVER_VERSION:
            print('first response is not a server version packet (0x%02x)' % frame[0])
            return 1
        protocol = int.from_bytes(frame[1:3], 'big')
        game = int.from_bytes(frame[3:5], 'big')
        print('server version packet: handshake v%d / game protocol %d' % (protocol, game))

        client.send(request_login_packet(args.username))
        frame = client.recv(10.0)
        if frame is None:
            print('no allow-login packet received')
            return 1
        if frame[0] == eagler.PROTOCOL_SERVER_DENY_LOGIN:
            length = int.from_bytes(frame[1:3], 'big')
            print('server denied login: %s' % frame[3:3 + length].decode('utf-8', 'replace'))
            return 1
        if frame[0] != eagler.PROTOCOL_SERVER_ALLOW_LOGIN:
            print('second response is not an allow-login packet (0x%02x)' % frame[0])
            return 1
        print('login allowed')

        client.send(bytes([eagler.PROTOCOL_CLIENT_FINISH_LOGIN]))
        frame = client.recv(10.0)
        if frame is None or frame[0] != eagler.PROTOCOL_SERVER_FINISH_LOGIN:
            print('no finish-login packet received')
            return 1
        print('login finished, validating play data (one frame must be one complete 1.8 packet)\n')

        sent_play = False
        bad: list[str] = []
        ok_count = loose_count = 0
        names: Counter[str] = Counter()
        first_names: list[str] = []
        deadline = time.time() + args.seconds
        while time.time() < deadline and client.closed is None:
            frame = client.recv(0.5)
            if frame is None:
                continue
            result, detail = check_frame(frame)
            if result == 'bad':
                if len(bad) < 8:
                    bad.append('%s | frame bytes: %s' % (detail, frame[:24].hex(' ')))
                continue
            if result == 'loose':
                loose_count += 1
            else:
                ok_count += 1
            names[detail] += 1
            if len(first_names) < 12:
                first_names.append(detail)
            if detail == 'KeepAlive' and not args.no_play:
                reader = Reader(frame)
                reader.varint()
                client.send(keep_alive_reply(reader.varint()))
            if not sent_play and not args.no_play and detail == 'JoinGame':
                client.send(client_settings())
                client.send(brand_plugin_message())
                sent_play = True

        print('packet sequence (first 12): %s' % ', '.join(first_names))
        print('strictly valid %d, id-only %d, suspicious %d'
              % (ok_count, loose_count, len(bad)))
        print('per-packet counts: %s' % ', '.join('%s x %d' % (name, count)
                                                  for name, count in names.most_common(20)))
        if 'SetCompression' in names:
            print('!! Set Compression appeared during the play phase; the client does not support compression, this is wrong')
        if bad:
            print('\nsuspicious frames:')
            for line in bad:
                print('  - %s' % line)
        if client.closed is not None:
            code, reason = client.closed
            print('\nconnection closed: code=%d %s' % (code, reason))
        if ok_count == 0:
            print('\nno packets received at all -- the target server may not be sending play data, '
                  'or the proxy has not reached the play phase yet')
        if bad or 'SetCompression' in names:
            print('\nverdict: framing is still broken (the client will hang on the loading screen)')
            return 1
        print('\nverdict: all return data is "one frame, one bare packet"; the client can parse it')
        return 0
    finally:
        client.close()


if __name__ == '__main__':
    sys.exit(main())

# Reader and the per-packet readers live in check_frames_reader (split for size).
from check_frames_reader import Reader  # noqa: F401
