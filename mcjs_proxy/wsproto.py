"""RFC 6455 WebSocket 服务端协议: 握手 + 帧编解码(仅用标准库)。

浏览器端 MC 客户端把 Minecraft 协议的原始字节装在 WebSocket 二进制帧里,
本模块负责把两者对接起来; 不涉及任何 Minecraft 协议内容。
"""

from __future__ import annotations

import base64
import hashlib
import secrets

GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'

OP_CONTINUATION = 0x0
OP_TEXT = 0x1
OP_BINARY = 0x2
OP_CLOSE = 0x8
OP_PING = 0x9
OP_PONG = 0xA

DEFAULT_MAX_PAYLOAD = 16 * 1024 * 1024
MAX_HEADER_SIZE = 16384

# 内部哨兵: 缓冲区里的数据还不够组成一整帧
_NEED_MORE = object()


class ProtocolError(Exception):
    """协议违例, close_code 是应当回给对端的关闭码。"""

    def __init__(self, message: str, close_code: int = 1002):
        super().__init__(message)
        self.close_code = close_code


class Frame:
    __slots__ = ('fin', 'opcode', 'payload')

    def __init__(self, fin: bool, opcode: int, payload: bytes):
        self.fin = fin
        self.opcode = opcode
        self.payload = payload

    @property
    def is_control(self) -> bool:
        return self.opcode >= 0x8

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return 'Frame(opcode=0x%x, fin=%s, len=%d)' % (self.opcode, self.fin, len(self.payload))


def compute_accept_key(sec_websocket_key: str) -> str:
    """Sec-WebSocket-Accept = base64(sha1(key + GUID))。"""
    digest = hashlib.sha1((sec_websocket_key.strip() + GUID).encode('ascii')).digest()
    return base64.b64encode(digest).decode('ascii')


def decode_base64_text(payload: bytes) -> bytes | None:
    """把文本帧里的 base64 内容还原成字节, 解不出来返回 None。

    浏览器端客户端的写法并不统一: 有的省略 '=' 补齐, 有的用 URL-safe 字符表(- 和 _),
    有的会插入换行。这里统一兼容; 结果里出现非法字符时按标准库规则处理。
    """
    text = ''.join(payload.decode('utf-8', 'ignore').split())
    if not text:
        return b''
    text = text.replace('-', '+').replace('_', '/')
    text += '=' * (-len(text) % 4)
    try:
        return base64.b64decode(text, validate=False)
    except Exception:
        return None


def encode_frame(opcode: int, payload: bytes = b'', fin: bool = True, mask: bool = False) -> bytes:
    """组帧。服务端 -> 客户端不加掩码; 客户端 -> 服务端必须加掩码。"""
    length = len(payload)
    header = bytearray()
    header.append((0x80 if fin else 0x00) | (opcode & 0x0F))
    mask_bit = 0x80 if mask else 0x00
    if length < 126:
        header.append(mask_bit | length)
    elif length <= 0xFFFF:
        header.append(mask_bit | 126)
        header += length.to_bytes(2, 'big')
    else:
        header.append(mask_bit | 127)
        header += length.to_bytes(8, 'big')
    if mask:
        mask_key = secrets.token_bytes(4)
        header += mask_key
        payload = bytes(byte ^ mask_key[index & 3] for index, byte in enumerate(payload))
    return bytes(header) + payload


def apply_mask(data: bytes, mask_key: bytes) -> bytes:
    """用 4 字节掩码还原数据。大数据用大整数异或, 避免逐字节循环。"""
    if not data:
        return data
    repeats = (len(data) + 3) // 4
    pattern = (mask_key * repeats)[:len(data)]
    return (int.from_bytes(data, 'big') ^ int.from_bytes(pattern, 'big')).to_bytes(len(data), 'big')


class FrameDecoder:
    """增量式帧解析器: 喂字节, 得到帧列表(分片消息会在结束后合并成单帧)。"""

    def __init__(self, max_payload: int = DEFAULT_MAX_PAYLOAD):
        self.max_payload = max_payload
        self._buffer = b''
        self._fragment_opcode: int | None = None
        self._fragment_parts: list[bytes] = []
        self._fragment_size = 0

    def feed(self, data: bytes) -> list[Frame]:
        self._buffer += data
        frames: list[Frame] = []
        while True:
            frame = self._next_frame()
            if frame is _NEED_MORE:
                break
            if frame is not None:  # 分片中间帧会被消费但不产生帧
                frames.append(frame)
        return frames

    def _next_frame(self):
        buffer = self._buffer
        if len(buffer) < 2:
            return _NEED_MORE
        first, second = buffer[0], buffer[1]
        fin = bool(first & 0x80)
        if first & 0x70:
            raise ProtocolError('RSV 位被置位(未协商任何扩展)')
        opcode = first & 0x0F
        masked = bool(second & 0x80)
        length = second & 0x7F
        if opcode >= 0x8 and (not fin or length > 125):
            raise ProtocolError('控制帧必须不分片且长度不超过 125')

        offset = 2
        if length == 126:
            if len(buffer) < 4:
                return _NEED_MORE
            length = int.from_bytes(buffer[2:4], 'big')
            offset = 4
        elif length == 127:
            if len(buffer) < 10:
                return _NEED_MORE
            length = int.from_bytes(buffer[2:10], 'big')
            offset = 10
            if length >> 63:
                raise ProtocolError('帧长度非法')
        if length > self.max_payload:
            raise ProtocolError('帧长度 %d 超过上限 %d' % (length, self.max_payload))

        mask_key = b''
        if masked:
            if len(buffer) < offset + 4:
                return _NEED_MORE
            mask_key = buffer[offset:offset + 4]
            offset += 4
        if len(buffer) < offset + length:
            return _NEED_MORE

        payload = buffer[offset:offset + length]
        self._buffer = buffer[offset + length:]
        if masked:
            payload = apply_mask(payload, mask_key)
        return self._classify(fin, opcode, payload)

    def _classify(self, fin: bool, opcode: int, payload: bytes) -> Frame | None:
        if opcode >= 0x8:  # 控制帧原样透出, 不参与分片状态
            return Frame(fin, opcode, payload)
        if opcode == OP_CONTINUATION:
            if self._fragment_opcode is None:
                raise ProtocolError('收到续帧, 但此前没有分片消息')
            self._fragment_parts.append(payload)
            self._fragment_size += len(payload)
            if self._fragment_size > self.max_payload:
                raise ProtocolError('分片消息超过上限')
            if not fin:
                return None
            data = b''.join(self._fragment_parts)
            start_opcode = self._fragment_opcode
            self._reset_fragments()
            return Frame(True, start_opcode, data)
        if opcode in (OP_TEXT, OP_BINARY):
            if self._fragment_opcode is not None:
                raise ProtocolError('上一条分片消息尚未结束')
            if fin:
                return Frame(True, opcode, payload)
            self._fragment_opcode = opcode
            self._fragment_parts = [payload]
            self._fragment_size = len(payload)
            return None
        raise ProtocolError('未知 opcode: 0x%x' % opcode)

    def _reset_fragments(self) -> None:
        self._fragment_opcode = None
        self._fragment_parts = []
        self._fragment_size = 0


def close_payload(code: int | None = None, reason: str = '') -> bytes:
    """生成关闭帧负载。"""
    if code is None:
        return b''
    data = code.to_bytes(2, 'big')
    if reason:
        data += reason.encode('utf-8')[:123]
    return data


def parse_close_payload(payload: bytes) -> tuple[int, str]:
    if len(payload) >= 2:
        code = int.from_bytes(payload[:2], 'big')
        return code, payload[2:].decode('utf-8', 'replace')
    return 1005, ''


def parse_http_head(data: bytes) -> tuple[str, dict[str, str]]:
    """解析 HTTP 请求头, 返回 (请求行, 小写键的请求头字典)。"""
    text = data.split(b'\r\n\r\n', 1)[0].decode('latin-1')
    lines = text.split('\r\n')
    request_line = lines[0].strip()
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line or ':' not in line:
            continue
        name, _, value = line.partition(':')
        headers[name.strip().lower()] = value.strip()
    return request_line, headers


def handshake_response(sec_websocket_key: str, subprotocol: str | None = None) -> bytes:
    """生成 101 Switching Protocols 响应。

    不返回 Sec-WebSocket-Extensions, 浏览器因此不会启用压缩, 帧里就是原始字节。
    """
    lines = [
        'HTTP/1.1 101 Switching Protocols',
        'Upgrade: websocket',
        'Connection: Upgrade',
        'Sec-WebSocket-Accept: %s' % compute_accept_key(sec_websocket_key),
    ]
    if subprotocol:
        lines.append('Sec-WebSocket-Protocol: %s' % subprotocol)
    return ('\r\n'.join(lines) + '\r\n\r\n').encode('ascii')


def http_response(status: str, body: bytes = b'', content_type: str = 'application/json; charset=utf-8') -> bytes:
    head = (
        'HTTP/1.1 %s\r\n'
        'Content-Type: %s\r\n'
        'Content-Length: %d\r\n'
        'Cache-Control: no-store\r\n'
        'Connection: close\r\n\r\n' % (status, content_type, len(body))
    )
    return head.encode('ascii') + body


def first_subprotocol(header_value: str | None) -> str | None:
    """客户端请求的子协议列表里取第一个(按客户端自己的偏好顺序)。"""
    if not header_value:
        return None
    for item in header_value.split(','):
        token = item.strip()
        if token:
            return token
    return None