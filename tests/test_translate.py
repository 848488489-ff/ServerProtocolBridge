"""Tests for the protocol translation layer: vanilla packet codec / EaglercraftX
handshake / state machine / end-to-end.

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import socket
import sys
import threading
import time
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from proxy import crypto, eagler, vanilla, wsproto, x509  # noqa: E402
from proxy.config import Config  # noqa: E402
from proxy.i18n import tr  # noqa: E402
from proxy.logger import NullLogger  # noqa: E402
from proxy.proxy import ProxyServer  # noqa: E402
from proxy.translator import EaglerTranslator  # noqa: E402
from test_all import WsClient, connect_ws, free_port  # noqa: E402

# First data packet observed from a real MCJS client (37 bytes), kept as a regression sample
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
                 play_packets=(), greet_delay=0.0):
        self.threshold = threshold
        self.encryption = encryption
        self.kick = kick
        self.play_packets = list(play_packets)
        self.greet_delay = greet_delay
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
                        continue
                    if packet.packet_id == 0x00 and not self.username:
                        username, _ = vanilla.read_string(packet.body, 0)
                        self.username = username
                        self._after_login(conn)
                        return
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

    def test_reject_trailing_bytes(self):
        data = REAL_FIRST_PACKET + b'\x00'
        self.assertIsNone(eagler.parse_client_version(data))

    def test_reject_other_traffic(self):
        self.assertIsNone(eagler.parse_client_version(b'\x00\x00\x00\x00\x00\x00\x00\x00'))
        self.assertIsNone(eagler.parse_client_version(b''))
        self.assertIsNone(eagler.parse_client_version(REAL_FIRST_PACKET[:10]))

    def test_select_lowest_when_only_v3(self):
        version = eagler.parse_client_version(build_client_version(handshake_protocols=(3,)))
        self.assertEqual(eagler.select_protocols(version), (3, 47))

    def test_server_version_formats(self):
        v3 = eagler.pack_server_version(3, 47, 'MCJS-Proxy', '1.0')
        self.assertEqual(v3[0], eagler.PROTOCOL_SERVER_VERSION)
        self.assertEqual(int.from_bytes(v3[1:3], 'big'), 3)
        self.assertEqual(int.from_bytes(v3[3:5], 'big'), 47)
        self.assertEqual(v3[-3:], b'\x00\x00\x00')      # authMethod + salt length
        v5 = eagler.pack_server_version(5, 47, 'MCJS-Proxy', '1.0')
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

    def test_sanitize_username(self):
        self.assertEqual(eagler.sanitize_username('Tester'), 'Tester')
        self.assertEqual(eagler.sanitize_username('a'), 'aMCJSEagler'[:16])
        self.assertEqual(eagler.sanitize_username('名字abc'), 'abc'[:16])
        self.assertTrue(eagler.USERNAME_PATTERN.match(eagler.sanitize_username('名字123')))


# ---------------------------------------------------------------- State machine


class TranslatorUnitTests(unittest.TestCase):
    def make(self, **kwargs):
        sent: list[bytes] = []            # sent to the browser
        to_backend: list[bytes] = []      # proxy-written straight to the target server (encryption response)
        closed: list[str] = []
        translator = EaglerTranslator(
            target_host='mc244.com', target_port=25565,
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
        self.assertEqual(address, 'mc244.com')
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
        translator.feed_server(build_disconnect('服务器已满'))
        self.assertEqual(sent[-1][0], eagler.PROTOCOL_SERVER_DENY_LOGIN)
        length = int.from_bytes(sent[-1][1:3], 'big')      # u16 length since v3
        # the kick reason is forwarded verbatim (the client parses it as JSON), so read it as JSON here too
        self.assertEqual(json.loads(sent[-1][3:3 + length].decode('utf-8'))['text'], '服务器已满')

    def test_plain_kick_reason_is_wrapped_as_json(self):
        """When the target server's reason is not JSON it must be wrapped in {'text': ...} before sending, or the client reports Invalid packet."""
        translator, sent, _closed, _backend = self.make()
        translator.feed_client(REAL_FIRST_PACKET)
        translator.feed_client(build_request_login())
        reason = '你被管理员踢出了游戏'
        body = vanilla.write_varint(len(reason.encode())) + reason.encode()
        translator.feed_server(vanilla.pack(vanilla.LOGIN_DISCONNECT, body))
        self.assertEqual(sent[-1][0], eagler.PROTOCOL_SERVER_DENY_LOGIN)
        length = int.from_bytes(sent[-1][1:3], 'big')
        body = sent[-1][3:3 + length].decode('utf-8')
        self.assertEqual(json.loads(body), {'text': reason})

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

    def test_spoof_brand_is_injected_and_client_brand_is_dropped(self):
        """Client-brand spoofing: inject an MC|Brand from config after login and drop the client's own.

        Clients (especially the EaglercraftX family) send an MC|Brand of their
        own after login, with a value like "EaglercraftX"; that is what plugins
        on the target server see as the "client brand" -- so verbatim forwarding
        is replaced with a config-driven declaration.
        """
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
        self.assertEqual(translator.feed_client(plugin), b'')
        self.assertEqual(to_backend, [])

    def test_version_mismatch(self):
        translator, sent, _closed, _backend = self.make()
        packet = build_client_version(handshake_protocols=(3, 4, 5), mc_protocols=(340,))
        translator.feed_client(packet)
        self.assertEqual(sent[0][0], eagler.PROTOCOL_VERSION_MISMATCH)
        self.assertEqual(translator.phase, 'closed')

    def test_bad_username_is_replaced(self):
        translator, _sent, _closed, _backend = self.make()
        translator.feed_client(REAL_FIRST_PACKET)
        translator.feed_client(build_request_login(username='a'))
        self.assertTrue(eagler.USERNAME_PATTERN.match(translator.username))
        self.assertEqual(translator.uuid, eagler.offline_uuid(translator.username))

    def test_empty_username_uses_handshake_name(self):
        """Real MCJS login requests carry an empty name; fall back to authUsername from the handshake packet."""
        translator, _sent, _closed, _backend = self.make()
        self.assertEqual(translator.feed_client(REAL_FIRST_PACKET), b'')
        translator.feed_client(build_request_login(username=''))
        self.assertEqual(translator.username, 'nopp')
        self.assertEqual(translator.uuid, eagler.offline_uuid('nopp'))


# ---------------------------------------------------------------- End-to-end


class TranslateEndToEndTests(unittest.TestCase):
    def test_browser_client_through_proxy(self):
        join_game = unframed(vanilla.pack(vanilla.PLAY_JOIN_GAME, b'\x00' * 12 + b'mc244'))
        backend = FakeVanillaServer(threshold=256, play_packets=[join_game])
        config = Config()
        config.tls_enabled = False
        config.wss_port = 0
        config.ws_port = free_port()
        config.listen_host = '127.0.0.1'
        config.target = '127.0.0.1:%d' % backend.port
        config.use_srv = False
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
            # After login the proxy first injects an MC|Brand from config (client
            # brand spoofing), then the play data.
            keep_alive = vanilla.pack(vanilla.PLAY_KEEP_ALIVE, b'\x00\x00\x00\x07')
            client.send(unframed(keep_alive))
            got = backend.read_packets(2)
            self.assertEqual(len(got), 2)
            self.assertEqual(got[0].packet_id, vanilla.CLIENT_PLUGIN_MESSAGE)
            self.assertIn(b'MC|Brand', got[0].payload)
            self.assertTrue(got[0].payload.endswith(b'vanilla'), got[0].payload)   # the default spoof value
            self.assertEqual([p.payload for p in got[1:]], [unframed(keep_alive)])

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

    def test_server_list_query_is_answered_locally(self):
        """Server-list queries (Accept: MOTD) are answered locally, without
        connecting to the target; the details carry the "current server address".

        The client's ServerQueryImpl sends one text frame on connect and waits
        for one JSON text frame; the "details" shown on hover in the server list
        are data.players.
        """
        config = Config()
        config.tls_enabled = False
        config.wss_port = 0
        config.ws_port = free_port()
        config.listen_host = '127.0.0.1'
        config.target = '127.0.0.1:1'          # deliberately unreachable port: a list query must not connect to it
        config.use_srv = False
        config.server_brand = 'Paper'
        config.server_brand_version = '1.8.8'
        server = ProxyServer(config)
        server.start()
        client = None
        try:
            client, _headers = connect_ws(config.ws_port, tls=False)
            client.send(b'Accept: MOTD', opcode=wsproto.OP_TEXT)
            frame = client.recv(timeout=5.0)
            self.assertIsNotNone(frame)
            data = json.loads(frame.decode('utf-8'))
            self.assertEqual(data['type'], 'MOTD')
            self.assertEqual(data['brand'], 'Paper')
            self.assertEqual(data['name'], 'Paper')
            self.assertEqual(data['vers'], '1.8.8')
            self.assertEqual(data['data']['players'][0],
                             tr('proxy.query.target', address='127.0.0.1:1'))
            self.assertFalse(data['data']['icon'])
            self.assertEqual(data['data']['online'], 0)
        finally:
            if client is not None:
                client.close()
            server.stop()


if __name__ == '__main__':
    unittest.main(verbosity=2)
