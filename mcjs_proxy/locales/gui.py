"""Translations for the GUI (``gui.py``).

Owner: ``gui.py`` (keys prefixed ``gui.*``).
"""

from __future__ import annotations

EN = {
    'gui.language': 'Language',

    # Window menu
    'gui.menu.file': 'File',
    'gui.menu.tools': 'Tools',
    'gui.menu.help': 'Help',
    'gui.menu.save_config': 'Save Config',
    'gui.menu.open_workdir': 'Open Working Directory',
    'gui.menu.quit': 'Exit',
    'gui.menu.copy_endpoint': 'Copy wss Address',
    'gui.menu.status_page': 'Open Status Page',
    'gui.menu.install_cert': 'Install Certificate into Trust Store',

    # Log panel
    'gui.log_frame': 'Runtime Log',
    'gui.log.clear': 'Clear Log',
    'gui.log.auto_scroll': 'Auto-scroll',
    'gui.log.hint': 'Tip: double-click the log to copy everything',

    # Group boxes
    'gui.group.basic': 'Basic Settings',
    'gui.group.cert': 'Certificate (needed for wss://, created automatically on first run)',
    'gui.group.advanced': 'Advanced',

    # Basic settings
    'gui.label.listen_host': 'Listen Address',
    'gui.label.wss_port': 'wss port',
    'gui.label.ws_port': 'ws port (0 = off)',
    'gui.label.target': 'Forward Target',
    'gui.label.use_srv': 'Resolve via SRV when no port is given',
    'gui.label.routes': 'Path Routes',
    'gui.label.routes_hint': 'One per line, path=target, e.g. /mc244=mc244.com',

    # Certificate
    'gui.label.cert_dir': 'Certificate Directory',
    'gui.label.cert_cn': 'Name (CN)',
    'gui.label.cert_days': 'Valid for (days)',
    'gui.label.cert_extra': 'Extra Names',
    'gui.label.cert_generator': 'Generator',
    'gui.label.cert_fill': 'Enter in MCJS:',
    'gui.button.regen_cert': 'Regenerate Certificate',
    'gui.button.install_cert': 'Install into Trust Store',
    'gui.button.open_cert_dir': 'Open Certificate Directory',
    'gui.cert.info_missing': 'No certificate yet -- a self-signed one is issued automatically '
                             'when the service starts',
    'gui.cert.info': 'File: %(file)s\nSHA-256 fingerprint: %(thumbprint)s\nCovers: %(names)s',

    # Advanced
    'gui.label.log_level': 'Log Level',
    'gui.label.heartbeat': 'Heartbeat (s, 0 = off)',
    'gui.label.connect_timeout': 'Connect Timeout (s)',
    'gui.label.max_payload': 'Max Frame Size (MB)',
    'gui.label.rewrite_host': 'Rewrite the handshake address to the target domain '
                              '(tick when the server validates or routes by address)',
    'gui.label.eagler_translate': 'Browser client protocol translation '
                                  '(required for EaglercraftX / MCJS clients)',

    # Action buttons
    'gui.button.start': 'Start Service',
    'gui.button.stop': 'Stop Service',
    'gui.button.copy_endpoint': 'Copy wss Address',
    'gui.button.save_config': 'Save Config',
    'gui.button.reset_defaults': 'Restore Defaults',
    'gui.button.status_page': 'Open Status Page',

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
    'gui.field.cert_days': 'Certificate validity',
    'gui.field.heartbeat': 'Heartbeat interval',
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
    'gui.dialog.not_running.text': 'Start the service before opening the status page.',
    'gui.dialog.save_failed': 'Save Failed',
    'gui.dialog.reset.title': 'Restore Defaults',
    'gui.dialog.reset.ask': 'The settings in the window will be reset to their defaults '
                            '(the saved configuration file is not overwritten). Continue?',
    'gui.dialog.open_failed': 'Open Failed',

    # Help / about
    'gui.help.title': 'User Guide',
    'gui.help.text': """Steps

1. Check the "Forward Target" (mc244.com by default). A bare domain is
   enough -- the program finds the real server node through its SRV record.
   To use another server, enter its domain or domain:port.
2. Click [Start Service]; the status at the bottom switches to "Running".
3. On first use click [Install into Trust Store] to add the self-signed
   certificate to Windows' "Trusted Root Certification Authorities";
   otherwise the browser warns that the wss:// certificate is untrusted.
   (Firefox needs a separate import under Settings -> Privacy & Security
   -> Certificates -> View Certificates.)
4. Enter the following in the MCJS client's server address field:
   wss://127.0.0.1:8443
   then connect. The program turns WebSocket frames back into the original
   Minecraft protocol byte stream and forwards it to the target server,
   byte for byte identical to a vanilla client connecting directly.

When a connection fails, check the "Runtime Log": every connection logs its
handshake details (protocol version / the address the client sent), the
up/down byte counts and the reason it closed.
""",
    'gui.about.title': 'About',
    'gui.about.text': """%(name)s v%(version)s

Turns a plain Minecraft server (Hypixel, for example) into a local
wss:// endpoint so browser clients such as MCJS can connect -- browsers
only allow wss:// connections.

Forwarding neither parses nor modifies any game data; the byte stream is
identical to a vanilla client connecting directly.
Working directory: %(workdir)s""",
}

ZH = {
    'gui.language': '界面语言',

    # 窗口菜单
    'gui.menu.file': '文件',
    'gui.menu.tools': '工具',
    'gui.menu.help': '帮助',
    'gui.menu.save_config': '保存配置',
    'gui.menu.open_workdir': '打开工作目录',
    'gui.menu.quit': '退出',
    'gui.menu.copy_endpoint': '复制 wss 地址',
    'gui.menu.status_page': '打开状态页',
    'gui.menu.install_cert': '安装证书到系统信任库',

    # 日志面板
    'gui.log_frame': '运行日志',
    'gui.log.clear': '清空日志',
    'gui.log.auto_scroll': '自动滚动',
    'gui.log.hint': '提示: 双击日志可复制全部内容',

    # 分组框
    'gui.group.basic': '基本设置',
    'gui.group.cert': '证书(wss:// 需要, 首次运行自动生成)',
    'gui.group.advanced': '高级',

    # 基本设置
    'gui.label.listen_host': '监听地址',
    'gui.label.wss_port': 'wss 端口',
    'gui.label.ws_port': 'ws 端口(0=关闭)',
    'gui.label.target': '转发目标',
    'gui.label.use_srv': '不带端口时按 SRV 解析',
    'gui.label.routes': '路径映射',
    'gui.label.routes_hint': '每行一条, 格式: 路径=目标, 例如 /mc244=mc244.com',

    # 证书
    'gui.label.cert_dir': '证书目录',
    'gui.label.cert_cn': '名称(CN)',
    'gui.label.cert_days': '有效期(天)',
    'gui.label.cert_extra': '额外名称',
    'gui.label.cert_generator': '生成器',
    'gui.label.cert_fill': '在 MCJS 中填写:',
    'gui.button.regen_cert': '重新生成证书',
    'gui.button.install_cert': '安装到系统信任库',
    'gui.button.open_cert_dir': '打开证书目录',
    'gui.cert.info_missing': '尚未生成证书 —— 启动服务时会自动签发一张自签名证书',
    'gui.cert.info': '文件: %(file)s\n指纹 SHA-256: %(thumbprint)s\n覆盖名称: %(names)s',

    # 高级
    'gui.label.log_level': '日志级别',
    'gui.label.heartbeat': '心跳(秒, 0=关闭)',
    'gui.label.connect_timeout': '连接超时(秒)',
    'gui.label.max_payload': '单帧上限(MB)',
    'gui.label.rewrite_host': '按目标域名改写握手地址(服务器按地址校验/分流时勾选)',
    'gui.label.eagler_translate': '浏览器客户端协议翻译(EaglercraftX/MCJS 系客户端必需)',

    # 操作按钮
    'gui.button.start': '启动服务',
    'gui.button.stop': '停止服务',
    'gui.button.copy_endpoint': '复制 wss 地址',
    'gui.button.save_config': '保存配置',
    'gui.button.reset_defaults': '恢复默认配置',
    'gui.button.status_page': '打开状态页',

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
    'gui.field.cert_days': '证书有效期',
    'gui.field.heartbeat': '心跳间隔',
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
    'gui.dialog.not_running.text': '请先启动服务, 再打开状态页。',
    'gui.dialog.save_failed': '保存失败',
    'gui.dialog.reset.title': '恢复默认配置',
    'gui.dialog.reset.ask': '将把界面上的设置恢复为默认值(不覆盖已保存的配置文件), 继续吗?',
    'gui.dialog.open_failed': '打开失败',

    # 帮助 / 关于
    'gui.help.title': '使用说明',
    'gui.help.text': """使用步骤

1. 确认"转发目标", 默认 mc244.com (只写域名即可, 程序会按 SRV 记录找到真正的服务器节点)。
   想连别的服务器就改成它的域名或 域名:端口。
2. 点击【启动服务】, 界面下方状态变为"运行中"。
3. 首次使用请点击【安装到系统信任库】, 把自签名证书加入 Windows 的
   "受信任的根证书颁发机构", 否则浏览器会提示 wss:// 证书不受信任。
   (Firefox 需要在 设置 → 隐私与安全 → 证书 → 查看证书 里单独导入一次。)
4. 在 MCJS 客户端的服务器地址栏填入:
   wss://127.0.0.1:8443
   然后连接即可。程序会把 WebSocket 帧原样还原成 Minecraft 协议字节流,
   转发到目标服务器, 数据与原版客户端直连完全一致。

连不上时看"运行日志": 每条连接的握手信息(协议版本/客户端填写的地址)、
上下行字节数、断开原因都会打出来。
""",
    'gui.about.title': '关于',
    'gui.about.text': """%(name)s v%(version)s

把普通 Minecraft 服务器(例如 Hypixel)转换为本地 wss:// 端点,
让 MCJS 等浏览器端客户端可以连接 —— 浏览器只允许建立 wss:// 连接。

转发过程不解析、不修改任何游戏数据, 字节流与原版客户端直连一致。
工作目录: %(workdir)s""",
}
