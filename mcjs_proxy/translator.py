"""协议翻译层: 让 EaglercraftX 系浏览器客户端连上原版 Minecraft 1.8 服务器。

原版服务器和浏览器客户端的差别只在"连接开头那一段":

    浏览器客户端                          原版服务器
    ----------------                      ----------
    1. 私有握手 (版本协商/登录/完成)   ->   (完全看不懂, 直接断线)
    2. 之后就是原版 1.8.8 游戏数据     <->  原版 1.8.8 游戏数据

所以本模块做的事情就是:
* 代答第 1 步 —— 在客户端面前扮演 EaglercraftX 服务端;
* 同时在服务器面前扮演一个原版 1.8.8 客户端 (发原版握手包 + 登录包, 离线模式即可);
* 把服务器发来的登录结果翻译成客户端的"允许登录/完成登录";
* 之后双向搬运游戏数据, 顺便把两边不一致的地方补齐:
    - 压缩: 服务器可以启用压缩, 客户端这边始终不压缩(不能给它发 Set Compression),
      所以代理负责解压/再压缩;
    - 握手完成前服务器已经发来的游戏数据要缓存到"完成登录"之后再发给客户端;
    - 客户端特有的 "EAG|..." 插件消息丢掉, 原版服务器不认识这些通道。

协议格式全部来自 EaglercraftX 服务端实现 (lax1dude/eaglerxserver)。
"""

from __future__ import annotations

import json
import os
import threading

from . import crypto, eagler, vanilla
from .logger import NullLogger

# 客户端方向永远不压缩(我们不会给客户端发 Set Compression)
CLIENT_THRESHOLD = 0

# 本代理自己说的话都带这个前缀, 好和服务器说的话区分开
PREFIX = '[协议转换器] '

# 日志里给常见包 id 一个好读的名字
PACKET_NAMES = {
    (vanilla.LOGIN_DISCONNECT, 'login'): 'LoginDisconnect',
    (vanilla.LOGIN_ENCRYPTION_REQUEST, 'login'): 'EncryptionRequest',
    (vanilla.LOGIN_SUCCESS, 'login'): 'LoginSuccess',
    (vanilla.LOGIN_SET_COMPRESSION, 'login'): 'SetCompression',
    (vanilla.PLAY_KEEP_ALIVE, 'play'): 'KeepAlive',
    (vanilla.PLAY_JOIN_GAME, 'play'): 'JoinGame',
    (0x02, 'play'): 'ChatMessage',
    (0x08, 'play'): 'PlayerPositionAndLook',
    (0x21, 'play'): 'ChunkData',
    (0x26, 'play'): 'MapChunkBulk',
    (vanilla.PLAY_PLUGIN_MESSAGE, 'play'): 'PluginMessage',
    (vanilla.PLAY_DISCONNECT, 'play'): 'Disconnect',
    (vanilla.CLIENT_PLUGIN_MESSAGE, 'play'): 'PluginMessage',
}


def packet_name(packet_id: int, state: str) -> str:
    return PACKET_NAMES.get((packet_id, state), '0x%02x' % packet_id)


def note(text: str) -> str:
    """给玩家看的文本加上本代理的标识前缀。"""
    return PREFIX + text


def chat_to_text(raw) -> str:
    """把聊天组件(JSON)拍平成纯文本。"""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        parts = []
        text = raw.get('text')
        if isinstance(text, str):
            parts.append(text)
        translate = raw.get('translate')
        if isinstance(translate, str) and not parts:
            parts.append(translate)
        extra = raw.get('extra')
        if isinstance(extra, list):
            parts.append(''.join(chat_to_text(item) for item in extra))
        return ''.join(parts)
    if isinstance(raw, list):
        return ''.join(chat_to_text(item) for item in raw)
    return ''


def uuid_from_string(text: str) -> bytes | None:
    value = text.replace('-', '').strip()
    if len(value) != 32:
        return None
    try:
        return bytes.fromhex(value)
    except ValueError:
        return None


class EaglerTranslator:
    """一条连接上的 EaglercraftX <-> 原版 翻译状态机。"""

    def __init__(self, target_host: str, target_port: int, log=None, tag: str = '',
                 send_client=None, send_backend=None, request_close=None,
                 brand: str = 'MCJS-Proxy', brand_version: str = '1.0'):
        self.target_host = target_host
        self.target_port = int(target_port)
        self.log = log or NullLogger()
        self.tag = tag
        self.brand = brand
        self.brand_version = brand_version
        self._send_client = send_client or (lambda data: None)
        self._send_backend = send_backend or (lambda data: None)
        self._request_close = request_close or (lambda reason: None)

        self.phase = 'client_version'     # client_version -> request_login -> backend_login
                                          # -> allow_sent -> play / closed
        self.client_version: eagler.ClientVersion | None = None
        self.handshake_protocol = 0
        self.mc_protocol = eagler.SUPPORTED_MC_PROTOCOLS[-1]
        self.username = ''
        self.uuid = b''
        self.client_finished = False      # 客户端是否已发"完成登录"
        self.login_done = False           # 后端是否已登录成功
        self.close_reason = ''

        self.client_decoder = vanilla.Decoder(CLIENT_THRESHOLD)
        self.client_encoder = vanilla.Encoder(CLIENT_THRESHOLD)
        self.server_decoder = vanilla.Decoder(0)
        self.server_encoder = vanilla.Encoder(0)
        self.server_decrypt: crypto.AesCfb8 | None = None   # 目标服务器 -> 本代理(AES)
        self.server_encrypt: crypto.AesCfb8 | None = None   # 本代理 -> 目标服务器(AES)
        self.pending_to_client = bytearray()
        self._lock = threading.Lock()

        self.packets_to_server = 0
        self.packets_to_client = 0
        self._seen_client_ids: set[tuple[int, str]] = set()
        self._seen_server_ids: set[tuple[int, str]] = set()

    # ---------- 对外: 两个方向 ----------
    def feed_client(self, data: bytes) -> bytes:
        """喂入客户端发来的数据(WS 帧内容), 返回要发给后端服务器的字节。"""
        if not data or self.phase == 'closed':
            return b''
        with self._lock:
            if self.phase == 'play':
                out = self._client_play(data)
            elif self.phase == 'client_version':
                out = self._handle_client_version(data)
            else:
                out = self._handle_handshake_packet(data)
            return self._encode_for_backend(out)

    def feed_server(self, data: bytes) -> bytes:
        """喂入后端服务器发来的数据, 返回要发给客户端的字节。"""
        if not data or self.phase == 'closed':
            return b''
        with self._lock:
            if self.server_decrypt is not None:
                data = self.server_decrypt.decrypt(data)
            self.server_decoder.push(data)
            out = bytearray()
            while True:
                try:
                    packet = self.server_decoder.next_packet()
                except vanilla.ProtocolError as exc:
                    self._fail('解析目标服务器数据失败: %s' % exc)
                    return bytes(out)
                if packet is None:
                    return bytes(out)
                self.packets_to_client += 1
                if not self.login_done:
                    self._handle_login_packet(packet, out)
                else:
                    self._handle_play_packet(packet, out)
                if self.phase == 'closed':
                    return bytes(out)

    def _encode_for_backend(self, data: bytes) -> bytes:
        """发给后端服务器之前: 如果已经启用加密, 在这里套上 AES。"""
        if not data:
            return b''
        if self.server_encrypt is not None:
            data = self.server_encrypt.encrypt(data)
        return data

    # ---------- 客户端: 首包 ----------
    def _handle_client_version(self, data: bytes) -> bytes:
        version = eagler.parse_client_version(data)
        if version is None:
            self._fail('客户端首个数据包不是认识的 EaglercraftX 握手')
            return b''
        self.client_version = version
        self.log.info('%s 浏览器端客户端握手: %s' % (self.tag, version.describe()))

        picked = eagler.select_protocols(version)
        if picked is None:
            message = ('本代理只支持 Minecraft 1.8.8 (协议 47), 客户端提供的是 %s'
                       % (version.mc_protocols or ['?']))
            if not version.handshake_protocols:
                message = '客户端提供的是 v1 握手协议, 太旧了'
            self.log.warn('%s %s' % (self.tag, message))
            self._send(eagler.pack_version_mismatch(
                eagler.SUPPORTED_HANDSHAKE_PROTOCOLS, min(eagler.SUPPORTED_MC_PROTOCOLS),
                max(eagler.SUPPORTED_MC_PROTOCOLS), 'Outdated Client'))
            self._fail(message)
            return b''

        self.handshake_protocol, self.mc_protocol = picked
        self.phase = 'request_login'
        self._send(eagler.pack_server_version(
            self.handshake_protocol, self.mc_protocol, self.brand, self.brand_version))
        self.log.info('%s 已选择握手协议 v%d / 游戏协议 %d, 等待客户端登录请求'
                      % (self.tag, self.handshake_protocol, self.mc_protocol))
        return b''

    # ---------- 客户端: 登录请求 / 完成登录 ----------
    def _handle_handshake_packet(self, data: bytes) -> bytes:
        packet_id = data[0]
        if packet_id == eagler.PROTOCOL_CLIENT_REQUEST_LOGIN:
            if self.phase != 'request_login':
                self._fail('重复的登录请求包')
                return b''
            try:
                request = eagler.parse_request_login(data, self.handshake_protocol)
            except eagler.HandshakeError as exc:
                self._fail('登录请求解析失败: %s' % exc)
                return b''
            return self._begin_backend_login(request)
        if packet_id == eagler.PROTOCOL_CLIENT_PROFILE_DATA:
            self.log.debug('%s 忽略客户端资料数据(皮肤等) %d 字节' % (self.tag, len(data)))
            return b''
        if packet_id == eagler.PROTOCOL_CLIENT_FINISH_LOGIN:
            if len(data) != 1:
                self._fail('完成登录包格式不对')
                return b''
            self.client_finished = True
            self.log.debug('%s 客户端完成登录' % self.tag)
            self._maybe_finish_login()
            return b''
        self._fail('意料之外的握手包 0x%02x' % packet_id)
        return b''

    def _begin_backend_login(self, request: eagler.LoginRequest) -> bytes:
        raw_name = (request.username or '').strip()
        if not raw_name and self.client_version is not None:
            # 有些浏览器端客户端(实测 MCJS)发的登录请求里名字是空的, 真正的名字在
            # 握手包的 authUsername 字段里, 优先用它, 免得所有人都叫同一个备用名。
            candidate = self.client_version.auth_username.decode('utf-8', 'replace').strip()
            if eagler.USERNAME_PATTERN.match(candidate):
                raw_name = candidate
                self.log.info('%s 登录请求里没带名字, 改用客户端握手包里的名字 %r'
                              % (self.tag, candidate))
        username = eagler.sanitize_username(raw_name)
        if username != raw_name:
            self.log.warn('%s 客户端用户名 %r 不符合服务器要求, 已改用 %r'
                          % (self.tag, raw_name, username))
        self.username = username
        self.uuid = eagler.offline_uuid(username)
        self.log.info('%s 客户端请求登录: %s' % (self.tag, request.describe()))
        self.phase = 'backend_login'

        # 原版握手包(下一步 = 登录) + 登录开始包
        address = self.target_host.encode('utf-8')
        handshake = vanilla.pack(0x00, (
            vanilla.write_varint(self.mc_protocol)
            + vanilla.write_varint(len(address)) + address
            + int(self.target_port).to_bytes(2, 'big')
            + vanilla.write_varint(2)))
        login_start = vanilla.pack(0x00, (
            vanilla.write_varint(len(username.encode('utf-8')))
            + username.encode('utf-8')))
        self.log.info('%s 已向目标服务器发送原版登录 (用户名 %s, 协议 %d)'
                      % (self.tag, username, self.mc_protocol))
        return handshake + login_start

    # ---------- 后端: 登录阶段 ----------
    def _handle_login_packet(self, packet: vanilla.Packet, out: bytearray) -> None:
        packet_id = packet.packet_id
        if packet_id == vanilla.LOGIN_SET_COMPRESSION:
            threshold = 256
            try:
                threshold, _ = vanilla.read_varint(packet.body, 0)
            except vanilla.ProtocolError:
                pass
            self.server_decoder.threshold = threshold
            self.server_encoder.threshold = threshold
            self.log.debug('%s 目标服务器启用压缩(阈值 %d), 由本代理解压/压缩, 不下发给客户端'
                           % (self.tag, threshold))
            return
        if packet_id == vanilla.LOGIN_DISCONNECT:
            reason = self._chat_text(packet.body)
            self.log.warn('%s 目标服务器拒绝登录: %s' % (self.tag, reason or '(无内容)'))
            self._send(eagler.pack_deny_login(reason or 'Kicked', self.handshake_protocol))
            self._fail('目标服务器拒绝登录: %s' % (reason or '(无内容)'), notify_client=False)
            return
        if packet_id == vanilla.LOGIN_ENCRYPTION_REQUEST:
            self._handle_encryption_request(packet)
            return
        if packet_id == vanilla.LOGIN_SUCCESS:
            self._handle_login_success(packet, out)
            return
        self.log.warn('%s 登录阶段收到意外包 %s' % (self.tag, packet_name(packet_id, 'login')))

    def _handle_encryption_request(self, packet: vanilla.Packet) -> None:
        """代客户端完成加密握手。

        服务器发加密请求不等于必须正版账号: 不少服务器(尤其"看起来像正版"的)只是
        想把链路加密, 并不会真的拿会话去 Mojang 校验, 离线名字照样放行。所以这一步
        自己代做: 用服务器给的公钥加密一个随机共享密钥回过去, 之后两个方向都套
        AES-128-CFB8。服务器若真要校验, 它会在之后发踢出原因, 那个原文照转给客户端。
        """
        if not crypto.available():
            message = ('目标服务器要求加密握手, 但本机没有可用的 AES 库, 代不了 —— '
                       '请安装 cryptography (pip install cryptography), 或换离线模式服务器')
            self.log.warn('%s %s' % (self.tag, message))
            self._send(eagler.pack_error(eagler.ERROR_CUSTOM_MESSAGE, note(message),
                                         self.handshake_protocol))
            self._fail(message, notify_client=False)
            return
        try:
            pos = 0
            server_id, pos = vanilla.read_string(packet.body, pos)
            length, pos = vanilla.read_varint(packet.body, pos)
            key_der = packet.body[pos:pos + length]
            pos += length
            length, pos = vanilla.read_varint(packet.body, pos)
            token = packet.body[pos:pos + length]
        except vanilla.ProtocolError as exc:
            self._fail('加密请求解析失败: %s' % exc)
            return
        if not key_der or not token:
            self._fail('加密请求内容为空')
            return
        try:
            secret = os.urandom(16)
            enc_secret = crypto.rsa_encrypt(key_der, secret)
            enc_token = crypto.rsa_encrypt(key_der, token)
        except Exception as exc:                     # 公钥格式不对/库报错
            message = '代做加密握手失败: %s' % exc
            self.log.warn('%s %s' % (self.tag, message))
            self._send(eagler.pack_error(eagler.ERROR_CUSTOM_MESSAGE, note(message),
                                         self.handshake_protocol))
            self._fail(message, notify_client=False)
            return
        body = (vanilla.write_varint(len(enc_secret)) + enc_secret
                + vanilla.write_varint(len(enc_token)) + enc_token)
        payload = vanilla.write_varint(vanilla.LOGIN_ENCRYPTION_RESPONSE) + body
        # 这一个是明文(加密从服务器收到它之后才开始), 所以直接发, 不走 _encode_for_backend
        self._send_backend(self.server_encoder.frame(payload))
        self.server_decrypt = crypto.AesCfb8(secret, secret)
        self.server_encrypt = crypto.AesCfb8(secret, secret)
        self.log.info('%s 已代做加密握手 (服务器 ID %r, 共享密钥 %s..., 用 %s), 之后全程 AES-128-CFB8'
                      % (self.tag, server_id, secret.hex()[:8], crypto.backend_name()))

    def _handle_login_success(self, packet: vanilla.Packet, out: bytearray) -> None:
        try:
            uuid_text, pos = vanilla.read_string(packet.body, 0)
            name, _ = vanilla.read_string(packet.body, pos)
        except vanilla.ProtocolError:
            self._fail('无法解析目标服务器的登录成功包')
            return
        uuid_bytes = uuid_from_string(uuid_text) or self.uuid
        if name and eagler.USERNAME_PATTERN.match(name):
            self.username = name
            if uuid_from_string(uuid_text) is None:
                uuid_bytes = eagler.offline_uuid(name)
        self.uuid = uuid_bytes
        self.login_done = True
        self.phase = 'allow_sent'
        self.log.info('%s 目标服务器登录成功: %s (UUID %s), 已通知客户端允许登录'
                      % (self.tag, self.username, uuid_text))
        self._send(eagler.pack_allow_login(self.username, self.uuid, self.handshake_protocol))
        self._maybe_finish_login()

    # ---------- 后端: 游戏阶段 ----------
    def _handle_play_packet(self, packet: vanilla.Packet, out: bytearray) -> None:
        if packet.packet_id == vanilla.PLAY_DISCONNECT:
            reason = self._chat_text(packet.body)
            if reason:
                self.log.warn('%s 目标服务器断开连接: %s' % (self.tag, reason))
            self.close_reason = reason or self.close_reason
        self._note_packet(packet.packet_id, 'play', to_client=True)
        if self.phase == 'play':
            out += self.client_encoder.frame(packet.payload)
        else:
            # 客户端还没完成握手, 先把游戏数据攒着
            self.pending_to_client += self.client_encoder.frame(packet.payload)

    def _client_play(self, data: bytes) -> bytes:
        try:
            packets = self.client_decoder.feed(data)
        except vanilla.ProtocolError as exc:
            self._fail('解析客户端数据失败: %s' % exc)
            return b''
        out = bytearray()
        for packet in packets:
            self.packets_to_server += 1
            self._note_packet(packet.packet_id, 'play', to_client=False)
            if self._is_eagler_extension(packet):
                continue
            out += self.server_encoder.frame(packet.payload)
        return bytes(out)

    def _is_eagler_extension(self, packet: vanilla.Packet) -> bool:
        """Eaglercraft 私有插件消息 —— 原版服务器不认识, 丢掉。"""
        if packet.packet_id != vanilla.CLIENT_PLUGIN_MESSAGE:
            return False
        try:
            channel, _ = vanilla.read_string(packet.body, 0)
        except vanilla.ProtocolError:
            return False
        if channel.startswith(vanilla.EAGLER_CHANNEL_PREFIXES):
            self.log.debug('%s 丢弃客户端扩展插件消息: 通道 %s' % (self.tag, channel))
            return True
        return False

    # ---------- 收尾 ----------
    def _maybe_finish_login(self) -> None:
        if self.phase != 'allow_sent' or not (self.client_finished and self.login_done):
            return
        self.phase = 'play'
        self._send(eagler.pack_finish_login())
        if self.pending_to_client:
            self.log.debug('%s 把握手期间缓存的 %d 字节游戏数据发给客户端'
                           % (self.tag, len(self.pending_to_client)))
            self._send(bytes(self.pending_to_client))
            self.pending_to_client.clear()
        self.log.info('%s 协议翻译完成, 进入游戏数据直通' % self.tag)

    def _chat_text(self, body: bytes) -> str:
        try:
            text, _ = vanilla.read_string(body, 0)
        except vanilla.ProtocolError:
            return ''
        try:
            return chat_to_text(json.loads(text)) or text
        except ValueError:
            return text

    def _note_packet(self, packet_id: int, state: str, to_client: bool) -> None:
        seen = self._seen_server_ids if to_client else self._seen_client_ids
        key = (packet_id, state)
        if key in seen or len(seen) > 60:
            return
        seen.add(key)
        self.log.debug('%s %s首见包 %s (id 0x%02x)'
                       % (self.tag, '下行' if to_client else '上行',
                          packet_name(packet_id, state), packet_id))

    def _send(self, data: bytes) -> None:
        if data:
            self._send_client(data)

    def _fail(self, reason: str, notify_client: bool = True) -> None:
        if self.phase == 'closed':
            return
        self.phase = 'closed'
        self.close_reason = reason
        if notify_client:
            try:
                self._send(eagler.pack_error(eagler.ERROR_CUSTOM_MESSAGE, note(reason),
                                             max(self.handshake_protocol, 3)))
            except Exception:      # 通知失败不影响收尾
                pass
        self._request_close(reason)
