"""EaglercraftX 1.8 客户端握手协议 (服务端侧实现)。

浏览器端客户端 (EaglercraftX 系) **不发送原版握手包**: 它先发一段自己协议的握手,
由服务端完成"版本协商 → 请求登录 → 允许登录 → 完成登录"流程, 之后才切换成原版
1.8.8 的游戏数据流。原版服务器看不懂这段数据, 所以会直接关连接 —— 需要中间层
把这段流程代答掉。

协议细节来自 EaglercraftX 服务端实现 (lax1dude/eaglerxserver, core/.../handshake 与
core/.../pipeline/WebSocketEaglerInitialHandler), 与实测抓包完全吻合:

    客户端首个数据包 (实测 37 字节):
      01 02                     标记: 0x01 = EaglercraftX 1.8, 0x02 = 握手协议 v2~v5
      00 03                     后面有 3 个"支持的握手协议版本"
      00 03 00 04 00 05         = 3, 4, 5
      00 01                     后面有 1 个"支持的 Minecraft 协议版本"
      00 2f                     = 47 = Minecraft 1.8.8
      0c "EaglercraftX"         客户端品牌
      03 "u53"                  客户端版本号
      00                        clientAuth = false
      04 "nopp"                 authUsername (未开启验证时是占位内容)

所有握手包都是"一个 WebSocket 帧一个包", 没有长度前缀, 因此解析时必须刚好吃掉整帧。
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

# 握手包类型 (HandshakePacketTypes)
PROTOCOL_CLIENT_VERSION = 0x01
PROTOCOL_SERVER_VERSION = 0x02
PROTOCOL_VERSION_MISMATCH = 0x03
PROTOCOL_CLIENT_REQUEST_LOGIN = 0x04
PROTOCOL_SERVER_ALLOW_LOGIN = 0x05
PROTOCOL_SERVER_DENY_LOGIN = 0x06
PROTOCOL_CLIENT_PROFILE_DATA = 0x07
PROTOCOL_CLIENT_FINISH_LOGIN = 0x08
PROTOCOL_SERVER_FINISH_LOGIN = 0x09
PROTOCOL_SERVER_REDIRECT_TO = 0x0A
PROTOCOL_SERVER_ERROR = 0xFF

# 服务端错误码
ERROR_UNKNOWN_PACKET = 0x01
ERROR_INVALID_PACKET = 0x02
ERROR_WRONG_PACKET = 0x03
ERROR_CUSTOM_MESSAGE = 0x08
ERROR_AUTHENTICATION_REQUIRED = 0x09

# 我们实现了 v2~v5 四档握手协议; 客户端会用它列表里的最高一档
SUPPORTED_HANDSHAKE_PROTOCOLS = (2, 3, 4, 5)
# 浏览器端客户端只会 1.8, 只支持这一个协议版本
SUPPORTED_MC_PROTOCOLS = (47,)

MARKER_CLASSIC = 0x01        # 首个字节: EaglercraftX 1.8
MARKER_MODERN = 0x02         # 第二个字节: v2~v5 握手
MARKER_LEGACY = 0x01         # 第二个字节: v1 握手

USERNAME_PATTERN = re.compile(r'^[A-Za-z0-9_]{3,16}$')
MAX_STRING = 255
MAX_LIST = 16


class HandshakeError(Exception):
    """握手数据不符合协议。"""


# ---------- 工具 ----------

def _as_u16(value: int) -> bytes:
    return int(value).to_bytes(2, 'big')


def _read_u16(data: bytes, pos: int) -> tuple[int, int]:
    if pos + 2 > len(data):
        raise HandshakeError('u16 越界')
    return int.from_bytes(data[pos:pos + 2], 'big'), pos + 2


def _write_string(text: str) -> bytes:
    encoded = text.encode('utf-8')
    if len(encoded) > MAX_STRING:
        encoded = encoded[:MAX_STRING]
    return bytes([len(encoded)]) + encoded


def _read_string(data: bytes, pos: int) -> tuple[str, int]:
    if pos >= len(data):
        raise HandshakeError('字符串长度越界')
    length = data[pos]
    start = pos + 1
    end = start + length
    if end > len(data):
        raise HandshakeError('字符串越界')
    return data[start:end].decode('utf-8', 'replace'), end


def offline_uuid(username: str) -> bytes:
    """离线模式 UUID: 和 Java 的 UUID.nameUUIDFromBytes("OfflinePlayer:"+名字) 一致。

    服务端与本地的实体 UUID 都按这个算, 三边必须一致, 否则客户端会把玩家自己
    当成陌生人(名字列表/皮肤/实体归属都可能错位)。
    """
    digest = bytearray(hashlib.md5(('OfflinePlayer:' + username).encode('utf-8')).digest())
    digest[6] = (digest[6] & 0x0F) | 0x30        # 版本 3 (name-based)
    digest[8] = (digest[8] & 0x3F) | 0x80        # IETF 变体
    return bytes(digest)


# ---------- 客户端首个包 ----------

@dataclass
class ClientVersion:
    """客户端首个数据包的内容。"""

    handshake_protocols: list[int] = field(default_factory=list)
    mc_protocols: list[int] = field(default_factory=list)
    brand: str = ''
    version: str = ''
    auth: bool = False
    auth_username: bytes = b''

    def describe(self) -> str:
        return ('品牌 %s %s | 支持握手协议 %s | 支持游戏协议 %s | 开启验证 %s'
                % (self.brand or '?', self.version or '?',
                   self.handshake_protocols, self.mc_protocols,
                   '是' if self.auth else '否'))


def _looks_like_modern_marker(data: bytes) -> bool:
    return (len(data) >= 8 and data[0] == MARKER_CLASSIC
            and data[1] in (MARKER_MODERN, MARKER_LEGACY))


def parse_client_version(data: bytes) -> ClientVersion | None:
    """解析客户端首个数据包; 不是我们认识的格式就返回 None(按原样转发)。

    严格按照协议契约: 必须刚好吃掉整帧, 多一个字节都算不合法。
    """
    if not _looks_like_modern_marker(data):
        return None
    version = ClientVersion()
    try:
        pos = 2
        if data[1] == MARKER_LEGACY:
            # v1 客户端: u8 游戏协议, 品牌, 版本号
            if pos >= len(data):
                raise HandshakeError('v1 包不完整')
            version.mc_protocols = [data[pos]]
            pos += 1
            version.brand, pos = _read_string(data, pos)
            version.version, pos = _read_string(data, pos)
        else:
            count, pos = _read_u16(data, pos)
            if not 1 <= count <= MAX_LIST:
                raise HandshakeError('握手协议数量异常: %d' % count)
            for _ in range(count):
                value, pos = _read_u16(data, pos)
                version.handshake_protocols.append(value)
            count, pos = _read_u16(data, pos)
            if not 1 <= count <= MAX_LIST:
                raise HandshakeError('游戏协议数量异常: %d' % count)
            for _ in range(count):
                value, pos = _read_u16(data, pos)
                version.mc_protocols.append(value)
            version.brand, pos = _read_string(data, pos)
            version.version, pos = _read_string(data, pos)
            if pos >= len(data):
                raise HandshakeError('缺少 clientAuth 字段')
            version.auth = bool(data[pos])
            pos += 1
            if pos >= len(data):
                raise HandshakeError('缺少 authUsername 字段')
            length = data[pos]
            pos += 1
            if pos + length > len(data):
                raise HandshakeError('authUsername 越界')
            version.auth_username = data[pos:pos + length]
            pos += length
        if pos != len(data):
            raise HandshakeError('首个包末尾有 %d 个多余字节' % (len(data) - pos))
    except HandshakeError:
        return None
    return version


def select_protocols(client: ClientVersion) -> tuple[int, int] | None:
    """挑出双方都支持的最高握手协议版本与游戏协议版本。"""
    handshake = [item for item in client.handshake_protocols
                 if item in SUPPORTED_HANDSHAKE_PROTOCOLS]
    mc = [item for item in client.mc_protocols if item in SUPPORTED_MC_PROTOCOLS]
    if not handshake or not mc:
        return None
    return max(handshake), max(mc)


# ---------- 服务端应答 ----------

def pack_server_version(handshake_protocol: int, mc_protocol: int, brand: str,
                        version: str, auth_method: int = 0,
                        salt: bytes = b'', nickname_selection: bool = False) -> bytes:
    """服务端版本号包 (0x02), 对应 HandshakerV2~V5 的 sendPacketVersionNoAuth。"""
    out = bytearray([PROTOCOL_SERVER_VERSION])
    out += _as_u16(handshake_protocol)
    out += _as_u16(mc_protocol)
    out += _write_string(brand)
    out += _write_string(version)
    out.append(auth_method & 0xFF)
    out += _as_u16(len(salt))
    out += salt
    if handshake_protocol >= 4:
        out.append(1 if nickname_selection else 0)
    return bytes(out)


def pack_version_mismatch(handshake_protocols, mc_min: int, mc_max: int,
                          message: str) -> bytes:
    """版本不匹配包 (0x03)。"""
    out = bytearray([PROTOCOL_VERSION_MISMATCH])
    out += _as_u16(len(handshake_protocols))
    for item in handshake_protocols:
        out += _as_u16(item)
    out += _as_u16(2)
    out += _as_u16(mc_min)
    out += _as_u16(mc_max)
    out += _write_string(message)
    return bytes(out)


def pack_allow_login(username: str, uuid_bytes: bytes, handshake_protocol: int,
                     capabilities: int = 0, capability_versions: bytes = b'',
                     ext_count: int = 0) -> bytes:
    """允许登录包 (0x05)。v5 才带能力位, v2~v4 只有名字 + UUID。"""
    out = bytearray([PROTOCOL_SERVER_ALLOW_LOGIN])
    out += _write_string(username)
    if len(uuid_bytes) != 16:
        raise HandshakeError('UUID 必须是 16 字节')
    out += uuid_bytes
    if handshake_protocol >= 5:
        out += _varint(capabilities)
        out += capability_versions
        out.append(ext_count & 0xFF)
    return bytes(out)


def pack_deny_login(message: str, handshake_protocol: int) -> bytes:
    """拒绝登录包 (0x06)。v3 起长度字段是 u16。"""
    encoded = message.encode('utf-8')
    out = bytearray([PROTOCOL_SERVER_DENY_LOGIN])
    if handshake_protocol >= 3:
        if len(encoded) > 65535:
            encoded = encoded[:65535]
        out += _as_u16(len(encoded))
    else:
        if len(encoded) > 255:
            encoded = encoded[:255]
        out.append(len(encoded))
    out += encoded
    return bytes(out)


def pack_error(code: int, message: str, handshake_protocol: int) -> bytes:
    """错误包 (0xFF)。v3 起长度字段是 u16。"""
    encoded = message.encode('utf-8')
    out = bytearray([PROTOCOL_SERVER_ERROR, code & 0xFF])
    if handshake_protocol >= 3:
        if len(encoded) > 65535:
            encoded = encoded[:65535]
        out += _as_u16(len(encoded))
    else:
        if len(encoded) > 255:
            encoded = encoded[:255]
        out.append(len(encoded))
    out += encoded
    return bytes(out)


def pack_finish_login() -> bytes:
    """服务端完成登录包 (0x09), 之后就是原版游戏数据。"""
    return bytes([PROTOCOL_SERVER_FINISH_LOGIN])


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _read_varint(data: bytes, pos: int) -> tuple[int, int]:
    value = 0
    for index in range(5):
        if pos >= len(data):
            raise HandshakeError('VarInt 越界')
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << (7 * index)
        if not byte & 0x80:
            return value, pos
    raise HandshakeError('VarInt 超过 5 字节')


# ---------- 客户端登录请求 ----------

@dataclass
class LoginRequest:
    username: str = ''
    requested_server: str = ''
    password: bytes = b''
    cookie: bytes = b''
    capabilities: int = 0

    def describe(self) -> str:
        return ('用户名 %s | 客户端填写的服务器地址 %r | 密码 %s | 客户端能力位 0x%x'
                % (self.username, self.requested_server,
                   '有' if self.password else '无', self.capabilities))


def parse_request_login(data: bytes, handshake_protocol: int) -> LoginRequest:
    """解析登录请求包 (0x04), 各握手版本的字段不同:
    v1~v3: 名字, 服务器地址, 密码
    v4   : 再加 cookie 开关与内容
    v5   : 再加能力位与扩展能力表
    """
    if not data or data[0] != PROTOCOL_CLIENT_REQUEST_LOGIN:
        raise HandshakeError('不是登录请求包')
    pos = 1
    request = LoginRequest()
    request.username, pos = _read_string(data, pos)
    request.requested_server, pos = _read_string(data, pos)
    if pos >= len(data):
        raise HandshakeError('缺少密码字段')
    length = data[pos]
    pos += 1
    if pos + length > len(data):
        raise HandshakeError('密码字段越界')
    request.password = data[pos:pos + length]
    pos += length
    if handshake_protocol >= 4:
        if pos >= len(data):
            raise HandshakeError('缺少 cookie 开关')
        enable_cookie = bool(data[pos])
        pos += 1
        if pos >= len(data):
            raise HandshakeError('缺少 cookie 长度')
        cookie_len = data[pos]
        pos += 1
        if enable_cookie:
            if pos + cookie_len > len(data):
                raise HandshakeError('cookie 越界')
            request.cookie = data[pos:pos + cookie_len]
            pos += cookie_len
        elif cookie_len != 0:
            raise HandshakeError('cookie 长度不为 0')
    if handshake_protocol >= 5:
        request.capabilities, pos = _read_varint(data, pos)
        count = bin(request.capabilities).count('1')
        for _ in range(count):
            _, pos = _read_varint(data, pos)
        if pos >= len(data):
            raise HandshakeError('缺少扩展能力数量')
        ext_count = data[pos]
        pos += 1
        if ext_count > 32:
            raise HandshakeError('扩展能力数量异常: %d' % ext_count)
        for _ in range(ext_count):
            if pos + 16 > len(data):
                raise HandshakeError('扩展能力 UUID 越界')
            pos += 16
            _, pos = _read_varint(data, pos)
    if pos != len(data):
        raise HandshakeError('登录请求末尾有 %d 个多余字节' % (len(data) - pos))
    return request


def sanitize_username(username: str, fallback: str = 'MCJSEagler') -> str:
    """目标服务器只接受 [A-Za-z0-9_]{3,16}, 不合格就换一个稳定可用的名字。"""
    if USERNAME_PATTERN.match(username or ''):
        return username
    cleaned = re.sub(r'[^A-Za-z0-9_]', '', username or '')
    if len(cleaned) > 16:
        cleaned = cleaned[:16]
    if len(cleaned) < 3:
        cleaned = (cleaned + fallback)[:16]
    return cleaned
