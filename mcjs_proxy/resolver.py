"""目标服务器地址解析。

Minecraft 客户端在只填域名不带端口时, 会先查 _minecraft._tcp.<域名> 的 SRV 记录。
这里用标准库实现一次最小 DNS 查询, 让本工具的转发目标行为与原版客户端一致。
"""

from __future__ import annotations

import random
import re
import socket
import struct
import sys

DEFAULT_PORT = 25565
QUERY_TIMEOUT = 3.0
FALLBACK_NAMESERVERS = ('223.5.5.5', '1.1.1.1', '8.8.8.8')

RECORD_A = 1
RECORD_SRV = 33


def system_nameservers() -> list[str]:
    """获取系统 DNS 服务器地址(Windows 读注册表, 其他系统读 resolv.conf)。"""
    servers: list[str] = []
    if sys.platform == 'win32':
        def _add(value: object) -> None:
            servers.extend(re.split(r'[\s,]+', str(value).strip()))

        try:
            import winreg

            root_path = r'SYSTEM\CurrentControlSet\Services\Tcpip\Parameters'
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, root_path) as key:
                    try:
                        _add(winreg.QueryValueEx(key, 'NameServer')[0])
                    except OSError:
                        pass
            except OSError:
                pass
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, root_path + r'\Interfaces') as key:
                    index = 0
                    while True:
                        try:
                            adapter = winreg.EnumKey(key, index)
                            index += 1
                        except OSError:
                            break
                        try:
                            with winreg.OpenKey(key, adapter) as sub_key:
                                for value_name in ('NameServer', 'DhcpNameServer'):
                                    try:
                                        _add(winreg.QueryValueEx(sub_key, value_name)[0])
                                    except OSError:
                                        continue
                        except OSError:
                            continue
            except OSError:
                pass
        except Exception:
            servers = []
    else:
        try:
            with open('/etc/resolv.conf', 'r', encoding='utf-8', errors='ignore') as handle:
                for line in handle:
                    if line.startswith('nameserver'):
                        servers += line.split()[1:2]
        except OSError:
            servers = []

    valid = [s for s in servers if re.fullmatch(r'\d{1,3}(\.\d{1,3}){3}', s)]
    return valid or list(FALLBACK_NAMESERVERS)


def _encode_name(name: str) -> bytes:
    out = bytearray()
    for label in name.rstrip('.').split('.'):
        data = label.encode('idna') if any(ord(ch) > 127 for ch in label) else label.encode('ascii')
        if not 0 < len(data) <= 63:
            raise ValueError('非法域名标签: %r' % label)
        out.append(len(data))
        out += data
    out.append(0)
    return bytes(out)


def _decode_name(data: bytes, offset: int) -> tuple[str, int]:
    labels: list[str] = []
    end = offset
    jumps = 0
    while True:
        if offset >= len(data):
            raise ValueError('DNS 响应被截断')
        length = data[offset]
        if length == 0:
            offset += 1
            if not jumps:
                end = offset
            break
        if length & 0xC0 == 0xC0:  # 压缩指针
            pointer = ((length & 0x3F) << 8) | data[offset + 1]
            if not jumps:
                end = offset + 2
            offset = pointer
            jumps += 1
            if jumps > 32:
                raise ValueError('DNS 名称压缩指针循环')
            continue
        offset += 1
        labels.append(data[offset:offset + length].decode('ascii', 'replace'))
        offset += length
    return '.'.join(labels), end


def query_srv(hostname: str, servers: list[str] | None = None, timeout: float = QUERY_TIMEOUT) -> list[dict]:
    """查询 _minecraft._tcp.<hostname> 的 SRV 记录。失败时抛 OSError, 查不到返回空列表。"""
    servers = servers or system_nameservers()
    question_name = '_minecraft._tcp.' + hostname.rstrip('.')
    transaction_id = random.randint(0, 0xFFFF)
    packet = (struct.pack('>HHHHHH', transaction_id, 0x0100, 1, 0, 0, 0)
              + _encode_name(question_name) + struct.pack('>HH', RECORD_SRV, 1))
    last_error: Exception | None = None
    for server in servers[:3]:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.settimeout(timeout)
                sock.sendto(packet, (server, 53))
                while True:
                    data, _ = sock.recvfrom(4096)
                    if len(data) < 12:
                        continue
                    rid, flags, qdcount, ancount = struct.unpack('>HHHH', data[:8])
                    if rid != transaction_id:
                        continue
                    if not flags & 0x8000:
                        raise OSError('DNS 服务器返回错误码 RCODE=%d' % (flags & 0xF))
                    offset = 12
                    for _ in range(qdcount):
                        _, offset = _decode_name(data, offset)
                        offset += 4
                    records: list[dict] = []
                    for _ in range(ancount):
                        name, offset = _decode_name(data, offset)
                        rtype, _rclass, _ttl, rdlength = struct.unpack('>HHIH', data[offset:offset + 10])
                        offset += 10
                        rdata_start = offset
                        if rtype == RECORD_SRV and rdlength >= 7:
                            priority, weight, port = struct.unpack('>HHH', data[rdata_start:rdata_start + 6])
                            target, _ = _decode_name(data, rdata_start + 6)
                            records.append({'name': name, 'priority': priority,
                                            'weight': weight, 'port': port, 'target': target})
                        offset += rdlength
                    return records
        except Exception as exc:  # 换下一个服务器继续尝试
            last_error = exc
    raise OSError('SRV 查询失败: %s' % (last_error,))


def pick_srv(records: list[dict]) -> tuple[str, int] | None:
    """按 RFC 2782 从 SRV 记录里挑一条: 优先级最低, 同优先级按权重随机。"""
    if not records:
        return None
    best_priority = min(item['priority'] for item in records)
    group = [item for item in records if item['priority'] == best_priority]
    total_weight = sum(item['weight'] for item in group)
    if total_weight <= 0:
        chosen = random.choice(group)
    else:
        roll = random.uniform(0, total_weight)
        accumulated = 0.0
        chosen = group[-1]
        for item in group:
            accumulated += item['weight']
            if roll <= accumulated:
                chosen = item
                break
    return chosen['target'].rstrip('.'), chosen['port']


def resolve_target(host: str, port: int | None = None, logger=None,
                   use_srv: bool = True, timeout: float = QUERY_TIMEOUT) -> tuple[str, int]:
    """把配置里的转发目标解析成 (主机, 端口)。

    指定了端口就直接用; 没指定则按 SRV 记录解析, 查不到回落到 25565。
    """
    host = (host or '').strip()
    if port:
        return host, int(port)
    if use_srv and host:
        try:
            records = query_srv(host, timeout=timeout)
            picked = pick_srv(records)
        except Exception as exc:
            picked = None
            if logger is not None:
                logger.warn('SRV 查询失败(%s): %s, 回落到默认端口 %d' % (host, exc, DEFAULT_PORT))
        if picked:
            target, srv_port = picked
            if logger is not None:
                logger.info('SRV 解析: %s -> %s:%d' % (host, target, srv_port))
            return target, srv_port
        if logger is not None:
            logger.debug('%s 没有 SRV 记录, 使用默认端口 %d' % (host, DEFAULT_PORT))
    return host, DEFAULT_PORT


def probe(host: str, port: int, timeout: float = 5.0) -> tuple[bool, float | None, str]:
    """尝试连接一次目标服务器, 用于 --check 与启动后的连通性提示。"""
    import time

    started = time.time()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            elapsed = (time.time() - started) * 1000
            return True, elapsed, ''
    except OSError as exc:
        return False, None, str(exc)