"""Translations for the desktop window and the Web UI.

Owner: ``gui_ctk.py`` and ``web.py`` (keys prefixed ``gui.*``).
"""

from __future__ import annotations

EN = {
    'gui.language': 'Language',

    # Window menu
    'gui.menu.file': 'File',
    'gui.menu.tools': 'Tools',
    'gui.menu.help': 'Help',
    'gui.menu.save_config': 'Save Config',
    'gui.menu.settings': 'Settings...',
    'gui.menu.open_workdir': 'Open Working Directory',
    'gui.menu.quit': 'Exit',
    'gui.menu.copy_endpoint': 'Copy wss Address',
    'gui.menu.install_cert': 'Install Certificate into Trust Store',
    'gui.menu.check_update': 'Check for Updates',

    # Log panel
    'gui.log_frame': 'Runtime Log',
    'gui.log.clear': 'Clear Log',
    'gui.log.auto_scroll': 'Auto-scroll',
    'gui.log.hint': 'Tip: double-click the log to copy everything',

    # Group boxes
    'gui.group.basic': 'Basic Settings',

    # Settings window (everything that would crowd the main window)
    'gui.settings.title': 'Settings',
    'gui.settings.tab.connection': 'Connection',
    'gui.settings.tab.accounts': 'Accounts',
    'gui.settings.tab.cert': 'Certificate',
    'gui.settings.tab.update': 'Updates',
    'gui.settings.apply': 'Apply & Save',
    'gui.settings.close': 'Close',
    'gui.settings.check_now': 'Check Now',
    'gui.settings.update_hint': 'The update endpoint is built into the program and cannot be '
                                'changed.',

    # Basic settings
    'gui.label.listen_host': 'Listen Address',
    'gui.label.wss_port': 'wss port',
    'gui.label.ws_port': 'ws port (0 = off)',
    'gui.label.target': 'Forward Target',
    'gui.label.use_srv': 'Resolve via SRV when no port is given',
    'gui.label.auto_exit': 'Auto exit (let connected clients leave the server '
                           'cleanly before stopping)',

    # Certificate
    'gui.label.cert_dir': 'Certificate Directory',
    'gui.label.cert_cn': 'Name (CN)',
    'gui.label.cert_days': 'Valid for (days)',
    'gui.label.cert_extra': 'Extra Names',
    'gui.label.cert_generator': 'Generator',
    'gui.label.cert_fill': 'Enter this address in your client:',

    # Cloud version check (settings window -> Updates)
    'gui.label.update_check': 'Check for a newer release on startup',
    'gui.button.regen_cert': 'Regenerate Certificate',
    'gui.button.install_cert': 'Install into Trust Store',
    'gui.button.open_cert_dir': 'Open Certificate Directory',
    'gui.cert.info_missing': 'No certificate yet -- a self-signed one is issued automatically '
                             'when the service starts',
    'gui.cert.info': 'File: %(file)s\nSHA-256 fingerprint: %(thumbprint)s\nCovers: %(names)s',
    'gui.cert.hint': 'Generate the certificate, install it into the system trust store, then '
                     'restart the browser. Clients can also open the certificate address and '
                     'trust it manually.',

    # Advanced
    'gui.label.log_level': 'Log Level',
    'gui.label.heartbeat': 'Heartbeat (s, 0 = off)',
    'gui.label.status_cache': 'Cache server-list status',
    'gui.label.status_cache_ttl': 'Cache lifetime (s)',
    'gui.label.status_cache_hint': 'Off: every list query waits for the target. On: cached results return '
                                   'immediately and refresh in the background.',
    'gui.label.connect_timeout': 'Connect Timeout (s)',
    'gui.label.max_payload': 'Max Frame Size (MB)',
    'gui.label.spoof_client': 'Client identity spoofing',
    'gui.spoof.off': 'Off (no spoofing)',
    'gui.spoof.vanilla': 'Vanilla',
    'gui.spoof.forge-1.8': 'Forge 1.8.x - 1.12.2',
    'gui.spoof.forge-1.13': 'Forge 1.13+',
    'gui.spoof.neoforge': 'NeoForge 1.20.2+',
    'gui.spoof.fabric': 'Fabric',
    'gui.label.rewrite_host': 'Rewrite the handshake address to the target domain '
                              '(tick when the server validates or routes by address)',
    'gui.label.eagler_translate': 'WebSocket client protocol translation '
                                  '(required for clients that use wss:// or ws://)',
    'gui.label.login_ack': 'Login acknowledge for 1.20.2+ targets '
                            '(sent on the client\'s behalf; modern servers need it)',
    'gui.label.resource_pack_mode': 'Resource pack handling',
    'gui.resource_pack_mode.forward': 'Forward prompt',
    'gui.resource_pack_mode.accept': 'Accept if present',
    'gui.resource_pack_mode.reject': 'Reject',
    'gui.resource_pack_mode.spoof': 'Fake accept (no prompt)',
    'gui.label.theme': 'Theme',
    'gui.theme.light': 'Light',
    'gui.theme.dark': 'Dark',
    'gui.theme.system': 'Follow system',

    # Action buttons
    'gui.button.start': 'Start Service',
    'gui.button.stop': 'Stop Service',
    'gui.button.copy': 'Copy',
    'gui.button.copy_endpoint': 'Copy wss Address',
    'gui.button.save_config': 'Save Config',
    'gui.button.settings': 'Settings...',
    'gui.button.reset_defaults': 'Restore Defaults',

    # Status bar
    'gui.stat.active': 'Active',
    'gui.stat.total': 'Total',
    'gui.stat.up': 'Up',
    'gui.stat.down': 'Down',
    'gui.stat.uptime': 'Uptime',

    # Run-state indicator
    'gui.status.stopped': 'Stopped',
    'gui.status.starting': 'Starting',
    'gui.status.running': 'Running',
    'gui.status.stopping': 'Stopping',
    'gui.status.start_failed': 'Start Failed',
    'gui.status.installing_cert': 'Installing Certificate',

    # Endpoint display
    'gui.endpoint.need_port': '(enter a port first)',
    'gui.endpoint.disabled': '(no listener enabled)',

    # Field labels used inside validation errors
    'gui.error.title': 'Invalid Configuration',
    'gui.error.empty': '"%(label)s" cannot be empty',
    'gui.error.not_number': '"%(label)s" must be a number, got: %(value)s',
    'gui.error.invalid_number': '"%(label)s" is not a valid number: %(value)s',
    'gui.error.port_range': '"%(label)s" must be between 0 and 65535, got: %(value)s',
    'gui.field.wss_port': 'wss port',
    'gui.field.ws_port': 'ws port',
    'gui.field.web_port': 'Web UI port',
    'gui.field.cert_days': 'Certificate validity',
    'gui.field.heartbeat': 'Heartbeat interval',
    'gui.field.status_cache_ttl': 'Server-list cache lifetime',
    'gui.field.connect_timeout': 'Connect timeout',
    'gui.field.max_payload': 'Max frame size',

    # Log lines written by the GUI itself
    'gui.log.starting': '%(name)s v%(version)s is starting...',
    'gui.log.target': 'Forward target: %(target)s',
    'gui.log.config_save_failed': 'Failed to save the configuration: %(error)s',
    'gui.log.start_failed': 'Start failed: %(error)s',
    'gui.log.listening': 'wss listener: %(url)s',
    'gui.log.fallback_listener': 'Plain-text fallback listener: %(url)s '
                                 '(usable when the page itself is served over http://)',
    'gui.log.cert_fingerprint': 'Certificate SHA-256 fingerprint: %(thumbprint)s',
    'gui.log.cert_trust_hint': 'If the browser reports the certificate as untrusted, click '
                               '[Install into Trust Store] and restart the browser.',
    'gui.log.copied': 'Copied to clipboard: %(text)s',
    'gui.log.config_saved': 'Configuration saved: %(path)s',
    'gui.log.certutil': 'certutil output: %(output)s',

    # Dialogs
    'gui.dialog.switch_failed': 'Language Switch Failed',
    'gui.dialog.need_stop.title': 'Stop the Service First',
    'gui.dialog.need_stop.text': 'The service must be stopped before the certificate '
                                 'can be regenerated.',
    'gui.dialog.regen.title': 'Regenerate Certificate',
    'gui.dialog.regen.confirm': 'The current certificate will be deleted and a new one '
                                'issued. Continue?',
    'gui.dialog.delete_failed': 'Delete Failed',
    'gui.dialog.generate_failed': 'Generation Failed',
    'gui.dialog.regen.done_title': 'Done',
    'gui.dialog.regen.done': 'The certificate has been regenerated.',
    'gui.dialog.regen.done_deleted': 'The certificate has been regenerated; '
                                     'the old one was deleted.',
    'gui.dialog.cert_missing.title': 'No Certificate Yet',
    'gui.dialog.cert_missing.ask': 'There is no certificate file yet. Generate and install it now?',
    'gui.dialog.install_ok.title': 'Installed',
    'gui.dialog.install_ok.text':
        'The certificate was added to the current user\'s "Trusted Root Certification '
        'Authorities".\n\n'
        'Please restart the browser (Chrome / Edge take effect immediately; Firefox\n'
        'needs a separate import under Settings -> Privacy & Security ->\n'
        'Certificates -> View Certificates).',
    'gui.dialog.install_failed': 'Installation Failed',
    'gui.dialog.unknown_error': 'Unknown error',
    'gui.dialog.no_endpoint.title': 'No Usable Address',
    'gui.dialog.no_endpoint.text': 'Set a wss port first',
    'gui.dialog.not_running.title': 'Not Running',
    'gui.dialog.not_running.text': 'Start the service first.',
    'gui.dialog.save_failed': 'Save Failed',
    'gui.dialog.reset.title': 'Restore Defaults',
    'gui.dialog.reset.ask': 'The settings in the window will be reset to their defaults '
                            '(the saved configuration file is not overwritten). Continue?',
    'gui.dialog.open_failed': 'Open Failed',

    # Help / about
    'gui.help.title': 'User Guide',
    'gui.help.text': """Steps

1. Enter the Java server address in "Forward Target". There is no default
   server: use the address you actually play on. A bare domain is enough --
   the program finds the real server node through its SRV record. Otherwise
   enter its domain or domain:port.
2. Click [Start Service]; the status at the bottom switches to "Running".
3. On first use open [Settings...] -> Certificate and click [Install into
   Trust Store], which adds the self-signed certificate to Windows'
   "Trusted Root Certification Authorities"; otherwise the browser warns
   that the wss:// certificate is untrusted.
   (Firefox needs a separate import under Settings -> Privacy & Security
   -> Certificates -> View Certificates.)
4. Enter the following in your client's server address field:
   wss://127.0.0.1:8443
   then connect. Native Java clients are forwarded byte for byte; WebSocket
   clients use the protocol translation their connection requires.

When a connection fails, check the "Runtime Log": every connection logs its
handshake details (protocol version / the address the client sent), the
up/down byte counts and the reason it closed.

FAQ

Q: The EXE won't open, it crashes on launch with an error.
A: Install the Visual C++ Redistributable, or run the program from source.
   The EXE is built with PyInstaller and requires the VC++ runtime to be
   present on the system. Download it from:
   https://aka.ms/vs/17/release/vc_redist.x64.exe

Q: The console prints "[0x...] ANOMALY: meaningless REX prefix used".
A: Ignore it. The line comes from the graphics driver, not from this program,
   and it does not affect any feature. If it keeps appearing while the app is
   running and you use an Intel iGPU, make sure the latest Intel graphics
   driver is installed.
""",
    # ---------- Cloud version check ----------
    'gui.update.title': 'Version Check',
    'gui.update.window_subtitle': 'Version information and download',
    'gui.update.label_current': 'Current version',
    'gui.update.label_latest': 'Latest release',
    'gui.update.label_page': 'Download page',
    'gui.update.label_source': 'Source code',
    'gui.update.label_state': 'Status',
    'gui.update.latest_unknown': 'not checked yet',
    'gui.update.no_page': 'none published',
    'gui.update.no_source': 'none published',
    'gui.update.idle': 'Click [Check for Updates] to ask the server for the newest release.',
    'gui.update.button_check': 'Check for Updates',
    'gui.update.button_open': 'Open Download Page',
    'gui.update.button_source': 'Download Source',
    'gui.update.checking': 'Checking for the newest release ...',
    'gui.update.failed': 'Version check failed: %(error)s',
    'gui.update.up_to_date': 'Version check: %(version)s is the newest release',
    'gui.update.available': 'Newer release %(version)s is available (running %(current)s)',
    'gui.update.banner': 'Newer release %(version)s is available (running %(current)s)',
    'gui.update.banner_page': '-- click to open the download page',
    'gui.update.label_date': 'Release date',
    'gui.update.label_size': 'File size',
    'gui.update.label_notes': 'Release notes',
    'gui.update.unknown_value': 'not published',
    'gui.update.no_notes': 'This release did not come with notes.',
    'gui.update.must_update': 'Update required: version %(version)s (running %(current)s)',
    'gui.update.force_hint': 'The publisher marks this release as required. Please download and '
                             'install it; the running version is no longer supported.',
    'gui.update.banner_force': 'Required update %(version)s (running %(current)s)',

    # ---------- Accounts ----------
    'gui.accounts.col.name': 'Account',
    'gui.accounts.col.kind': 'Type',
    'gui.accounts.col.uuid': 'UUID',
    'gui.accounts.col.state': 'In use',
    'gui.accounts.button.add': 'Add account',
    'gui.accounts.add.offline': 'Offline account',
    'gui.accounts.add.thirdparty': 'Third-party account',
    'gui.accounts.add.microsoft': 'Microsoft account',
    'gui.accounts.button.active': 'Use this account',
    'gui.accounts.button.clear': 'Use none',
    'gui.accounts.button.remove': 'Remove',
    'gui.accounts.button.open_dir': 'Open folder',
    'gui.accounts.hint': 'The selected account is used to sign in to the target server: its '
                         'exact name and UUID are sent upstream, and third-party / Microsoft '
                         'accounts also register the session join, so servers that require '
                         'an authenticated session let browser clients through.  Microsoft '
                         'credentials are refreshed automatically before every join; if that '
                         'fails, the connection closes and the reason appears in chat.  '
                         '"Use none" keeps the old behaviour: the name the client sends.',
    'gui.accounts.data_dir': 'Account file: %(path)s',
    'gui.accounts.need_selection': 'Select an account in the list first.',
    'gui.accounts.selected': 'Now using account %(name)s',
    'gui.accounts.cleared': 'No account selected; clients use their own names again',
    'gui.accounts.removed': 'Removed account %(name)s',
    'gui.accounts.remove.title': 'Remove account',
    'gui.accounts.remove.ask': 'Remove account %(name)s?',
    'gui.accounts.offline.prompt': 'Player name (letters / digits / underscore, 3-16 characters)',
    'gui.accounts.offline.bad_name': 'That name cannot be used: 3-16 characters, letters / '
                                     'digits / underscore only',
    'gui.accounts.thirdparty.title': 'Add third-party account',
    'gui.accounts.thirdparty.server': 'Account service address',
    'gui.accounts.thirdparty.username': 'User name / e-mail',
    'gui.accounts.thirdparty.password': 'Password',
    'gui.accounts.thirdparty.note': 'Use the API root provided by your third-party account '
                                    'service.',
    'gui.accounts.thirdparty.submit': 'Sign in and add',
    'gui.accounts.thirdparty.busy': 'Signing in...',
    'gui.accounts.thirdparty.added': 'Added third-party account %(name)s',
    'gui.accounts.thirdparty.missing': 'Please fill in the address, the user name and the password.',
    'gui.accounts.ms.title': 'Add Microsoft account',
    'gui.accounts.ms.intro': 'A browser window opens at microsoft.com/link: type the '
                             'code below there and sign in to your Microsoft account.  '
                             'If no browser opened, use the buttons below.  This window '
                             'carries on by itself once the browser is done.',
    'gui.accounts.ms.code_label': 'Code:',
    'gui.accounts.ms.starting': 'Requesting a sign-in code from Microsoft...',
    'gui.accounts.ms.waiting': 'Waiting for the sign-in in the browser...',
    'gui.accounts.ms.copy_code': 'Copy code',
    'gui.accounts.ms.code_copied': 'Sign-in code copied to the clipboard',
    'gui.accounts.ms.copy': 'Copy link',
    'gui.accounts.ms.open': 'Open in browser',
    'gui.accounts.ms.copied': 'Sign-in link copied to the clipboard',
    'gui.accounts.ms.open_failed': 'Could not open a browser; use "Copy link" and paste '
                                   'the address into a browser window instead',
    'gui.accounts.ms.added': 'Added Microsoft account %(name)s',
    'gui.accounts.ms.ssl_title': 'Certificate check failed',
    'gui.accounts.ms.ssl_ask': 'The secure connection to Microsoft could not be '
                               'verified:\n\n%(detail)s\n\n'
                               'Click Yes to ignore the SSL certificate error and '
                               'continue; click No to stop.\n\n'
                               'If you ignore it, data on this connection could be '
                               'read by others on the network.',
    'gui.accounts.ms.renewing': 'Microsoft rejected this sign-in code; '
                                'requesting a new one...',
    'gui.accounts.ms.retrying_ssl': 'Certificate check skipped; requesting a new '
                                    'sign-in code...',
    'gui.accounts.legal': 'By adding an offline or third-party account, you confirm that you '
                          'own Minecraft with a Microsoft account.',

    'gui.about.title': 'About',
    'gui.about.subtitle': 'About this build',
    'gui.about.blurb': 'A local wss:// or ws:// relay for Minecraft clients. '
                       'Game traffic runs directly on the websockets transport, without '
                       'an ASGI gateway. The open-source components below are included in '
                       'this build.',
    'gui.about.project_license': 'Project license: Unlicense (public domain). '
                                 'Full text: LICENSE in the source package; '
                                 'https://unlicense.org/',
    'gui.about.components': 'Third-party components',
    'gui.about.stdlib': 'Python standard library modules',
    'gui.about.column_component': 'Component',
    'gui.about.column_license': 'License',
    'gui.about.column_project': 'Project',
    'gui.about.hint': 'Click any row to open the official site or GitHub repository.',
    'gui.about.close': 'Close',
    'gui.about.text': """%(name)s v%(version)s

Turns a plain Minecraft server (Hypixel, for example) into a local
wss:// or ws:// endpoint so WebSocket clients can connect -- browsers
only allow wss:// connections.

Native Java clients are forwarded byte for byte. WebSocket clients go
through the handshake and protocol translation their connection requires.
Working directory: %(workdir)s""",
    # ---------- CustomTkinter shell / Web UI entry ----------
    'gui.nav.control': 'Control',
    'gui.nav.settings': 'Settings',
    'gui.nav.accounts': 'Accounts',
    'gui.nav.cert': 'Certificate',
    'gui.nav.log': 'Log',
    'gui.nav.about': 'About',
    'gui.page.control.subtitle': 'Start the bridge, watch the session and hand out the endpoint.',
    'gui.page.settings.subtitle': 'Every option in the configuration file, grouped by purpose.',
    'gui.page.accounts.subtitle': 'Sign-in identities used when a browser client joins a server.',
    'gui.page.cert.subtitle': 'The TLS certificate browser clients are asked to trust.',
    'gui.page.log.subtitle': 'Everything the proxy, the window and the Web UI report.',
    'gui.page.about.subtitle': 'Version, licence and the components this build ships.',
    'gui.section.connection': 'Connection',
    'gui.section.actions': 'Service',
    'gui.section.status': 'Session',
    'gui.section.forwarding': 'Forwarding and identity',
    'gui.section.protocol': 'Protocol translation',
    'gui.section.runtime': 'Runtime',
    'gui.section.certificate': 'Certificate',
    'gui.section.web': 'Web UI',
    'gui.label.web_host': 'Bind address',
    'gui.label.web_port': 'Bind port',
    'gui.hint.web_bind': '0.0.0.0 exposes the page on the LAN; 0 lets the system pick a free port.',
    'gui.label.web_password': 'Require access password',
    'gui.hint.web_password': 'Off by default. Only the Web UI asks for it; the window never does.',
    'gui.label.web_password_new': 'New password',
    'gui.label.web_password_confirm': 'Confirm password',
    'gui.hint.web_password_keep': 'Leave both password fields blank to keep the current password.',
    'gui.error.password_mismatch': 'The two passwords do not match.',
    'gui.error.password_required': 'Enter a password before enabling access control.',
    'gui.error.password_short': 'The password must contain at least 4 characters.',
    'gui.log.web_password_on': 'Web UI access password enabled.',
    'gui.log.web_password_off': 'Web UI access password disabled.',
    'gui.button.web_restart': 'Restart Web UI',
    'gui.label.server_brand': 'Server brand',
    'gui.label.server_brand_version': 'Server version',
    'gui.label.spoof_brand': 'Spoofed client brand',
    'gui.label.routes': 'Path routes',
    'gui.hint.routes': 'One path=target per line, for example /lobby=play.example.net:25565',
    'gui.hint.spoof_brand': 'Empty uses the preset default; the value must be ASCII.',
    'gui.hint.endpoint': 'Paste this address into the browser client.',
    'gui.button.open_web': 'Open Web UI',
    'gui.web.title': 'Web UI',
    'gui.web.hint': 'The Web UI offers the same controls in a browser (start, stop, configure, monitor).',
    'gui.web.running': 'Web UI running at %(url)s',
    'gui.web.failed': 'The Web UI could not start: %(error)s',
    'gui.log.web_started': 'Web UI started at %(url)s',
    'gui.accounts.none': 'No account yet. Add one above.',
    'gui.accounts.added_offline': 'Offline account added: %(name)s',
    'runtime.busy': 'The service is already starting, running or stopping.',
}

ZH = {
    'gui.language': '界面语言',

    # 窗口菜单
    'gui.menu.file': '文件',
    'gui.menu.tools': '工具',
    'gui.menu.help': '帮助',
    'gui.menu.save_config': '保存配置',
    'gui.menu.settings': '设置...',
    'gui.menu.open_workdir': '打开工作目录',
    'gui.menu.quit': '退出',
    'gui.menu.copy_endpoint': '复制 wss 地址',
    'gui.menu.install_cert': '安装证书到系统信任库',
    'gui.menu.check_update': '检查更新',

    # 日志面板
    'gui.log_frame': '运行日志',
    'gui.log.clear': '清空日志',
    'gui.log.auto_scroll': '自动滚动',
    'gui.log.hint': '提示: 双击日志可复制全部内容',

    # 分组框
    'gui.group.basic': '基本设置',

    # 设置窗口(放不进主窗口的东西)
    'gui.settings.title': '设置',
    'gui.settings.tab.connection': '连接',
    'gui.settings.tab.accounts': '账号',
    'gui.settings.tab.cert': '证书',
    'gui.settings.tab.update': '更新',
    'gui.settings.apply': '应用并保存',
    'gui.settings.close': '关闭',
    'gui.settings.check_now': '立即检查',
    'gui.settings.update_hint': '版本检查地址由程序内置, 不可修改。',

    # 基本设置
    'gui.label.listen_host': '监听地址',
    'gui.label.wss_port': 'wss 端口',
    'gui.label.ws_port': 'ws 端口(0=关闭)',
    'gui.label.target': '转发目标',
    'gui.label.use_srv': '不带端口时按 SRV 解析',
    'gui.label.auto_exit': '自动退出(停止/关闭前让客户端正常退出服务器)',

    # 证书
    'gui.label.cert_dir': '证书目录',
    'gui.label.cert_cn': '名称(CN)',
    'gui.label.cert_days': '有效期(天)',
    'gui.label.cert_extra': '额外名称',
    'gui.label.cert_generator': '生成器',
    'gui.label.cert_fill': '在客户端中填写:',

    # 版本检查(设置窗口 -> 更新)
    'gui.label.update_check': '启动时检查新版本',
    'gui.button.regen_cert': '重新生成证书',
    'gui.button.install_cert': '安装到系统信任库',
    'gui.button.open_cert_dir': '打开证书目录',
    'gui.cert.info_missing': '尚未生成证书 —— 启动服务时会自动签发一张自签名证书',
    'gui.cert.info': '文件: %(file)s\n指纹 SHA-256: %(thumbprint)s\n覆盖名称: %(names)s',
    'gui.cert.hint': '生成证书后安装到系统信任库，然后重启浏览器。客户端也可以直接打开证书地址并手动信任。',

    # 高级
    'gui.label.log_level': '日志级别',
    'gui.label.heartbeat': '心跳(秒, 0=关闭)',
    'gui.label.status_cache': '缓存服务器列表状态',
    'gui.label.status_cache_ttl': '缓存时间(秒)',
    'gui.label.status_cache_hint': '关闭后每次列表查询都会等待目标服务器；开启后优先返回缓存，并在后台刷新。',
    'gui.label.connect_timeout': '连接超时(秒)',
    'gui.label.max_payload': '单帧上限(MB)',
    'gui.label.spoof_client': '客户端标识伪装',
    'gui.spoof.off': '关闭(不伪装)',
    'gui.spoof.vanilla': '原版',
    'gui.spoof.forge-1.8': 'Forge 1.8.x ~ 1.12.2',
    'gui.spoof.forge-1.13': 'Forge 1.13+',
    'gui.spoof.neoforge': 'NeoForge 1.20.2+',
    'gui.spoof.fabric': 'Fabric',
    'gui.label.rewrite_host': '按目标域名改写握手地址(服务器按地址校验/分流时勾选)',
    'gui.label.eagler_translate': 'WebSocket 客户端协议翻译(使用 wss:// 或 ws:// 的客户端必需)',
    'gui.label.login_ack': '补发登录确认包(1.20.2+ 服务器必需, 否则进服即断)',
    'gui.label.resource_pack_mode': '资源包处理方式',
    'gui.resource_pack_mode.forward': '转发提示',
    'gui.resource_pack_mode.accept': '有则允许',
    'gui.resource_pack_mode.reject': '拒绝',
    'gui.resource_pack_mode.spoof': '假装允许（不提示）',
    'gui.label.theme': '主题',
    'gui.theme.light': '浅色',
    'gui.theme.dark': '深色',
    'gui.theme.system': '跟随系统',

    # 操作按钮
    'gui.button.start': '启动服务',
    'gui.button.stop': '停止服务',
    'gui.button.copy': '复制',
    'gui.button.copy_endpoint': '复制 wss 地址',
    'gui.button.save_config': '保存配置',
    'gui.button.settings': '设置...',
    'gui.button.reset_defaults': '恢复默认配置',

    # 状态栏
    'gui.stat.active': '活动连接',
    'gui.stat.total': '累计连接',
    'gui.stat.up': '上行',
    'gui.stat.down': '下行',
    'gui.stat.uptime': '运行时长',

    # 运行状态
    'gui.status.stopped': '已停止',
    'gui.status.starting': '启动中',
    'gui.status.running': '运行中',
    'gui.status.stopping': '停止中',
    'gui.status.start_failed': '启动失败',
    'gui.status.installing_cert': '导入证书中',

    # endpoint 显示
    'gui.endpoint.need_port': '(请先填写端口)',
    'gui.endpoint.disabled': '(未启用监听)',

    # 校验错误里的字段名
    'gui.error.title': '配置有误',
    'gui.error.empty': '「%(label)s」不能为空',
    'gui.error.not_number': '「%(label)s」只能是数字, 当前值是: %(value)s',
    'gui.error.invalid_number': '「%(label)s」不是有效的数字: %(value)s',
    'gui.error.port_range': '「%(label)s」必须在 0~65535 之间, 当前值是: %(value)s',
    'gui.field.wss_port': 'wss 端口',
    'gui.field.ws_port': 'ws 端口',
    'gui.field.web_port': 'Web UI 端口',
    'gui.field.cert_days': '证书有效期',
    'gui.field.heartbeat': '心跳间隔',
    'gui.field.status_cache_ttl': '服务器列表缓存时间',
    'gui.field.connect_timeout': '连接超时',
    'gui.field.max_payload': '单帧上限',

    # GUI 自己写出的日志
    'gui.log.starting': '%(name)s v%(version)s 正在启动...',
    'gui.log.target': '转发目标: %(target)s',
    'gui.log.config_save_failed': '配置保存失败: %(error)s',
    'gui.log.start_failed': '启动失败: %(error)s',
    'gui.log.listening': 'wss 监听地址: %(url)s',
    'gui.log.fallback_listener': '备用明文监听: %(url)s (页面本身是 http:// 时也可以用)',
    'gui.log.cert_fingerprint': '证书指纹 SHA-256: %(thumbprint)s',
    'gui.log.cert_trust_hint': '如浏览器提示证书不受信任, 请点【安装到系统信任库】后重启浏览器。',
    'gui.log.copied': '已复制到剪贴板: %(text)s',
    'gui.log.config_saved': '配置已保存: %(path)s',
    'gui.log.certutil': 'certutil 输出: %(output)s',

    # 对话框
    'gui.dialog.switch_failed': '切换语言失败',
    'gui.dialog.need_stop.title': '请先停止服务',
    'gui.dialog.need_stop.text': '重新生成证书需要先停止服务。',
    'gui.dialog.regen.title': '重新生成证书',
    'gui.dialog.regen.confirm': '将删除现有证书并重新签发一张, 需要继续吗?',
    'gui.dialog.delete_failed': '删除失败',
    'gui.dialog.generate_failed': '生成失败',
    'gui.dialog.regen.done_title': '完成',
    'gui.dialog.regen.done': '证书已重新生成。',
    'gui.dialog.regen.done_deleted': '证书已重新生成。已删除旧证书。',
    'gui.dialog.cert_missing.title': '尚未生成证书',
    'gui.dialog.cert_missing.ask': '还没有证书文件, 是否现在生成并导入?',
    'gui.dialog.install_ok.title': '导入成功',
    'gui.dialog.install_ok.text':
        '证书已加入当前用户的"受信任的根证书颁发机构"。\n\n'
        '请重启浏览器(Chrome / Edge 立即生效, Firefox 需要在\n'
        '设置 → 隐私与安全 → 证书 → 查看证书 中再单独导入一次)。',
    'gui.dialog.install_failed': '导入失败',
    'gui.dialog.unknown_error': '未知错误',
    'gui.dialog.no_endpoint.title': '没有可用地址',
    'gui.dialog.no_endpoint.text': '请先设置 wss 端口',
    'gui.dialog.not_running.title': '未运行',
    'gui.dialog.not_running.text': '请先启动服务。',
    'gui.dialog.save_failed': '保存失败',
    'gui.dialog.reset.title': '恢复默认配置',
    'gui.dialog.reset.ask': '将把界面上的设置恢复为默认值(不覆盖已保存的配置文件), 继续吗?',
    'gui.dialog.open_failed': '打开失败',

    # 帮助 / 关于
    'gui.help.title': '使用说明',
    'gui.help.text': """使用步骤

1. 在"转发目标"里填入你要玩的 Java 服务器地址。没有默认服务器。
   只写域名即可, 程序会按 SRV 记录找到真正的服务器节点; 也可以写域名:端口。
2. 点击【启动服务】, 界面下方状态变为"运行中"。
3. 首次使用请打开【设置...】→ 证书 → 【安装到系统信任库】, 把自签名证书
   加入 Windows 的"受信任的根证书颁发机构", 否则浏览器会提示 wss:// 证书不受信任。
   (Firefox 需要在 设置 → 隐私与安全 → 证书 → 查看证书 里单独导入一次。)
4. 在客户端的服务器地址栏填入:
   wss://127.0.0.1:8443
   然后连接即可。原版 Java 客户端按字节原样转发; WebSocket 客户端会经过
   其连接所需的握手与协议转换。

连不上时看"运行日志": 每条连接的握手信息(协议版本/客户端填写的地址)、
上下行字节数、断开原因都会打出来。

常见问题

Q: 打不开，打开就报错。
A: 安装 VC++ 运行时即可解决，或从源码运行。
   EXE 是用 PyInstaller 打包的，需要系统装有 VC++ 运行时。下载地址:
   https://aka.ms/vs/17/release/vc_redist.x64.exe

Q: 控制台输出 "[0x...] ANOMALY: meaningless REX prefix used"。
A: 请忽略，不影响软件功能。该提示由显卡驱动产生，并不是本程序的问题。
   如果在使用过程中反复输出，且您使用的是 Intel 核显 (iGPU)，请检查是否
   已安装最新的 Intel 显卡驱动。
""",
    # ---------- 云端版本检查 ----------
    'gui.update.title': '版本检查',
    'gui.update.window_subtitle': '版本信息与下载',
    'gui.update.label_current': '当前版本',
    'gui.update.label_latest': '最新版本',
    'gui.update.label_page': '下载页面',
    'gui.update.label_source': '源码',
    'gui.update.label_state': '状态',
    'gui.update.latest_unknown': '尚未检查',
    'gui.update.no_page': '未提供',
    'gui.update.no_source': '未提供',
    'gui.update.idle': '点击【检查更新】从服务器获取最新版本。',
    'gui.update.button_check': '检查更新',
    'gui.update.button_open': '打开下载页面',
    'gui.update.button_source': '下载源码',
    'gui.update.checking': '正在检查最新版本...',
    'gui.update.failed': '版本检查失败: %(error)s',
    'gui.update.up_to_date': '版本检查: 当前 %(version)s 已是最新版本',
    'gui.update.available': '有新版本可用: %(version)s (当前 %(current)s)',
    'gui.update.banner': '有新版本 %(version)s (当前 %(current)s)',
    'gui.update.banner_page': '—— 点击打开下载页面',
    'gui.update.label_date': '发布日期',
    'gui.update.label_size': '文件大小',
    'gui.update.label_notes': '更新日志',
    'gui.update.unknown_value': '未提供',
    'gui.update.no_notes': '本次发布没有提供更新日志。',
    'gui.update.must_update': '必须更新: 版本 %(version)s (当前 %(current)s)',
    'gui.update.force_hint': '发布者把此版本标记为必须更新，请下载并安装；当前版本已不再支持。',
    'gui.update.banner_force': '必须更新到 %(version)s (当前 %(current)s)',

    # ---------- 账号 ----------
    'gui.accounts.col.name': '账号',
    'gui.accounts.col.kind': '类型',
    'gui.accounts.col.uuid': 'UUID',
    'gui.accounts.col.state': '当前',
    'gui.accounts.button.add': '添加账号',
    'gui.accounts.add.offline': '离线账号',
    'gui.accounts.add.thirdparty': '第三方账号',
    'gui.accounts.add.microsoft': '微软账号',
    'gui.accounts.button.active': '设为当前',
    'gui.accounts.button.clear': '不使用账号',
    'gui.accounts.button.remove': '删除',
    'gui.accounts.button.open_dir': '打开文件夹',
    'gui.accounts.hint': '选中的账号用于登录目标服务器: 上行的名字和 UUID 用账号本身的, '
                         '第三方 / 微软账号还会代做会话加入(session join), '
                         '这样会校验登录会话的服务器才放浏览器客户端进来。'
                         '微软账号每次进入服务器前会自动刷新登录凭据; 刷新失败会断开连接, '
                         '原因显示在游戏聊天栏。选"不使用账号"则维持原行为: 用客户端自己请求的名字。',
    'gui.accounts.data_dir': '账号文件: %(path)s',
    'gui.accounts.need_selection': '请先在列表里选择一个账号。',
    'gui.accounts.selected': '已改用账号 %(name)s',
    'gui.accounts.cleared': '已取消账号, 客户端重新使用自己的名字',
    'gui.accounts.removed': '已删除账号 %(name)s',
    'gui.accounts.remove.title': '删除账号',
    'gui.accounts.remove.ask': '确定删除账号 %(name)s 吗?',
    'gui.accounts.offline.prompt': '角色名(字母/数字/下划线, 3-16 位)',
    'gui.accounts.offline.bad_name': '这个名字不能使用: 需要 3-16 位字母/数字/下划线',
    'gui.accounts.thirdparty.title': '添加第三方账号',
    'gui.accounts.thirdparty.server': '账号服务地址',
    'gui.accounts.thirdparty.username': '用户名/邮箱',
    'gui.accounts.thirdparty.password': '密码',
    'gui.accounts.thirdparty.note': '填第三方账号服务提供的 API 根地址。',
    'gui.accounts.thirdparty.submit': '登录并添加',
    'gui.accounts.thirdparty.busy': '正在登录...',
    'gui.accounts.thirdparty.added': '已添加第三方账号 %(name)s',
    'gui.accounts.thirdparty.missing': '请把地址、用户名和密码都填上。',
    'gui.accounts.ms.title': '添加微软账号',
    'gui.accounts.ms.intro': '浏览器会打开 microsoft.com/link, 请在页面里输入下面的代码并登录微软账号; '
                             '浏览器没弹出来的话, 点下面的按钮。登录完成后本窗口会自动继续。',
    'gui.accounts.ms.code_label': '代码:',
    'gui.accounts.ms.starting': '正在向微软申请登录代码...',
    'gui.accounts.ms.waiting': '正在等待浏览器中完成登录...',
    'gui.accounts.ms.copy_code': '复制代码',
    'gui.accounts.ms.code_copied': '登录代码已复制到剪贴板',
    'gui.accounts.ms.copy': '复制链接',
    'gui.accounts.ms.open': '在浏览器中打开',
    'gui.accounts.ms.copied': '登录链接已复制到剪贴板',
    'gui.accounts.ms.open_failed': '无法自动打开浏览器; 请点「复制链接」, 把地址粘贴到浏览器里打开',
    'gui.accounts.ms.added': '已添加微软账号 %(name)s',
    'gui.accounts.ms.ssl_title': '证书验证失败',
    'gui.accounts.ms.ssl_ask': '无法验证与微软的安全连接:\n\n%(detail)s\n\n'
                               '如果要忽略 SSL 证书错误并继续, 请点「是」; '
                               '如果不忽略, 请点「否」。\n\n'
                               '忽略后, 这条连接上的数据可能被网络中的其他人读取。',
    'gui.accounts.ms.renewing': '微软没有接受这个登录代码, 正在重新获取...',
    'gui.accounts.ms.retrying_ssl': '已跳过证书检查, 正在重新获取登录代码...',
    'gui.accounts.legal': '如添加离线账号或第三方账号, 代表您已确认您拥有我的世界微软账号。',

    'gui.about.title': '关于',
    'gui.about.subtitle': '关于此版本',
    'gui.about.blurb': '面向 Minecraft 客户端的本地 wss:// 或 ws:// 中继。'
                       '游戏流量直接走 websockets 传输层, 不再经过 ASGI 网关。'
                       '此构建包含以下开源组件。',
    'gui.about.project_license': '项目许可证: Unlicense (公有领域)。'
                                 '完整文本见源码包内的 LICENSE; '
                                 'https://unlicense.org/',
    'gui.about.components': '第三方组件',
    'gui.about.stdlib': 'Python 标准库模块',
    'gui.about.column_component': '组件',
    'gui.about.column_license': '许可证',
    'gui.about.column_project': '项目地址',
    'gui.about.hint': '点击任意一行打开官网或 GitHub 仓库。',
    'gui.about.close': '关闭',
    'gui.about.text': """%(name)s v%(version)s

把普通 Minecraft 服务器(例如 Hypixel)转换为本地 wss:// 或 ws:// 端点,
让 WebSocket 客户端可以连接 —— 浏览器只允许建立 wss:// 连接。

原版 Java 客户端按字节原样转发; WebSocket 客户端会经过其连接所需的
握手与协议转换。
工作目录: %(workdir)s""",
    # ---------- CustomTkinter 外壳 / Web UI 入口 ----------
    'gui.nav.control': '控制',
    'gui.nav.settings': '设置',
    'gui.nav.accounts': '账号',
    'gui.nav.cert': '证书',
    'gui.nav.log': '日志',
    'gui.nav.about': '关于',
    'gui.page.control.subtitle': '启动中继、查看会话状态，并把连接地址交给客户端。',
    'gui.page.settings.subtitle': '配置文件里的全部选项，按用途分组。',
    'gui.page.accounts.subtitle': '浏览器客户端进入服务器时使用的登录身份。',
    'gui.page.cert.subtitle': '浏览器客户端需要信任的 TLS 证书。',
    'gui.page.log.subtitle': '代理、窗口和 Web UI 的全部输出。',
    'gui.page.about.subtitle': '版本、许可证以及本次构建包含的组件。',
    'gui.section.connection': '连接',
    'gui.section.actions': '服务',
    'gui.section.status': '会话',
    'gui.section.forwarding': '转发与身份',
    'gui.section.protocol': '协议转换',
    'gui.section.runtime': '运行时',
    'gui.section.certificate': '证书',
    'gui.section.web': 'Web UI',
    'gui.label.web_host': '绑定地址',
    'gui.label.web_port': '绑定端口',
    'gui.hint.web_bind': '0.0.0.0 表示允许局域网访问；端口填 0 表示由系统自动选择空闲端口。',
    'gui.label.web_password': '启用访问密码',
    'gui.hint.web_password': '默认关闭。只对 Web UI 生效，桌面窗口不需要密码。',
    'gui.label.web_password_new': '新密码',
    'gui.label.web_password_confirm': '确认密码',
    'gui.hint.web_password_keep': '两个密码框都留空表示保持当前密码不变。',
    'gui.error.password_mismatch': '两次输入的密码不一致。',
    'gui.error.password_required': '启用访问控制前请先设置密码。',
    'gui.error.password_short': '密码至少需要 4 个字符。',
    'gui.log.web_password_on': '已启用 Web UI 访问密码。',
    'gui.log.web_password_off': '已关闭 Web UI 访问密码。',
    'gui.button.web_restart': '重启 Web UI',
    'gui.label.server_brand': '服务器品牌',
    'gui.label.server_brand_version': '服务器版本',
    'gui.label.spoof_brand': '伪造的客户端品牌',
    'gui.label.routes': '路径路由',
    'gui.hint.routes': '每行一个 path=目标，例如 /lobby=play.example.net:25565',
    'gui.hint.spoof_brand': '留空使用预设默认值；必须为 ASCII 字符。',
    'gui.hint.endpoint': '把这个地址填入浏览器客户端。',
    'gui.button.open_web': '打开 Web UI',
    'gui.web.title': 'Web UI',
    'gui.web.hint': 'Web UI 在浏览器里提供同样的操作（启动、停止、配置、监控）。',
    'gui.web.running': 'Web UI 正在运行: %(url)s',
    'gui.web.failed': 'Web UI 启动失败: %(error)s',
    'gui.log.web_started': 'Web UI 已启动: %(url)s',
    'gui.accounts.none': '还没有账号，请在上方添加。',
    'gui.accounts.added_offline': '已添加离线账号: %(name)s',
    'runtime.busy': '服务正在启动、运行或停止中。',
}
