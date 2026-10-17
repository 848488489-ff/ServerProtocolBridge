"""Minecraft 握手包的解析与可选的地址改写。

代理本身不做协议处理, 这里只针对**上行第一个包**(握手包)做两件事:

* 解析出协议版本 / 客户端填写的服务器地址 / 端口 / 下一步动作, 写进日志 ——
  排查"连上就被踢"时, 这一行信息通常就是答案;
* 在用户显式开启"握手地址改写"时, 把握手里的地址替换成真实的目标域名 ——
  浏览器端客户端往往把本地地址(127.0.0.1:8443)填进去, 部分服务器会按这个地址
  做校验或按域名分流, 于是表现为"刚连上就被关闭"。

解析失败(数据不是握手包、被拆包等)时一律原样透传, 不做任何猜测。
"""

from __future__ import annotations

NEXT_STATE_NAMES = {
    1: '状态查询(Server List Ping)',
    2: '登录(Login)',
    3: '传输(已废弃)',
}


def read_varint(data: bytes, pos: int = 0) -> tuple[int, int]:
    """读一个 VarInt, 返回 (值, 新位置)。"""
    value = 0
    for index in range(5):
        if pos >= len(data):
            raise ValueError('VarInt 不完整')
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << (7 * index)
        if not byte & 0x80:
            return value, pos
    raise ValueError('VarInt 超过 5 字节')


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
    """返回第一个包的完整长度(含长度前缀); 数据少到读不出长度前缀时返回 None。"""
    try:
        packet_length, pos = read_varint(data, 0)
    except ValueError:
        return None
    return packet_length + pos


def looks_like_handshake(data: bytes, max_packet: int = 2048,
                         max_protocol: int = 2000) -> bool:
    """判断数据开头是否像"还没收全的握手包"。

    只按长度前缀判断是不够的 —— 任意游戏数据的首字节都可能被当成一个合法的长度,
    于是被误缓存下来。这里额外要求 packet id 必须是 0x00、协议版本和地址长度都在
    合理范围内, 才会认为是"握手包还没收齐"。任一项不满足就返回 False(直接转发)。
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
        return True                       # 有长度、packet id 也是 0, 先当握手包缓存
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
    """给日志用的十六进制预览。"""
    chunk = data[:limit]
    text = ' '.join('%02x' % byte for byte in chunk)
    if len(data) > limit:
        text += ' ...(共 %d 字节)' % len(data)
    return text


def parse_handshake(data: bytes) -> dict | None:
    """把上行数据当成握手包解析; 不是握手包或数据不完整时返回 None。"""
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
        'next_state_name': NEXT_STATE_NAMES.get(next_state, '未知(%d)' % next_state),
        'consumed': pos,       # 握手包在 data 里占用的字节数
    }


def rewrite_handshake(data: bytes, address: str, port: int | None = None) -> bytes | None:
    """把握手包里的服务器地址(和端口)换成新的值。

    返回改写后的完整数据(含其后的其它包); 解析失败返回 None, 由调用方决定是否原样转发。
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
    return ('协议版本 %d, 客户端填写地址 "%s:%d", 下一步 %s'
            % (info['protocol'], info['address'], info['port'], info['next_state_name']))
