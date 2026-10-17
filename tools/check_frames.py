"""像真正的 EaglercraftX 客户端那样读代理发回来的数据, 校验"一个帧 = 一个原版包"。

用法:
    py -3.14 -X utf8 tools\\check_frames.py
    py -3.14 -X utf8 tools\\check_frames.py --url wss://127.0.0.1:1000 --seconds 20

为什么需要它: 浏览器端客户端读 WebSocket 帧时是**直接拿帧的开头当包 id** 的 —— 帧里
既没有原版的 [VarInt 包长] 前缀, 也没有压缩。所以代理必须"一个包发一个帧, 帧里就是
裸包"。本工具按这个规则严格校验回程的每一个帧:

* 包 id 必须是 1.8 客户端方向的合法 id;
* 包内容要被正好解析完(不多不少);
* 游戏阶段出现 Set Compression 直接算错(客户端根本不支持压缩)。

只要出现"未知包 id"或"结构对不上", 就说明封帧又错了 —— 客户端会卡在加载界面。

退出码: 0 = 全部合法; 1 = 发现可疑数据。
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import socket
import ssl
import struct
import sys
import threading
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcjs_proxy import eagler, vanilla, wsproto       # noqa: E402
from mcjs_proxy.config import Config                   # noqa: E402


# ---------------------------------------------------------------- 数据读取

class Reader:
    """按 1.8 的数据类型读一个包的内容, 读过头就报错。"""

    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def left(self) -> int:
        return len(self.data) - self.pos

    def take(self, size: int) -> bytes:
        if self.pos + size > len(self.data):
            raise ValueError('读到第 %d 字节就没了(还差 %d)'
                             % (self.pos, self.pos + size - len(self.data)))
        chunk = self.data[self.pos:self.pos + size]
        self.pos += size
        return chunk

    def varint(self) -> int:
        value, self.pos = vanilla.read_varint(self.data, self.pos)
        return value

    def u8(self) -> int:
        return self.take(1)[0]

    def i8(self) -> int:
        return int.from_bytes(self.take(1), 'big', signed=True)

    def u16(self) -> int:
        return int.from_bytes(self.take(2), 'big')

    def i16(self) -> int:
        return int.from_bytes(self.take(2), 'big', signed=True)

    def i32(self) -> int:
        return int.from_bytes(self.take(4), 'big', signed=True)

    def i64(self) -> int:
        return int.from_bytes(self.take(8), 'big', signed=True)

    def f32(self) -> float:
        return struct.unpack('>f', self.take(4))[0]

    def f64(self) -> float:
        return struct.unpack('>d', self.take(8))[0]

    def boolean(self) -> bool:
        return self.u8() != 0

    def string(self) -> str:
        return self.take(self.varint()).decode('utf-8', 'replace')

    def uuid(self) -> bytes:
        return self.take(16)

    def rest(self) -> bytes:
        return self.take(self.left())


# 客户端方向 (1.8.8) 的包 id -> (名字, 严格解析函数)
# 解析函数读完后必须刚好读完整个帧, 否则说明封帧错了
PARSERS = {
    0x00: ('KeepAlive', lambda r: r.varint()),
    0x01: ('JoinGame', lambda r: (r.i32(), r.u8(), r.i8(), r.u8(), r.u8(),
                                  r.string(), r.boolean())),
    0x02: ('ChatMessage', lambda r: (r.string(), r.u8())),
    0x03: ('TimeUpdate', lambda r: (r.i64(), r.i64())),
    0x05: ('SpawnPosition', lambda r: r.i64()),
    0x06: ('UpdateHealth', lambda r: (r.f32(), r.varint(), r.f32())),
    0x07: ('Respawn', lambda r: (r.i32(), r.u8(), r.u8(), r.string())),
    0x08: ('PlayerPositionAndLook', lambda r: (r.f64(), r.f64(), r.f64(),
                                               r.f32(), r.f32(), r.u8())),
    0x09: ('HeldItemChange', lambda r: r.i8()),
    0x0B: ('Animation', lambda r: (r.varint(), r.u8())),
    0x0D: ('CollectItem', lambda r: (r.varint(), r.varint(), r.varint())),
    0x12: ('EntityVelocity', lambda r: (r.varint(), r.i16(), r.i16(), r.i16())),
    0x13: ('DestroyEntities', lambda r: [r.varint() for _ in range(r.varint())]),
    0x14: ('Entity', lambda r: r.varint()),
    0x15: ('EntityRelativeMove', lambda r: (r.varint(), r.i8(), r.i8(), r.i8())),
    0x16: ('EntityLook', lambda r: (r.varint(), r.i8(), r.i8())),
    0x17: ('EntityLookAndRelativeMove', lambda r: (r.varint(), r.i8(), r.i8(), r.i8(),
                                                   r.i8(), r.i8())),
    0x18: ('EntityTeleport', lambda r: (r.varint(), r.i32(), r.i32(), r.i32(),
                                        r.i8(), r.i8(), r.boolean())),
    0x19: ('EntityHeadLook', lambda r: (r.varint(), r.i8())),
    0x1A: ('EntityStatus', lambda r: (r.i32(), r.i8())),
    0x1B: ('AttachEntity', lambda r: (r.i32(), r.i32(), r.boolean())),
    0x1D: ('EntityEffect', lambda r: (r.varint(), r.u8(), r.u8(), r.varint(), r.u8())),
    0x1E: ('RemoveEntityEffect', lambda r: (r.varint(), r.u8())),
    0x1F: ('SetExperience', lambda r: (r.f32(), r.varint(), r.varint())),
    0x20: ('EntityProperties', lambda r: _entity_properties(r)),
    0x21: ('ChunkData', lambda r: _chunk_data(r)),
    0x22: ('MultiBlockChange', lambda r: (r.i32(), r.i32(), r.u16(), r.rest())),
    0x23: ('BlockChange', lambda r: (r.i64(), r.varint())),
    0x25: ('BlockBreakAnimation', lambda r: (r.varint(), r.i64(), r.i8())),
    0x26: ('MapChunkBulk', lambda r: _map_chunk_bulk(r)),
    0x27: ('Explosion', lambda r: _explosion(r)),
    0x28: ('Effect', lambda r: (r.i32(), r.i64(), r.i32(), r.boolean())),
    0x29: ('SoundEffect', lambda r: (r.string(), r.i32(), r.i32(), r.i32(),
                                     r.f32(), r.f32())),
    0x2A: ('Particle', lambda r: _particle(r)),
    0x2B: ('ChangeGameState', lambda r: (r.u8(), r.f32())),
    0x2C: ('SpawnGlobalEntity', lambda r: (r.varint(), r.u8(), r.i32(), r.i32(), r.i32())),
    0x2D: ('OpenWindow', lambda r: (r.u8(), r.string(), r.string(), r.u8())),
    0x2E: ('CloseWindow', lambda r: r.u8()),
    0x31: ('WindowProperty', lambda r: (r.u8(), r.i16(), r.i16())),
    0x32: ('ConfirmTransaction', lambda r: (r.i8(), r.i16(), r.boolean())),
    0x33: ('UpdateSign', lambda r: (r.i64(), r.string(), r.string(), r.string(), r.string())),
    0x36: ('OpenSignEditor', lambda r: r.i64()),
    0x38: ('PlayerListItem', lambda r: _player_list_item(r)),
    0x39: ('PlayerAbilities', lambda r: (r.u8(), r.f32(), r.f32())),
    0x3B: ('ScoreboardObjective', lambda r: _scoreboard_objective(r)),
    0x3C: ('UpdateScore', lambda r: (r.string(), r.u8(), r.string(), r.varint())),
    0x3D: ('DisplayScoreboard', lambda r: (r.i8(), r.string())),
    0x3F: ('PluginMessage', lambda r: (r.string(), r.rest())),
    0x40: ('Disconnect', lambda r: r.string()),
    0x41: ('ServerDifficulty', lambda r: r.u8()),
    0x42: ('CombatEvent', lambda r: _combat_event(r)),
    0x43: ('Camera', lambda r: r.varint()),
    0x46: ('SetCompression', lambda r: r.varint()),
    0x47: ('PlayerListHeaderFooter', lambda r: (r.string(), r.string())),
    0x48: ('ResourcePackSend', lambda r: (r.string(), r.string())),
}

# id 合法但结构太啰嗦(要解析 NBT / 元数据), 这里只检查 id 不检查内容
LOOSE_IDS = {
    0x04: 'EntityEquipment', 0x0A: 'UseBed', 0x0C: 'SpawnPlayer',
    0x0E: 'SpawnObject', 0x0F: 'SpawnMob', 0x10: 'SpawnPainting',
    0x11: 'SpawnExperienceOrb', 0x1C: 'EntityMetadata', 0x24: 'BlockAction',
    0x2F: 'SetSlot', 0x30: 'WindowItems', 0x31: 'WindowProperty',
    0x34: 'Map', 0x35: 'UpdateBlockEntity', 0x36: 'OpenSignEditor',
    0x37: 'Statistics', 0x3A: 'TabComplete', 0x3E: 'Teams',
    0x44: 'WorldBorder', 0x45: 'Title', 0x49: 'UpdateEntityNBT',
}

PLAY_MAX_ID = 0x49


def _chunk_data(r: Reader):
    chunk_x, chunk_z, full = r.i32(), r.i32(), r.boolean()
    size = r.varint()
    if size < 0 or size > r.left():
        raise ValueError('ChunkData 声明 %d 字节, 实际只剩 %d' % (size, r.left()))
    r.take(size)


def _map_chunk_bulk(r: Reader):
    r.boolean()
    count = r.varint()
    for _ in range(count):
        r.i32(), r.i32(), r.u16()
    for _ in range(count):
        size = r.varint()
        if size < 0 or size > r.left():
            raise ValueError('MapChunkBulk 声明 %d 字节, 实际只剩 %d' % (size, r.left()))
        r.take(size)


def _explosion(r: Reader):
    r.f32(), r.f32(), r.f32(), r.f32()
    count = r.i32()
    if count < 0 or count * 3 > r.left() + 12:
        raise ValueError('Explosion 声明 %d 个方块, 剩下只有 %d 字节' % (count, r.left()))
    for _ in range(count):
        r.i8(), r.i8(), r.i8()
    r.f32(), r.f32(), r.f32()


def _particle(r: Reader):
    r.i32(), r.boolean()
    r.f32(), r.f32(), r.f32()
    r.f32(), r.f32(), r.f32()
    r.f32()
    for _ in range(r.i32()):
        r.varint()


def _entity_properties(r: Reader):
    r.varint()
    for _ in range(r.i32()):
        r.string(), r.f64()
        for _ in range(r.i16()):
            r.uuid(), r.f64(), r.i8()


def _player_list_item(r: Reader):
    action = r.varint()
    for _ in range(r.varint()):
        r.uuid()
        if action == 0:                      # 加人: 名字 + 属性列表(皮肤签名很占地方)
            r.string()
            for _ in range(r.varint()):
                r.string(), r.string()
                if r.boolean():
                    r.string()
        elif action == 1:
            r.varint()
        elif action == 2:
            r.varint()
        elif action == 3:
            r.boolean()
        elif action == 4:
            r.string()


def _scoreboard_objective(r: Reader):
    r.string()
    mode = r.u8()
    if mode != 1:                            # 1 = 删除, 没有后面两个字段
        r.string(), r.string()               # 显示名 + 类型(integer/hearts)


def _combat_event(r: Reader):
    event = r.varint()
    if event == 0:
        r.varint(), r.i32()
    elif event == 1:
        r.varint()
    elif event == 2:
        r.varint(), r.i32(), r.i32()


def check_frame(frame: bytes) -> tuple[str, str]:
    """校验一个帧; 返回 (结果, 说明)。结果: ok / loose / bad。"""
    if not frame:
        return 'bad', '空帧'
    try:
        packet_id, at = vanilla.read_varint(frame, 0)
    except vanilla.ProtocolError as exc:
        return 'bad', '开头不是合法的包 id: %s' % exc
    if packet_id > PLAY_MAX_ID:
        return 'bad', '包 id 0x%02x 超出 1.8 游戏阶段范围(最大 0x49), 说明帧里带了长度前缀' % packet_id
    body = frame[at:]
    if packet_id in LOOSE_IDS:
        return 'loose', LOOSE_IDS[packet_id]
    entry = PARSERS.get(packet_id)
    if entry is None:
        return 'bad', '包 id 0x%02x 在 1.8 客户端方向不存在' % packet_id
    name, parse = entry
    reader = Reader(body)
    try:
        parse(reader)
    except Exception as exc:
        return 'bad', '%s 结构对不上: %s' % (name, exc)
    if reader.left() != 0:
        return 'bad', ('%s 读完还剩 %d 字节(帧共 %d 字节): %s'
                       % (name, reader.left(), len(frame), reader.rest()[:16].hex(' ')))
    return 'ok', name


# ---------------------------------------------------------------- WebSocket 客户端

class MiniWs:
    """够用的 WebSocket 客户端(带掩码, 读服务端帧)。"""

    def __init__(self, url: str, timeout: float = 10.0):
        parsed = urlparse(url)
        secure = parsed.scheme in ('wss', 'https')
        host = parsed.hostname or '127.0.0.1'
        port = parsed.port or (443 if secure else 80)
        path = parsed.path or '/'
        if parsed.query:
            path += '?' + parsed.query
        sock = socket.create_connection((host, port), timeout=timeout)
        if secure:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            sock = context.wrap_socket(sock, server_hostname=host)
        sock.settimeout(timeout)
        key = base64.b64encode(os.urandom(16)).decode('ascii')
        request = ('GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\n'
                   'Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n'
                   'Sec-WebSocket-Version: 13\r\n\r\n'
                   % (path, host, port, key))
        sock.sendall(request.encode('ascii'))
        head = b''
        while b'\r\n\r\n' not in head:
            chunk = sock.recv(4096)
            if not chunk:
                raise RuntimeError('WebSocket 握手时连接被关闭')
            head += chunk
        first_line = head.split(b'\r\n', 1)[0].decode('latin-1')
        if '101' not in first_line:
            raise RuntimeError('WebSocket 握手失败: %s' % first_line)
        self.sock = sock
        self.decoder = wsproto.FrameDecoder()
        self.inbox: list[wsproto.Frame] = []
        self.closed: tuple[int, str] | None = None
        self.eof = False
        self._pending = head.split(b'\r\n\r\n', 1)[1]
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()

    def _reader(self) -> None:
        try:
            while True:
                chunk = self._pending or self.sock.recv(65536)
                self._pending = b''
                if not chunk:
                    self.eof = True
                    return
                for frame in self.decoder.feed(chunk):
                    with self._lock:
                        if frame.opcode == wsproto.OP_CLOSE:
                            self.closed = wsproto.parse_close_payload(frame.payload)
                        elif frame.opcode in (wsproto.OP_BINARY, wsproto.OP_TEXT):
                            self.inbox.append(frame)
        except (OSError, ssl.SSLError):
            self.eof = True

    def send(self, data: bytes) -> None:
        self.sock.sendall(wsproto.encode_frame(wsproto.OP_BINARY, data, mask=True))

    def recv(self, timeout: float = 5.0) -> bytes | None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            with self._lock:
                if self.inbox:
                    return self.inbox.pop(0).payload
            time.sleep(0.01)
        return None

    def close(self) -> None:
        try:
            self.sock.sendall(wsproto.encode_frame(
                wsproto.OP_CLOSE, wsproto.close_payload(1000, 'bye'), mask=True))
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


# ---------------------------------------------------------------- 客户端握手包

def client_version_packet(username: str) -> bytes:
    out = bytearray([eagler.PROTOCOL_CLIENT_VERSION, 0x02])
    out += (3).to_bytes(2, 'big')                  # 支持 3 个握手协议
    for item in (3, 4, 5):
        out += item.to_bytes(2, 'big')
    out += (1).to_bytes(2, 'big') + (47).to_bytes(2, 'big')
    for text in ('EaglercraftX', 'u53'):
        out += bytes([len(text)]) + text.encode('ascii')
    out.append(0)                                  # 不带密码
    out += bytes([len(username)]) + username.encode('ascii')
    return bytes(out)


def request_login_packet(username: str) -> bytes:
    out = bytearray([eagler.PROTOCOL_CLIENT_REQUEST_LOGIN])
    for field in (username.encode('ascii'), b'default', b''):
        out += bytes([len(field)]) + field
    out += bytes([0, 0])                           # 不用 cookie
    out += eagler._varint(0)                       # standardCaps
    out.append(0)                                  # extCaps 数量
    return bytes(out)


def keep_alive_reply(packet_id_value: int) -> bytes:
    return vanilla.write_varint(vanilla.PLAY_KEEP_ALIVE) + vanilla.write_varint(packet_id_value)


def client_settings() -> bytes:
    locale = b'zh_CN'
    return (vanilla.write_varint(0x15)
            + vanilla.write_varint(len(locale)) + locale
            + bytes([8, 0, 1, 0x7F]))              # 视距 / 聊天 / 颜色 / 皮肤部位


def brand_plugin_message(brand: str = 'EaglercraftX') -> bytes:
    channel = b'MC|Brand'
    return (vanilla.write_varint(vanilla.CLIENT_PLUGIN_MESSAGE)
            + vanilla.write_varint(len(channel)) + channel
            + vanilla.write_varint(len(brand)) + brand.encode('ascii'))


# ---------------------------------------------------------------- 主流程

def default_url() -> str:
    try:
        config = Config.load()
    except Exception:
        return 'wss://127.0.0.1:1000'
    if config.tls_enabled and int(config.wss_port) > 0:
        return 'wss://127.0.0.1:%d' % int(config.wss_port)
    if int(config.ws_port) > 0:
        return 'ws://127.0.0.1:%d' % int(config.ws_port)
    return 'wss://127.0.0.1:1000'


def main() -> int:
    parser = argparse.ArgumentParser(description='校验代理回程数据是不是"一个帧一个原版包"')
    parser.add_argument('--url', default=None, help='代理监听地址(默认读 config.json)')
    parser.add_argument('--seconds', type=float, default=20.0, help='收多久(默认 20 秒)')
    parser.add_argument('--username', default='ProxyCheck', help='用哪个名字登录')
    parser.add_argument('--no-play', action='store_true', help='不模拟客户端发游戏包')
    args = parser.parse_args()

    url = args.url or default_url()
    print('连接 %s (用名字 %s)' % (url, args.username))
    client = None
    last_error: Exception | None = None
    deadline = time.time() + 10.0
    while client is None and time.time() < deadline:
        try:
            client = MiniWs(url)
        except Exception as exc:          # 代理可能刚启动, 稍微等一下再试
            last_error = exc
            time.sleep(0.5)
    if client is None:
        print('连不上代理: %s' % last_error)
        print('(确认代理已经在运行, 而且地址/端口对得上)')
        return 1

    try:
        client.send(client_version_packet(args.username))
        frame = client.recv(8.0)
        if frame is None:
            print('没等到服务端版本包')
            return 1
        if frame[0] != eagler.PROTOCOL_SERVER_VERSION:
            print('第一个回包不是服务端版本包(0x%02x)' % frame[0])
            return 1
        protocol = int.from_bytes(frame[1:3], 'big')
        game = int.from_bytes(frame[3:5], 'big')
        print('服务端版本包: 握手协议 v%d / 游戏协议 %d' % (protocol, game))

        client.send(request_login_packet(args.username))
        frame = client.recv(10.0)
        if frame is None:
            print('没等到允许登录包')
            return 1
        if frame[0] == eagler.PROTOCOL_SERVER_DENY_LOGIN:
            length = int.from_bytes(frame[1:3], 'big')
            print('服务器拒绝登录: %s' % frame[3:3 + length].decode('utf-8', 'replace'))
            return 1
        if frame[0] != eagler.PROTOCOL_SERVER_ALLOW_LOGIN:
            print('第二个回包不是允许登录包(0x%02x)' % frame[0])
            return 1
        print('允许登录')

        client.send(bytes([eagler.PROTOCOL_CLIENT_FINISH_LOGIN]))
        frame = client.recv(10.0)
        if frame is None or frame[0] != eagler.PROTOCOL_SERVER_FINISH_LOGIN:
            print('没等到完成登录包')
            return 1
        print('完成登录, 开始校验游戏数据(一个帧必须是一个完整的 1.8 包)\n')

        sent_play = False
        bad: list[str] = []
        ok_count = loose_count = 0
        names: Counter[str] = Counter()
        first_names: list[str] = []
        deadline = time.time() + args.seconds
        while time.time() < deadline and client.closed is None:
            frame = client.recv(0.5)
            if frame is None:
                continue
            result, detail = check_frame(frame)
            if result == 'bad':
                if len(bad) < 8:
                    bad.append('%s | 帧内容: %s' % (detail, frame[:24].hex(' ')))
                continue
            if result == 'loose':
                loose_count += 1
            else:
                ok_count += 1
            names[detail] += 1
            if len(first_names) < 12:
                first_names.append(detail)
            if detail == 'KeepAlive' and not args.no_play:
                reader = Reader(frame)
                reader.varint()
                client.send(keep_alive_reply(reader.varint()))
            if not sent_play and not args.no_play and detail == 'JoinGame':
                client.send(client_settings())
                client.send(brand_plugin_message())
                sent_play = True

        print('包统计(前 12 个): %s' % ', '.join(first_names))
        print('严格校验通过 %d 个, 只查 id %d 个, 可疑 %d 个'
              % (ok_count, loose_count, len(bad)))
        print('各包数量: %s' % ', '.join('%s×%d' % (name, count)
                                        for name, count in names.most_common(20)))
        if 'SetCompression' in names:
            print('!! 游戏阶段出现了 Set Compression, 客户端不支持压缩, 这是错的')
        if bad:
            print('\n可疑帧:')
            for line in bad:
                print('  - %s' % line)
        if client.closed is not None:
            code, reason = client.closed
            print('\n连接被关闭: code=%d %s' % (code, reason))
        if ok_count == 0:
            print('\n一个包都没收到 —— 目标服务器可能没发游戏数据, 或者代理还没进游戏阶段')
        if bad or 'SetCompression' in names:
            print('\n结论: 封帧仍然有问题(客户端会卡在加载界面)')
            return 1
        print('\n结论: 回程数据都是"一个帧一个裸包", 客户端能正常解析')
        return 0
    finally:
        client.close()


if __name__ == '__main__':
    sys.exit(main())
