"""Tests for the protocol translation layer: vanilla packet codec / EaglercraftX
handshake / state machine / end-to-end.

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import socket
import struct
import sys
import threading
import time
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from proxy import crypto, eagler, vanilla, wsproto, x509  # noqa: E402
from proxy import accounts  # noqa: E402
from proxy.config import Config  # noqa: E402
from proxy import i18n  # noqa: E402
from proxy.i18n import tr  # noqa: E402
from proxy.logger import NullLogger  # noqa: E402
import proxy.proxy as proxy_core  # noqa: E402
from proxy.proxy import Bridge, ProxyServer  # noqa: E402
from proxy.eagler import chat_passthrough  # noqa: E402
from proxy.translator import EaglerTranslator, chat_to_text  # noqa: E402
from test_all import WsClient, connect_ws, free_port  # noqa: E402

# First data packet observed from a real browser client (37 bytes), kept as a regression sample
REAL_FIRST_PACKET = bytes.fromhex(
    '010200030003000400050001002f0c') + b'EaglercraftX' + bytes.fromhex('03753533') + bytes.fromhex(
    '00') + bytes.fromhex('04') + b'nopp'


# ---------------------------------------------------------------- Building handshake packets


def build_client_version(handshake_protocols=(3, 4, 5), mc_protocols=(47,),
                         brand='EaglercraftX', version='u53',
                         auth=False, auth_user=b'nopp') -> bytes:
    out = bytearray([0x01, 0x02])
    out += len(handshake_protocols).to_bytes(2, 'big')
    for item in handshake_protocols:
        out += item.to_bytes(2, 'big')
    out += len(mc_protocols).to_bytes(2, 'big')
    for item in mc_protocols:
        out += item.to_bytes(2, 'big')
    out += bytes([len(brand)]) + brand.encode()
    out += bytes([len(version)]) + version.encode()
    out.append(1 if auth else 0)
    out += bytes([len(auth_user)]) + auth_user
    return bytes(out)


def build_request_login(username='Tester', server='wss://127.0.0.1:1000',
                        password=b'', version=5, cookie=None, caps=0) -> bytes:
    out = bytearray([eagler.PROTOCOL_CLIENT_REQUEST_LOGIN])
    for field in (username.encode(), server.encode(), password):
        out += bytes([len(field)]) + field
    if version >= 4:
        data = cookie or b''
        out += bytes([1 if cookie is not None else 0])
        out += bytes([len(data)]) + data
    if version >= 5:
        out += eagler._varint(caps)
        for _ in range(bin(caps).count('1')):     # every supported capability bit is followed by a version number
            out += eagler._varint(1)
        out.append(0)
    return bytes(out)


def build_login_success(username='Tester', uuid_text=None) -> bytes:
    if uuid_text is None:
        raw = eagler.offline_uuid(username).hex()
        uuid_text = '%s-%s-%s-%s-%s' % (raw[:8], raw[8:12], raw[12:16], raw[16:20], raw[20:])
    body = (vanilla.write_varint(len(uuid_text)) + uuid_text.encode()
            + vanilla.write_varint(len(username)) + username.encode())
    return vanilla.pack(vanilla.LOGIN_SUCCESS, body)


def build_disconnect(message: str) -> bytes:
    text = json.dumps({'text': message})
    body = vanilla.write_varint(len(text.encode())) + text.encode()
    return vanilla.pack(vanilla.LOGIN_DISCONNECT, body)


def build_play_disconnect(raw_text: str) -> bytes:
    body = vanilla.write_string(raw_text)
    return vanilla.pack(vanilla.PLAY_DISCONNECT, body)


def read_eagler_string(data: bytes, pos: int):
    length = data[pos]
    return data[pos + 1:pos + 1 + length].decode('utf-8', 'replace'), pos + 1 + length


def unframed(frame: bytes) -> bytes:
    """Strip the length prefix, yielding "packet id + body" (i.e. Packet.payload)."""
    _, pos = vanilla.read_varint(frame, 0)
    return frame[pos:]


def rsa_decrypt(key: dict, data: bytes) -> bytes:
    """Test helper: decrypt a PKCS#1 v1.5 ciphertext with the private key."""
    size = (key['n'].bit_length() + 7) // 8
    block = pow(int.from_bytes(data, 'big'), key['d'], key['n']).to_bytes(size, 'big')
    if block[:2] != b'\x00\x02':
        raise AssertionError('bad PKCS#1 v1.5 padding header: %s' % block[:2].hex())
    return block[block.index(b'\x00', 2) + 1:]


def build_encryption_request(key: dict, token=b'\x11\x22\x33\x44',
                             server_id='serverid') -> bytes:
    """Build an encryption request packet in vanilla wire format."""
    spki = x509.subject_public_key_info(key)
    body = (vanilla.write_varint(len(server_id)) + server_id.encode()
            + vanilla.write_varint(len(spki)) + spki
            + vanilla.write_varint(len(token)) + token)
    return vanilla.pack(vanilla.LOGIN_ENCRYPTION_REQUEST, body)


class FakeVanillaServer:
    """A fake server that speaks the vanilla 1.8 protocol."""

    def __init__(self, threshold=None, encryption=False, kick=None,
                 play_packets=(), greet_delay=0.0, modern=False):
        self.threshold = threshold
        self.encryption = encryption
        self.kick = kick
        self.play_packets = list(play_packets)
        self.greet_delay = greet_delay
        # "modern" emulates a 1.20.2+ target: Login Success, then nothing is
        # sent until the login acknowledge arrives, and anything that arrives
        # before it drops the connection (the join-kicked-instantly bug)
        self.modern = modern
        self.acked = False
        self.dropped_early = False
        self.after_ack: list = []
        self.received = bytearray()
        self.handshake_address = ''
        self.handshake_protocol = 0
        self.username = ''
        self._conn: socket.socket | None = None
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(('127.0.0.1', 0))
        self._server.listen(4)
        self.port = self._server.getsockname()[1]
        self._stop = False
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        self._server.settimeout(0.3)
        while not self._stop:
            try:
                conn, _ = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            self._conn = conn
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        conn.settimeout(10)
        try:
            decoder = vanilla.Decoder(0)
            handshake_done = False
            while True:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                for packet in decoder.feed(chunk):
                    if not handshake_done:
                        handshake_done = True
                        protocol, pos = vanilla.read_varint(packet.body, 0)
                        self.handshake_protocol = protocol
                        address, pos = vanilla.read_string(packet.body, pos)
                        self.handshake_address = address
                        pos += 2                         # server port
                        next_state, _pos = vanilla.read_varint(packet.body, pos)
                        if next_state == 1:
                            # A server-list status probe, not a player login:
                            # answer with a disconnect and stop this connection.
                            conn.close()
                            return
                        continue
                    if packet.packet_id == 0x00 and not self.username:
                        username, _ = vanilla.read_string(packet.body, 0)
                        self.username = username
                        if self.modern:
                            # 1.20.2+ layout: the name is followed by the UUID;
                            # answer with Login Success and then wait for the
                            # acknowledge before doing anything else
                            conn.sendall(vanilla.pack(
                                vanilla.LOGIN_SUCCESS,
                                eagler.offline_uuid(username) + vanilla.write_string(username)))
                            continue
                        self._after_login(conn)
                        return
                    if self.modern:
                        if not self.acked:
                            if (packet.packet_id == vanilla.LOGIN_ACKNOWLEDGED
                                    and not packet.body):
                                self.acked = True
                                payload = b''.join(vanilla.Encoder(0).frame(item)
                                                   for item in self.play_packets)
                                if payload:
                                    conn.sendall(payload)
                                continue
                            self.dropped_early = True
                            conn.close()
                            return
                        self.after_ack.append(packet)
        except OSError:
            return

    def _after_login(self, conn: socket.socket) -> None:
        if self.greet_delay:
            time.sleep(self.greet_delay)
        if self.kick is not None:
            conn.sendall(build_disconnect(self.kick))
            return
        if self.encryption:
            conn.sendall(vanilla.pack(vanilla.LOGIN_ENCRYPTION_REQUEST,
                                      vanilla.write_varint(7) + b'serverid'))
            return
        if self.threshold:
            # Real servers often squeeze the remaining handshake packets into one
            # TCP segment; packets after Set Compression must be parsed with the
            # new threshold already active.
            head = vanilla.pack(vanilla.LOGIN_SET_COMPRESSION, vanilla.write_varint(self.threshold))
        else:
            head = b''
        encoder = vanilla.Encoder(self.threshold or 0)
        conn.sendall(head + encoder.frame(unframed(build_login_success(self.username))))
        payload = b''
        for packet in self.play_packets:
            payload += encoder.frame(packet)
        if payload:
            conn.sendall(payload)

    def send_play(self, payload: bytes) -> None:
        self._conn.sendall(vanilla.Encoder(self.threshold or 0).frame(payload))

    def read_packets(self, count: int, timeout: float = 5.0):
        """Read count packets under the negotiated compression rules (returns
        as soon as that many have arrived, regardless of TCP chunking)."""
        assert self._conn is not None
        self._conn.settimeout(timeout)
        decoder = vanilla.Decoder(self.threshold or 0)
        packets = []
        deadline = time.time() + timeout
        while len(packets) < count and time.time() < deadline:
            try:
                chunk = self._conn.recv(65536)
            except socket.timeout:
                break
            if not chunk:
                break
            self.received.extend(chunk)
            packets.extend(decoder.feed(chunk))
        return packets

    def close(self) -> None:
        self._stop = True
        try:
            self._server.close()
        except OSError:
            pass
        if self._conn is not None:
            try:
                self._conn.close()
            except OSError:
                pass


# ---------------------------------------------------------------- Packet codec


class VanillaCodecTests(unittest.TestCase):
    def test_varint_roundtrip(self):
        for value in (0, 1, 127, 128, 255, 300, 25565, 2097151, 2147483647):
            encoded = vanilla.write_varint(value)
            decoded, pos = vanilla.read_varint(encoded, 0)
            self.assertEqual(decoded, value)
            self.assertEqual(pos, len(encoded))

    def test_uncompressed_framing(self):
        decoder = vanilla.Decoder(0)
        packets = decoder.feed(vanilla.pack(0x00, b'abc') + vanilla.pack(0x21, b'xyz'))
        self.assertEqual([(p.packet_id, p.body) for p in packets],
                         [(0x00, b'abc'), (0x21, b'xyz')])

    def test_incremental_feed(self):
        decoder = vanilla.Decoder(0)
        data = vanilla.pack(0x03, b'hello world')
        self.assertEqual(decoder.feed(data[:3]), [])
        packets = decoder.feed(data[3:])
        self.assertEqual(len(packets), 1)
        self.assertEqual(packets[0].body, b'hello world')

    def test_compressed_framing_roundtrip(self):
        encoder = vanilla.Encoder(16)
        decoder = vanilla.Decoder(16)
        small = unframed(vanilla.pack(0x00, b'small'))
        big = unframed(vanilla.pack(0x21, b'x' * 500))
        packets = decoder.feed(encoder.frame(small) + encoder.frame(big))
        self.assertEqual(len(packets), 2)
        self.assertEqual(packets[0].payload, small)
        self.assertEqual(packets[1].payload, big)
        # small packets stay uncompressed (marker 0); big ones get compressed (marker = uncompressed length)
        small_frame = encoder.frame(small)
        _, pos = vanilla.read_varint(small_frame, 0)
        marker, _ = vanilla.read_varint(small_frame, pos)
        self.assertEqual(marker, 0)
        big_frame = encoder.frame(big)
        _, pos = vanilla.read_varint(big_frame, 0)
        marker, _ = vanilla.read_varint(big_frame, pos)
        self.assertEqual(marker, len(big))

    def test_garbage_raises(self):
        decoder = vanilla.Decoder(0)
        with self.assertRaises(vanilla.ProtocolError):
            decoder.feed(vanilla.write_varint(0))       # an empty packet is clearly invalid


# ---------------------------------------------------------------- Handshake protocol


class EaglerProtocolTests(unittest.TestCase):
    def setUp(self):
        # name_warning returns a localised string; pin English so the
        # "3-16" shape assertions stay stable.
        self._lang = i18n.get_language()
        i18n.set_language('en')

    def tearDown(self):
        i18n.set_language(self._lang)

    def test_parse_real_client_packet(self):
        version = eagler.parse_client_version(REAL_FIRST_PACKET)
        self.assertIsNotNone(version)
        self.assertEqual(version.handshake_protocols, [3, 4, 5])
        self.assertEqual(version.mc_protocols, [47])
        self.assertEqual(version.brand, 'EaglercraftX')
        self.assertEqual(version.version, 'u53')
        self.assertFalse(version.auth)
        self.assertEqual(version.auth_username, b'nopp')
        self.assertEqual(eagler.select_protocols(version), (5, 47))

    def test_accept_trailing_bytes(self):
        """Extra bytes after the fields we know are ignored, so a client newer
        than this proxy still connects."""
        data = REAL_FIRST_PACKET + b'\x00'
        version = eagler.parse_client_version(data)
        self.assertIsNotNone(version)
        self.assertEqual(version.handshake_protocols, [3, 4, 5])
        self.assertEqual(version.mc_protocols, [47])

    def test_reject_other_traffic(self):
        self.assertIsNone(eagler.parse_client_version(b'\x00\x00\x00\x00\x00\x00\x00\x00'))
        self.assertIsNone(eagler.parse_client_version(b''))
        self.assertIsNone(eagler.parse_client_version(REAL_FIRST_PACKET[:10]))

    def test_select_lowest_when_only_v3(self):
        version = eagler.parse_client_version(build_client_version(handshake_protocols=(3,)))
        self.assertEqual(eagler.select_protocols(version), (3, 47))

    def test_any_mc_protocol_is_accepted(self):
        """No game version is refused: the client's own choice is passed through."""
        for mc in (47, 340, 578, 754, 766, 774, 775, 776, 777, 9999):
            version = eagler.parse_client_version(
                build_client_version(handshake_protocols=(3, 4, 5), mc_protocols=(mc,)))
            self.assertEqual(eagler.select_protocols(version), (5, mc))

    def test_newer_handshake_revision_is_answered_with_our_newest(self):
        """A client that only lists newer handshake revisions is still answered
        (with our newest dialect) instead of being turned away."""
        version = eagler.parse_client_version(
            build_client_version(handshake_protocols=(6,), mc_protocols=(777,)))
        self.assertEqual(eagler.select_protocols(version), (5, 777))

    def test_server_version_formats(self):
        v3 = eagler.pack_server_version(3, 47, 'TestProxy', '1.0')
        self.assertEqual(v3[0], eagler.PROTOCOL_SERVER_VERSION)
        self.assertEqual(int.from_bytes(v3[1:3], 'big'), 3)
        self.assertEqual(int.from_bytes(v3[3:5], 'big'), 47)
        self.assertEqual(v3[-3:], b'\x00\x00\x00')      # authMethod + salt length
        v5 = eagler.pack_server_version(5, 47, 'TestProxy', '1.0')
        self.assertEqual(v5[-4:], b'\x00\x00\x00\x00')  # one extra nicknameSelection

    def test_request_login_variants(self):
        v3 = eagler.parse_request_login(build_request_login(version=3), 3)
        self.assertEqual(v3.username, 'Tester')
        self.assertEqual(v3.requested_server, 'wss://127.0.0.1:1000')
        v4 = eagler.parse_request_login(build_request_login(version=4, cookie=b'ab'), 4)
        self.assertEqual(v4.cookie, b'ab')
        v5 = eagler.parse_request_login(build_request_login(version=5, caps=0b101), 5)
        self.assertEqual(v5.capabilities, 0b101)
        with self.assertRaises(eagler.HandshakeError):
            eagler.parse_request_login(build_request_login(version=5) + b'\x01', 5)

    def test_offline_uuid_shape(self):
        value = eagler.offline_uuid('Notch')
        self.assertEqual(len(value), 16)
        self.assertEqual(value[6] >> 4, 3)          # version 3
        self.assertEqual(value[8] >> 6, 0b10)       # IETF variant
        self.assertNotEqual(value, eagler.offline_uuid('Herobrine'))

    def test_usable_name(self):
        """Only empty or control-character-only input is refused."""
        for name in ('Tester', 'a', '名字', '名前_1'):
            self.assertEqual(eagler.usable_name(name), name)
        self.assertEqual(eagler.usable_name('  Tester  '), 'Tester')
        for bad in ('', '   ', None, '\x00', '\n\t', '\x7f'):
            self.assertEqual(eagler.usable_name(bad), '')

    def test_sanitize_username(self):
        # ASCII, short, long and non-ASCII names all pass through untouched: the
        # proxy cannot decide what the target server will accept, so it only
        # supplies a fallback when the client sent no name at all.
        for name in ('Tester', 'a', 'a' * 200, '名字abc', '名字123'):
            self.assertEqual(eagler.sanitize_username(name), name)
        for bad in ('', '   ', None, '\x00\t'):
            self.assertEqual(eagler.sanitize_username(bad), 'Player')
        self.assertEqual(eagler.sanitize_username('', fallback='Alt'), 'Alt')

    def test_name_warning_only_for_non_vanilla_shape(self):
        """The warning is advisory: valid Mojang-shaped names are quiet, every
        other shape is flagged but still allowed through."""
        for name in ('Tester', 'abc', 'a' * 16, 'Steve_123'):
            self.assertEqual(eagler.name_warning(name), '')
        for name in ('ab', 'a' * 17, '名字', 'bad-name', 'has space'):
            self.assertIn('3-16', eagler.name_warning(name))

# ---------------------------------------------------------------- State machine


class TranslatorUnitTests(unittest.TestCase):
    def make(self, **kwargs):
        sent: list[bytes] = []            # sent to the browser
        to_backend: list[bytes] = []      # proxy-written straight to the target server (encryption response)
        closed: list[str] = []
        translator = EaglerTranslator(
            target_host='play.example.net', target_port=25565,
            log=kwargs.pop('log', None) or NullLogger(),
            tag='#1', send_client=sent.append, send_backend=to_backend.append,
            request_close=closed.append, **kwargs)
        return translator, sent, closed, to_backend

    def test_full_offline_flow(self):
        translator, sent, closed, _backend = self.make()
        self.assertEqual(translator.feed_client(REAL_FIRST_PACKET), b'')
        self.assertEqual(sent[0][0], eagler.PROTOCOL_SERVER_VERSION)
        self.assertEqual(int.from_bytes(sent[0][1:3], 'big'), 5)

        to_server = translator.feed_client(build_request_login(username='Tester'))
        # vanilla handshake packet + login start packet
        decoder = vanilla.Decoder(0)
        packets = decoder.feed(to_server)
        self.assertEqual(len(packets), 2)
        protocol, pos = vanilla.read_varint(packets[0].body, 0)
        address, pos = vanilla.read_string(packets[0].body, pos)
        self.assertEqual(protocol, 47)
        self.assertEqual(address, 'play.example.net')
        username, _ = vanilla.read_string(packets[1].body, 0)
        self.assertEqual(username, 'Tester')

        # Set Compression + login success from the server: packets after the
        # threshold takes effect must be framed in the compressed format (real
        # servers put these two packets in one segment, so the threshold must
        # apply mid-parse).
        uuid_text = '1' * 8 + '-' + '2' * 4 + '-' + '3' * 4 + '-' + '4' * 4 + '-' + '5' * 12
        payload = (vanilla.pack(vanilla.LOGIN_SET_COMPRESSION, vanilla.write_varint(256))
                   + vanilla.Encoder(256).frame(
                       unframed(build_login_success('Tester', uuid_text=uuid_text))))
        out = translator.feed_server(payload)
        self.assertEqual(out, [])                # login-phase packets are not forwarded to the client directly
        self.assertEqual(len(sent), 2)
        self.assertEqual(sent[1][0], eagler.PROTOCOL_SERVER_ALLOW_LOGIN)
        self.assertEqual(translator.server_encoder.threshold, 256)

        # Play data arriving before the handshake completes is buffered and only
        # sent after login finishes; everything sent to the client is "one frame
        # per bare packet": no length prefix, no compression.
        play = unframed(vanilla.pack(vanilla.PLAY_JOIN_GAME, b'\x01\x02\x03'))
        self.assertEqual(translator.feed_server(vanilla.Encoder(256).frame(play)), [])
        self.assertEqual(translator.feed_client(bytes([eagler.PROTOCOL_CLIENT_FINISH_LOGIN])), b'')
        self.assertEqual(sent[2][0], eagler.PROTOCOL_SERVER_FINISH_LOGIN)
        self.assertEqual(sent[3], play)
        self.assertEqual(translator.phase, 'play')
        self.assertEqual(closed, [])

    def test_configuration_packets_pass_through_to_the_client(self):
        """1.20.2+ configuration packets are forwarded untouched.

        The browser client implements the configuration state itself (its
        code carries ServerboundFinishConfigurationPacket and friends), so the
        proxy must not answer or eat Finish Configuration / Keep Alive on its
        behalf: doing so left the client waiting for a finish it never saw and
        the join hung after the registry data.
        """
        translator, _sent, _closed, _backend = self.make()
        translator.mc_protocol = 774
        translator.login_done = True
        translator.phase = 'play'
        for packet_id in (0x03, 0x04):
            packet = vanilla.pack(packet_id, b'\x00' * 8)
            self.assertEqual(translator.feed_server(packet), [unframed(packet)])

    def test_play_passthrough_and_extension_filter(self):
        translator, sent, _closed, _backend = self.make()
        translator.feed_client(REAL_FIRST_PACKET)
        translator.feed_client(build_request_login())
        translator.feed_server(build_login_success('Tester'))
        translator.feed_client(bytes([eagler.PROTOCOL_CLIENT_FINISH_LOGIN]))

        # client upstream: one bare packet -> one length-prefixed packet in the vanilla stream
        keep_alive = unframed(vanilla.pack(vanilla.PLAY_KEEP_ALIVE, b'\x00\x00\x00\x01'))
        moved = translator.feed_client(keep_alive)
        packets = vanilla.Decoder(0).feed(moved)
        self.assertEqual([p.payload for p in packets], [keep_alive])

        # client-specific EAG| plugin messages are dropped
        channel = b'EAG|Skins-1.8'
        plugin = unframed(vanilla.pack(vanilla.CLIENT_PLUGIN_MESSAGE,
                                       vanilla.write_varint(len(channel)) + channel + b'\x01\x02'))
        self.assertEqual(translator.feed_client(plugin), b'')

        # server downstream: one packet -> one bare frame (not a single byte-stream frame)
        big = unframed(vanilla.pack(0x21, b'z' * 400))
        out = translator.feed_server(vanilla.Encoder(0).frame(big))
        self.assertEqual(out, [big])

    def test_movement_and_held_item_packets_pass_through_unchanged(self):
        """No 1.8 pacing layer: every client tick reaches the server with the
        exact bytes the browser client sent, and none is held back."""
        translator, _sent, _closed, _backend = self.make()
        translator.feed_client(REAL_FIRST_PACKET)
        translator.feed_client(build_request_login())
        translator.feed_server(build_login_success('Tester'))
        translator.feed_client(bytes([eagler.PROTOCOL_CLIENT_FINISH_LOGIN]))

        cases = [
            (vanilla.CLIENT_PLAYER, b'\x01'),
            (vanilla.CLIENT_PLAYER_LOOK, struct.pack('>ffB', 90.0, 45.0, 1)),
            (vanilla.CLIENT_PLAYER_POSITION,
             struct.pack('>dddB', 1.5, 64.0, -2.5, 0)),
            (vanilla.CLIENT_PLAYER_POSITION_LOOK,
             struct.pack('>dddffB', 1.5, 64.0, -2.5, 90.0, 45.0, 1)),
            (vanilla.CLIENT_HELD_ITEM_CHANGE, b'\x00\x03'),
        ]
        for packet_id, body in cases:
            bare = unframed(vanilla.pack(packet_id, body))
            out = translator.feed_client(bare)
            packets = vanilla.Decoder(0).feed(out)
            self.assertEqual(len(packets), 1, 'packet 0x%02x was delayed or split' % packet_id)
            self.assertEqual(packets[0].payload, bare)

    def test_negative_transaction_probe_is_not_answered_locally(self):
        """A server transaction probe reaches the browser client untouched; the
        proxy must not synthesize a reply on its behalf."""
        translator, _sent, _closed, to_backend = self.make()
        translator.feed_client(REAL_FIRST_PACKET)
        translator.feed_client(build_request_login())
        translator.feed_server(build_login_success('Tester'))
        translator.feed_client(bytes([eagler.PROTOCOL_CLIENT_FINISH_LOGIN]))
        to_backend.clear()

        body = b'\x00' + (-193).to_bytes(2, 'big', signed=True) + b'\x00'
        bare = unframed(vanilla.pack(vanilla.PLAY_WINDOW_CONFIRMATION, body))
        out = translator.feed_server(vanilla.Encoder(0).frame(bare))
        self.assertEqual(out, [bare])
        self.assertEqual(to_backend, [])

    def test_server_packets_become_one_frame_each(self):
        """A server chunk with N packets must yield N frames, each holding one bare packet."""
        translator, sent, _closed, _backend = self.make()
        translator.feed_client(REAL_FIRST_PACKET)
        translator.feed_client(build_request_login())
        translator.feed_server(build_login_success('Tester'))
        translator.feed_client(bytes([eagler.PROTOCOL_CLIENT_FINISH_LOGIN]))
        sent.clear()

        first = unframed(vanilla.pack(vanilla.PLAY_JOIN_GAME, b'\x01\x02'))
        second = unframed(vanilla.pack(vanilla.PLAY_KEEP_ALIVE, b'\x00\x00\x00\x09'))
        chunk = unframed(vanilla.pack(0x21, b'q' * 500))
        out = translator.feed_server(
            vanilla.Encoder(0).frame(first) + vanilla.Encoder(0).frame(second)
            + vanilla.Encoder(0).frame(chunk))
        self.assertEqual(out, [first, second, chunk])
        # no length prefix inside the frame: the first byte is the packet id itself
        self.assertEqual(out[0][0], vanilla.PLAY_JOIN_GAME)

    def test_client_injected_frames_are_dropped(self):
        """v5 client injected-message frames (starting with 0xEE) are not
        vanilla packets and must not reach the server."""
        translator, _sent, _closed, _backend = self.make()
        translator.feed_client(REAL_FIRST_PACKET)
        translator.feed_client(build_request_login())
        translator.feed_server(build_login_success('Tester'))
        translator.feed_client(bytes([eagler.PROTOCOL_CLIENT_FINISH_LOGIN]))
        self.assertEqual(translator.feed_client(bytes([0xEE, 0x01, 0x02, 0x03])), b'')
        self.assertEqual(translator.feed_client(bytes([0xEE, 0xFF, 0x00])), b'')

    def test_encryption_request_is_completed(self):
        """The encryption request is answered on the client's behalf: shared
        secret and token encrypted back with the server's public key, then
        AES-128-CFB8 for the rest of the session."""
        translator, sent, closed, to_backend = self.make()
        translator.feed_client(REAL_FIRST_PACKET)
        translator.feed_client(build_request_login(username='Tester'))

        key = x509.generate_rsa_key(1024)
        token = b'\x11\x22\x33\x44'
        self.assertEqual(translator.feed_server(build_encryption_request(key, token)), [])

        # 1) the proxy wrote the encryption response straight to the target server
        self.assertEqual(closed, [])
        self.assertEqual(len(to_backend), 1)
        packets = vanilla.Decoder(0).feed(to_backend[0])
        self.assertEqual(len(packets), 1)
        self.assertEqual(packets[0].packet_id, vanilla.LOGIN_ENCRYPTION_RESPONSE)
        pos = 0
        length, pos = vanilla.read_varint(packets[0].body, pos)
        enc_secret = packets[0].body[pos:pos + length]
        pos += length
        length, pos = vanilla.read_varint(packets[0].body, pos)
        enc_token = packets[0].body[pos:pos + length]
        secret = rsa_decrypt(key, enc_secret)
        self.assertEqual(len(secret), 16)
        self.assertEqual(rsa_decrypt(key, enc_token), token)

        # 2) from here on all server data is AES-128-CFB8 ciphertext; the proxy must decrypt it to carry on
        server_side = crypto.AesCfb8(secret, secret)
        out = translator.feed_server(server_side.encrypt(build_login_success('Tester')))
        self.assertEqual(out, [])
        self.assertEqual(sent[-1][0], eagler.PROTOCOL_SERVER_ALLOW_LOGIN)
        translator.feed_client(bytes([eagler.PROTOCOL_CLIENT_FINISH_LOGIN]))
        self.assertEqual(translator.phase, 'play')

        # 3) client upstream traffic must be encrypted too
        keep_alive = vanilla.pack(vanilla.PLAY_KEEP_ALIVE, b'\x00\x00\x00\x01')
        moved = translator.feed_client(unframed(keep_alive))
        self.assertNotEqual(moved, keep_alive)
        self.assertEqual(crypto.AesCfb8(secret, secret).decrypt(moved), keep_alive)
        self.assertEqual(closed, [])

    def test_encryption_without_aes_library_reports_clearly(self):
        translator, sent, closed, to_backend = self.make()
        translator.feed_client(REAL_FIRST_PACKET)
        translator.feed_client(build_request_login(username='Tester'))
        key = x509.generate_rsa_key(1024)
        with unittest.mock.patch.object(crypto, '_BACKEND', ''):
            self.assertEqual(translator.feed_server(build_encryption_request(key)), [])
        self.assertEqual(to_backend, [])
        self.assertEqual(sent[-1][0], eagler.PROTOCOL_SERVER_ERROR)
        length = int.from_bytes(sent[-1][2:4], 'big')          # 0xFF + error code + u16 length
        # Since v3 the body must be valid JSON (the client runs it through
        # jsonToComponent); the message text lives in "text".
        text = json.loads(sent[-1][4:4 + length].decode('utf-8'))['text']
        self.assertTrue(text.startswith(tr('translator.prefix')), text)
        self.assertIn('cryptography', text)
        self.assertEqual(translator.phase, 'closed')
        self.assertTrue(closed)

    def test_our_messages_are_marked(self):
        """Errors raised by the proxy itself carry the adapter prefix; server text does not."""
        translator, sent, _closed, _backend = self.make()
        translator.feed_client(REAL_FIRST_PACKET)
        translator.feed_client(build_request_login(username='Tester'))
        translator.feed_server(b'\x00')                        # truncated frame, length 0 -> proxy-side error
        self.assertEqual(sent[-1][0], eagler.PROTOCOL_SERVER_ERROR)
        length = int.from_bytes(sent[-1][2:4], 'big')
        text = json.loads(sent[-1][4:4 + length].decode('utf-8'))['text']
        self.assertTrue(text.startswith(tr('translator.prefix')), text)

    def test_kick_message_is_forwarded(self):
        translator, sent, _closed, _backend = self.make()
        translator.feed_client(REAL_FIRST_PACKET)
        translator.feed_client(build_request_login())
        translator.feed_server(build_disconnect('Server closed'))
        self.assertEqual(sent[-1][0], eagler.PROTOCOL_SERVER_DENY_LOGIN)
        length = int.from_bytes(sent[-1][1:3], 'big')
        # The reason is flattened to plain text: the client must never see a
        # JSON wall instead of the message the server actually sent.
        self.assertEqual(sent[-1][3:3 + length].decode('utf-8'), 'Server closed')

    def test_plain_kick_reason_is_forwarded_as_plain_text(self):
        translator, sent, _closed, _backend = self.make()
        translator.feed_client(REAL_FIRST_PACKET)
        translator.feed_client(build_request_login())
        reason = 'You were kicked'
        body = vanilla.write_varint(len(reason.encode())) + reason.encode()
        translator.feed_server(vanilla.pack(vanilla.LOGIN_DISCONNECT, body))
        self.assertEqual(sent[-1][0], eagler.PROTOCOL_SERVER_DENY_LOGIN)
        length = int.from_bytes(sent[-1][1:3], 'big')
        self.assertEqual(sent[-1][3:3 + length].decode('utf-8'), reason)

    def test_kick_body_is_forwarded_verbatim_regardless_of_brand(self):
        """The deny body is whatever the server sent, byte for byte.

        There is no per-brand flattening any more: a browser client gets the
        JSON component as JSON or a ``§``-coded string as plain text, whichever
        the content is, so no brand heuristic is consulted.
        """
        translator, sent, _closed, _backend = self.make()
        translator.feed_client(build_client_version(brand='Gaius', version='26.3'))
        translator.feed_client(build_request_login())
        translator.feed_server(build_disconnect('服务器已满'))
        self.assertEqual(sent[-1][0], eagler.PROTOCOL_SERVER_DENY_LOGIN)
        length = int.from_bytes(sent[-1][1:3], 'big')
        self.assertEqual(sent[-1][3:3 + length].decode('utf-8'), '服务器已满')

    def test_json_kick_reason_is_flattened_to_plain_text(self):
        """A JSON chat component is flattened before it reaches the client: the
        player sees the message text, not a wall of JSON."""
        component = json.dumps({'text': 'Kicked by admin', 'color': 'gray'})
        body = vanilla.write_varint(len(component.encode())) + component.encode()
        translator, sent, _closed, _backend = self.make()
        translator.feed_client(REAL_FIRST_PACKET)
        translator.feed_client(build_request_login())
        translator.feed_server(vanilla.pack(vanilla.LOGIN_DISCONNECT, body))
        self.assertEqual(sent[-1][0], eagler.PROTOCOL_SERVER_DENY_LOGIN)
        length = int.from_bytes(sent[-1][1:3], 'big')
        self.assertEqual(sent[-1][3:3 + length].decode('utf-8'), 'Kicked by admin')

    def test_double_encoded_kick_reason_is_unwrapped_not_flattened(self):
        """A twice-serialized component is decoded to the component, not flattened."""
        component = json.dumps({'text': 'Kicked by admin', 'color': 'gray'})
        raw = json.dumps(component)
        body = vanilla.write_varint(len(raw.encode())) + raw.encode()
        translator, sent, _closed, _backend = self.make()
        translator.feed_client(build_client_version(brand='Gaius', version='26.3'))
        translator.feed_client(build_request_login())
        translator.feed_server(vanilla.pack(vanilla.LOGIN_DISCONNECT, body))
        self.assertEqual(sent[-1][0], eagler.PROTOCOL_SERVER_DENY_LOGIN)
        length = int.from_bytes(sent[-1][1:3], 'big')
        self.assertEqual(sent[-1][3:3 + length].decode('utf-8'), 'Kicked by admin')

    def test_play_disconnect_body_is_forwarded_verbatim(self):
        translator, _sent, _closed, _backend = self.make()
        translator.feed_client(REAL_FIRST_PACKET)
        translator.phase = 'play'
        component = json.dumps({'text': 'Kicked by admin', 'color': 'gray'})
        packet = vanilla.Decoder(0).feed(build_play_disconnect(component))[0]
        frames = []
        translator._handle_play_packet(packet, frames)
        self.assertEqual(len(frames), 1)
        packet_id, pos = vanilla.read_varint(frames[0], 0)
        self.assertEqual(packet_id, vanilla.PLAY_DISCONNECT)
        body, _ = vanilla.read_string(frames[0], pos)
        self.assertEqual(body, component)

    def test_legacy_kick_reason_keeps_its_codes(self):
        reason = '\u00a77You were \u00a7ckicked'
        body = vanilla.write_varint(len(reason.encode())) + reason.encode()
        translator, sent, _closed, _backend = self.make()
        translator.feed_client(REAL_FIRST_PACKET)
        translator.feed_client(build_request_login())
        translator.feed_server(vanilla.pack(vanilla.LOGIN_DISCONNECT, body))
        length = int.from_bytes(sent[-1][1:3], 'big')
        self.assertEqual(sent[-1][3:3 + length].decode('utf-8'), reason)

    def test_chat_passthrough_keeps_a_component_as_json(self):
        """A JSON body goes out as JSON: the colour field stays exactly what the
        server sent, including an arbitrary hex rather than a near palette match."""
        component = json.dumps({'text': 'hi', 'color': '#ff5500'})
        body, chat_json = chat_passthrough(component, 'Kicked')
        self.assertTrue(chat_json)
        self.assertEqual(body, component)

    def test_chat_passthrough_keeps_legacy_codes_as_plain_text(self):
        body, chat_json = chat_passthrough('\u00a7aGreen', 'Kicked')
        self.assertFalse(chat_json)
        self.assertEqual(body, '\u00a7aGreen')

    def test_chat_passthrough_wraps_nothing_around_plain_text(self):
        body, chat_json = chat_passthrough('You were kicked', 'Kicked')
        self.assertFalse(chat_json)
        self.assertEqual(body, 'You were kicked')

    def test_chat_passthrough_unwraps_double_encoded_component(self):
        component = json.dumps({'text': 'Kicked', 'color': 'red'})
        body, chat_json = chat_passthrough(json.dumps(component), 'Kicked')
        self.assertTrue(chat_json)
        self.assertEqual(json.loads(body), {'text': 'Kicked', 'color': 'red'})

    def test_chat_passthrough_falls_back_on_empty_input(self):
        body, chat_json = chat_passthrough('', 'Kicked')
        self.assertFalse(chat_json)
        self.assertEqual(body, 'Kicked')

    def test_chat_to_text_unwraps_nested_json(self):
        inner = json.dumps({'extra': [{'color': 'gray', 'text': 'hello'}]})
        self.assertEqual(chat_to_text(json.dumps(inner)), 'hello')
        self.assertEqual(chat_to_text(json.dumps({'text': inner})), 'hello')
        self.assertEqual(chat_to_text('{"foo":"bar"}'), '{"foo":"bar"}')

    def test_as_chat_json_unwraps_double_encoded_component(self):
        inner = json.dumps({'text': 'hello'})
        self.assertEqual(json.loads(eagler.as_chat_json(json.dumps(inner))),
                         {'text': 'hello'})
        self.assertEqual(json.loads(eagler.as_chat_json(json.dumps('hello'))),
                         {'text': 'hello'})

    def test_error_bodies_are_plain_text_for_verbatim_clients(self):
        """The same rule covers the proxy's own error messages (custom 0xFF)."""
        translator, sent, _closed, _backend = self.make()
        translator.feed_client(build_client_version(brand='Gaius', version='26.3'))
        translator.feed_client(build_request_login())
        translator.feed_server(b'\x00')                    # truncated frame -> proxy-side error
        self.assertEqual(sent[-1][0], eagler.PROTOCOL_SERVER_ERROR)
        length = int.from_bytes(sent[-1][2:4], 'big')
        text = sent[-1][4:4 + length].decode('utf-8')
        self.assertTrue(text.startswith(tr('translator.prefix')), text)

    def test_server_brand_and_version_are_configurable(self):
        """The server brand/version the browser client sees must come from
        config and land in the server version packet."""
        translator, sent, _closed, _backend = self.make(brand='Paper', brand_version='1.8.8-R0.1')
        translator.feed_client(REAL_FIRST_PACKET)
        self.assertEqual(sent[0][0], eagler.PROTOCOL_SERVER_VERSION)
        # the brand string starts only after packet id (1) + handshake protocol (2) + game protocol (2)
        brand, pos = read_eagler_string(sent[0], 5)
        version, _ = read_eagler_string(sent[0], pos)
        self.assertEqual(brand, 'Paper')
        self.assertEqual(version, '1.8.8-R0.1')

    def test_spoof_brand_is_injected_and_client_brand_is_rewritten(self):
        """Client-brand spoofing: an MC|Brand from config is announced after
        login, and the client's own MC|Brand is rewritten to the configured
        value instead of reaching the target verbatim (plugins on the target
        see only our declaration)."""
        translator, _sent, _closed, to_backend = self.make(spoof_brand='forge/1.8.8')
        translator.feed_client(REAL_FIRST_PACKET)
        translator.feed_client(build_request_login(username='Tester'))
        translator.feed_server(build_login_success('Tester'))
        to_backend.clear()
        translator.feed_client(bytes([eagler.PROTOCOL_CLIENT_FINISH_LOGIN]))
        self.assertEqual(translator.phase, 'play')
        blob = b''.join(to_backend)
        self.assertIn(b'MC|Brand', blob)
        self.assertIn(b'forge/1.8.8', blob)

        channel = b'MC|Brand'
        plugin = unframed(vanilla.pack(vanilla.CLIENT_PLUGIN_MESSAGE,
                                       vanilla.write_varint(len(channel)) + channel
                                       + vanilla.write_varint(11) + b'EaglercraftX'))
        to_backend.clear()
        moved = translator.feed_client(plugin)
        packets = list(vanilla.Decoder(0).feed(moved))
        self.assertEqual(packets[0].packet_id, vanilla.CLIENT_PLUGIN_MESSAGE)
        moved_channel, pos = vanilla.read_string(packets[0].body, 0)
        moved_value, _ = vanilla.read_string(packets[0].body, pos)
        self.assertEqual(moved_channel, 'MC|Brand')
        self.assertEqual(moved_value, 'forge/1.8.8')
        self.assertEqual(to_backend, [])

    def test_forge_1_8_preset_shapes_handshake_and_registers_fml_channels(self):
        """The forge-1.8 preset reproduces the legacy Forge fingerprints: the FML marker
        in the handshake address, the REGISTER channel list after login, brand last."""
        translator, _sent, _closed, to_backend = self.make(
            spoof_client='forge-1.8', spoof_brand='fml,forge')
        translator.feed_client(REAL_FIRST_PACKET)
        to_server = translator.feed_client(build_request_login(username='Tester'))
        packets = vanilla.Decoder(0).feed(to_server)
        self.assertEqual(len(packets), 2)
        _protocol, pos = vanilla.read_varint(packets[0].body, 0)
        address, _ = vanilla.read_string(packets[0].body, pos)
        self.assertEqual(address, 'play.example.net\x00FML\x00')

        translator.feed_server(build_login_success('Tester'))
        to_backend.clear()
        translator.feed_client(bytes([eagler.PROTOCOL_CLIENT_FINISH_LOGIN]))
        blob = b''.join(to_backend)
        self.assertIn(b'REGISTER', blob)
        self.assertIn(b'FML|HS\x00FML\x00FML|MP', blob)
        self.assertIn(b'MC|Brand', blob)
        self.assertLess(blob.index(b'REGISTER'), blob.index(b'MC|Brand'))

    def test_forge_1_13_preset_reports_the_brand_only(self):
        """Modern Forge (1.13+) dropped the legacy FML marker: the handshake address
        stays untouched and no REGISTER is sent -- just the "forge" brand after login."""
        translator, _sent, _closed, to_backend = self.make(
            spoof_client='forge-1.13', spoof_brand='forge')
        translator.feed_client(REAL_FIRST_PACKET)
        to_server = translator.feed_client(build_request_login(username='Tester'))
        self.assertNotIn(b'\x00FML\x00', to_server)
        translator.feed_server(build_login_success('Tester'))
        to_backend.clear()
        translator.feed_client(bytes([eagler.PROTOCOL_CLIENT_FINISH_LOGIN]))
        blob = b''.join(to_backend)
        self.assertNotIn(b'REGISTER', blob)
        self.assertIn(b'MC|Brand', blob)
        self.assertTrue(blob.endswith(b'forge'), blob)

    def test_vanilla_preset_adds_no_forge_fingerprints(self):
        translator, _sent, _closed, to_backend = self.make(
            spoof_client='vanilla', spoof_brand='vanilla')
        translator.feed_client(REAL_FIRST_PACKET)
        to_server = translator.feed_client(build_request_login(username='Tester'))
        self.assertNotIn(b'\x00FML\x00', to_server)
        translator.feed_server(build_login_success('Tester'))
        to_backend.clear()
        translator.feed_client(bytes([eagler.PROTOCOL_CLIENT_FINISH_LOGIN]))
        blob = b''.join(to_backend)
        self.assertNotIn(b'REGISTER', blob)
        self.assertNotIn(b'\x00FML\x00', blob)
        self.assertIn(b'MC|Brand', blob)

    def test_newer_game_protocol_is_not_rejected(self):
        translator, sent, closed, _backend = self.make()
        packet = build_client_version(handshake_protocols=(3, 4, 5), mc_protocols=(340,))
        translator.feed_client(packet)
        self.assertEqual(sent[0][0], eagler.PROTOCOL_SERVER_VERSION)
        self.assertEqual(int.from_bytes(sent[0][3:5], 'big'), 340)
        self.assertEqual(translator.mc_protocol, 340)
        self.assertEqual(closed, [])

    def test_v1_handshake_still_gets_a_clear_notice(self):
        """The 2022-era v1 handshake carries no version list; it gets the
        version-mismatch notice instead of a server-version answer."""
        translator, sent, _closed, _backend = self.make()
        packet = bytes([0x01, 0x01, 0x2f, 0x0b]) + b'Eaglercraft' + bytes([3]) + b'u53'
        translator.feed_client(packet)
        self.assertEqual(sent[0][0], eagler.PROTOCOL_VERSION_MISMATCH)
        self.assertEqual(translator.phase, 'closed')

    def test_modern_login_start_carries_the_uuid(self):
        """1.20.2+ servers parse Login Start with a required UUID field, so it
        must be present even though the proxy just relays."""
        translator, _sent, _closed, _backend = self.make()
        translator.feed_client(build_client_version(handshake_protocols=(5,),
                                                    mc_protocols=(766,)))
        to_server = translator.feed_client(build_request_login(username='Tester'))
        packets = vanilla.Decoder(0).feed(to_server)
        self.assertEqual(len(packets), 2)
        protocol, _ = vanilla.read_varint(packets[0].body, 0)
        self.assertEqual(protocol, 766)
        name, pos = vanilla.read_string(packets[1].body, 0)
        self.assertEqual(name, 'Tester')
        self.assertEqual(packets[1].body[pos:], eagler.offline_uuid('Tester'))

    def test_modern_login_success_binary_uuid(self):
        """Since 1.16 Login Success carries the UUID as 16 raw bytes."""
        translator, sent, _closed, _backend = self.make()
        translator.feed_client(build_client_version(handshake_protocols=(5,),
                                                    mc_protocols=(754,)))
        translator.feed_client(build_request_login(username='Tester'))
        raw = bytes(range(16))
        translator.feed_server(vanilla.pack(vanilla.LOGIN_SUCCESS,
                                            raw + vanilla.write_string('Tester')))
        self.assertEqual(sent[-1][0], eagler.PROTOCOL_SERVER_ALLOW_LOGIN)
        name, pos = read_eagler_string(sent[-1], 1)
        self.assertEqual(name, 'Tester')
        self.assertEqual(sent[-1][pos:pos + 16], raw)

    def test_modern_protocol_rewrites_the_client_brand(self):
        """Outside 1.8 the plugin-message packet id differs per version, but a
        spoofed client identity is still honoured: the client's own
        minecraft:brand packet is rewritten to the configured value instead of
        reaching the target server verbatim (no FML marker, no REGISTER --
        those stay 1.8-only)."""
        translator, _sent, _closed, to_backend = self.make(
            spoof_client='forge-1.8', spoof_brand='fml,forge')
        translator.feed_client(build_client_version(handshake_protocols=(5,),
                                                    mc_protocols=(766,)))
        to_server = translator.feed_client(build_request_login(username='Tester'))
        self.assertNotIn(b'\x00FML\x00', to_server)
        translator.feed_server(vanilla.pack(vanilla.LOGIN_SUCCESS,
                                            bytes(range(16)) + vanilla.write_string('Tester')))
        to_backend.clear()
        translator.feed_client(bytes([eagler.PROTOCOL_CLIENT_FINISH_LOGIN]))
        self.assertEqual(to_backend, [])            # no REGISTER, no brand injection
        channel = b'minecraft:brand'
        value = 'EaglercraftX 1.21.11 (u1-beta)'.encode()
        plugin = unframed(vanilla.pack(0x12,
                                       vanilla.write_varint(len(channel)) + channel
                                       + vanilla.write_varint(len(value)) + value))
        moved = translator.feed_client(plugin)
        packets = list(vanilla.Decoder(0).feed(moved))
        self.assertEqual(packets[0].packet_id, 0x12)
        moved_channel, pos = vanilla.read_string(packets[0].body, 0)
        moved_value, _ = vanilla.read_string(packets[0].body, pos)
        self.assertEqual(moved_channel, 'minecraft:brand')
        self.assertEqual(moved_value, 'fml,forge')

    def test_modern_protocol_passes_the_client_brand_through_when_not_spoofed(self):
        translator, _sent, _closed, _backend = self.make()
        translator.feed_client(build_client_version(handshake_protocols=(5,),
                                                    mc_protocols=(766,)))
        translator.feed_client(build_request_login(username='Tester'))
        translator.feed_server(vanilla.pack(vanilla.LOGIN_SUCCESS,
                                            bytes(range(16)) + vanilla.write_string('Tester')))
        translator.feed_client(bytes([eagler.PROTOCOL_CLIENT_FINISH_LOGIN]))
        channel = b'minecraft:brand'
        plugin = unframed(vanilla.pack(0x12,
                                       vanilla.write_varint(len(channel)) + channel
                                       + vanilla.write_varint(11) + b'EaglercraftX'))
        moved = translator.feed_client(plugin)
        self.assertEqual([p.payload for p in vanilla.Decoder(0).feed(moved)], [plugin])

    def test_clean_version_string(self):
        self.assertEqual(eagler.clean_version_string('EaglercraftX 1.21.11 (u1-beta)'),
                         'EaglercraftX 1.21.11')
        self.assertEqual(eagler.clean_version_string('1.2.3 (a) (b)'), '1.2.3')
        self.assertEqual(eagler.clean_version_string('1.20.6'), '1.20.6')
        self.assertEqual(eagler.clean_version_string(''), '')
        self.assertEqual(eagler.clean_version_string(' (u1-beta) '), '')

    def test_modern_login_success_sends_login_acknowledged(self):
        """1.20.2+ targets hold the connection in the login state until the
        login result is acknowledged; the browser client never sends that
        packet (its login phase is the EaglercraftX handshake), so the proxy
        sends it in the client's place -- without it the target drops the
        connection the moment the first configuration packet arrives."""
        translator, sent, closed, to_backend = self.make()
        translator.feed_client(build_client_version(handshake_protocols=(3, 4, 5),
                                                    mc_protocols=(774,)))
        translator.feed_client(build_request_login(username='Tester'))
        to_backend.clear()
        translator.feed_server(vanilla.pack(
            vanilla.LOGIN_SUCCESS, bytes(range(16)) + vanilla.write_string('Tester')))
        packets = vanilla.Decoder(0).feed(b''.join(to_backend))
        self.assertEqual(len(packets), 1)
        self.assertEqual(packets[0].packet_id, vanilla.LOGIN_ACKNOWLEDGED)
        self.assertEqual(packets[0].body, b'')
        self.assertEqual(sent[-1][0], eagler.PROTOCOL_SERVER_ALLOW_LOGIN)
        self.assertEqual(closed, [])

    def test_login_acknowledge_switch_off_sends_nothing(self):
        """The acknowledge is a setting of its own; with the switch off the
        login flow stays as it was and nothing is fabricated."""
        translator, _sent, _closed, to_backend = self.make(login_ack=False)
        translator.feed_client(build_client_version(handshake_protocols=(3, 4, 5),
                                                    mc_protocols=(774,)))
        translator.feed_client(build_request_login(username='Tester'))
        to_backend.clear()
        translator.feed_server(vanilla.pack(
            vanilla.LOGIN_SUCCESS, bytes(range(16)) + vanilla.write_string('Tester')))
        self.assertEqual(b''.join(to_backend), b'')

    def test_login_acknowledge_respects_compression(self):
        """The acknowledge has to be framed under the compression rules the
        target server has negotiated."""
        translator, _sent, _closed, to_backend = self.make()
        translator.feed_client(build_client_version(handshake_protocols=(3, 4, 5),
                                                    mc_protocols=(774,)))
        translator.feed_client(build_request_login(username='Tester'))
        translator.feed_server(vanilla.pack(vanilla.LOGIN_SET_COMPRESSION,
                                            vanilla.write_varint(256)))
        to_backend.clear()
        translator.feed_server(vanilla.Encoder(256).frame(unframed(vanilla.pack(
            vanilla.LOGIN_SUCCESS, bytes(range(16)) + vanilla.write_string('Tester')))))
        self.assertEqual(
            b''.join(to_backend),
            vanilla.Encoder(256).frame(vanilla.write_varint(vanilla.LOGIN_ACKNOWLEDGED)))

    def test_1_8_login_success_sends_no_acknowledge(self):
        """The acknowledge only exists since 1.20.2; 1.8 connections stay pure."""
        translator, _sent, _closed, to_backend = self.make()
        translator.feed_client(REAL_FIRST_PACKET)
        translator.feed_client(build_request_login(username='Tester'))
        to_backend.clear()
        translator.feed_server(build_login_success('Tester'))
        self.assertEqual(b''.join(to_backend), b'')

    def test_account_dictates_the_upstream_identity(self):
        """With an account selected the target sees exactly the account's name
        and UUID -- that pair must match what the session service vouches for,
        so the name the browser client asked for is ignored."""
        account = accounts.Account(kind=accounts.KIND_THIRDPARTY, id='a1',
                                   username='RealPlayer',
                                   uuid='0f0e0d0c-0b0a-0908-0706-050403020100',
                                   authserver='https://example.invalid/api/yggdrasil')
        translator, _sent, closed, _backend = self.make(account=account)
        translator.feed_client(build_client_version(handshake_protocols=(3, 4, 5),
                                                    mc_protocols=(774,)))
        out = translator.feed_client(build_request_login(username='BrowserKid'))
        packets = vanilla.Decoder(0).feed(out)
        self.assertEqual(len(packets), 2)
        name, pos = vanilla.read_string(packets[1].body, 0)
        self.assertEqual(name, 'RealPlayer')
        self.assertEqual(packets[1].body[pos:pos + 16],
                         bytes.fromhex('0f0e0d0c0b0a09080706050403020100'))
        self.assertEqual(translator.username, 'RealPlayer')
        self.assertEqual(closed, [])

    def test_offline_account_pins_the_name(self):
        """An offline account fixes the name; its UUID stays the one an
        offline-mode server computes for that name itself."""
        account = accounts.Account(kind=accounts.KIND_OFFLINE, id='a2',
                                   username='OfflineGuy')
        translator, _sent, closed, _backend = self.make(account=account)
        translator.feed_client(REAL_FIRST_PACKET)
        out = translator.feed_client(build_request_login(username='SomeoneElse'))
        packets = vanilla.Decoder(0).feed(out)
        name, _ = vanilla.read_string(packets[1].body, 0)
        self.assertEqual(name, 'OfflineGuy')
        self.assertEqual(translator.uuid, eagler.offline_uuid('OfflineGuy'))
        self.assertEqual(closed, [])

    def test_authenticated_account_joins_the_session_before_answering(self):
        """A Microsoft/third-party account registers the session join while the
        encryption request is being answered: a validating server looks that
        join up, and the browser client cannot do this part itself."""
        calls: list[tuple[str, str]] = []
        account = accounts.Account(kind=accounts.KIND_MICROSOFT, id='a3',
                                   username='RealPlayer',
                                   uuid='0f0e0d0c-0b0a-0908-0706-050403020100',
                                   access_token='tok',
                                   token_expires=time.time() + 3600)
        translator, _sent, closed, to_backend = self.make(account=account)
        translator.feed_client(build_client_version(handshake_protocols=(3, 4, 5),
                                                    mc_protocols=(774,)))
        translator.feed_client(build_request_login(username='BrowserKid'))
        key = x509.generate_rsa_key(1024)
        with unittest.mock.patch.object(accounts, 'join_session',
                                        lambda item, hashed, **kwargs: calls.append(
                                            (item.username, hashed))):
            translator.feed_server(build_encryption_request(key))
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], 'RealPlayer')
        self.assertRegex(calls[0][1], r'^[0-9a-f]{40}$')
        # the encryption response went out only after the join was registered
        self.assertEqual(len(to_backend), 1)
        self.assertEqual(closed, [])

    def test_account_join_failure_closes_with_the_reason(self):
        account = accounts.Account(kind=accounts.KIND_MICROSOFT, id='a4',
                                   username='RealPlayer',
                                   uuid='0f0e0d0c-0b0a-0908-0706-050403020100',
                                   access_token='tok',
                                   token_expires=time.time() + 3600)
        translator, sent, closed, to_backend = self.make(account=account)
        translator.feed_client(build_client_version(handshake_protocols=(3, 4, 5),
                                                    mc_protocols=(774,)))
        translator.feed_client(build_request_login(username='BrowserKid'))
        key = x509.generate_rsa_key(1024)

        def explode(_account, _hash, **_kwargs):
            raise accounts.AccountError('session rejected')

        with unittest.mock.patch.object(accounts, 'join_session', explode):
            translator.feed_server(build_encryption_request(key))
        # the encryption response must NOT go out when the join failed
        self.assertEqual(to_backend, [])
        self.assertEqual(sent[-1][0], eagler.PROTOCOL_SERVER_ERROR)
        self.assertEqual(translator.phase, 'closed')
        self.assertTrue(closed)
        self.assertIn('session rejected', closed[-1])

    def test_username_is_kept_untouched(self):
        """Short and non-ASCII names are forwarded as sent; the target decides."""
        for name in ('a', '名字', '名前_1'):
            translator, _sent, _closed, _backend = self.make()
            self.assertEqual(translator.feed_client(REAL_FIRST_PACKET), b'')
            translator.feed_client(build_request_login(username=name))
            self.assertEqual(translator.username, name)
            self.assertEqual(translator.uuid, eagler.offline_uuid(name))

    def test_empty_username_uses_handshake_name(self):
        """Real browser login requests can carry an empty name; fall back to authUsername from the handshake packet."""
        translator, _sent, _closed, _backend = self.make()
        self.assertEqual(translator.feed_client(REAL_FIRST_PACKET), b'')
        translator.feed_client(build_request_login(username=''))
        self.assertEqual(translator.username, 'nopp')
        self.assertEqual(translator.uuid, eagler.offline_uuid('nopp'))


# ---------------------------------------------------------------- End-to-end


class TranslateEndToEndTests(unittest.TestCase):
    def test_browser_client_through_proxy(self):
        join_game = unframed(vanilla.pack(vanilla.PLAY_JOIN_GAME, b'\x00' * 12 + b'world'))
        backend = FakeVanillaServer(threshold=256, play_packets=[join_game])
        config = Config()
        config.tls_enabled = False
        config.wss_port = 0
        config.ws_port = free_port()
        config.listen_host = '127.0.0.1'
        config.target = '127.0.0.1:%d' % backend.port
        config.use_srv = False
        # Do not let an account selected in the developer's accounts.json
        # override the name these end-to-end tests put in the login request.
        config.account_override = '__test_no_selected_account__'
        config.log_level = 'debug'
        server = ProxyServer(config)
        server.start()
        client = None
        try:
            client, _headers = connect_ws(config.ws_port, tls=False)
            client.send(REAL_FIRST_PACKET)
            version = client.recv(timeout=5.0)
            self.assertIsNotNone(version)
            self.assertEqual(version[0], eagler.PROTOCOL_SERVER_VERSION)
            self.assertEqual(int.from_bytes(version[1:3], 'big'), 5)
            self.assertEqual(int.from_bytes(version[3:5], 'big'), 47)

            client.send(build_request_login(username='Browser'))
            deadline = time.time() + 5.0
            while not backend.username and time.time() < deadline:
                time.sleep(0.02)
            self.assertEqual(backend.username, 'Browser')
            self.assertEqual(backend.handshake_protocol, 47)
            # the default is "off": no Forge FML marker is added to the address
            self.assertEqual(backend.handshake_address, '127.0.0.1')

            allow = client.recv(timeout=5.0)
            self.assertEqual(allow[0], eagler.PROTOCOL_SERVER_ALLOW_LOGIN)
            name, pos = read_eagler_string(allow, 1)
            self.assertEqual(name, 'Browser')
            self.assertEqual(allow[pos:pos + 16], eagler.offline_uuid('Browser'))

            client.send(bytes([eagler.PROTOCOL_CLIENT_FINISH_LOGIN]))
            finish = client.recv(timeout=5.0)
            self.assertEqual(finish, bytes([eagler.PROTOCOL_SERVER_FINISH_LOGIN]))
            # Play packets buffered during the handshake: one bare packet per frame (no length prefix, no compression)
            buffered = client.recv(timeout=5.0)
            self.assertEqual(buffered, join_game)

            # Play data: the client sends bare packets too; the proxy has to reframe
            # them into the vanilla stream using the server's compression threshold.
            # With the default "off" preset there is no injected client identity,
            # so the keep-alive is the first play packet the backend sees.
            keep_alive = vanilla.pack(vanilla.PLAY_KEEP_ALIVE, b'\x00\x00\x00\x07')
            client.send(unframed(keep_alive))
            got = backend.read_packets(1)
            self.assertEqual(len(got), 1)
            self.assertEqual(got[0].payload, unframed(keep_alive))

            # Plugin messages on Eaglercraft private channels and 0xEE injected-message frames are dropped
            channel = b'EAG|Skins-1.8'
            plugin = unframed(vanilla.pack(vanilla.CLIENT_PLUGIN_MESSAGE,
                                           vanilla.write_varint(len(channel)) + channel + b'\xaa'))
            client.send(plugin)
            client.send(bytes([0xEE, 0x01, 0x02, 0x03]))
            self.assertEqual(backend.read_packets(1, timeout=0.6), [])

            # server -> client: a compressed big packet must be restored as one bare frame
            chunk = unframed(vanilla.pack(0x21, b'q' * 900))
            backend.send_play(chunk)
            raw = client.recv(timeout=5.0)
            self.assertEqual(raw, chunk)
        finally:
            if client is not None:
                client.close()
            server.stop()
            backend.close()

    def test_modern_target_waits_for_the_login_acknowledge(self):
        """Full stack against a 1.20.2+ style target that enforces the login
        acknowledge: the proxy sends it in the client's place, and the
        configuration data the target produces afterwards reaches the browser
        client (buffered until the client finishes its own handshake)."""
        config_blob = unframed(vanilla.pack(0x07, b'R' * 900))
        backend = FakeVanillaServer(modern=True, play_packets=[config_blob])
        config = Config()
        config.tls_enabled = False
        config.wss_port = 0
        config.ws_port = free_port()
        config.listen_host = '127.0.0.1'
        config.target = '127.0.0.1:%d' % backend.port
        config.use_srv = False
        # Do not let an account selected in the developer's accounts.json
        # override the name these end-to-end tests put in the login request.
        config.account_override = '__test_no_selected_account__'
        config.log_level = 'debug'
        server = ProxyServer(config)
        server.start()
        client = None
        try:
            client, _headers = connect_ws(config.ws_port, tls=False)
            client.send(build_client_version(handshake_protocols=(5,), mc_protocols=(774,)))
            version = client.recv(timeout=5.0)
            self.assertIsNotNone(version)
            self.assertEqual(version[0], eagler.PROTOCOL_SERVER_VERSION)
            self.assertEqual(int.from_bytes(version[3:5], 'big'), 774)

            client.send(build_request_login(username='Browser'))
            deadline = time.time() + 5.0
            while not backend.acked and time.time() < deadline:
                time.sleep(0.02)
            self.assertTrue(backend.acked)               # the proxy acknowledged in the client's place
            self.assertFalse(backend.dropped_early)

            allow = client.recv(timeout=5.0)
            self.assertEqual(allow[0], eagler.PROTOCOL_SERVER_ALLOW_LOGIN)

            client.send(bytes([eagler.PROTOCOL_CLIENT_FINISH_LOGIN]))
            finish = client.recv(timeout=5.0)
            self.assertEqual(finish, bytes([eagler.PROTOCOL_SERVER_FINISH_LOGIN]))
            buffered = client.recv(timeout=5.0)          # configuration data buffered before the finish
            self.assertEqual(buffered, config_blob)

            # client -> target keeps flowing after the configuration switch
            echo = unframed(vanilla.pack(0x02, b'\x05abcde'))
            client.send(echo)
            deadline = time.time() + 5.0
            while not backend.after_ack and time.time() < deadline:
                time.sleep(0.02)
            self.assertEqual([p.payload for p in backend.after_ack], [echo])
        finally:
            if client is not None:
                client.close()
            server.stop()
            backend.close()

    def test_server_list_query_waits_for_first_status(self):
        """A cache miss waits for the live query instead of showing a fake no-MOTD."""
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(('127.0.0.1', 0))
        listener.listen(1)
        target_port = listener.getsockname()[1]

        def slow_target():
            try:
                connection, _ = listener.accept()
                try:
                    time.sleep(0.6)
                finally:
                    connection.close()
            except OSError:
                pass

        threading.Thread(target=slow_target, daemon=True).start()
        config = Config()
        config.tls_enabled = False
        config.wss_port = 0
        config.ws_port = free_port()
        config.listen_host = '127.0.0.1'
        config.target = '127.0.0.1:%d' % target_port
        config.use_srv = False
        config.status_cache = False
        config.server_brand = 'Paper'
        config.server_brand_version = '1.8.8'
        server = ProxyServer(config)
        server.start()
        client = None
        try:
            client, _headers = connect_ws(config.ws_port, tls=False)
            started = time.time()
            client.send(b'Accept: MOTD', opcode=wsproto.OP_TEXT)
            frame = client.recv(timeout=5.0)
            elapsed = time.time() - started
            self.assertIsNotNone(frame)
            self.assertGreaterEqual(elapsed, 0.5, 'the first answer must use the target status')
            data = json.loads(frame.decode('utf-8'))
            self.assertEqual(data['type'], 'MOTD')
            self.assertEqual(data['brand'], 'Paper')
            self.assertNotEqual(data['data']['motd'], [tr('proxy.query.no_motd')])
        finally:
            if client is not None:
                client.close()
            server.stop()
            listener.close()

    def test_server_list_query_uses_live_status_on_cache_miss(self):
        """A cache miss asks the target and returns its real MOTD.

        The client's ServerQueryImpl sends one text frame on connect and waits
        for one JSON text frame; the "details" shown on hover in the server list
        are data.players.
        """
        config = Config()
        config.tls_enabled = False
        config.wss_port = 0
        config.ws_port = free_port()
        config.listen_host = '127.0.0.1'
        config.target = '127.0.0.1:25565'
        config.use_srv = False
        config.status_cache = False
        config.server_brand = 'Paper'
        config.server_brand_version = '1.8.8'
        status = {
            'ok': True,
            'ms': 12.0,
            'status': {
                'description': 'A real MOTD',
                'version': {'name': '1.20.4'},
                'players': {'online': 3, 'max': 20, 'sample': [{'name': 'Alex'}]},
            },
            'error': '',
        }
        server = ProxyServer(config)
        server.start()
        client = None
        try:
            with unittest.mock.patch('proxy.resolver.query_status', return_value=status):
                client, _headers = connect_ws(config.ws_port, tls=False)
                client.send(b'Accept: MOTD', opcode=wsproto.OP_TEXT)
                frame = client.recv(timeout=5.0)
            self.assertIsNotNone(frame)
            data = json.loads(frame.decode('utf-8'))
            self.assertEqual(data['type'], 'MOTD')
            self.assertEqual(data['brand'], 'Paper')
            self.assertEqual(data['name'], 'Paper')
            self.assertEqual(data['vers'], '1.8.8')
            self.assertEqual(data['data']['motd'], ['A real MOTD'])
            self.assertEqual(data['data']['players'], ['Alex'])
            self.assertEqual(data['data']['online'], 3)
            self.assertEqual(data['data']['max'], 20)
            self.assertFalse(data['data']['icon'])
        finally:
            if client is not None:
                client.close()
            server.stop()

    def test_status_cache_disabled_queries_every_time(self):
        """Caching is removed: every MOTD/status call queries the target live."""
        status = {
            'ok': True,
            'ms': 1.0,
            'status': {'description': 'Live MOTD'},
            'error': '',
        }
        config = Config()
        config.status_cache = True   # kept for config compat; ignored at runtime
        config.status_cache_ttl = 30
        server = ProxyServer(config)

        with unittest.mock.patch('proxy.resolver.query_status', return_value=status) as query:
            first = server.target_status('127.0.0.1', 25565)
            second = server.target_status('127.0.0.1', 25565)
            self.assertEqual(first['status']['description'], 'Live MOTD')
            self.assertEqual(second['status']['description'], 'Live MOTD')
            # No cache: every call performs a fresh query.
            self.assertEqual(query.call_count, 2)

            q1 = server.status_for_query('127.0.0.1', 25565)
            q2 = server.status_for_query('127.0.0.1', 25565)
            self.assertEqual(q1['status']['description'], 'Live MOTD')
            self.assertEqual(q2['status']['description'], 'Live MOTD')
            self.assertEqual(query.call_count, 4)
            # Nothing is ever stored.
            self.assertEqual(server._status_cache, {})


class TranslatorSchedulingTests(unittest.IsolatedAsyncioTestCase):
    """The play path must not pay a thread-pool round trip per packet."""

    def make_bridge(self) -> Bridge:
        bridge = object.__new__(Bridge)
        bridge._translator_direct = False
        bridge._translator_inflight = 0
        return bridge

    async def test_login_stays_on_worker_but_play_switches_to_direct(self):
        bridge = self.make_bridge()
        translator = unittest.mock.Mock()
        translator.phase = 'login'
        translator.login_done = False
        threaded = []

        def feed(data: bytes) -> bytes:
            return b'ok:' + data

        async def fake_to_thread(func, data):
            threaded.append(data)
            return func(data)

        with unittest.mock.patch.object(proxy_core.asyncio, 'to_thread', fake_to_thread):
            self.assertEqual(
                await bridge._translator_call(feed, b'login', translator), b'ok:login')
            self.assertEqual(threaded, [b'login'])
            self.assertFalse(bridge._translator_direct)

            translator.phase = 'play'
            translator.login_done = True
            self.assertEqual(
                await bridge._translator_call(feed, b'first', translator), b'ok:first')
            self.assertEqual(threaded, [b'login', b'first'])
            self.assertTrue(bridge._translator_direct)

            # Once every worker call has returned, later packets stay on the
            # event loop; no executor hop and no lock handed across threads.
            self.assertEqual(
                await bridge._translator_call(feed, b'second', translator), b'ok:second')
            self.assertEqual(threaded, [b'login', b'first'])


class ConnectionLimitTests(unittest.TestCase):
    def test_limit_refuses_extra_upgrades_and_frees_slots(self):
        """max_connections caps simultaneous sessions at the upgrade.

        websockets 17 no longer takes max_connections, so the cap lives in the
        HTTP handler: a full listener answers 503 instead of completing a
        WebSocket handshake, and closing a session frees its slot again.
        """
        target = FakeVanillaServer()
        config = Config()
        config.tls_enabled = False
        config.wss_port = 0
        config.ws_port = free_port()
        config.listen_host = '127.0.0.1'
        config.target = '127.0.0.1:%d' % target.port
        config.use_srv = False
        config.max_connections = 1
        server = ProxyServer(config)
        server.start()
        first = None
        second = None
        try:
            first, _headers = connect_ws(config.ws_port, tls=False)
            deadline = time.time() + 5.0
            while time.time() < deadline and not server.list_connections():
                time.sleep(0.02)
            self.assertEqual(len(server.list_connections()), 1)

            with self.assertRaises(AssertionError) as raised:
                connect_ws(config.ws_port, tls=False)
            self.assertIn('503', str(raised.exception))

            first.close()
            first = None
            deadline = time.time() + 5.0
            while time.time() < deadline and server.list_connections():
                time.sleep(0.02)
            self.assertEqual(server.list_connections(), [])

            second, _headers = connect_ws(config.ws_port, tls=False)
            self.assertIsNotNone(second)
        finally:
            if second is not None:
                second.close()
            if first is not None:
                first.close()
            server.stop()
            target.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
