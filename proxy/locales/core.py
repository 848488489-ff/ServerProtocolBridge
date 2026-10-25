"""Locale table for the core namespace.

Split into themed fragments (core_cli); this module merges them so the rest of the program still does ``from proxy.locales import core``.
"""

from . import core_cli


EN = {
    'core.app_name': 'Server Protocol Bridge',
    'core.tagline': 'Turns a plain Minecraft server into a local wss:// or ws:// '
                    'endpoint for WebSocket clients.',
    'core.config.address_empty': 'Address must not be empty',
    'core.config.route_format': 'A route must look like "path=target", '
                                'for example: /lobby=play.example.net',
    'core.config.route_missing_target': 'Route "%(path)s" has no target address',
    'core.config.route_missing_path': 'Route has no path; both sides of '
                                      '"path=target" must be filled in',
    'core.config.default_created': 'Created the default configuration file: %(path)s',
    'core.config.listen_host_empty': 'Listen address must not be empty',
    'core.config.port_wss': 'wss port',
    'core.config.port_ws': 'ws port',
    'core.config.port_range': '%(name)s must be between 0 and 65535',
    'core.config.tls_needs_wss_port': 'TLS is enabled, so the wss port must be set '
                                      '(or disable TLS and use ws only)',
    'core.config.tls_needs_ws_port': 'TLS is disabled, so the ws port must be set',
    'core.config.ports_conflict': 'The wss port and the ws port must not be the same',
    'core.config.target_empty': 'Forward target must not be empty',
    'core.config.target_invalid': 'Invalid forward target: %(error)s',
    'core.config.target_srv': '%(host)s (resolved via SRV, port defaults to 25565)',
    'core.config.route_target_invalid': 'Route %(path)s has an invalid target: %(target)s',
    'core.config.brand_server': 'server brand',
    'core.config.brand_server_version': 'server version',
    'core.config.brand_spoof': 'spoofed client brand',
    'core.config.spoof_client_invalid': 'spoof_client must be one of: %(choices)s',
    'core.config.name_required': '%(name)s must not be empty',
    'core.config.brand_ascii': '%(name)s may only contain ASCII characters '
                               '(the client reads it byte by byte)',
    'core.config.brand_too_long': '%(name)s must be at most %(limit)d characters',
    'core.config.max_payload_positive': 'Max payload must be greater than 0',
    'core.config.connect_timeout_positive': 'Connect timeout must be greater than 0',
    'core.config.heartbeat_non_negative': 'Heartbeat interval must not be negative',
    'core.config.status_cache_ttl_range': 'Server-list cache lifetime must be between 1 and 86400 seconds',
    'core.config.log_level_invalid': 'Log level must be one of debug / info / warn / error',
    'core.config.log_max_lines_invalid': 'The log buffer size must be between 50 and 100000 lines',
    'core.config.language_invalid': 'Language must be "en" or "zh"',
    'core.config.web_host_empty': 'Web UI bind address must not be empty',
    'core.config.web_port_range': 'Web UI port must be between 0 and 65535 (0 = pick a free port)',
    'core.log.debug': 'DEBUG',
    'core.log.info': 'INFO',
    'core.log.warn': 'WARN',
    'core.log.error': 'ERROR',
    'core.main.gui_fallback': 'Could not load the GUI (%(error)s); falling back to '
                              'command line mode.',
    'core.main.gui_fallback_hint': 'Hint: on Windows install a Python build that includes '
                                   'tkinter; on Linux install python3-tk.\n',
    'accounts.kind.offline': 'Offline account',
    'accounts.kind.thirdparty': 'Third-party account',
    'accounts.kind.microsoft': 'Microsoft account',
    'accounts.error.network': 'Network error: %(error)s',
    'accounts.error.http': 'The service answered %(code)s: %(detail)s',
    'accounts.error.unknown': 'unknown error',
    'accounts.error.bad_response': 'The service sent an unexpected answer',
    'accounts.error.need_login': 'The sign-in has expired; sign in again',
    'accounts.error.no_uuid': 'This account has no profile ID yet; sign in again',
    'accounts.thirdparty.bad_url': 'The account service address must start with '
                                   'http:// or https://; use the API root given by '
                                   'your provider',
    'accounts.thirdparty.no_profile': 'That service has no Minecraft profile for this account',
    'accounts.ms.refreshed': 'Renewed the Minecraft token of %(name)s',
    'accounts.ms.refresh_failed': 'Could not refresh the Microsoft sign-in: '
                                  '%(error)s. Open Settings > Accounts and sign '
                                  'in again.',
    'accounts.ms.no_character': 'This Microsoft account has no Minecraft profile yet: '
                               'set a player name on the official site first',
    'accounts.ms.library_missing': 'The Microsoft sign-in component (mcauth3) is not '
                                   'installed; run: pip install mcauth3',
    'accounts.ms.ssl_failed': 'The TLS certificate could not be verified: %(detail)s',
    'accounts.ms.code_used': 'Microsoft says this sign-in code has already been '
                             'used. Requesting a new code.',
}

ZH = {
    'core.app_name': '服务器协议转换',
    'core.tagline': '把普通 Minecraft 服务器转换为本地 wss:// 或 ws:// 端点, '
                    '供 WebSocket 客户端连接。',
    'core.config.address_empty': '地址不能为空',
    'core.config.route_format': '路径映射格式应为 "路径=目标", 例如: /lobby=play.example.net',
    'core.config.route_missing_target': '路径映射 "%(path)s" 缺少目标地址',
    'core.config.route_missing_path': '路径映射缺少路径；"路径=目标" 两边都必须填写',
    'core.config.default_created': '已生成默认配置文件: %(path)s',
    'core.config.listen_host_empty': '监听地址不能为空',
    'core.config.port_wss': 'wss 端口',
    'core.config.port_ws': 'ws 端口',
    'core.config.port_range': '%(name)s 必须在 0~65535 之间',
    'core.config.tls_needs_wss_port': '启用了 TLS 就必须设置 wss 端口(或关闭 TLS 只用 ws)',
    'core.config.tls_needs_ws_port': 'TLS 已关闭, 必须设置 ws 端口',
    'core.config.ports_conflict': 'wss 端口与 ws 端口不能相同',
    'core.config.target_empty': '转发目标不能为空',
    'core.config.target_invalid': '转发目标无效: %(error)s',
    'core.config.target_srv': '%(host)s (按 SRV 解析, 缺省 25565)',
    'core.config.route_target_invalid': '路径映射 %(path)s 的目标无效: %(target)s',
    'core.config.brand_server': '服务器品牌',
    'core.config.brand_server_version': '服务器版本',
    'core.config.brand_spoof': '客户端品牌伪装',
    'core.config.spoof_client_invalid': 'spoof_client 只能是以下之一: %(choices)s',
    'core.config.name_required': '%(name)s不能为空',
    'core.config.brand_ascii': '%(name)s只能用 ASCII 字符(客户端按单字节读取)',
    'core.config.brand_too_long': '%(name)s最长 %(limit)d 个字符',
    'core.config.max_payload_positive': '单帧上限必须大于 0',
    'core.config.connect_timeout_positive': '连接超时必须大于 0',
    'core.config.heartbeat_non_negative': '心跳间隔不能为负数',
    'core.config.status_cache_ttl_range': '服务器列表缓存时间必须在 1 到 86400 秒之间',
    'core.config.log_level_invalid': '日志级别只能是 debug / info / warn / error',
    'core.config.log_max_lines_invalid': '日志缓冲区大小必须在 50 到 100000 行之间',
    'core.config.language_invalid': '语言只能是 "en" 或 "zh"',
    'core.config.web_host_empty': 'Web UI 绑定地址不能为空',
    'core.config.web_port_range': 'Web UI 端口必须在 0 到 65535 之间（0 = 自动选择空闲端口）',
    'core.log.debug': '调试',
    'core.log.info': '信息',
    'core.log.warn': '警告',
    'core.log.error': '错误',
    'core.main.gui_fallback': '无法加载图形界面(%(error)s), 已切换到命令行模式。',
    'core.main.gui_fallback_hint': '提示: Windows 请安装带 tkinter 的 Python; Linux 需安装 python3-tk。\n',
    'accounts.kind.offline': '离线账号',
    'accounts.kind.thirdparty': '第三方账号',
    'accounts.kind.microsoft': '微软账号',
    'accounts.error.network': '网络错误: %(error)s',
    'accounts.error.http': '服务端返回 %(code)s: %(detail)s',
    'accounts.error.unknown': '未知错误',
    'accounts.error.bad_response': '服务端返回了无法识别的数据',
    'accounts.error.need_login': '登录已过期, 请重新登录',
    'accounts.error.no_uuid': '该账号还没有角色 ID, 请重新登录',
    'accounts.thirdparty.bad_url': '账号服务地址必须以 http:// 或 https:// 开头, '
                                   '请填写服务商提供的 API 根地址',
    'accounts.thirdparty.no_profile': '该服务上没有此账号的 Minecraft 角色',
    'accounts.ms.refreshed': '已刷新 %(name)s 的 Minecraft 令牌',
    'accounts.ms.refresh_failed': '刷新微软登录凭据失败: %(error)s。'
                                  '请打开“设置 → 账号”重新登录。',
    'accounts.ms.no_character': '该微软账号还没有 Minecraft 角色档案(先在官网设置角色名)',
    'accounts.ms.library_missing': '缺少微软登录组件 (mcauth3), 请执行: pip install mcauth3',
    'accounts.ms.ssl_failed': '无法验证 TLS 证书: %(detail)s',
    'accounts.ms.code_used': '微软提示这个登录代码已经被使用过了, 正在重新获取新的代码。',
}

for _sub in (core_cli,):
    EN.update(_sub.EN)
    ZH.update(_sub.ZH)
