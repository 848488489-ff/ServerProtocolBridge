"""探测目标 Minecraft 服务器: 直接发一个原版登录, 把服务器的回应原文打印出来。

    python tools/probe.py mc244.com                 :: 按 SRV 逐个节点探测
    python tools/probe.py mc244.com:25565 --protocol 47,340,754
    python tools/probe.py mc244.com --address 127.0.0.1  :: 换握手里的地址(测分流/转发配置)

输出里会明确写出: 登录成功 / 被踢(原文) / 要求正版验证 / 一声不吭直接断开 / 超时。
用来判断"浏览器端客户端连不上"到底是协议层的问题还是目标服务器不接受我们。
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

RECV_TIMEOUT = 3.0          # 每次 recv 的最长等待
TOTAL_TIMEOUT = 12.0        # 整个探测的最长时间


def build_login(protocol: int, address: str, port: int, username: str) -> bytes:
    host = address.encode('utf-8')
    handshake = vanilla.pack(0x00, (
        vanilla.write_varint(protocol)
        + vanilla.write_varint(len(host)) + host
        + int(port).to_bytes(2, 'big')
        + vanilla.write_varint(2)))          # 下一步 = 登录
    login_start = vanilla.pack(0x00, (
        vanilla.write_varint(len(username)) + username.encode('utf-8')))
    return handshake + login_start


def describe_packet(packet: vanilla.Packet, threshold: int) -> str:
    pid = packet.packet_id
    if pid == vanilla.LOGIN_DISCONNECT:
        try:
            text, _ = vanilla.read_string(packet.body, 0)
        except vanilla.ProtocolError:
            return '踢出(内容无法解析): %s' % packet.body[:80].hex()
        try:
            pretty = chat_to_text(json.loads(text))
        except ValueError:
            pretty = text
        return '被踢: %s  [原始 JSON: %s]' % (pretty or '(空)', text[:200])
    if pid == vanilla.LOGIN_ENCRYPTION_REQUEST:
        return '要求正版验证(加密握手) —— 离线模式客户端过不去'
    if pid == vanilla.LOGIN_SUCCESS:
        try:
            uuid_text, pos = vanilla.read_string(packet.body, 0)
            name, _ = vanilla.read_string(packet.body, pos)
        except vanilla.ProtocolError:
            return '登录成功(内容解析失败, 可能是加密/压缩状态没对上): %s' % packet.body[:60].hex()
        return '登录成功: %s (UUID %s)' % (name, uuid_text)
    if pid == vanilla.LOGIN_SET_COMPRESSION:
        try:
            value, _ = vanilla.read_varint(packet.body, 0)
        except vanilla.ProtocolError:
            value = -1
        return '启用压缩, 阈值 %d' % value
    if pid == vanilla.PLAY_DISCONNECT:
        try:
            text, _ = vanilla.read_string(packet.body, 0)
        except vanilla.ProtocolError:
            text = ''
        try:
            pretty = chat_to_text(json.loads(text))
        except ValueError:
            pretty = text
        return '游戏中被踢: %s' % (pretty or text[:120])
    name = {0x00: 'KeepAlive', 0x01: 'JoinGame', 0x02: 'ChatMessage',
            0x03: 'TimeUpdate', 0x08: 'PlayerPositionAndLook',
            0x21: 'ChunkData', 0x26: 'MapChunkBulk', 0x3F: 'PluginMessage'}.get(pid, '')
    return '游戏数据 0x%02x %s (%d 字节)' % (pid, name, len(packet.payload))


def complete_encryption(sock: socket.socket, packet: vanilla.Packet, threshold: int) -> dict:
    """代做加密握手, 返回 {'key': 共享密钥, 'decrypt': ..., 'encrypt': ...}。"""
    pos = 0
    server_id, pos = vanilla.read_string(packet.body, pos)
    length, pos = vanilla.read_varint(packet.body, pos)
    key_der = packet.body[pos:pos + length]
    pos += length
    length, pos = vanilla.read_varint(packet.body, pos)
    token = packet.body[pos:pos + length]
    if not crypto.available():
        raise crypto.CryptoUnavailable('缺少 AES 库, 无法代做加密握手')
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
    if spoof_ip:      # BungeeCord 的 ip_forward 格式: 域名\0客户端IP\0UUID
        handshake_address = '%s\0%s\0%s' % (handshake_address, spoof_ip,
                                            '00000000-0000-0000-0000-000000000000')

    started = time.time()
    try:
        sock = socket.create_connection((host, port), timeout=5.0)
    except OSError as exc:
        result['verdict'] = '连不上: %s' % exc
        note(result['verdict'])
        return result

    sock.settimeout(RECV_TIMEOUT)
    try:
        sock.sendall(build_login(protocol, handshake_address, port, username))
        note('已发送: 握手(协议 %d, 地址 %r, 端口 %d) + 登录开始(%s)'
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
                    result['verdict'] = '超时: %.1f 秒内服务器一个字节都没回' % RECV_TIMEOUT
                    note(result['verdict'])
                else:
                    result['verdict'] = result['verdict'] or '数据停止(登录/游戏已开始)'
                break
            except OSError as exc:
                result['verdict'] = '连接中断: %s' % exc
                note(result['verdict'])
                break
            if not chunk:
                closed_at = time.time() - started
                if not saw_anything:
                    result['verdict'] = ('服务器收下登录后 %.2f 秒直接关闭连接, 且一个字都没发 '
                                         '(典型的: 地址/分流对不上、需要 ip_forward、或端口不是游戏端口)'
                                         % closed_at)
                else:
                    result['verdict'] = result['verdict'] or ('服务器在 %.2f 秒后关闭连接' % closed_at)
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
                    note('数据流无法继续解析: %s' % exc)
                    break
                if packet is None:
                    break
                if packet.packet_id == vanilla.LOGIN_SET_COMPRESSION:
                    try:
                        threshold, _ = vanilla.read_varint(packet.body, 0)
                        decoder.threshold = threshold      # 立刻对新包生效
                    except vanilla.ProtocolError:
                        pass
                note(describe_packet(packet, decoder.threshold))
                if packet.packet_id == vanilla.LOGIN_ENCRYPTION_REQUEST:
                    if not encrypt:
                        result['verdict'] = '要求正版验证(加密握手); 加 --encrypt 可以代做这一步'
                        note('(提示: 加 --encrypt 可代做加密握手, 用来验证离线账号能不能进)')
                        continue
                    try:
                        session = complete_encryption(sock, packet, decoder.threshold)
                    except Exception as exc:
                        note('代做加密握手失败: %s' % exc)
                        result['verdict'] = '代做加密握手失败: %s' % exc
                        break
                    note('已代做加密握手(共享密钥 %s...), 之后全程 AES-128-CFB8'
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
    """服务器列表 ping: 服务器会如实报告自己的协议版本与说明文字。"""
    handshake_address = (address or host).encode('utf-8')
    payload = (vanilla.pack(0x00, (
        vanilla.write_varint(protocol)
        + vanilla.write_varint(len(handshake_address)) + handshake_address
        + int(port).to_bytes(2, 'big')
        + vanilla.write_varint(1)))                      # 下一步 = 状态
        + vanilla.pack(0x00))                             # 状态请求
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
        print('    状态查询失败: %s' % exc)
        return {}
    if not data:
        print('    服务器对状态查询也一声不吭')
        return {}
    try:
        length, pos = vanilla.read_varint(data, 0)
        packet_id, pos = vanilla.read_varint(data, pos)
        text, pos = vanilla.read_string(data, pos)
    except vanilla.ProtocolError as exc:
        print('    响应无法解析(%s): %s' % (exc, data[:120].hex()))
        return {}
    info = {}
    try:
        info = json.loads(text)
    except ValueError:
        print('    响应原文: %s' % text[:300])
    version = info.get('version', {})
    players = info.get('players', {})
    description = info.get('description')
    if isinstance(description, dict) or isinstance(description, list):
        description = chat_to_text(description)
    print('    协议版本: %s (%s)' % (version.get('name', '?'), version.get('protocol', '?')))
    print('    在线人数: %s/%s' % (players.get('online', '?'), players.get('max', '?')))
    print('    说明文字: %s' % (description or '(空)'))
    return info


def eagler_probe(host: str, port: int, username_bytes: bytes = b'nopp') -> None:
    """按 EaglercraftX 客户端的方式打招呼, 看对面是不是浏览器端服务器。"""
    packet = (bytes.fromhex('010200030003000400050001002f')      # 标记 + 支持 3/4/5 + 协议 47
              + bytes([len('EaglercraftX')]) + b'EaglercraftX'
              + bytes([len('u53')]) + b'u53'
              + b'\x00' + bytes([len(username_bytes)]) + username_bytes)
    names = {0x02: '服务端版本', 0x03: '版本不匹配', 0x05: '允许登录', 0x06: '拒绝登录',
             0x09: '完成登录', 0xFF: '错误'}
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
        print('    连接失败: %s' % exc)
        return
    if not data:
        print('    对面一声不吭就关了 -> 不是浏览器端服务器(或它不认这种握手)')
        return
    print('    收到 %d 字节: %s' % (len(data), data.hex()))
    packet_id = data[0]
    print('    看起来是 EaglercraftX 的 %s 包(0x%02x)'
          % (names.get(packet_id, '未知'), packet_id))


def main() -> int:
    parser = argparse.ArgumentParser(description='探测目标 Minecraft 服务器对原版登录的回应')
    parser.add_argument('target', help='目标, 例如 mc244.com 或 mc244.com:25565')
    parser.add_argument('--protocol', default='47', help='要试探的协议版本, 逗号分隔(默认 47)')
    parser.add_argument('--address', help='握手包里填的服务器地址(默认用节点主机名)')
    parser.add_argument('--username', default='MCJSTestProbe', help='登录用的用户名')
    parser.add_argument('--spoof-ip', help='按 BungeeCord ip_forward 格式拼地址(填客户端 IP)')
    parser.add_argument('--status', action='store_true', help='只做状态查询(服务器列表 ping), 看它自报的版本/MOTD')
    parser.add_argument('--eagler', action='store_true', help='发 EaglercraftX 握手, 看对面是不是浏览器端服务器')
    parser.add_argument('--encrypt', action='store_true',
                        help='遇到加密请求就代做加密握手(服务器"假正版"时用来验证能否进去)')
    parser.add_argument('--no-srv', action='store_true', help='不做 SRV 解析')
    args = parser.parse_args()

    raw = args.target.strip()
    if ':' in raw and not raw.endswith(']'):
        host, _, port_text = raw.rpartition(':')
        port = int(port_text)
    else:
        host, port = raw, None

    protocols = [int(item) for item in args.protocol.split(',') if item.strip()]

    print('目标: %s' % raw)
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
                print('SRV: 无记录, 用 %s:25565' % host)
        if not candidates:
            candidates.append((host, 25565))

    for node_host, node_port in candidates:
        if args.status:
            for protocol in protocols:
                print('\n== %s:%d 状态查询(协议 %d) ==' % (node_host, node_port, protocol))
                status_probe(node_host, node_port, protocol, args.address)
            continue
        if args.eagler:
            print('\n== %s:%d EaglercraftX 握手探测 ==' % (node_host, node_port))
            eagler_probe(node_host, node_port)
            continue
        for protocol in protocols:
            print('\n== %s:%d 协议 %d ==' % (node_host, node_port, protocol))
            probe(node_host, node_port, protocol, address=args.address,
                  username=args.username, spoof_ip=args.spoof_ip, encrypt=args.encrypt)
    return 0


if __name__ == '__main__':
    sys.exit(main())
