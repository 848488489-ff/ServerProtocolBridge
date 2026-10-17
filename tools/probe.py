"""Probe a target Minecraft server: send a vanilla login and print the server's raw replies.

    python tools/probe.py mc244.com                 :: probe each SRV node
    python tools/probe.py mc244.com:25565 --protocol 47,340,754
    python tools/probe.py mc244.com --address 127.0.0.1  :: override the address in the handshake
                                                           (to test routing / forwarding setups)

The output classifies the outcome explicitly: login success / kicked (verbatim text) / online-mode
verification required / silent disconnect / timeout. Use it to tell whether "the browser client
cannot connect" is a protocol-layer problem or the target server simply refusing us.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcjs_proxy import crypto, resolver, vanilla  # noqa: E402
from mcjs_proxy.translator import chat_to_text  # noqa: E402

RECV_TIMEOUT = 3.0          # longest wait for each recv
TOTAL_TIMEOUT = 12.0        # longest duration of one whole probe


def build_login(protocol: int, address: str, port: int, username: str) -> bytes:
    host = address.encode('utf-8')
    handshake = vanilla.pack(0x00, (
        vanilla.write_varint(protocol)
        + vanilla.write_varint(len(host)) + host
        + int(port).to_bytes(2, 'big')
        + vanilla.write_varint(2)))          # next state = login
    login_start = vanilla.pack(0x00, (
        vanilla.write_varint(len(username)) + username.encode('utf-8')))
    return handshake + login_start


def describe_packet(packet: vanilla.Packet, threshold: int) -> str:
    pid = packet.packet_id
    if pid == vanilla.LOGIN_DISCONNECT:
        try:
            text, _ = vanilla.read_string(packet.body, 0)
        except vanilla.ProtocolError:
            return 'kicked (content not parseable): %s' % packet.body[:80].hex()
        try:
            pretty = chat_to_text(json.loads(text))
        except ValueError:
            pretty = text
        return 'kicked: %s  [raw JSON: %s]' % (pretty or '(empty)', text[:200])
    if pid == vanilla.LOGIN_ENCRYPTION_REQUEST:
        return 'online-mode verification required (encryption handshake) -- an offline-mode client cannot get through'
    if pid == vanilla.LOGIN_SUCCESS:
        try:
            uuid_text, pos = vanilla.read_string(packet.body, 0)
            name, _ = vanilla.read_string(packet.body, pos)
        except vanilla.ProtocolError:
            return ('login success (content parse failed, possibly an encryption/compression state '
                    'mismatch): %s' % packet.body[:60].hex())
        return 'login success: %s (UUID %s)' % (name, uuid_text)
    if pid == vanilla.LOGIN_SET_COMPRESSION:
        try:
            value, _ = vanilla.read_varint(packet.body, 0)
        except vanilla.ProtocolError:
            value = -1
        return 'compression enabled, threshold %d' % value
    if pid == vanilla.PLAY_DISCONNECT:
        try:
            text, _ = vanilla.read_string(packet.body, 0)
        except vanilla.ProtocolError:
            text = ''
        try:
            pretty = chat_to_text(json.loads(text))
        except ValueError:
            pretty = text
        return 'kicked from the game: %s' % (pretty or text[:120])
    name = {0x00: 'KeepAlive', 0x01: 'JoinGame', 0x02: 'ChatMessage',
            0x03: 'TimeUpdate', 0x08: 'PlayerPositionAndLook',
            0x21: 'ChunkData', 0x26: 'MapChunkBulk', 0x3F: 'PluginMessage'}.get(pid, '')
    return 'play data 0x%02x %s (%d bytes)' % (pid, name, len(packet.payload))


def complete_encryption(sock: socket.socket, packet: vanilla.Packet, threshold: int) -> dict:
    """Complete the encryption handshake on behalf of the client; returns
    {'key': shared secret, 'decrypt': ..., 'encrypt': ...}."""
    pos = 0
    server_id, pos = vanilla.read_string(packet.body, pos)
    length, pos = vanilla.read_varint(packet.body, pos)
    key_der = packet.body[pos:pos + length]
    pos += length
    length, pos = vanilla.read_varint(packet.body, pos)
    token = packet.body[pos:pos + length]
    if not crypto.available():
        raise crypto.CryptoUnavailable('AES library missing, cannot complete the encryption handshake')
    secret = os.urandom(16)
    body = (vanilla.write_varint(len(secret)) + crypto.rsa_encrypt(key_der, secret)
            + vanilla.write_varint(len(token)) + crypto.rsa_encrypt(key_der, token))
    payload = vanilla.write_varint(0x01) + body + b''      # Encryption Response
    sock.sendall(vanilla.Encoder(threshold).frame(payload))
    return {'server_id': server_id, 'key': secret,
            'decrypt': crypto.AesCfb8(secret, secret),
            'encrypt': crypto.AesCfb8(secret, secret)}


def probe(host: str, port: int, protocol: int, address: str | None = None,
          username: str = 'MCJSTestProbe', spoof_ip: str | None = None,
          quiet: bool = False, encrypt: bool = False) -> dict:
    result = {'host': host, 'port': port, 'protocol': protocol, 'verdict': '', 'lines': []}

    def note(text: str) -> None:
        result['lines'].append(text)
        if not quiet:
            print('    ' + text)

    handshake_address = address or host
    if spoof_ip:      # BungeeCord ip_forward format: host\0client IP\0UUID
        handshake_address = '%s\0%s\0%s' % (handshake_address, spoof_ip,
                                            '00000000-0000-0000-0000-000000000000')

    started = time.time()
    try:
        sock = socket.create_connection((host, port), timeout=5.0)
    except OSError as exc:
        result['verdict'] = 'cannot connect: %s' % exc
        note(result['verdict'])
        return result

    sock.settimeout(RECV_TIMEOUT)
    try:
        sock.sendall(build_login(protocol, handshake_address, port, username))
        note('sent: handshake (protocol %d, address %r, port %d) + login start (%s)'
             % (protocol, handshake_address, port, username))
        decoder = vanilla.Decoder(0)
        saw_anything = False
        closed_at = None
        session: dict = {}
        while time.time() - started < TOTAL_TIMEOUT:
            try:
                chunk = sock.recv(65536)
            except socket.timeout:
                if not saw_anything:
                    result['verdict'] = 'timeout: the server sent no byte within %.1f s' % RECV_TIMEOUT
                    note(result['verdict'])
                else:
                    result['verdict'] = result['verdict'] or 'data stopped (login/play already started)'
                break
            except OSError as exc:
                result['verdict'] = 'connection broken: %s' % exc
                note(result['verdict'])
                break
            if not chunk:
                closed_at = time.time() - started
                if not saw_anything:
                    result['verdict'] = ('the server accepted the login and then closed the connection '
                                         'after %.2f s without sending a single byte '
                                         '(typical causes: address/routing mismatch, ip_forward required, '
                                         'or the port is not the game port)' % closed_at)
                else:
                    result['verdict'] = result['verdict'] or ('the server closed the connection after %.2f s' % closed_at)
                note(result['verdict'])
                break
            saw_anything = True
            if session.get('decrypt') is not None:
                chunk = session['decrypt'].decrypt(chunk)
            decoder.push(chunk)
            finished = False
            while True:
                try:
                    packet = decoder.next_packet()
                except vanilla.ProtocolError as exc:
                    note('stream cannot be parsed further: %s' % exc)
                    break
                if packet is None:
                    break
                if packet.packet_id == vanilla.LOGIN_SET_COMPRESSION:
                    try:
                        threshold, _ = vanilla.read_varint(packet.body, 0)
                        decoder.threshold = threshold      # takes effect for the following packets at once
                    except vanilla.ProtocolError:
                        pass
                note(describe_packet(packet, decoder.threshold))
                if packet.packet_id == vanilla.LOGIN_ENCRYPTION_REQUEST:
                    if not encrypt:
                        result['verdict'] = 'online-mode verification required (encryption handshake); pass --encrypt to complete it'
                        note('(hint: pass --encrypt to complete the encryption handshake and verify whether an offline account gets in)')
                        continue
                    try:
                        session = complete_encryption(sock, packet, decoder.threshold)
                    except Exception as exc:
                        note('failed to complete the encryption handshake: %s' % exc)
                        result['verdict'] = 'failed to complete the encryption handshake: %s' % exc
                        break
                    note('encryption handshake completed (shared secret %s...), AES-128-CFB8 from here on'
                         % session['key'].hex()[:8])
                    continue
                if packet.packet_id in (vanilla.LOGIN_SUCCESS, vanilla.LOGIN_DISCONNECT):
                    result['login_packet'] = packet.packet_id
                    result['verdict'] = describe_packet(packet, decoder.threshold)
                    finished = True
                    break
            if finished:
                break
    finally:
        try:
            sock.close()
        except OSError:
            pass
    result['elapsed'] = time.time() - started
    return result


def status_probe(host: str, port: int, protocol: int = 47, address: str | None = None) -> dict:
    """Server-list ping: the server truthfully reports its own protocol version and MOTD text."""
    handshake_address = (address or host).encode('utf-8')
    payload = (vanilla.pack(0x00, (
        vanilla.write_varint(protocol)
        + vanilla.write_varint(len(handshake_address)) + handshake_address
        + int(port).to_bytes(2, 'big')
        + vanilla.write_varint(1)))                      # next state = status
        + vanilla.pack(0x00))                             # status request
    try:
        with socket.create_connection((host, port), timeout=6.0) as sock:
            sock.settimeout(6.0)
            sock.sendall(payload)
            data = b''
            while len(data) < 1 << 20:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                data += chunk
                if len(data) > 2:
                    try:
                        length, pos = vanilla.read_varint(data, 0)
                    except vanilla.ProtocolError:
                        continue
                    if len(data) >= pos + length:
                        break
    except OSError as exc:
        print('    status query failed: %s' % exc)
        return {}
    if not data:
        print('    the server stayed silent to the status query as well')
        return {}
    try:
        length, pos = vanilla.read_varint(data, 0)
        packet_id, pos = vanilla.read_varint(data, pos)
        text, pos = vanilla.read_string(data, pos)
    except vanilla.ProtocolError as exc:
        print('    response not parseable (%s): %s' % (exc, data[:120].hex()))
        return {}
    info = {}
    try:
        info = json.loads(text)
    except ValueError:
        print('    raw response: %s' % text[:300])
    version = info.get('version', {})
    players = info.get('players', {})
    description = info.get('description')
    if isinstance(description, dict) or isinstance(description, list):
        description = chat_to_text(description)
    print('    protocol version: %s (%s)' % (version.get('name', '?'), version.get('protocol', '?')))
    print('    players online: %s/%s' % (players.get('online', '?'), players.get('max', '?')))
    print('    MOTD: %s' % (description or '(empty)'))
    return info


def eagler_probe(host: str, port: int, username_bytes: bytes = b'nopp') -> None:
    """Greet the server the way an EaglercraftX client does, to see whether the peer is a browser-side server."""
    packet = (bytes.fromhex('010200030003000400050001002f')      # marker + supports 3/4/5 + protocol 47
              + bytes([len('EaglercraftX')]) + b'EaglercraftX'
              + bytes([len('u53')]) + b'u53'
              + b'\x00' + bytes([len(username_bytes)]) + username_bytes)
    names = {0x02: 'server version', 0x03: 'version mismatch', 0x05: 'login allowed', 0x06: 'login denied',
             0x09: 'finish login', 0xFF: 'error'}
    try:
        with socket.create_connection((host, port), timeout=6.0) as sock:
            sock.settimeout(4.0)
            sock.sendall(packet)
            data = b''
            try:
                while len(data) < 4096:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    data += chunk
            except socket.timeout:
                pass
    except OSError as exc:
        print('    connection failed: %s' % exc)
        return
    if not data:
        print('    the peer closed without a word -> not a browser-side server (or it does not accept this handshake)')
        return
    print('    received %d bytes: %s' % (len(data), data.hex()))
    packet_id = data[0]
    print('    looks like an EaglercraftX %s packet (0x%02x)'
          % (names.get(packet_id, 'unknown'), packet_id))


def main() -> int:
    parser = argparse.ArgumentParser(description='probe how a target Minecraft server responds to a vanilla login')
    parser.add_argument('target', help='target, e.g. mc244.com or mc244.com:25565')
    parser.add_argument('--protocol', default='47', help='protocol versions to try, comma separated (default 47)')
    parser.add_argument('--address', help='server address placed in the handshake packet (defaults to the node hostname)')
    parser.add_argument('--username', default='MCJSTestProbe', help='username used for the login')
    parser.add_argument('--spoof-ip', help='compose the address in BungeeCord ip_forward format (the client IP to fill in)')
    parser.add_argument('--status', action='store_true', help='status query only (server-list ping): self-reported version/MOTD')
    parser.add_argument('--eagler', action='store_true', help='send an EaglercraftX handshake to see whether the peer is a browser-side server')
    parser.add_argument('--encrypt', action='store_true',
                        help='complete the encryption handshake when requested (to verify access when the server "fakes" online mode)')
    parser.add_argument('--no-srv', action='store_true', help='skip SRV lookup')
    args = parser.parse_args()

    raw = args.target.strip()
    if ':' in raw and not raw.endswith(']'):
        host, _, port_text = raw.rpartition(':')
        port = int(port_text)
    else:
        host, port = raw, None

    protocols = [int(item) for item in args.protocol.split(',') if item.strip()]

    print('target: %s' % raw)
    candidates: list[tuple[str, int]] = []
    if port:
        candidates.append((host, port))
    else:
        if not args.no_srv:
            records = resolver.query_srv(host)
            srv = resolver.pick_srv(records) if records else None
            if srv:
                print('SRV: %s -> %s:%d' % (host, srv[0], srv[1]))
                candidates.append(srv)
            else:
                print('SRV: no record, using %s:25565' % host)
        if not candidates:
            candidates.append((host, 25565))

    for node_host, node_port in candidates:
        if args.status:
            for protocol in protocols:
                print('\n== %s:%d status query (protocol %d) ==' % (node_host, node_port, protocol))
                status_probe(node_host, node_port, protocol, args.address)
            continue
        if args.eagler:
            print('\n== %s:%d EaglercraftX handshake probe ==' % (node_host, node_port))
            eagler_probe(node_host, node_port)
            continue
        for protocol in protocols:
            print('\n== %s:%d protocol %d ==' % (node_host, node_port, protocol))
            probe(node_host, node_port, protocol, address=args.address,
                  username=args.username, spoof_ip=args.spoof_ip, encrypt=args.encrypt)
    return 0


if __name__ == '__main__':
    sys.exit(main())
