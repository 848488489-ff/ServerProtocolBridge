"""Self-check suite: stdlib unittest only, no third-party dependencies.

    python -m unittest discover -s tests -v
    python tests/test_all.py

Covers: DER encoding / self-signed certificates (including a real TLS handshake
check) / WebSocket frame codec / address and config parsing / SRV fallback /
end-to-end forwarding over wss and ws / base64 compatibility mode / path
mapping / unreachable target / large-volume data integrity.
"""

from __future__ import annotations

import base64
import concurrent.futures
import hashlib
import json
import os
import shutil
import socket
import ssl
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from proxy import certs, config as config_module, der, resolver, webauth, wsproto, x509  # noqa: E402
from proxy.config import Config  # noqa: E402
from proxy.i18n import tr  # noqa: E402
from proxy.logger import Logger  # noqa: E402
from proxy.proxy import ProxyServer  # noqa: E402


# ---------------------------------------------------------------- Helpers


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def _read_tlv(data: bytes, offset: int = 0):
    """Minimal DER reader: returns (tag, value, next offset)."""
    tag = data[offset]
    length = data[offset + 1]
    offset += 2
    if length & 0x80:
        count = length & 0x7F
        length = int.from_bytes(data[offset:offset + count], 'big')
        offset += count
    return tag, data[offset:offset + length], offset + length


def _children(data: bytes):
    items = []
    offset = 0
    while offset < len(data):
        tag, value, offset = _read_tlv(data, offset)
        items.append((tag, value))
    return items


class EchoServer:
    """Fake Minecraft server: sends a greeting right after connect, then echoes bytes back verbatim."""

    def __init__(self, greeting: bytes = b''):
        self.greeting = greeting
        self.received = bytearray()
        self.connections = 0
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(('127.0.0.1', 0))
        self._server.listen(8)
        self.port = self._server.getsockname()[1]
        self._stop = False
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        self._server.settimeout(0.3)
        while not self._stop:
            try:
                conn, _addr = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            self.connections += 1
            threading.Thread(target=self._handle, args=(conn,), daemon=True).start()

    def _handle(self, conn: socket.socket) -> None:
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        try:
            if self.greeting:
                conn.sendall(self.greeting)
            while True:
                data = conn.recv(65536)
                if not data:
                    break
                self.received.extend(data)
                conn.sendall(data)
        except OSError:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def close(self) -> None:
        self._stop = True
        try:
            self._server.close()
        except OSError:
            pass
        self._thread.join(timeout=2)


class WsClient:
    """Minimal WebSocket client used to exercise the server-side implementation."""

    def __init__(self, sock: socket.socket, initial: bytes = b''):
        self.sock = sock
        self.decoder = wsproto.FrameDecoder()
        self.inbox: list[wsproto.Frame] = []
        self.closed: tuple[int, str] | None = None
        self.eof = False
        self._lock = threading.Lock()
        # The first server frame may arrive right behind the handshake response
        # (within the same TCP segment); it must be fed into the decoder before
        # the reader thread starts -- two threads feeding the same decoder would
        # tear frames apart.
        if initial:
            self._ingest(initial)
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()

    def _ingest(self, chunk: bytes) -> None:
        for frame in self.decoder.feed(chunk):
            if frame.opcode == wsproto.OP_CLOSE:
                self.closed = wsproto.parse_close_payload(frame.payload)
            else:
                self.inbox.append(frame)

    def _reader(self) -> None:
        try:
            while True:
                chunk = self.sock.recv(65536)
                if not chunk:
                    self.eof = True
                    return
                with self._lock:
                    self._ingest(chunk)
        except (OSError, ssl.SSLError):
            self.eof = True

    def send(self, data: bytes, opcode: int = wsproto.OP_BINARY) -> None:
        self.sock.sendall(wsproto.encode_frame(opcode, data, mask=True))

    def send_fragmented(self, data: bytes, pieces: int = 4) -> None:
        step = max(1, len(data) // pieces)
        offset = 0
        first = True
        while offset < len(data):
            piece = data[offset:offset + step]
            offset += step
            self.sock.sendall(wsproto.encode_frame(
                wsproto.OP_BINARY if first else wsproto.OP_CONTINUATION, piece,
                fin=offset >= len(data), mask=True))
            first = False

    def recv(self, timeout: float = 5.0, opcode: int | None = None) -> bytes | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                for index, frame in enumerate(self.inbox):
                    if opcode is None or frame.opcode == opcode:
                        return self.inbox.pop(index).payload
            time.sleep(0.01)
        return None

    def recv_exactly(self, size: int, timeout: float = 30.0) -> bytes:
        """Receive exactly size bytes.

        The server wraps each chunk read from TCP into its own WebSocket frame,
        so the return traffic may be split across several frames; a real client
        has to reassemble them into a byte stream anyway, so do the same here.
        """
        buffer = bytearray()
        deadline = time.time() + timeout
        while len(buffer) < size and time.time() < deadline:
            frame = None
            with self._lock:
                for index, item in enumerate(self.inbox):
                    if item.opcode in (wsproto.OP_BINARY, wsproto.OP_TEXT):
                        frame = self.inbox.pop(index)
                        break
            if frame is None:
                time.sleep(0.01)
            else:
                buffer.extend(frame.payload)
        return bytes(buffer)

    def recv_text_decoded(self, size: int, timeout: float = 30.0) -> bytes:
        """Receive exactly size bytes in base64 text-frame mode (decode each frame first, then append)."""
        buffer = bytearray()
        deadline = time.time() + timeout
        while len(buffer) < size and time.time() < deadline:
            frame = None
            with self._lock:
                for index, item in enumerate(self.inbox):
                    if item.opcode in (wsproto.OP_BINARY, wsproto.OP_TEXT):
                        frame = self.inbox.pop(index)
                        break
            if frame is None:
                time.sleep(0.01)
            elif frame.opcode == wsproto.OP_TEXT:
                buffer.extend(base64.b64decode(frame.payload.decode('ascii')))
            else:
                buffer.extend(frame.payload)
        return bytes(buffer)

    def wait_close(self, timeout: float = 5.0) -> tuple[int, str] | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.closed is not None:
                return self.closed
            time.sleep(0.01)
        return None

    def close(self) -> None:
        try:
            self.sock.sendall(wsproto.encode_frame(wsproto.OP_CLOSE, wsproto.close_payload(1000, 'bye'), mask=True))
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


def connect_ws(port: int, host: str = '127.0.0.1', tls: bool = False,
               ca_file: str | None = None, subprotocol: str | None = None,
               path: str = '/', timeout: float = 8.0) -> tuple[WsClient, dict]:
    sock = socket.create_connection((host, port), timeout=timeout)
    if tls:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        if ca_file:
            context.load_verify_locations(cafile=ca_file)
        sock = context.wrap_socket(sock, server_hostname='localhost')
    key = base64.b64encode(os.urandom(16)).decode('ascii')
    request = ('GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\n'
               'Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n'
               'Sec-WebSocket-Version: 13\r\n' % (path, host, port, key))
    if subprotocol:
        request += 'Sec-WebSocket-Protocol: %s\r\n' % subprotocol
    request += '\r\n'
    sock.sendall(request.encode('ascii'))

    data = b''
    while b'\r\n\r\n' not in data:
        chunk = sock.recv(4096)
        if not chunk:
            raise AssertionError('empty handshake response')
        data += chunk
    head, rest = data.split(b'\r\n\r\n', 1)
    lines = head.decode('latin-1').split('\r\n')
    if not lines[0].startswith('HTTP/1.1 101'):
        raise AssertionError('handshake failed: %s (body=%r)' % (lines[0], rest[:200]))
    headers = {}
    for line in lines[1:]:
        if ':' in line:
            name, _, value = line.partition(':')
            headers[name.strip().lower()] = value.strip()
    headers['_request_key'] = key
    return WsClient(sock, initial=rest), headers


def http_get(port: int, path: str = '/', host: str = '127.0.0.1', timeout: float = 5.0) -> dict:
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.sendall(('GET %s HTTP/1.1\r\nHost: %s:%d\r\nConnection: close\r\n\r\n' % (path, host, port)).encode())
        data = b''
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            data += chunk
    head, _, body = data.partition(b'\r\n\r\n')
    return {'head': head.decode('latin-1'), 'body': body}


# ---------------------------------------------------------------- DER / X.509


class DerTests(unittest.TestCase):
    def test_integer_encoding(self):
        self.assertEqual(der.integer(2), b'\x02\x01\x02')
        self.assertEqual(der.integer(0), b'\x02\x01\x00')
        self.assertEqual(der.integer(0x80), b'\x02\x02\x00\x80')
        self.assertEqual(der.integer(b'\x00\x00\xff'), b'\x02\x02\x00\xff')  # a leading 1 bit needs a 0x00 pad

    def test_oid_encoding(self):
        self.assertEqual(der.oid('1.2.840.113549.1.1.11'),
                         b'\x06\x09\x2a\x86\x48\x86\xf7\x0d\x01\x01\x0b')
        self.assertEqual(der.oid('2.5.29.17'), b'\x06\x03\x55\x1d\x11')

    def test_length_encoding(self):
        self.assertEqual(der.encode_length(5), b'\x05')
        self.assertEqual(der.encode_length(200), b'\x81\xc8')
        self.assertEqual(der.encode_length(300), b'\x82\x01\x2c')

    def test_time_encoding(self):
        import datetime
        value = datetime.datetime(2026, 10, 17, 12, 34, 56)
        self.assertEqual(der.utc_time(value), b'\x17\x0d' + b'261017123456Z')


class CertificateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.cert_dir = Path(cls.tmp.name)
        cls.certificate = x509.create_self_signed_certificate(
            common_name='localhost',
            alt_names=['localhost', '127.0.0.1', '::1', 'hypixel.local'],
            days=3650,
            key_bits=2048,
        )

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def _write(self):
        cert_path = self.cert_dir / 'cert.pem'
        key_path = self.cert_dir / 'key.pem'
        cert_path.write_text(self.certificate['cert_pem'], encoding='ascii')
        key_path.write_text(self.certificate['key_pem'], encoding='ascii')
        return cert_path, key_path

    def test_pem_format(self):
        self.assertTrue(self.certificate['cert_pem'].startswith('-----BEGIN CERTIFICATE-----'))
        self.assertTrue(self.certificate['key_pem'].startswith('-----BEGIN RSA PRIVATE KEY-----'))
        self.assertEqual(x509.pem_to_der(self.certificate['cert_pem']), self.certificate['cert_der'])

    def test_openssl_can_load_certificate(self):
        """The stdlib SSLContext can load it, proving the DER structure is valid and the private key matches."""
        cert_path, key_path = self._write()
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(cert_path), str(key_path))

    def test_thumbprint(self):
        expected = hashlib.sha256(self.certificate['cert_der']).hexdigest().upper()
        actual = certs.thumbprint(self.certificate['cert_pem']).replace(':', '')
        self.assertEqual(expected, actual)

    def test_signature_verifies_against_public_key(self):
        """Extract the public key from the certificate DER and verify the self-signature really came from that key."""
        _tag, certificate, _end = _read_tlv(self.certificate['cert_der'])
        items = _children(certificate)
        tbs_value = items[0][1]
        signature = items[2][1][1:]  # BIT STRING: drop the unused-bits byte
        tbs_der = der.tlv(0x30, tbs_value)

        fields = _children(tbs_value)
        spki_children = _children(fields[6][1])          # field 7: subjectPublicKeyInfo
        rsa_key = _children(spki_children[1][1][1:])[0][1]  # BIT STRING with the unused-bits byte stripped
        rsa_fields = _children(rsa_key)                  # contents of the RSAPublicKey sequence
        modulus = int.from_bytes(rsa_fields[0][1], 'big')
        exponent = int.from_bytes(rsa_fields[1][1], 'big')

        recovered = pow(int.from_bytes(signature, 'big'), exponent, modulus).to_bytes(
            (modulus.bit_length() + 7) // 8, 'big')
        digest_info = bytes.fromhex('3031300d060960864801650304020105000420')
        self.assertTrue(recovered.startswith(b'\x00\x01\xff\xff'), 'bad PKCS#1 v1.5 padding')
        self.assertEqual(recovered[-len(digest_info) - 32:-32], digest_info)
        self.assertEqual(recovered[-32:], hashlib.sha256(tbs_der).digest())

    def test_tls_handshake_with_hostname_and_ip(self):
        """Real handshake: both the certificate chain and the SANs must be right, or check_hostname fails."""
        cert_path, key_path = self._write()
        server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(str(cert_path), str(key_path))

        for server_hostname in ('localhost', '127.0.0.1'):
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.bind(('127.0.0.1', 0))
            listener.listen(1)
            port = listener.getsockname()[1]
            error = []

            def serve():
                try:
                    with socket.socket() as conn:
                        conn.settimeout(10)
                        accepted, _ = listener.accept()
                        with server_context.wrap_socket(accepted, server_side=True) as tls_conn:
                            tls_conn.sendall(b'ok')
                except Exception as exc:  # pragma: no cover
                    error.append(exc)
                finally:
                    listener.close()

            thread = threading.Thread(target=serve, daemon=True)
            thread.start()
            try:
                client_context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                client_context.load_verify_locations(cafile=str(cert_path))
                with socket.create_connection(('127.0.0.1', port), timeout=10) as raw:
                    with client_context.wrap_socket(raw, server_hostname=server_hostname) as tls_sock:
                        self.assertEqual(tls_sock.recv(16), b'ok')
            finally:
                thread.join(timeout=10)
            self.assertEqual(error, [], 'server-side handshake error: %s' % error)

    def test_ensure_certificate_creates_files(self):
        directory = self.cert_dir / 'generated'
        info = certs.ensure_certificate(directory, common_name='localhost',
                                        extra_names=['example.test'], days=30,
                                        generator='python')
        self.assertTrue(Path(info['cert_path']).exists())
        self.assertTrue(Path(info['key_path']).exists())
        self.assertTrue(info['thumbprint'])
        again = certs.ensure_certificate(directory, common_name='localhost', generator='python')
        self.assertEqual(again['thumbprint'], info['thumbprint'], 'an existing certificate must be reused')

    def test_default_alt_names(self):
        names = certs.default_alt_names('localhost', ['extra.example', '10.0.0.5'])
        for expected in ('localhost', '127.0.0.1', '::1', 'extra.example', '10.0.0.5'):
            self.assertIn(expected, names)
        self.assertEqual(len(names), len(set(names)), 'names must not be duplicated')


# ---------------------------------------------------------------- WebSocket frames


class FrameTests(unittest.TestCase):
    def test_roundtrip_sizes(self):
        for size in (0, 1, 125, 126, 127, 1000, 65535, 65536, 200000):
            payload = os.urandom(size)
            decoder = wsproto.FrameDecoder()
            frames = decoder.feed(wsproto.encode_frame(wsproto.OP_BINARY, payload))
            self.assertEqual(len(frames), 1, 'size=%d' % size)
            self.assertEqual(frames[0].payload, payload, 'size=%d' % size)

    def test_masked_and_unmasked(self):
        payload = os.urandom(1000)
        decoder = wsproto.FrameDecoder()
        masked = wsproto.encode_frame(wsproto.OP_BINARY, payload, mask=True)
        self.assertEqual(decoder.feed(masked)[0].payload, payload)
        decoder = wsproto.FrameDecoder()
        self.assertEqual(decoder.feed(wsproto.encode_frame(wsproto.OP_BINARY, payload))[0].payload, payload)

    def test_byte_by_byte_feed(self):
        payload = os.urandom(700)
        raw = wsproto.encode_frame(wsproto.OP_BINARY, payload, mask=True)
        decoder = wsproto.FrameDecoder()
        frames = []
        for index in range(len(raw)):
            frames.extend(decoder.feed(raw[index:index + 1]))
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].payload, payload)

    def test_fragmentation(self):
        payload = os.urandom(5000)
        raw = (wsproto.encode_frame(wsproto.OP_BINARY, payload[:1000], fin=False)
               + wsproto.encode_frame(wsproto.OP_CONTINUATION, payload[1000:3000], fin=False)
               + wsproto.encode_frame(wsproto.OP_CONTINUATION, payload[3000:], fin=True))
        decoder = wsproto.FrameDecoder()
        frames = decoder.feed(raw)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].opcode, wsproto.OP_BINARY)
        self.assertEqual(frames[0].payload, payload)

    def test_control_frames_interleaved(self):
        raw = (wsproto.encode_frame(wsproto.OP_BINARY, b'x', fin=False)
               + wsproto.encode_frame(wsproto.OP_PING, b'ping')
               + wsproto.encode_frame(wsproto.OP_CONTINUATION, b'y', fin=True))
        frames = wsproto.FrameDecoder().feed(raw)
        self.assertEqual([f.opcode for f in frames], [wsproto.OP_PING, wsproto.OP_BINARY])
        self.assertEqual(frames[1].payload, b'xy')

    def test_protocol_errors(self):
        cases = {
            'RSV bit set': bytes([0xC0, 0x00]),
            'unknown opcode': wsproto.encode_frame(0x3, b'x'),
            'fragmented control frame': wsproto.encode_frame(wsproto.OP_PING, b'x', fin=False),
            'oversized control frame': bytes([0x89, 126, 0x01, 0x00]),
            'continuation without start': wsproto.encode_frame(wsproto.OP_CONTINUATION, b'x'),
        }
        for name, raw in cases.items():
            with self.assertRaises(wsproto.ProtocolError, msg=name):
                wsproto.FrameDecoder().feed(raw)

    def test_payload_limit(self):
        with self.assertRaises(wsproto.ProtocolError):
            wsproto.FrameDecoder(max_payload=1024).feed(
                wsproto.encode_frame(wsproto.OP_BINARY, b'a' * 2048))

    def test_close_payload(self):
        self.assertEqual(wsproto.parse_close_payload(wsproto.close_payload(1011, 'boom')), (1011, 'boom'))
        self.assertEqual(wsproto.parse_close_payload(b''), (1005, ''))

    def test_handshake_accept_key(self):
        # RFC 6455 example
        self.assertEqual(wsproto.compute_accept_key('dGhlIHNhbXBsZSBub25jZQ=='), 's3pPLMBiTxaQ9kYGzzhZRbK+xOo=')

    def test_first_subprotocol(self):
        self.assertEqual(wsproto.first_subprotocol('binary, base64'), 'binary')
        self.assertIsNone(wsproto.first_subprotocol(None))
        self.assertIsNone(wsproto.first_subprotocol(' , '))


# ---------------------------------------------------------------- Logger


class LoggerLevelTests(unittest.TestCase):
    def test_set_level_applies_to_the_next_line(self):
        lines = []
        logger = Logger('warn', callback=lambda level, text: lines.append(level),
                        echo=False)
        logger.info('hidden')
        logger.warn('shown')
        logger.set_level('debug')
        logger.debug('visible now')
        self.assertEqual(lines, ['warn', 'debug'])


# ---------------------------------------------------------------- Configuration


class ConfigTests(unittest.TestCase):
    def test_parse_address(self):
        self.assertEqual(config_module.parse_address('mc.hypixel.net'), ('mc.hypixel.net', None))
        self.assertEqual(config_module.parse_address('mc.hypixel.net:25565'), ('mc.hypixel.net', 25565))
        self.assertEqual(config_module.parse_address('mc://mc.hypixel.net:25565'), ('mc.hypixel.net', 25565))
        self.assertEqual(config_module.parse_address('[::1]:25566'), ('::1', 25566))
        self.assertEqual(config_module.parse_address('example.test/path'), ('example.test', None))
        self.assertEqual(config_module.parse_address('1.2.3.4', 25565), ('1.2.3.4', 25565))
        with self.assertRaises(ValueError):
            config_module.parse_address('   ')

    def test_routes_text_roundtrip(self):
        text = '/hypixel=mc.hypixel.net:25565\n/本地=127.0.0.1:25565\n'
        routes = config_module.parse_routes_text(text)
        self.assertEqual(routes, {'/hypixel': 'mc.hypixel.net:25565', '/本地': '127.0.0.1:25565'})
        self.assertEqual(config_module.parse_routes_text(config_module.format_routes_text(routes)), routes)
        with self.assertRaises(ValueError):
            config_module.parse_routes_text('缺少等号')

    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'config.json'
            config = Config()
            config.target = 'mc.hypixel.net:25565'
            config.routes = {'/a': '127.0.0.1:25566'}
            config.wss_port = 9443
            config.status_cache = False
            config.status_cache_ttl = 120
            config.spoof_client = 'forge-1.8'
            config.save(path)
            loaded = Config.load(path)
            self.assertEqual(loaded.target, config.target)
            self.assertEqual(loaded.routes, config.routes)
            self.assertEqual(loaded.wss_port, 9443)
            self.assertFalse(loaded.status_cache)
            self.assertEqual(loaded.status_cache_ttl, 120)
            self.assertEqual(loaded.config_version, 2)
            self.assertEqual(loaded.spoof_client, 'forge-1.8')

    def test_unknown_keys_ignored(self):
        config = Config.from_dict({'target': 'a:1', '不存在的键': 5, 'wss_port': '1234'})
        self.assertEqual(config.target, 'a:1')
        self.assertEqual(config.wss_port, 1234)

    def test_validate(self):
        config = Config()
        self.assertTrue(config.status_cache)
        self.assertEqual(config.status_cache_ttl, 30)
        self.assertEqual(config.target, '')
        self.assertTrue(any(tr('core.config.target_empty') in item
                            for item in config.validate()))
        config.target = 'play.example.net'
        self.assertEqual(config.validate(), [])
        config.wss_port = 70000
        expected = tr('core.config.port_range', name=tr('core.config.port_wss'))
        self.assertTrue(any(expected in item for item in config.validate()))
        config = Config()
        config.target = '  '
        expected = tr('core.config.target_empty')
        self.assertTrue(any(expected in item for item in config.validate()))
        config = Config()
        config.language = 'fr'
        self.assertTrue(any(tr('core.config.language_invalid') in item
                            for item in config.validate()))
        config = Config()
        config.status_cache_ttl = 0
        self.assertTrue(any(tr('core.config.status_cache_ttl_range') in item
                            for item in config.validate()))
        config.status_cache_ttl = 86401
        self.assertTrue(any(tr('core.config.status_cache_ttl_range') in item
                            for item in config.validate()))

    def test_spoof_presets(self):
        config = Config()
        self.assertEqual(config.spoof_client, 'off')
        self.assertEqual(config.spoof_brand, '')
        self.assertEqual(config.spoof_brand_value(), '')
        for preset, brand in (('vanilla', 'vanilla'), ('forge-1.8', 'fml,forge'),
                              ('forge-1.13', 'forge'), ('neoforge', 'neoforge'),
                              ('fabric', 'fabric')):
            config.spoof_client = preset
            self.assertEqual(config.spoof_brand_value(), brand)
        config.spoof_client = 'off'
        self.assertEqual(config.spoof_brand_value(), '')
        config.spoof_client = 'forge-1.8'
        config.spoof_brand = 'forge/1.8.8'          # an explicit brand overrides the preset default
        self.assertEqual(config.spoof_brand_value(), 'forge/1.8.8')

    def test_spoof_client_validation(self):
        config = Config()
        config.target = 'play.example.net'
        self.assertEqual(config.validate(), [])
        config.spoof_client = 'paper'
        expected = tr('core.config.spoof_client_invalid',
                      choices=' / '.join(config_module.SPOOF_CLIENTS))
        self.assertTrue(any(expected in item for item in config.validate()))

    def test_legacy_vanilla_brand_migrates_to_the_new_default(self):
        """A pre-1.1.3 config.json has no preset and carried the old literal default
        "vanilla"; it must fall back to the current no-spoof default instead of
        sending a brand the user never chose."""
        config = Config.from_dict({'target': 'a:1', 'spoof_brand': 'vanilla'})
        self.assertEqual(config.spoof_client, 'off')
        self.assertEqual(config.spoof_brand, '')
        self.assertEqual(config.spoof_brand_value(), '')
        config = Config.from_dict({'target': 'a:1', 'spoof_brand': 'Paper'})
        self.assertEqual(config.spoof_brand, 'Paper')
        self.assertEqual(config.spoof_brand_value(), '')

    def test_legacy_forge_default_migrates_to_off(self):
        """1.1.5.2 changes the default from forge-1.8 to off.  Old files that
        never chose a custom brand must stop sending Forge fingerprints, while
        a deliberate preset (config_version 2) and a custom brand survive."""
        config = Config.from_dict({'target': 'a:1', 'spoof_client': 'forge-1.8',
                                   'spoof_brand': ''})
        self.assertEqual(config.spoof_client, 'off')
        self.assertEqual(config.spoof_brand_value(), '')

        config = Config.from_dict({'target': 'a:1', 'config_version': 2,
                                   'spoof_client': 'forge-1.8', 'spoof_brand': ''})
        self.assertEqual(config.spoof_client, 'forge-1.8')
        self.assertEqual(config.spoof_brand_value(), 'fml,forge')

        config = Config.from_dict({'target': 'a:1', 'spoof_client': 'forge-1.8',
                                   'spoof_brand': 'forge/1.8.8'})
        self.assertEqual(config.spoof_client, 'forge-1.8')
        self.assertEqual(config.spoof_brand_value(), 'forge/1.8.8')

    def test_cli_spoof_client_argument(self):
        from proxy.cli import apply_arguments, build_parser

        config = apply_arguments(Config(), build_parser().parse_args(['--spoof-client', 'vanilla']))
        self.assertEqual(config.spoof_client, 'vanilla')
        self.assertEqual(config.spoof_brand_value(), 'vanilla')
        config = apply_arguments(Config(), build_parser().parse_args(['--no-spoof-brand']))
        self.assertEqual(config.spoof_client, 'off')
        self.assertEqual(config.spoof_brand_value(), '')

    def test_spoof_preset_dropdown_labels_roundtrip(self):
        """The settings window edits the spoof preset through a dropdown: every
        label must map back to its code, whichever language is active now."""
        from proxy import gui_ctk as gui
        from proxy.i18n import get_language, set_language

        self.addCleanup(set_language, get_language())
        labels_by_language = {}
        for code in ('en', 'zh'):
            set_language(code)
            labels = [gui.spoof_label(preset) for preset in config_module.SPOOF_CLIENTS]
            labels_by_language[code] = labels
            self.assertEqual(len(set(labels)), len(labels), 'duplicate dropdown labels in %s' % code)

        # A language switch can leave the combobox showing the previous
        # language's label until the form is rebuilt; it must still map back.
        for active in ('en', 'zh'):
            set_language(active)
            for index, preset in enumerate(config_module.SPOOF_CLIENTS):
                for label_language in ('en', 'zh'):
                    label = labels_by_language[label_language][index]
                    self.assertEqual(gui.spoof_code(label), preset,
                                     '%r -> %s (active %s)' % (label, preset, active))

    def test_describe_and_urls(self):
        config = Config()
        self.assertEqual(config.target, '')
        config.target = 'play.example.net'
        self.assertIn('SRV', config.describe_target())      # no port, so SRV is used
        config.target = '127.0.0.1:25565'
        self.assertEqual(config.describe_target(), '127.0.0.1:25565')
        self.assertEqual(config.wss_url(), 'wss://127.0.0.1:8443')
        config.wss_port = 0
        config.ws_port = 0
        self.assertIsNone(config.wss_url())


# ---------------------------------------------------------------- Web UI auth


class WebAuthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='spb-auth-'))
        self._original_path = webauth.auth_path
        webauth.auth_path = lambda: self.tmp / 'web_auth.json'
        webauth.clear_failures('')

    def tearDown(self):
        webauth.auth_path = self._original_path
        webauth.clear_failures('')
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_disabled_by_default(self):
        self.assertFalse(webauth.is_enabled())
        self.assertFalse(webauth.has_password())
        self.assertEqual(webauth.state(), {'enabled': False, 'has_password': False})

    def test_password_is_hashed_and_verified(self):
        webauth.set_password('hunter22')
        self.assertTrue(webauth.is_enabled())
        self.assertTrue(webauth.verify('hunter22'))
        self.assertFalse(webauth.verify('hunter23'))
        raw = (self.tmp / 'web_auth.json').read_text(encoding='utf-8')
        self.assertNotIn('hunter22', raw)
        webauth.disable()
        self.assertFalse(webauth.is_enabled())
        self.assertFalse(webauth.verify('hunter22'))

    def test_login_is_enforced_by_the_server(self):
        from proxy.web import create_app

        app = create_app()
        app.testing = True
        owner = app.test_client()
        self.assertEqual(owner.get('/api/status').status_code, 200)
        self.assertEqual(owner.post('/api/auth', json={
            'enabled': True, 'password': 'abcd1234'}).status_code, 200)

        anonymous = app.test_client()
        self.assertEqual(anonymous.get('/api/status').status_code, 401)
        self.assertEqual(anonymous.get('/api/config').status_code, 401)
        self.assertEqual(anonymous.post('/api/auth', json={
            'enabled': False}).status_code, 401)
        page = anonymous.get('/')
        self.assertEqual(page.status_code, 302)
        self.assertTrue(page.headers['Location'].startswith('/login'))

        failed = anonymous.post('/login', data={'password': 'wrong'})
        self.assertIn(tr('web.login_failed'), failed.get_data(as_text=True))
        self.assertEqual(anonymous.get('/api/status').status_code, 401)

        signed_in = anonymous.post('/login', data={'password': 'abcd1234'})
        self.assertEqual(signed_in.status_code, 302)
        self.assertEqual(anonymous.get('/api/status').status_code, 200)
        self.assertEqual(anonymous.post('/api/logout').status_code, 200)
        self.assertEqual(anonymous.get('/api/status').status_code, 401)

        self.assertEqual(owner.post('/api/auth', json={'enabled': False}).status_code, 200)
        self.assertEqual(anonymous.get('/api/status').status_code, 200)

    def test_login_throttling(self):
        for _ in range(webauth.LOCK_AFTER):
            webauth.record_failure('203.0.113.9')
        self.assertGreater(webauth.throttle_remaining('203.0.113.9'), 0)
        webauth.clear_failures('203.0.113.9')
        self.assertEqual(webauth.throttle_remaining('203.0.113.9'), 0)


# ---------------------------------------------------------------- DNS / SRV


class ResolverTests(unittest.TestCase):
    def test_explicit_port_skips_dns(self):
        self.assertEqual(resolver.resolve_target('example.test', 12345), ('example.test', 12345))

    def test_fallback_when_dns_unreachable(self):
        original = resolver.system_nameservers
        resolver.system_nameservers = lambda: ['127.0.0.1']  # guaranteed unreachable, keeps the test offline-capable
        try:
            logger = Logger('error', echo=False)
            self.assertEqual(resolver.resolve_target('example.test', None, logger=logger, timeout=0.2),
                             ('example.test', 25565))
        finally:
            resolver.system_nameservers = original

    def test_pick_srv_priority_and_weight(self):
        records = [
            {'priority': 10, 'weight': 1, 'port': 25565, 'target': 'low.example'},
            {'priority': 20, 'weight': 1, 'port': 25566, 'target': 'high.example'},
        ]
        self.assertEqual(resolver.pick_srv(records), ('low.example', 25565))
        self.assertIsNone(resolver.pick_srv([]))

    def test_system_nameservers_returns_something(self):
        servers = resolver.system_nameservers()
        self.assertTrue(servers)
        for item in servers:
            self.assertRegex(item, r'^\d{1,3}(\.\d{1,3}){3}$')


# ---------------------------------------------------------------- End-to-end forwarding


class ProxyEndToEndTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.cert_dir = Path(cls.tmp.name) / 'certs'
        cls.backend = EchoServer(greeting=b'HELLO-FROM-SERVER')
        cls.log_lines: list[str] = []

        def callback(level, text):
            cls.log_lines.append(text)

        cls.config = Config()
        cls.config.target = '127.0.0.1:%d' % cls.backend.port
        cls.config.listen_host = '127.0.0.1'
        cls.config.wss_port = free_port()
        cls.config.ws_port = free_port()
        cls.config.cert_dir = str(cls.cert_dir)
        cls.config.cert_generator = 'python'
        cls.config.heartbeat_sec = 1
        cls.config.connect_timeout = 3
        cls.server = ProxyServer(cls.config, Logger('debug', callback=callback, echo=False))
        cls.info = cls.server.start()
        cls.ca_file = cls.server.certificate['cert_path']

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()
        cls.backend.close()
        cls.tmp.cleanup()

    def test_describe(self):
        self.assertTrue(self.info['running'])
        self.assertIn('wss://127.0.0.1:%d' % self.config.wss_port, self.info['listeners'])
        self.assertTrue(self.info['certificate']['thumbprint'])

    def test_discard_future_result_survives_cancellation(self):
        """The done callback ProxyServer.stop() attaches retrieves the shutdown result;
        a future cancelled while its event loop shuts down must not make the callback
        raise CancelledError (printed as "exception calling callback for <Future ...>").
        """
        from proxy.proxy import _discard_future_result

        cancelled = concurrent.futures.Future()
        cancelled.cancel()
        _discard_future_result(cancelled)            # must not raise
        failed = concurrent.futures.Future()
        failed.set_exception(RuntimeError('shutdown failed'))
        _discard_future_result(failed)               # retrieved, must not raise

    def test_websocket_handshake_over_wss(self):
        client, headers = connect_ws(self.config.wss_port, tls=True, ca_file=self.ca_file,
                                     subprotocol='binary')
        try:
            self.assertEqual(headers.get('sec-websocket-accept'),
                             wsproto.compute_accept_key(headers['_request_key']))
            self.assertEqual(headers.get('sec-websocket-protocol'), 'binary')
            self.assertNotIn('sec-websocket-extensions', headers)  # compression stays off
            self.assertEqual(client.recv_exactly(len(b'HELLO-FROM-SERVER')),
                             b'HELLO-FROM-SERVER')
        finally:
            client.close()

    def test_plain_websocket(self):
        client, _headers = connect_ws(self.config.ws_port)
        try:
            self.assertEqual(client.recv_exactly(len(b'HELLO-FROM-SERVER')),
                             b'HELLO-FROM-SERVER')
            payload = os.urandom(2048)
            client.send(payload)
            self.assertEqual(client.recv_exactly(len(payload)), payload)
        finally:
            client.close()

    def test_large_payload_integrity(self):
        client, _headers = connect_ws(self.config.ws_port)
        try:
            client.recv_exactly(len(b'HELLO-FROM-SERVER'))
            payload = os.urandom(1024 * 1024)
            client.send(payload)
            received = client.recv_exactly(len(payload))
            self.assertEqual(hashlib.sha256(received).hexdigest(),
                             hashlib.sha256(payload).hexdigest())
        finally:
            client.close()

    def test_fragmented_client_frames(self):
        client, _headers = connect_ws(self.config.ws_port)
        try:
            client.recv_exactly(len(b'HELLO-FROM-SERVER'))
            payload = os.urandom(200000)
            client.send_fragmented(payload, pieces=5)
            self.assertEqual(client.recv_exactly(len(payload)), payload)
        finally:
            client.close()

    def test_two_concurrent_connections(self):
        first, _ = connect_ws(self.config.ws_port)
        second, _ = connect_ws(self.config.ws_port)
        try:
            self.assertEqual(first.recv_exactly(len(b'HELLO-FROM-SERVER')),
                             b'HELLO-FROM-SERVER')
            self.assertEqual(second.recv_exactly(len(b'HELLO-FROM-SERVER')),
                             b'HELLO-FROM-SERVER')
            first.send(b'ping-from-first')
            second.send(b'ping-from-second')
            self.assertEqual(first.recv_exactly(len(b'ping-from-first')), b'ping-from-first')
            self.assertEqual(second.recv_exactly(len(b'ping-from-second')), b'ping-from-second')
        finally:
            first.close()
            second.close()

    def test_status_page(self):
        # /status is JSON for programs; the human-readable page is the Web UI
        # on its own port, so the game port answers 404 for everything else.
        result = http_get(self.config.ws_port, '/status')
        self.assertIn('200 OK', result['head'])
        data = json.loads(result['body'].decode('utf-8'))
        self.assertTrue(data['running'])
        self.assertEqual(data['service'], 'server-protocol-bridge')
        self.assertEqual(data['target'], '127.0.0.1:%d' % self.backend.port)
        self.assertIn('listeners', data)
        self.assertEqual(data['target_source'], '127.0.0.1:%d' % self.backend.port)

        page = http_get(self.config.ws_port, '/')
        self.assertIn('404 Not Found', page['head'])
        self.assertIn('text/plain', page['head'])

    def test_base64_subprotocol_mode(self):
        client, headers = connect_ws(self.config.ws_port, subprotocol='base64')
        try:
            self.assertEqual(headers.get('sec-websocket-protocol'), 'base64')
            self.assertEqual(client.recv_text_decoded(len(b'HELLO-FROM-SERVER')),
                             b'HELLO-FROM-SERVER')
            payload = b'base64-mode-payload'
            client.send(base64.b64encode(payload), opcode=wsproto.OP_TEXT)
            self.assertEqual(client.recv_text_decoded(len(payload)), payload)
        finally:
            client.close()

    def test_text_frame_auto_switch(self):
        client, _headers = connect_ws(self.config.ws_port)
        try:
            payload = b'text-frame-payload'
            client.send(base64.b64encode(payload), opcode=wsproto.OP_TEXT)
            # No subprotocol was declared, so receiving a text frame auto-switches
            # to base64 mode; the server greeting and the echo may land in the
            # same frame, hence the byte-stream read.
            stream = client.recv_text_decoded(len(b'HELLO-FROM-SERVER') + len(payload))
            self.assertEqual(stream, b'HELLO-FROM-SERVER' + payload)
        finally:
            client.close()

    def test_route_mapping(self):
        other = EchoServer(greeting=b'SECOND-SERVER')
        try:
            self.config.routes = {'/second': '127.0.0.1:%d' % other.port}
            client, _headers = connect_ws(self.config.ws_port, path='/second')
            try:
                self.assertEqual(client.recv_exactly(len(b'SECOND-SERVER')), b'SECOND-SERVER')
                self.assertEqual(other.connections, 1)
            finally:
                client.close()
        finally:
            self.config.routes = {}
            other.close()

    def test_target_unreachable_closes_with_1011(self):
        dead_port = free_port()
        config = Config()
        config.tls_enabled = False
        config.target = '127.0.0.1:%d' % dead_port
        config.listen_host = '127.0.0.1'
        config.wss_port = 0
        config.ws_port = free_port()
        config.connect_timeout = 2
        config.heartbeat_sec = 0
        server = ProxyServer(config, Logger('error', echo=False))
        server.start()
        try:
            client, _headers = connect_ws(config.ws_port)
            try:
                closed = client.wait_close(10)
                self.assertIsNotNone(closed, 'a close frame is expected when the target is unreachable')
                self.assertEqual(closed[0], 1011)
            finally:
                client.close()
        finally:
            server.stop()

    def test_stats_and_route_resolution(self):
        # Routes are mutable runtime config: set them up here and assert, without relying on state left by other tests
        original = self.config.routes
        self.config.routes = {'/second': '127.0.0.1:%d' % self.backend.port}
        try:
            self.assertEqual(self.server.resolve_route('/second')['label'],
                             tr('proxy.route.path', path='/second'))
            self.assertEqual(self.server.resolve_route('/')['label'], tr('proxy.route.default'))
        finally:
            self.config.routes = original
        status = self.server.status('/')
        self.assertGreaterEqual(status['total_connections'], 1)
        self.assertGreater(status['bytes_to_client'], 0)

    def test_server_stop_closes_connections(self):
        config = Config()
        config.tls_enabled = False
        config.target = '127.0.0.1:%d' % self.backend.port
        config.listen_host = '127.0.0.1'
        config.wss_port = 0
        config.ws_port = free_port()
        config.heartbeat_sec = 0
        server = ProxyServer(config, Logger('error', echo=False))
        server.start()
        client, _headers = connect_ws(config.ws_port)
        client.recv_exactly(len(b'HELLO-FROM-SERVER'))
        server.stop()
        closed = client.wait_close(5)
        client.close()
        self.assertFalse(server.running)
        self.assertIsNotNone(closed, 'stopping the server should actively close client connections')
        self.assertIn(closed[0], (1001, 1000))

    def test_openssl_generator(self):
        if not shutil.which('openssl'):
            self.skipTest('openssl not found on this system, skipping')
        directory = Path(self.tmp.name) / 'openssl-cert'
        info = certs.ensure_certificate(directory, common_name='localhost', generator='openssl')
        self.assertEqual(info['generator'], 'openssl')
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(info['cert_path'], info['key_path'])  # loading cleanly means it is valid


if __name__ == '__main__':
    unittest.main(verbosity=2)