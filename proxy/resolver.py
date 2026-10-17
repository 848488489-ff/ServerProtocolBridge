"""Resolve the target server address.

When the Minecraft client is given a bare domain name without a port, it
first looks up the SRV records of _minecraft._tcp.<domain>.  A minimal DNS
query is implemented here with the standard library so the bridge forwards
to the same target the vanilla client would have used.
"""

from __future__ import annotations

import json
import random
import re
import socket
import struct
import sys

from .i18n import tr

DEFAULT_PORT = 25565
QUERY_TIMEOUT = 3.0
FALLBACK_NAMESERVERS = ('223.5.5.5', '1.1.1.1', '8.8.8.8')

RECORD_A = 1
RECORD_SRV = 33


def system_nameservers() -> list[str]:
    """Return the system DNS servers (Windows: registry, everywhere else: resolv.conf)."""
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
            raise ValueError(tr('resolver.bad_label', label=repr(label)))
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
            raise ValueError(tr('resolver.truncated'))
        length = data[offset]
        if length == 0:
            offset += 1
            if not jumps:
                end = offset
            break
        if length & 0xC0 == 0xC0:  # compression pointer
            pointer = ((length & 0x3F) << 8) | data[offset + 1]
            if not jumps:
                end = offset + 2
            offset = pointer
            jumps += 1
            if jumps > 32:
                raise ValueError(tr('resolver.pointer_loop'))
            continue
        offset += 1
        labels.append(data[offset:offset + length].decode('ascii', 'replace'))
        offset += length
    return '.'.join(labels), end


def query_srv(hostname: str, servers: list[str] | None = None, timeout: float = QUERY_TIMEOUT) -> list[dict]:
    """Query the SRV records of _minecraft._tcp.<hostname>. Raises OSError on failure, returns an empty list when nothing is found."""
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
                        raise OSError(tr('resolver.rcode', code=flags & 0xF))
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
        except Exception as exc:  # try the next server
            last_error = exc
    raise OSError(tr('resolver.srv_failed', error=last_error))


def pick_srv(records: list[dict]) -> tuple[str, int] | None:
    """Pick one SRV record per RFC 2782: lowest priority first, random by weight within the same priority."""
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
    """Turn the forwarding target from the config into (host, port).

    An explicit port is used as-is; without one the name is resolved through
    SRV records and falls back to 25565 when none are found.
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
                logger.warn(tr('resolver.log_srv_failed', host=host, error=exc,
                               port=DEFAULT_PORT))
        if picked:
            target, srv_port = picked
            if logger is not None:
                logger.info(tr('resolver.log_srv_resolved', host=host,
                               target=target, port=srv_port))
            return target, srv_port
        if logger is not None:
            logger.debug(tr('resolver.log_no_srv', host=host, port=DEFAULT_PORT))
    return host, DEFAULT_PORT


def probe(host: str, port: int, timeout: float = 5.0) -> tuple[bool, float | None, str]:
    """Try to connect to the target once; used by --check and the connectivity hint after start-up."""
    import time

    started = time.time()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            elapsed = (time.time() - started) * 1000
            return True, elapsed, ''
    except OSError as exc:
        return False, None, str(exc)


def _recv_exactly(sock: socket.socket, count: int) -> bytes:
    data = b''
    while len(data) < count:
        chunk = sock.recv(count - len(data))
        if not chunk:
            raise OSError(tr('resolver.peer_closed'))
        data += chunk
    return data


def _read_varint(sock: socket.socket) -> int:
    value = 0
    for shift in range(5):
        byte = _recv_exactly(sock, 1)[0]
        value |= (byte & 0x7F) << (7 * shift)
        if not byte & 0x80:
            return value
    raise OSError(tr('resolver.varint_too_long'))


def query_status(host: str, port: int, timeout: float = 5.0) -> dict:
    """Run one vanilla status query against the target and grab the JSON it keeps for the server list.

    This is exactly what the vanilla client does when it refreshes the server
    list:
        handshake packet (next state = 1, status)  ->  status request (0x00)  ->  the server answers with a JSON string.

    Returns {'ok': whether it worked, 'ms': round-trip milliseconds, 'status': the JSON dict or None, 'error': the reason}
    """
    import time

    from . import vanilla

    started = time.time()
    try:
        with socket.create_connection((host, int(port)), timeout=timeout) as sock:
            sock.settimeout(timeout)
            address = str(host).encode('utf-8')
            handshake = vanilla.pack(0x00, (
                vanilla.write_varint(-1)                  # the status query always uses -1
                + vanilla.write_varint(len(address)) + address
                + int(port).to_bytes(2, 'big')
                + vanilla.write_varint(1)))               # next state = status
            sock.sendall(handshake + vanilla.pack(0x00))
            length = _read_varint(sock)
            if length <= 0 or length > 2 * 1024 * 1024:
                raise OSError(tr('resolver.bad_status_length', length=length))
            body = _recv_exactly(sock, length)
            packet_id, pos = vanilla.read_varint(body, 0)
            if packet_id != 0x00:
                raise OSError(tr('resolver.bad_status_packet', packet_id='0x%02x' % packet_id))
            text, _ = vanilla.read_string(body, pos)
            status = json.loads(text)
        if not isinstance(status, dict):
            raise ValueError(tr('resolver.bad_status_json'))
        return {'ok': True, 'ms': (time.time() - started) * 1000,
                'status': status, 'error': ''}
    except (OSError, ValueError, vanilla.ProtocolError) as exc:
        return {'ok': False, 'ms': None, 'status': None, 'error': str(exc) or exc.__class__.__name__}
