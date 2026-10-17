"""原版 Minecraft 协议 (1.8, 协议版本 47) 的封包分帧与压缩 —— 只做搬运需要的部分。

分帧规则:
* 未启用压缩: [VarInt 包长][VarInt 包 id][内容]
* 启用压缩后: [VarInt 包长][VarInt 未压缩长度][内容]
    - 未压缩长度 == 0: 内容是原始的 (包 id + 数据)
    - 未压缩长度 > 0 : 内容是 zlib 压缩后的 (包 id + 数据)

素材来源: EaglercraftX 服务端 (lax1dude/eaglerxserver) 的 VanillaInitializer 与
Netty 管线, 它的做法是替 Eaglercraft 客户端收发原版封包, 这里照同样的规则实现。
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass

MAX_PACKET_BYTES = 8 * 1024 * 1024

# 登录阶段的包 id
LOGIN_DISCONNECT = 0x00
LOGIN_ENCRYPTION_REQUEST = 0x01
LOGIN_ENCRYPTION_RESPONSE = 0x01
LOGIN_SUCCESS = 0x02
LOGIN_SET_COMPRESSION = 0x03

# 游戏阶段 (Play) 里和我们相关的包 id (1.8.8)
PLAY_KEEP_ALIVE = 0x00
PLAY_JOIN_GAME = 0x01
PLAY_PLUGIN_MESSAGE = 0x3F      # 服务端 -> 客户端
PLAY_DISCONNECT = 0x40

CLIENT_PLUGIN_MESSAGE = 0x17    # 客户端 -> 服务端

# Eaglercraft 自己的扩展全部走插件消息通道, 前缀是这两个
EAGLER_CHANNEL_PREFIXES = ('EAG|', 'eagler:')


class ProtocolError(Exception):
    """数据流不符合原版封包格式。"""


class NeedMoreData(ProtocolError):
    """数据还不完整, 需要继续收。

    是 ProtocolError 的子类: 解析"已经完整的一个包"时遇到字节不够, 说明包本身就是
    残缺的(格式错), 调用方按协议错误处理即可; 只有流式解析才需要区分这两种情况。
    """


def write_varint(value: int) -> bytes:
    if value < 0:
        value &= 0xFFFFFFFF
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def read_varint(data: bytes, pos: int = 0) -> tuple[int, int]:
    """读一个 VarInt, 返回 (值, 新位置)。数据不够时抛 NeedMoreData。"""
    value = 0
    for index in range(5):
        if pos >= len(data):
            raise NeedMoreData()
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << (7 * index)
        if not byte & 0x80:
            return value, pos
    raise ProtocolError('VarInt 超过 5 字节')


def read_string(data: bytes, pos: int = 0) -> tuple[str, int]:
    """读一个 VarInt 长度前缀的 UTF-8 字符串。"""
    length, pos = read_varint(data, pos)
    if length < 0 or pos + length > len(data):
        raise NeedMoreData()
    return data[pos:pos + length].decode('utf-8', 'replace'), pos + length


def read_u16(data: bytes, pos: int = 0) -> tuple[int, int]:
    if pos + 2 > len(data):
        raise NeedMoreData()
    return int.from_bytes(data[pos:pos + 2], 'big'), pos + 2


def pack(packet_id: int, body: bytes = b'') -> bytes:
    """拼出一个完整的未压缩封帧(长度前缀 + 包 id + 内容)。"""
    payload = write_varint(packet_id) + body
    return write_varint(len(payload)) + payload


@dataclass
class Packet:
    """一个解析出来的原版数据包。"""

    packet_id: int
    body: bytes        # 包 id 之后的内容
    payload: bytes     # 包 id + 内容(未压缩形式)


class Decoder:
    """增量解析一个方向的字节流。

    注意: 压缩阈值可能在数据流中间变化(服务器发来 Set Compression 之后), 所以
    要把 ``feed`` 当成"批量"用法并不安全 —— 只要可能遇到阈值变化, 就应该用
    ``push`` + ``next_packet`` 一个一个取, 这样阈值改完立刻对新包生效。
    """

    def __init__(self, threshold: int = 0):
        self.buffer = b''
        self.threshold = threshold

    def push(self, data: bytes) -> None:
        self.buffer += data

    def feed(self, data: bytes) -> list[Packet]:
        self.push(data)
        packets: list[Packet] = []
        while True:
            packet = self.next_packet()
            if packet is None:
                return packets
            packets.append(packet)

    def next_packet(self) -> Packet | None:
        """取出下一个完整的包; 数据不够就返回 None(留在缓冲区里等下次)。"""
        buffer = self.buffer
        try:
            length, pos = read_varint(buffer, 0)
        except NeedMoreData:
            return None
        if length <= 0 or length > MAX_PACKET_BYTES:
            raise ProtocolError('包长度异常: %d' % length)
        if len(buffer) < pos + length:
            return None
        body = buffer[pos:pos + length]
        self.buffer = buffer[pos + length:]
        if self.threshold > 0:
            try:
                uncompressed, offset = read_varint(body, 0)
            except NeedMoreData:
                raise ProtocolError('压缩包缺少未压缩长度字段')
            payload = body[offset:]
            if uncompressed > 0:
                try:
                    payload = zlib.decompress(payload)
                except zlib.error as exc:
                    raise ProtocolError('zlib 解压失败: %s' % exc)
                if len(payload) != uncompressed:
                    raise ProtocolError('解压后长度 %d 与声明 %d 不符'
                                        % (len(payload), uncompressed))
        else:
            payload = body
        try:
            packet_id, at = read_varint(payload, 0)
        except NeedMoreData:
            raise ProtocolError('包内容里没有包 id')
        return Packet(packet_id, payload[at:], payload)


class Encoder:
    """按协商好的压缩阈值把包重新封帧。"""

    def __init__(self, threshold: int = 0):
        self.threshold = threshold

    def frame(self, payload: bytes) -> bytes:
        if self.threshold > 0:
            if len(payload) >= self.threshold:
                body = write_varint(len(payload)) + zlib.compress(payload)
            else:
                body = write_varint(0) + payload
        else:
            body = payload
        return write_varint(len(body)) + body
