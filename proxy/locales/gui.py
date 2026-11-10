"""Locale table for the gui namespace.

Split into themed fragments (gui_accounts, gui_about, gui_update, gui_dialog, gui_log, gui_controls); this module merges them so the rest of the program still does ``from proxy.locales import gui``.
"""

from . import gui_accounts, gui_about, gui_update, gui_dialog, gui_log, gui_controls


EN = {
    'gui.language': 'Language',
    'gui.language.auto': 'Auto',
    'gui.language.en': 'English',
    'gui.language.zh': 'Chinese (simplified)',
    'gui.cert_generator.auto': 'Automatic',
    'gui.cert_generator.python': 'Python (built-in)',
    'gui.cert_generator.openssl': 'OpenSSL',
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
    'gui.label.listen_host': 'Listen Address',
    'gui.label.wss_port': 'wss port',
    'gui.label.ws_port': 'ws port (0 = off)',
    'gui.label.target': 'Forward Target',
    'gui.label.use_srv': 'Resolve via SRV when no port is given',
    'gui.label.auto_exit': 'Auto exit (let connected clients leave the server '
                           'cleanly before stopping)',
    'gui.label.cert_dir': 'Certificate Directory',
    'gui.label.cert_cn': 'Name (CN)',
    'gui.label.cert_days': 'Valid for (days)',
    'gui.label.cert_extra': 'Extra Names',
    'gui.label.cert_generator': 'Generator',
    'gui.label.cert_fill': 'Enter this address in your client:',
    'gui.label.update_check': 'Check for a newer release on startup',
    'gui.cert.info_missing': 'No certificate yet -- a self-signed one is issued automatically '
                             'when the service starts',
    'gui.cert.info': 'File: %(file)s\nSHA-256 fingerprint: %(thumbprint)s\nCovers: %(names)s',
    'gui.cert.hint': 'Generate the certificate, install it into the system trust store, then '
                     'restart the browser. Clients can also open the certificate address and '
                     'trust it manually.',
    'gui.label.log_level': 'Log Level',
    'gui.label.log_max_lines': 'Log Buffer',
    'gui.hint.log_max_lines': 'How many recent lines are kept. Older lines scroll off, so a long '
                              'session cannot use unbounded memory. Raise it to look further back.',
    'gui.label.heartbeat': 'Heartbeat (s, 0 = off)',
    'gui.label.status_cache': 'Cache server-list status',
    'gui.label.status_cache_ttl': 'Cache lifetime (s)',
    'gui.label.status_cache_hint': 'Off: every list query waits for the target. On: cached results return '
                                   'immediately and refresh in the background.',
    'gui.label.connect_timeout': 'Connect Timeout (s)',
    'gui.label.max_payload': 'Max Frame Size (MB)',
    'gui.label.spoof_client': 'Client identity and brand spoofing',
    'gui.spoof.off': 'Off (no spoofing)',
    'gui.spoof.vanilla': 'Vanilla',
    'gui.spoof.forge-1.8': 'Forge 1.8.x - 1.12.2',
    'gui.spoof.forge-1.13': 'Forge 1.13+',
    'gui.spoof.neoforge': 'NeoForge 1.20.2+',
    'gui.spoof.fabric': 'Fabric',
    'gui.spoof.custom': 'Custom',
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
    'gui.status.stopped': 'Stopped',
    'gui.status.starting': 'Starting',
    'gui.status.running': 'Running',
    'gui.status.stopping': 'Stopping',
    'gui.status.start_failed': 'Start Failed',
    'gui.status.installing_cert': 'Installing Certificate',
    'gui.endpoint.need_port': '(enter a port first)',
    'gui.endpoint.disabled': '(no listener enabled)',
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
    'gui.label.web_host': 'Bind address',
    'gui.label.web_port': 'Bind port',
    'gui.hint.web_bind': '0.0.0.0 exposes the page on the LAN; 0 lets the system pick a free port.',
    'gui.label.web_password': 'Require access password',
    'gui.hint.web_password': 'Off by default. Applies to the Web UI only; saving settings never clears it.',
    'gui.label.web_password_new': 'New password',
    'gui.label.web_password_confirm': 'Confirm password',
    'gui.hint.web_password_keep': 'At least 4 characters. Leave both password fields blank to keep the current password.',
    'gui.status.web_password_on': 'Password: enabled',
    'gui.status.web_password_stored': 'Password: stored, not enabled',
    'gui.status.web_password_off': 'Password: not set',
    'gui.label.server_brand': 'Server brand',
    'gui.hint.server_brand': 'Brand shown to browser clients; keep the default unless you need another value.',
    'gui.label.server_brand_version': 'Server version',
    'gui.hint.server_brand_version': 'Optional version string sent with the brand; empty reports the program version.',
    'gui.label.spoof_brand': 'Custom client brand',
    'gui.hint.spoof_brand': 'Sent to the target server as the client brand. ASCII only. A trailing parenthesised suffix such as "(u1-beta)" is dropped on save.',
    'gui.label.suffix_route': 'Suffix routing',
    'gui.hint.suffix_route': 'The request path itself names the target server: /mc244.com -> mc244.com (SRV / default port), /hypixel.net -> hypixel.net, /127.0.0.1:25565 -> 127.0.0.1:25565. "/" uses the default target. Cannot be enabled together with the path routes below. Anyone who can reach the listener would be able to connect anywhere through the relay -- enable it only on a trusted network.',
    'gui.hint.suffix_route_disabled': 'Clear the path routes first to enable suffix routing',
    'gui.label.routes': 'Path routes',
    'gui.hint.routes': 'Connections to a listed path are sent to the server on the right; everything else uses the address above. A row is only used when both halves are filled in.',
    'gui.hint.routes_empty': 'No routes: every connection goes to the server address above.',
    'gui.hint.endpoint': 'Paste this address into the browser client.',
    'gui.web.title': 'Web UI',
    'gui.web.hint': 'The Web UI offers the same controls in a browser (start, stop, configure, monitor).',
    'gui.web.running': 'Web UI running at %(url)s',
    'gui.web.failed': 'The Web UI could not start: %(error)s',
}

ZH = {
    'gui.language': '界面语言',
    'gui.language.auto': '自动',
    'gui.language.en': '英语',
    'gui.language.zh': '简体中文',
    'gui.cert_generator.auto': '自动',
    'gui.cert_generator.python': 'Python（内置）',
    'gui.cert_generator.openssl': 'OpenSSL',
    'gui.settings.title': '设置',
    'gui.settings.tab.connection': '连接',
    'gui.settings.tab.accounts': '账号',
    'gui.settings.tab.cert': '证书',
    'gui.settings.tab.update': '更新',
    'gui.settings.apply': '应用并保存',
    'gui.settings.close': '关闭',
    'gui.settings.check_now': '立即检查',
    'gui.settings.update_hint': '版本检查地址由程序内置, 不可修改。',
    'gui.label.listen_host': '监听地址',
    'gui.label.wss_port': 'wss 端口',
    'gui.label.ws_port': 'ws 端口(0=关闭)',
    'gui.label.target': '转发目标',
    'gui.label.use_srv': '不带端口时按 SRV 解析',
    'gui.label.auto_exit': '自动退出(停止/关闭前让客户端正常退出服务器)',
    'gui.label.cert_dir': '证书目录',
    'gui.label.cert_cn': '名称(CN)',
    'gui.label.cert_days': '有效期(天)',
    'gui.label.cert_extra': '额外名称',
    'gui.label.cert_generator': '生成器',
    'gui.label.cert_fill': '在客户端中填写:',
    'gui.label.update_check': '启动时检查新版本',
    'gui.cert.info_missing': '尚未生成证书 —— 启动服务时会自动签发一张自签名证书',
    'gui.cert.info': '文件: %(file)s\n指纹 SHA-256: %(thumbprint)s\n覆盖名称: %(names)s',
    'gui.cert.hint': '生成证书后安装到系统信任库，然后重启浏览器。客户端也可以直接打开证书地址并手动信任。',
    'gui.label.log_level': '日志级别',
    'gui.label.log_max_lines': '日志缓冲区',
    'gui.hint.log_max_lines': '保留最近多少行。更早的行会滚出缓冲区，所以长时间运行不会无限占内存；'
                              '调大可以回看更久以前发生的事。',
    'gui.label.heartbeat': '心跳(秒, 0=关闭)',
    'gui.label.status_cache': '缓存服务器列表状态',
    'gui.label.status_cache_ttl': '缓存时间(秒)',
    'gui.label.status_cache_hint': '关闭后每次列表查询都会等待目标服务器；开启后优先返回缓存，并在后台刷新。',
    'gui.label.connect_timeout': '连接超时(秒)',
    'gui.label.max_payload': '单帧上限(MB)',
    'gui.label.spoof_client': '客户端标识与品牌伪装',
    'gui.spoof.off': '关闭(不伪装)',
    'gui.spoof.vanilla': '原版',
    'gui.spoof.forge-1.8': 'Forge 1.8.x ~ 1.12.2',
    'gui.spoof.forge-1.13': 'Forge 1.13+',
    'gui.spoof.neoforge': 'NeoForge 1.20.2+',
    'gui.spoof.fabric': 'Fabric',
    'gui.spoof.custom': '自定义',
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
    'gui.status.stopped': '已停止',
    'gui.status.starting': '启动中',
    'gui.status.running': '运行中',
    'gui.status.stopping': '停止中',
    'gui.status.start_failed': '启动失败',
    'gui.status.installing_cert': '导入证书中',
    'gui.endpoint.need_port': '(请先填写端口)',
    'gui.endpoint.disabled': '(未启用监听)',
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
    'gui.label.web_host': '绑定地址',
    'gui.label.web_port': '绑定端口',
    'gui.hint.web_bind': '0.0.0.0 表示允许局域网访问；端口填 0 表示由系统自动选择空闲端口。',
    'gui.label.web_password': '启用访问密码',
    'gui.hint.web_password': '默认关闭，只对 Web UI 生效；保存配置不会清空已设置的密码。',
    'gui.label.web_password_new': '新密码',
    'gui.label.web_password_confirm': '确认密码',
    'gui.hint.web_password_keep': '至少 4 个字符；两个密码框都留空表示保持当前密码不变。',
    'gui.status.web_password_on': '访问密码：已启用',
    'gui.status.web_password_stored': '访问密码：已保存但未启用',
    'gui.status.web_password_off': '访问密码：未设置',
    'gui.label.server_brand': '服务器品牌',
    'gui.hint.server_brand': '浏览器客户端看到的服务器品牌；没有特殊需要就保持默认。',
    'gui.label.server_brand_version': '服务器版本',
    'gui.hint.server_brand_version': '可选的版本号字符串，随品牌一起发送；留空则显示程序版本。',
    'gui.label.spoof_brand': '自定义客户端品牌',
    'gui.hint.spoof_brand': '向目标服务器声明的客户端品牌。只能填 ASCII 字符。保存时会自动去掉 "(u1-beta)" 之类的括号后缀。',
    'gui.label.suffix_route': '路径后缀直连',
    'gui.hint.suffix_route': '连接路径本身就是目标服务器地址：/mc244.com -> mc244.com（按 SRV/默认端口），/hypixel.net -> hypixel.net，/127.0.0.1:25565 -> 127.0.0.1:25565。“/” 走默认目标。不能和下面的路径映射同时开启。任何能连上监听器的人都可以经此中继连到任意服务器——只在可信网络里开启。',
    'gui.hint.suffix_route_disabled': '先清空路径映射再启用后缀直连',
    'gui.label.routes': '路径路由',
    'gui.hint.routes': '填了路径的连接会转到右边填的服务器，其余地址走上面的默认服务器。路径和服务器都填了才算一条路由。',
    'gui.hint.routes_empty': '还没有路由：所有连接都发到上面的服务器。',
    'gui.hint.endpoint': '把这个地址填入浏览器客户端。',
    'gui.web.title': 'Web UI',
    'gui.web.hint': 'Web UI 在浏览器里提供同样的操作（启动、停止、配置、监控）。',
    'gui.web.running': 'Web UI 正在运行: %(url)s',
    'gui.web.failed': 'Web UI 启动失败: %(error)s',
}

for _sub in (gui_accounts, gui_about, gui_update, gui_dialog, gui_log, gui_controls,):
    EN.update(_sub.EN)
    ZH.update(_sub.ZH)
