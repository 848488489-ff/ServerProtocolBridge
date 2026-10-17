"""Translations for the bridge / server (``proxy.py``).

Owner: ``proxy.py`` (keys prefixed ``proxy.*``): log messages, close reasons,
connection diagnostics, the status page and the server list ("Accept: MOTD")
response.
"""

from __future__ import annotations

EN = {
    # -- configuration / listener errors (raised towards the GUI) --
    'proxy.error.bad_config': 'Invalid configuration: %(problems)s',
    'proxy.error.listen_failed': 'cannot listen on %(host)s:%(port)d (%(error)s)',

    # -- connection failure reasons (logged and sent to the player) --
    'proxy.error.timeout': 'Connection timed out; the server may be offline',
    'proxy.error.dns': 'Domain name lookup failed; the address may be misspelled',
    'proxy.error.refused': 'The other side refused the connection; the port is '
                           'closed or the service is not running',
    'proxy.error.unreachable': 'Network unreachable',
    'proxy.error.resolve_failed': 'Failed to resolve the target server address: %(error)s',
    'proxy.error.connect_failed': 'Cannot connect to the target server '
                                  '%(host)s:%(port)d (%(reason)s)',
    'proxy.error.connect_note': 'Cannot reach the target server. Check that the '
                                'address is correct, or try again later\n'
                                'Target: %(host)s:%(port)d\nReason: %(reason)s',
    'proxy.error.login_stage_closed': 'The target server closed the connection during '
                                      'login; it may not support this version, or it may '
                                      'restrict where connections come from',

    # -- close reasons (shown in the log / GUI) --
    'proxy.reason.service_stopped': 'local service stopped',
    'proxy.reason.client_closed': 'client closed the connection',
    'proxy.reason.client_closed_code': 'client closed the connection (code=%(code)s)',
    'proxy.reason.query_idle_timeout': 'server list query connection idle timeout',
    'proxy.reason.text_frame_in_translate': 'text frame received in protocol translation mode',
    'proxy.reason.target_closed': 'target server closed the connection',
    'proxy.reason.send_to_target_failed': 'sending to the target server failed: %(error)s',
    'proxy.reason.normal_close': 'closed normally',

    # -- route labels (used in log lines) --
    'proxy.route.path': 'path %(path)s',
    'proxy.route.default': 'default target',
    'proxy.route.default_missing': 'default target (no route for %(path)s)',

    # -- connection diagnostics --
    'proxy.diag.no_reply': 'The target server closed the connection without sending '
                           'back a single byte after the login request. Common causes:',
    'proxy.diag.address_mismatch': '  · the address "%(shown)s" in the handshake does '
                                   'not match the server\'s real hostname "%(actual)s"; '
                                   'some servers validate or split traffic by address '
                                   '-- try enabling the handshake address rewrite',
    'proxy.diag.protocol_unsupported': '  · client protocol version %(version)d is not '
                                       'supported by that server (servers sometimes just '
                                       'disconnect without sending a message)',
    'proxy.diag.policy': '  · the server requires a premium account / whitelist / a '
                         'specific port, or it blocks connections based on where they '
                         'come from',

    # -- frame kinds --
    'proxy.frame.text': 'text frame',
    'proxy.frame.binary': 'binary frame',

    # -- log messages --
    'proxy.log.connection_error': '#%(id)d connection handler failed: %(error)s',
    'proxy.log.accepted': '#%(id)d %(scheme)s accepted %(host)s:%(port)s -> '
                          '%(source)s [%(label)s]',
    'proxy.log.connected': '#%(id)d connected to the target server %(host)s:%(port)d',
    'proxy.log.failure_sent': '#%(id)d sent the connection failure reason to the client',
    'proxy.log.failure_send_error': '#%(id)d error while sending the failure reason: '
                                    '%(error)s',
    'proxy.log.query_received': '#%(id)d %(scheme)s server list query: %(payload)r',
    'proxy.log.query_binary_ignored': '#%(id)d server list query received a binary frame '
                                      'of %(size)d bytes, ignoring it',
    'proxy.log.query_wants': '#%(id)d server list query request types: %(wants)s',
    'proxy.log.empty': '(none)',
    'proxy.log.query_resolve_failed': '#%(id)d failed to resolve the target address for '
                                      'the server list query: %(error)s',
    'proxy.log.query_send_failed': '#%(id)d failed to send the server list query result: '
                                   '%(error)s',
    'proxy.log.frame_in': '#%(id)d inbound frame #%(index)d: %(kind)s, %(size)d bytes, '
                          'content: %(preview)s',
    'proxy.log.text_frame_closing': '#%(id)d text frame received in protocol translation '
                                    'mode, closing the connection',
    'proxy.log.base64_switch': '#%(id)d text frame received, switching to base64 '
                               'transport mode automatically',
    'proxy.log.bad_base64': '#%(id)d text frame is not valid base64, dropped %(size)d '
                            'bytes (starts with: %(preview)r)',
    'proxy.log.base64_decoded': '#%(id)d text frame of %(size)d bytes -> %(decoded)d '
                                'bytes after base64 decoding',
    'proxy.log.translator_enabled': '#%(id)d browser client detected (EaglercraftX '
                                    'handshake), enabling the protocol translation layer',
    'proxy.log.handshake_incomplete': '#%(id)d handshake packet is still %(missing)d '
                                      'bytes short, buffering until it is complete',
    'proxy.log.not_handshake': '#%(id)d first inbound packet is not a handshake, '
                               'forwarding as-is; first 64 bytes: %(preview)s',
    'proxy.log.handshake': '#%(id)d handshake packet: %(info)s',
    'proxy.log.rewrite_failed': '#%(id)d handshake address rewrite failed, forwarding '
                                'as-is',
    'proxy.log.address_rewritten': '#%(id)d handshake address rewritten to '
                                   '%(host)s:%(port)d',
    'proxy.log.send_client_failed': '#%(id)d failed to send to the client: %(error)s',
    'proxy.log.session_end': '#%(id)d connection ended after %(seconds).1f seconds: '
                             '%(reason)s | up %(up)s, down %(down)s',
    'proxy.log.listeners_ready': 'listeners ready: %(listeners)s',
    'proxy.log.stopped': 'service stopped',
    'proxy.log.bad_route': 'route %(path)s has an invalid target (%(error)s), using the '
                           'default target',
    'proxy.log.status_resolve_failed': 'failed to resolve the target address for the '
                                       'status page: %(error)s',

    # -- status page --
    'proxy.page.title': '%(app)s · Status',
    'proxy.page.subtitle': 'Version %(version)s · %(state)s',
    'proxy.page.details': 'Full information (JSON)',
    'proxy.page.address': 'Current server address',
    'proxy.page.resolved': 'resolved to %(address)s',
    'proxy.page.target_status': 'Target server status',
    'proxy.page.online': 'online · %(ping)s ms',
    'proxy.page.players': 'players %(online)s/%(max)s',
    'proxy.page.unreachable': 'temporarily unreachable',
    'proxy.page.wss_url': 'Address to enter in the browser client',
    'proxy.page.alt_addresses': 'Alternative addresses',
    'proxy.page.app': 'Program',
    'proxy.page.state': 'Status',
    'proxy.page.running': 'Running',
    'proxy.page.stopped': 'Stopped',
    'proxy.page.uptime': 'Uptime',
    'proxy.page.uptime_value': '%(seconds).1f seconds',
    'proxy.page.connections': 'Connections',
    'proxy.page.connections_value': 'active %(active)s / total %(total)s',
    'proxy.page.traffic': 'Traffic',
    'proxy.page.traffic_value': 'up %(up)s · down %(down)s',
    'proxy.page.server_brand': 'Server brand (shown to clients)',
    'proxy.page.spoof_brand': 'Client brand spoof (shown to the target server)',
    'proxy.page.spoof_off': 'off, no MC|Brand is sent',
    'proxy.page.routes': 'Path routes',
    'proxy.page.cert_thumbprint': 'Certificate thumbprint',

    # -- server list ("Accept: MOTD") response --
    'proxy.query.target': 'Current server address: %(address)s',
}

ZH = {
    # -- configuration / listener errors --
    'proxy.error.bad_config': '配置有误: %(problems)s',
    'proxy.error.listen_failed': '无法监听 %(host)s:%(port)d (%(error)s)',

    # -- connection failure reasons --
    'proxy.error.timeout': '连接超时, 服务器可能不在线',
    'proxy.error.dns': '域名解析失败, 地址可能写错了',
    'proxy.error.refused': '对方拒绝连接, 端口没开或服务没启动',
    'proxy.error.unreachable': '网络不可达',
    'proxy.error.resolve_failed': '解析目标服务器地址失败: %(error)s',
    'proxy.error.connect_failed': '无法连接目标服务器 %(host)s:%(port)d (%(reason)s)',
    'proxy.error.connect_note': '目标服务器连不上, 请检查地址填得对不对, 或者稍后再试\n'
                                '目标: %(host)s:%(port)d\n原因: %(reason)s',
    'proxy.error.login_stage_closed': '目标服务器在登录阶段就把连接关掉了, 可能它不支持这个'
                                      '版本, 或者对访问来源做了限制',

    # -- close reasons --
    'proxy.reason.service_stopped': '本地服务已停止',
    'proxy.reason.client_closed': '客户端关闭了连接',
    'proxy.reason.client_closed_code': '客户端关闭了连接 (code=%(code)s)',
    'proxy.reason.query_idle_timeout': '列表查询连接空闲超时',
    'proxy.reason.text_frame_in_translate': '协议翻译模式下收到文本帧',
    'proxy.reason.target_closed': '目标服务器关闭了连接',
    'proxy.reason.send_to_target_failed': '发送到目标服务器失败: %(error)s',
    'proxy.reason.normal_close': '正常关闭',

    # -- route labels --
    'proxy.route.path': '路径 %(path)s',
    'proxy.route.default': '默认目标',
    'proxy.route.default_missing': '默认目标(路径 %(path)s 无映射)',

    # -- connection diagnostics --
    'proxy.diag.no_reply': '目标服务器收到登录请求后一个字节都没回就把连接关了, 常见原因:',
    'proxy.diag.address_mismatch': '  · 握手里的地址 "%(shown)s" 和服务器的真实域名 '
                                   '"%(actual)s" 不一致, 部分服务器会按地址校验/分流 '
                                   '—— 可以试试打开"握手地址改写"',
    'proxy.diag.protocol_unsupported': '  · 客户端协议版本 %(version)d 不被该服务器支持'
                                       '(服务端有时直接断开而不发提示)',
    'proxy.diag.policy': '  · 该服务器要求正版/白名单/特定端口, 或按访问来源做了拦截',

    # -- frame kinds --
    'proxy.frame.text': '文本帧',
    'proxy.frame.binary': '二进制帧',

    # -- log messages --
    'proxy.log.connection_error': '#%(id)d 连接处理异常: %(error)s',
    'proxy.log.accepted': '#%(id)d %(scheme)s 接入 %(host)s:%(port)s -> '
                          '%(source)s [%(label)s]',
    'proxy.log.connected': '#%(id)d 已连接目标服务器 %(host)s:%(port)d',
    'proxy.log.failure_sent': '#%(id)d 已把连接失败的原因发给客户端',
    'proxy.log.failure_send_error': '#%(id)d 发送失败原因时出错: %(error)s',
    'proxy.log.query_received': '#%(id)d %(scheme)s 服务器列表查询: %(payload)r',
    'proxy.log.query_binary_ignored': '#%(id)d 列表查询收到二进制帧 %(size)d 字节, 忽略',
    'proxy.log.query_wants': '#%(id)d 列表查询请求类型: %(wants)s',
    'proxy.log.empty': '(空)',
    'proxy.log.query_resolve_failed': '#%(id)d 列表查询时解析目标地址失败: %(error)s',
    'proxy.log.query_send_failed': '#%(id)d 发送列表查询结果失败: %(error)s',
    'proxy.log.frame_in': '#%(id)d 上行帧 #%(index)d %(kind)s 长度 %(size)d, '
                          '内容: %(preview)s',
    'proxy.log.text_frame_closing': '#%(id)d 协议翻译模式下收到文本帧, 断开连接',
    'proxy.log.base64_switch': '#%(id)d 收到文本帧, 自动切换为 base64 传输模式',
    'proxy.log.bad_base64': '#%(id)d 文本帧不是有效的 base64, 已丢弃 %(size)d 字节 '
                            '(开头: %(preview)r)',
    'proxy.log.base64_decoded': '#%(id)d 文本帧 %(size)d 字节 -> base64 解码出 '
                                '%(decoded)d 字节',
    'proxy.log.translator_enabled': '#%(id)d 检测到浏览器端客户端 (EaglercraftX 握手), '
                                    '启用协议翻译层',
    'proxy.log.handshake_incomplete': '#%(id)d 握手包还差 %(missing)d 字节, 先缓存等收齐',
    'proxy.log.not_handshake': '#%(id)d 上行首包不是握手包, 原样转发; 前 64 字节: '
                               '%(preview)s',
    'proxy.log.handshake': '#%(id)d 握手包: %(info)s',
    'proxy.log.rewrite_failed': '#%(id)d 握手地址改写失败, 已按原样转发',
    'proxy.log.address_rewritten': '#%(id)d 已把握手地址改写为 %(host)s:%(port)d',
    'proxy.log.send_client_failed': '#%(id)d 发送到客户端失败: %(error)s',
    'proxy.log.session_end': '#%(id)d 连接结束, 持续 %(seconds).1f 秒: %(reason)s | '
                             '上行 %(up)s, 下行 %(down)s',
    'proxy.log.listeners_ready': '监听就绪: %(listeners)s',
    'proxy.log.stopped': '服务已停止',
    'proxy.log.bad_route': '路径映射 %(path)s 的目标无效(%(error)s), 使用默认目标',
    'proxy.log.status_resolve_failed': '状态页解析目标地址失败: %(error)s',

    # -- status page --
    'proxy.page.title': '%(app)s · 运行状态',
    'proxy.page.subtitle': '版本 %(version)s · %(state)s',
    'proxy.page.details': '完整信息 (JSON)',
    'proxy.page.address': '当前服务器地址',
    'proxy.page.resolved': '解析到 %(address)s',
    'proxy.page.target_status': '目标服务器状态',
    'proxy.page.online': '在线 · %(ping)s ms',
    'proxy.page.players': '玩家 %(online)s/%(max)s',
    'proxy.page.unreachable': '暂时连不上',
    'proxy.page.wss_url': '浏览器客户端填这个地址',
    'proxy.page.alt_addresses': '备用地址',
    'proxy.page.app': '程序',
    'proxy.page.state': '运行状态',
    'proxy.page.running': '运行中',
    'proxy.page.stopped': '已停止',
    'proxy.page.uptime': '运行时长',
    'proxy.page.uptime_value': '%(seconds).1f 秒',
    'proxy.page.connections': '连接数',
    'proxy.page.connections_value': '当前 %(active)s 条 / 累计 %(total)s 条',
    'proxy.page.traffic': '流量',
    'proxy.page.traffic_value': '上行 %(up)s · 下行 %(down)s',
    'proxy.page.server_brand': '服务器品牌(给客户端看)',
    'proxy.page.spoof_brand': '客户端标识伪装(给目标服看)',
    'proxy.page.spoof_off': '已关闭, 不发送 MC|Brand',
    'proxy.page.routes': '路径映射',
    'proxy.page.cert_thumbprint': '证书指纹',

    # -- server list ("Accept: MOTD") response --
    'proxy.query.target': '当前服务器地址: %(address)s',
}
