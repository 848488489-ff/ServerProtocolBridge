"""Translations for the protocol translation layer.

Owner: ``translator.py`` / ``eagler.py`` / ``vanilla.py`` (keys prefixed
``translator.*``, ``eagler.*`` and ``vanilla.*``).

``translator.prefix`` is the tag prepended to every message the proxy injects
into the player's chat, so it must stay short.

EN and ZH must always carry the same key set with the same named placeholders.
"""

from __future__ import annotations

EN = {
    'translator.prefix': '[Protocol Adapter] ',

    # --- Messages shown to the player / reported as a close reason ---
    'translator.denied_login': 'Target server refused login: %(reason)s',
    'translator.empty_content': '(empty)',
    'translator.kick_fallback': 'Kicked',
    'translator.error.aes_missing': 'The target server requires an encrypted handshake, '
                                    'but this machine has no usable AES library, so the '
                                    'proxy cannot stand in for the client \u2014 install '
                                    'cryptography (pip install cryptography), or switch '
                                    'to an offline-mode server',
    'translator.error.backend_parse_failed': 'Failed to parse data from the target server: %(error)s',
    'translator.error.client_parse_failed': 'Failed to parse client data: %(error)s',
    'translator.error.duplicate_login_request': 'Duplicate login-request packet',
    'translator.error.encryption_handshake_failed': 'Failed to complete the encrypted handshake on behalf of the client: %(error)s',
    'translator.error.encryption_request_empty': 'The encryption request is empty',
    'translator.error.encryption_request_parse_failed': 'Failed to parse the encryption request: %(error)s',
    'translator.error.finish_login_malformed': 'Malformed finish-login packet',
    'translator.error.handshake_v1_too_old': 'The client offers the v1 handshake protocol, which is too old',
    'translator.error.login_request_parse_failed': 'Failed to parse the login request: %(error)s',
    'translator.error.login_success_parse_failed': "Could not parse the target server's login-success packet",
    'translator.error.unexpected_handshake_packet': 'Unexpected handshake packet 0x%(packet_id)02x',
    'translator.error.unrecognized_client_version': "The client's first packet is not a recognized EaglercraftX handshake",
    'translator.error.unsupported_mc_protocol': 'This proxy only supports Minecraft 1.8.8 (protocol 47); the client offered %(protocols)s',

    # --- Log lines (the connection tag is prepended at the call site) ---
    'translator.direction.downstream': 'downstream',
    'translator.direction.upstream': 'upstream',
    'translator.log.backend_disconnect': 'target server closed the connection: %(reason)s',
    'translator.log.backend_login_ok': 'target server login succeeded: %(username)s (UUID %(uuid)s); the client has been told it may log in',
    'translator.log.brand_spoofed': 'declared client brand %(brand)r to the target server (client identification spoof)',
    'translator.log.client_finished_login': 'client finished login',
    'translator.log.client_handshake': 'browser client handshake: %(detail)s',
    'translator.log.compression_enabled': 'target server enabled compression (threshold %(threshold)d); the proxy decompresses/recompresses and does not forward it to the client',
    'translator.log.drop_client_brand': "dropping the client's own MC|Brand (spoofed as %(brand)r)",
    'translator.log.drop_injected_frame': 'dropping client injected-message frame, %(size)d bytes',
    'translator.log.drop_plugin_message': 'dropping client extension plugin message: channel %(channel)s',
    'translator.log.empty_username_fallback': 'login request carries no name; using the name from the client handshake packet %(name)r',
    'translator.log.encryption_done': 'completed the encrypted handshake on behalf of the client (server ID %(server_id)r, shared secret %(secret)s..., using %(backend)s); all traffic is now AES-128-CFB8',
    'translator.log.first_packet': '%(direction)s first-seen packet %(name)s (id 0x%(packet_id)02x)',
    'translator.log.flush_pending': 'sending the %(count)d game packets buffered during the handshake (%(size)d bytes) to the client',
    'translator.log.ignore_profile_data': 'ignoring client profile data (skins etc.), %(size)d bytes',
    'translator.log.login_request': 'client login request: %(detail)s',
    'translator.log.protocols_selected': 'selected handshake protocol v%(handshake)d / MC protocol %(mc)d; waiting for the client login request',
    'translator.log.translation_done': 'protocol translation complete; passing game data through',
    'translator.log.unexpected_login_packet': 'unexpected packet %(packet)s during the login phase',
    'translator.log.username_sanitized': 'client username %(raw)r does not meet server requirements; using %(clean)r instead',
    'translator.log.vanilla_login_sent': 'sent vanilla login to the target server (username %(username)s, protocol %(protocol)d)',

    # --- eagler.py: handshake parsing / descriptions ---
    'eagler.describe.auth_disabled': 'disabled',
    'eagler.describe.auth_enabled': 'enabled',
    'eagler.describe.client_version': 'brand %(brand)s %(version)s | supported handshake protocols %(handshake)s | supported MC protocols %(mc)s | authentication %(auth)s',
    'eagler.describe.login_request': 'username %(username)s | server address the client entered %(server)r | password %(password)s | client capability bits 0x%(caps)x',
    'eagler.describe.password_set': 'set',
    'eagler.describe.password_unset': 'not set',
    'eagler.error.auth_username_out_of_range': 'authUsername out of range',
    'eagler.error.bad_extension_count': 'bad extension capability count: %(count)d',
    'eagler.error.bad_handshake_count': 'bad handshake protocol count: %(count)d',
    'eagler.error.bad_mc_count': 'bad Minecraft protocol count: %(count)d',
    'eagler.error.cookie_length_not_zero': 'cookie length is not 0',
    'eagler.error.cookie_out_of_range': 'cookie out of range',
    'eagler.error.extension_uuid_out_of_range': 'extension capability UUID out of range',
    'eagler.error.login_trailing_bytes': '%(count)d trailing bytes after the login request',
    'eagler.error.missing_auth_username': 'missing authUsername field',
    'eagler.error.missing_client_auth': 'missing clientAuth field',
    'eagler.error.missing_cookie_flag': 'missing cookie flag',
    'eagler.error.missing_cookie_length': 'missing cookie length',
    'eagler.error.missing_extension_count': 'missing extension capability count',
    'eagler.error.missing_password_field': 'missing password field',
    'eagler.error.not_login_request': 'not a login-request packet',
    'eagler.error.password_out_of_range': 'password field out of range',
    'eagler.error.string_length_out_of_range': 'string length out of range',
    'eagler.error.string_out_of_range': 'string body out of range',
    'eagler.error.trailing_bytes': '%(count)d trailing bytes after the first packet',
    'eagler.error.u16_out_of_range': 'u16 out of range',
    'eagler.error.uuid_not_16_bytes': 'UUID must be 16 bytes',
    'eagler.error.v1_packet_incomplete': 'incomplete v1 packet',
    'eagler.error.varint_out_of_range': 'VarInt out of range',
    'eagler.error.varint_too_long': 'VarInt longer than 5 bytes',

    # --- vanilla.py: framing / compression ---
    'vanilla.error.bad_packet_length': 'bad packet length: %(length)d',
    'vanilla.error.decompressed_length_mismatch': 'decompressed length %(actual)d does not match the declared %(declared)d',
    'vanilla.error.missing_packet_id': 'packet body contains no packet id',
    'vanilla.error.missing_uncompressed_length': 'compressed packet is missing the uncompressed length field',
    'vanilla.error.varint_too_long': 'VarInt longer than 5 bytes',
    'vanilla.error.zlib_failed': 'zlib decompression failed: %(error)s',
}

ZH = {
    'translator.prefix': '[协议转换器] ',

    # --- 发给玩家 / 作为关闭原因上报的文案 ---
    'translator.denied_login': '目标服务器拒绝登录: %(reason)s',
    'translator.empty_content': '(无内容)',
    'translator.kick_fallback': '被踢出',
    'translator.error.aes_missing': '目标服务器要求加密握手, 但本机没有可用的 AES 库, 代不了 —— '
                                    '请安装 cryptography (pip install cryptography), 或换离线模式服务器',
    'translator.error.backend_parse_failed': '解析目标服务器数据失败: %(error)s',
    'translator.error.client_parse_failed': '解析客户端数据失败: %(error)s',
    'translator.error.duplicate_login_request': '重复的登录请求包',
    'translator.error.encryption_handshake_failed': '代做加密握手失败: %(error)s',
    'translator.error.encryption_request_empty': '加密请求内容为空',
    'translator.error.encryption_request_parse_failed': '加密请求解析失败: %(error)s',
    'translator.error.finish_login_malformed': '完成登录包格式不对',
    'translator.error.handshake_v1_too_old': '客户端提供的是 v1 握手协议, 太旧了',
    'translator.error.login_request_parse_failed': '登录请求解析失败: %(error)s',
    'translator.error.login_success_parse_failed': '无法解析目标服务器的登录成功包',
    'translator.error.unexpected_handshake_packet': '意料之外的握手包 0x%(packet_id)02x',
    'translator.error.unrecognized_client_version': '客户端首个数据包不是认识的 EaglercraftX 握手',
    'translator.error.unsupported_mc_protocol': '本代理只支持 Minecraft 1.8.8 (协议 47), 客户端提供的是 %(protocols)s',

    # --- 日志文案(调用处会在前面拼上连接标识) ---
    'translator.direction.downstream': '下行',
    'translator.direction.upstream': '上行',
    'translator.log.backend_disconnect': '目标服务器断开连接: %(reason)s',
    'translator.log.backend_login_ok': '目标服务器登录成功: %(username)s (UUID %(uuid)s), 已通知客户端允许登录',
    'translator.log.brand_spoofed': '已向目标服务器声明客户端品牌 %(brand)r (客户端标识伪装)',
    'translator.log.client_finished_login': '客户端完成登录',
    'translator.log.client_handshake': '浏览器端客户端握手: %(detail)s',
    'translator.log.compression_enabled': '目标服务器启用压缩(阈值 %(threshold)d), 由本代理解压/压缩, 不下发给客户端',
    'translator.log.drop_client_brand': '丢弃客户端自带的 MC|Brand (已伪装成 %(brand)r)',
    'translator.log.drop_injected_frame': '丢弃客户端注入消息帧 %(size)d 字节',
    'translator.log.drop_plugin_message': '丢弃客户端扩展插件消息: 通道 %(channel)s',
    'translator.log.empty_username_fallback': '登录请求里没带名字, 改用客户端握手包里的名字 %(name)r',
    'translator.log.encryption_done': '已代做加密握手 (服务器 ID %(server_id)r, 共享密钥 %(secret)s..., 用 %(backend)s), 之后全程 AES-128-CFB8',
    'translator.log.first_packet': '%(direction)s首见包 %(name)s (id 0x%(packet_id)02x)',
    'translator.log.flush_pending': '把握手期间缓存的 %(count)d 个游戏包(共 %(size)d 字节)发给客户端',
    'translator.log.ignore_profile_data': '忽略客户端资料数据(皮肤等) %(size)d 字节',
    'translator.log.login_request': '客户端请求登录: %(detail)s',
    'translator.log.protocols_selected': '已选择握手协议 v%(handshake)d / 游戏协议 %(mc)d, 等待客户端登录请求',
    'translator.log.translation_done': '协议翻译完成, 进入游戏数据直通',
    'translator.log.unexpected_login_packet': '登录阶段收到意外包 %(packet)s',
    'translator.log.username_sanitized': '客户端用户名 %(raw)r 不符合服务器要求, 已改用 %(clean)r',
    'translator.log.vanilla_login_sent': '已向目标服务器发送原版登录 (用户名 %(username)s, 协议 %(protocol)d)',

    # --- eagler.py: 握手解析 / 描述文本 ---
    'eagler.describe.auth_disabled': '否',
    'eagler.describe.auth_enabled': '是',
    'eagler.describe.client_version': '品牌 %(brand)s %(version)s | 支持握手协议 %(handshake)s | 支持游戏协议 %(mc)s | 开启验证 %(auth)s',
    'eagler.describe.login_request': '用户名 %(username)s | 客户端填写的服务器地址 %(server)r | 密码 %(password)s | 客户端能力位 0x%(caps)x',
    'eagler.describe.password_set': '有',
    'eagler.describe.password_unset': '无',
    'eagler.error.auth_username_out_of_range': 'authUsername 越界',
    'eagler.error.bad_extension_count': '扩展能力数量异常: %(count)d',
    'eagler.error.bad_handshake_count': '握手协议数量异常: %(count)d',
    'eagler.error.bad_mc_count': '游戏协议数量异常: %(count)d',
    'eagler.error.cookie_length_not_zero': 'cookie 长度不为 0',
    'eagler.error.cookie_out_of_range': 'cookie 越界',
    'eagler.error.extension_uuid_out_of_range': '扩展能力 UUID 越界',
    'eagler.error.login_trailing_bytes': '登录请求末尾有 %(count)d 个多余字节',
    'eagler.error.missing_auth_username': '缺少 authUsername 字段',
    'eagler.error.missing_client_auth': '缺少 clientAuth 字段',
    'eagler.error.missing_cookie_flag': '缺少 cookie 开关',
    'eagler.error.missing_cookie_length': '缺少 cookie 长度',
    'eagler.error.missing_extension_count': '缺少扩展能力数量',
    'eagler.error.missing_password_field': '缺少密码字段',
    'eagler.error.not_login_request': '不是登录请求包',
    'eagler.error.password_out_of_range': '密码字段越界',
    'eagler.error.string_length_out_of_range': '字符串长度越界',
    'eagler.error.string_out_of_range': '字符串越界',
    'eagler.error.trailing_bytes': '首个包末尾有 %(count)d 个多余字节',
    'eagler.error.u16_out_of_range': 'u16 越界',
    'eagler.error.uuid_not_16_bytes': 'UUID 必须是 16 字节',
    'eagler.error.v1_packet_incomplete': 'v1 包不完整',
    'eagler.error.varint_out_of_range': 'VarInt 越界',
    'eagler.error.varint_too_long': 'VarInt 超过 5 字节',

    # --- vanilla.py: 封帧 / 压缩 ---
    'vanilla.error.bad_packet_length': '包长度异常: %(length)d',
    'vanilla.error.decompressed_length_mismatch': '解压后长度 %(actual)d 与声明 %(declared)d 不符',
    'vanilla.error.missing_packet_id': '包内容里没有包 id',
    'vanilla.error.missing_uncompressed_length': '压缩包缺少未压缩长度字段',
    'vanilla.error.varint_too_long': 'VarInt 超过 5 字节',
    'vanilla.error.zlib_failed': 'zlib 解压失败: %(error)s',
}
