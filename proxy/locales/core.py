"""Translations for the small core modules.

Owner: ``config.py`` / ``cli.py`` / ``main.py`` / ``logger.py`` / ``utils.py`` /
``version.py`` (keys prefixed ``core.*``).
"""

from __future__ import annotations

EN = {
    # ---------- identity (version.py) ----------
    'core.app_name': 'Server Protocol Bridge',
    'core.tagline': 'Turns a plain Minecraft server into a local wss:// or ws:// '
                    'endpoint for WebSocket clients.',

    # ---------- config.py ----------
    'core.config.address_empty': 'Address must not be empty',
    'core.config.route_format': 'A route must look like "path=target", '
                                'for example: /lobby=play.example.net',
    'core.config.route_missing_target': 'Route "%(path)s" has no target address',
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
    'core.config.language_invalid': 'Language must be "en" or "zh"',
    'core.config.web_host_empty': 'Web UI bind address must not be empty',
    'core.config.web_port_range': 'Web UI port must be between 0 and 65535 (0 = pick a free port)',

    # ---------- logger.py ----------
    'core.log.debug': 'DEBUG',
    'core.log.info': 'INFO',
    'core.log.warn': 'WARN',
    'core.log.error': 'ERROR',

    # ---------- cli.py ----------
    'core.cli.description': '%(app)s v%(version)s - turns an ordinary Minecraft '
                            'server into a local wss:// or ws:// endpoint',
    'core.cli.version_line': '%(app)s v%(version)s',
    'core.cli.config_help': 'Path to the config file (default: config.json next to the program)',
    'core.cli.no_gui_help': 'Run in command line mode (this mode already is the CLI; '
                            'the flag exists for compatibility with main.py)',
    'core.cli.target_help': 'Forward target, e.g. play.example.net (resolved '
                            'via SRV) or 127.0.0.1:25565',
    'core.cli.listen_help': 'Listen address (default 127.0.0.1)',
    'core.cli.port_help': 'wss:// listen port (default 8443)',
    'core.cli.ws_port_help': 'ws:// (plaintext, fallback) listen port; 0 disables it',
    'core.cli.no_srv_help': 'Skip SRV lookups; use port 25565 when the target has none',
    'core.cli.rewrite_host_help': 'Rewrite the server address in the handshake to the '
                                  'target domain (for servers that validate or route by address)',
    'core.cli.no_eagler_help': 'Disable WebSocket client protocol translation; '
                               'forward raw bytes only',
    'core.cli.no_login_ack_help': 'Disable the 1.20.2+ login acknowledge sent to the target '
                                  'server on the client\'s behalf',
    'core.cli.account_help': 'Use this account (name or id from the account list) for this '
                             'run instead of the selected one',
    'core.cli.server_brand_help': 'Server brand shown to WebSocket clients '
                                  '(default ServerProtocolBridge)',
    'core.cli.server_version_help': 'Server version shown to WebSocket clients '
                                    '(empty = program version)',
    'core.cli.spoof_client_help': 'Client identity to imitate at the target server (pick the '
                                  'target server\'s Minecraft era): off / vanilla / forge-1.8 / '
                                  'forge-1.13 / neoforge / fabric (default forge-1.8; on 1.8 '
                                  'connections forge-1.8 also reproduces the legacy FML fingerprints)',
    'core.cli.spoof_brand_help': 'Client brand (MC|Brand) sent to the target server; empty = the '
                                 'preset default, e.g. fml,forge for Forge 1.8.x and forge for 1.13+',
    'core.cli.no_spoof_brand_help': 'Send no client identity at all (same as --spoof-client off)',
    'core.cli.cert_dir_help': 'Certificate directory (default certs)',
    'core.cli.regen_cert_help': 'Regenerate the certificate',
    'core.cli.install_cert_help': 'Import the certificate into the system trust store, then exit',
    'core.cli.check_help': 'Check the certificate and the connectivity to the target '
                           'server, then exit',
    'core.cli.selftest_help': 'Print an environment self-test (crypto backend / GUI / config); '
                              'use it after packaging to confirm every dependency is present',
    'core.cli.log_level_help': 'Log level',
    'core.cli.heartbeat_help': 'WebSocket heartbeat interval in seconds; 0 disables it',
    'core.cli.max_payload_help': 'Max size of a single frame (MB)',
    'core.cli.language_help': 'UI language: en (English) or zh (Chinese)',
    'core.cli.check_update_help': 'Ask the cloud endpoint for the newest release, print the '
                                  'result and exit (exit code 1 = a newer release exists)',
    'core.cli.no_update_check_help': 'Do not check for a newer release on startup',
    'core.cli.config_problem': 'Configuration: %(problem)s',
    'core.cli.work_dir': 'Working directory: %(path)s',
    'core.cli.target_line': 'Forward target: %(target)s',
    'core.cli.checking_cert': 'Checking the certificate ...',
    'core.cli.cert_ok': 'Certificate is usable: %(path)s',
    'core.cli.cert_thumbprint': 'SHA-256 fingerprint: %(thumbprint)s',
    'core.cli.cert_alt_names': 'Covered names: %(names)s',
    'core.cli.cert_trust_hint': 'If the browser still reports the certificate as untrusted, '
                                'run --install-cert and restart the browser.',
    'core.cli.cert_check_failed': 'Certificate check failed: %(error)s',
    'core.cli.probing': 'Testing connectivity to %(host)s:%(port)d ...',
    'core.cli.probe_ok': 'Target server reachable, handshake took %(ms)s ms',
    'core.cli.probe_failed': 'Target server unreachable: %(error)s',
    'core.cli.run_mode': 'Running from: %(mode)s',
    'core.cli.run_mode_frozen': 'packaged EXE',
    'core.cli.run_mode_source': 'source code',
    'core.cli.crypto_ok': 'Encryption handshake: available (backend %(backend)s) -- the proxy '
                          'can perform it when the target server requires it',
    'core.cli.crypto_missing': 'Encryption handshake: unavailable -- cryptography is required '
                               '(pip install cryptography)',
    'core.cli.gui_ok': 'GUI: available (tkinter)',
    'core.cli.gui_missing': 'GUI: unavailable (%(error)s)',
    'core.cli.regen_notice': 'Re-issuing the certificate ...',
    'core.cli.cert_generate_failed': 'Certificate generation failed: %(error)s',
    'core.cli.install_failed': 'Import failed: %(error)s',
    'core.cli.install_done': 'Done. Restart the browser, then use %(url)s',
    'core.cli.start_failed': 'Startup failed: %(error)s',
    'core.cli.wss_line': 'wss address: %(url)s',
    'core.cli.disabled': '(disabled)',
    'core.cli.fallback_ws_line': 'Fallback plaintext address: %(url)s',
    'core.cli.stop_hint': 'Press Ctrl+C to stop the service',
    'core.cli.ctrl_c': 'Received Ctrl+C, stopping ...',
    'core.cli.update_failed': 'Version check failed: %(error)s',
    'core.cli.update_available': 'A newer release is available: %(version)s (running %(current)s)',
    'core.cli.update_required': 'This update is required -- please install the new release.',
    'core.cli.update_min_version': 'The oldest supported version is %(version)s.',
    'core.cli.update_release_date': 'Release date: %(date)s',
    'core.cli.update_file_size': 'Download size: %(size)s',
    'core.cli.update_sha256': 'SHA256: %(sha256)s',
    'core.cli.update_notes_header': 'Release notes:',
    'core.cli.update_page': 'Download page: %(url)s',
    'core.cli.update_source': 'Source code: %(url)s',
    'core.cli.update_latest': 'Version check: %(version)s is the newest release',

    # ---------- main.py ----------
    'core.main.gui_fallback': 'Could not load the GUI (%(error)s); falling back to '
                              'command line mode.',
    'core.main.gui_fallback_hint': 'Hint: on Windows install a Python build that includes '
                                   'tkinter; on Linux install python3-tk.\n',

    # ---------- accounts.py ----------
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
    # ---------- identity (version.py) ----------
    'core.app_name': '服务器协议转换',
    'core.tagline': '把普通 Minecraft 服务器转换为本地 wss:// 或 ws:// 端点, '
                    '供 WebSocket 客户端连接。',

    # ---------- config.py ----------
    'core.config.address_empty': '地址不能为空',
    'core.config.route_format': '路径映射格式应为 "路径=目标", 例如: /lobby=play.example.net',
    'core.config.route_missing_target': '路径映射 "%(path)s" 缺少目标地址',
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
    'core.config.language_invalid': '语言只能是 "en" 或 "zh"',
    'core.config.web_host_empty': 'Web UI 绑定地址不能为空',
    'core.config.web_port_range': 'Web UI 端口必须在 0 到 65535 之间（0 = 自动选择空闲端口）',

    # ---------- logger.py ----------
    'core.log.debug': '调试',
    'core.log.info': '信息',
    'core.log.warn': '警告',
    'core.log.error': '错误',

    # ---------- cli.py ----------
    'core.cli.description': '%(app)s v%(version)s —— 把普通 Minecraft 服务器转换为本地 wss:// 或 ws:// 端点',
    'core.cli.version_line': '%(app)s v%(version)s',
    'core.cli.config_help': '配置文件路径(默认程序目录下的 config.json)',
    'core.cli.no_gui_help': '以命令行方式运行(这里本来就是命令行模式, 这个参数只是为了和 main.py 的用法保持一致)',
    'core.cli.target_help': '转发目标, 例如 play.example.net(按 SRV 解析) 或 127.0.0.1:25565',
    'core.cli.listen_help': '监听地址(默认 127.0.0.1)',
    'core.cli.port_help': 'wss:// 监听端口(默认 8443)',
    'core.cli.ws_port_help': 'ws://(明文, 备用)监听端口, 0 表示关闭',
    'core.cli.no_srv_help': '不做 SRV 解析, 目标不带端口时直接用 25565',
    'core.cli.rewrite_host_help': '把握手包里的服务器地址改写成目标域名(服务器按地址校验/分流时使用)',
    'core.cli.no_eagler_help': '关闭 WebSocket 客户端协议翻译, 只做纯字节转发',
    'core.cli.no_login_ack_help': '关闭代客户端补发的 1.20.2+ 登录确认包',
    'core.cli.account_help': '本次改用指定账号(账号名或列表里的 ID), 不改变已选账号',
    'core.cli.server_brand_help': 'WebSocket 客户端看到的"服务器品牌"(默认 ServerProtocolBridge)',
    'core.cli.server_version_help': 'WebSocket 客户端看到的"服务器版本"(空 = 用程序版本号)',
    'core.cli.spoof_client_help': '向目标服务器伪装成哪种客户端(按目标服务器的大概版本选): '
                                  'off / vanilla / forge-1.8 / forge-1.13 / neoforge / fabric '
                                  '(默认 forge-1.8; 1.8 连接上还会复刻旧版 FML 握手特征)',
    'core.cli.spoof_brand_help': '发给目标服务器的客户端标识(MC|Brand); 留空 = 用预设默认值, '
                                 '例如 Forge 1.8.x 写 fml,forge, 1.13+ 写 forge',
    'core.cli.no_spoof_brand_help': '完全不伪装客户端标识(等同于 --spoof-client off)',
    'core.cli.cert_dir_help': '证书目录(默认 certs)',
    'core.cli.regen_cert_help': '重新生成证书',
    'core.cli.install_cert_help': '把证书导入系统信任库后退出',
    'core.cli.check_help': '检查证书与目标服务器连通性后退出',
    'core.cli.selftest_help': '打印运行环境自检(加密库/图形界面/配置), 打包后用来确认依赖齐全',
    'core.cli.log_level_help': '日志级别',
    'core.cli.heartbeat_help': 'WebSocket 心跳间隔秒数, 0 关闭',
    'core.cli.max_payload_help': '单帧上限(MB)',
    'core.cli.language_help': '界面语言: en(英文) 或 zh(中文)',
    'core.cli.check_update_help': '向云端查询最新版本并退出(退出码 1 = 有新版本)',
    'core.cli.no_update_check_help': '启动时不自动检查新版本',
    'core.cli.config_problem': '配置: %(problem)s',
    'core.cli.work_dir': '工作目录: %(path)s',
    'core.cli.target_line': '转发目标: %(target)s',
    'core.cli.checking_cert': '正在检查证书...',
    'core.cli.cert_ok': '证书可用: %(path)s',
    'core.cli.cert_thumbprint': '指纹 SHA-256: %(thumbprint)s',
    'core.cli.cert_alt_names': '覆盖名称: %(names)s',
    'core.cli.cert_trust_hint': '如果浏览器仍提示证书不受信任, 请执行 --install-cert 后重启浏览器。',
    'core.cli.cert_check_failed': '证书检查失败: %(error)s',
    'core.cli.probing': '正在测试 %(host)s:%(port)d 的连通性...',
    'core.cli.probe_ok': '目标服务器可达, 握手耗时 %(ms)s ms',
    'core.cli.probe_failed': '目标服务器不可达: %(error)s',
    'core.cli.run_mode': '运行方式: %(mode)s',
    'core.cli.run_mode_frozen': '打包的 EXE',
    'core.cli.run_mode_source': '源码',
    'core.cli.crypto_ok': '加密握手: 可用 (后端 %(backend)s) —— 目标服务器要求加密时可以代做',
    'core.cli.crypto_missing': '加密握手: 不可用 —— 需要 cryptography (pip install cryptography)',
    'core.cli.gui_ok': '图形界面: 可用 (tkinter)',
    'core.cli.gui_missing': '图形界面: 不可用 (%(error)s)',
    'core.cli.regen_notice': '将重新签发证书...',
    'core.cli.cert_generate_failed': '证书生成失败: %(error)s',
    'core.cli.install_failed': '导入失败: %(error)s',
    'core.cli.install_done': '完成。请重启浏览器后使用 %(url)s',
    'core.cli.start_failed': '启动失败: %(error)s',
    'core.cli.wss_line': 'wss 地址: %(url)s',
    'core.cli.disabled': '(未启用)',
    'core.cli.fallback_ws_line': '备用明文地址: %(url)s',
    'core.cli.stop_hint': '按 Ctrl+C 停止服务',
    'core.cli.ctrl_c': '收到 Ctrl+C, 正在停止...',
    'core.cli.update_failed': '版本检查失败: %(error)s',
    'core.cli.update_available': '有新版本可用: %(version)s (当前 %(current)s)',
    'core.cli.update_required': '此更新为必须更新，请安装新版本。',
    'core.cli.update_min_version': '仍然支持的最旧版本是 %(version)s。',
    'core.cli.update_release_date': '发布日期: %(date)s',
    'core.cli.update_file_size': '下载大小: %(size)s',
    'core.cli.update_sha256': 'SHA256: %(sha256)s',
    'core.cli.update_notes_header': '更新日志:',
    'core.cli.update_page': '下载页面: %(url)s',
    'core.cli.update_source': '源码下载: %(url)s',
    'core.cli.update_latest': '版本检查: 当前 %(version)s 已是最新版本',

    # ---------- main.py ----------
    'core.main.gui_fallback': '无法加载图形界面(%(error)s), 已切换到命令行模式。',
    'core.main.gui_fallback_hint': '提示: Windows 请安装带 tkinter 的 Python; Linux 需安装 python3-tk。\n',

    # ---------- accounts.py ----------
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
