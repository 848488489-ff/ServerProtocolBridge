"""tkinter 图形界面。

界面只负责配置与展示; 转发本身跑在 ProxyServer 的后台线程里,
日志通过队列回到主线程刷新, 因此界面不会卡住。
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from pathlib import Path
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from . import certs
from . import config as config_module
from .logger import Logger
from .proxy import ProxyServer
from .utils import app_dir, human_bytes, human_duration, resolve_path
from .version import APP_NAME, VERSION

LOG_COLORS = {
    'debug': '#6a6a6a',
    'info': '#1c1c1c',
    'warn': '#b06000',
    'error': '#c02b2b',
}

HELP_TEXT = """使用步骤

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
"""


def _pick_font_family(root: tk.Misc) -> str:
    preferred = ('Microsoft YaHei UI', 'Microsoft YaHei', '微软雅黑', 'Segoe UI', 'SimHei')
    try:
        available = set(tkfont.families(root))
    except Exception:
        return preferred[0]
    for family in preferred:
        if family in available:
            return family
    return preferred[0]


def _apply_font(root: tk.Misc) -> None:
    family = _pick_font_family(root)
    for name in ('TkDefaultFont', 'TkTextFont', 'TkMenuFont', 'TkHeadingFont', 'TkCaptionFont'):
        try:
            tkfont.nametofont(name, root=root).configure(family=family, size=9)
        except Exception:
            pass


class NumericEntry(ttk.Entry):
    """只接受数字的输入框。

    在按键/粘贴阶段就拒绝非数字字符(中文、字母、空格、全角数字都打不进去),
    避免出现"端口号填成中文"这类情况。allow_decimal=True 时允许一个英文小数点。
    """

    def __init__(self, master=None, textvariable=None, *, max_length: int | None = None,
                 allow_decimal: bool = False, **kwargs):
        super().__init__(master, textvariable=textvariable, **kwargs)
        self._max_length = max_length
        self._allow_decimal = allow_decimal
        self._validation = (self.register(self._is_allowed), '%P')
        self.configure(validate='all', validatecommand=self._validation)

    def _is_allowed(self, proposed: str) -> bool:
        if proposed == '':
            return True                      # 允许清空后重新输入
        if not proposed.isascii():
            return False                     # 全角数字、中文等一律拒绝
        text = proposed[1:] if proposed.startswith('-') else proposed
        if self._allow_decimal and text.count('.') <= 1:
            head, _, tail = text.partition('.')
            if not (head == '' or head.isdigit()) or not (tail == '' or tail.isdigit()):
                return False
        elif not text.isdigit():
            return False
        if self._max_length is not None and len(text) > self._max_length:
            return False
        return True

    def set_value(self, text: str) -> None:
        """程序化赋值: 期间关闭校验, 免得历史配置里的脏值触发 Tk 校验告警。"""
        self.configure(validate='none')
        try:
            self.delete('0', 'end')
            self.insert('0', text)
        finally:
            self.configure(validatecommand=self._validation)
            self.configure(validate='all')


class BridgeApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('%s  v%s' % (APP_NAME, VERSION))
        self.geometry('960x720')
        self.minsize(900, 660)
        _apply_font(self)

        self.log_queue: 'queue.Queue[tuple[str, str]]' = queue.Queue()
        self.logger: Logger | None = None
        self.server: ProxyServer | None = None
        self.config = config_module.Config.load()
        self._closing = False

        self._build_variables()
        self._build_menu()
        self._build_ui()
        self._load_form()
        for variable in (self.var_listen_host, self.var_wss_port, self.var_ws_port, self.var_target):
            variable.trace_add('write', self._refresh_target_hint)
        self._refresh_target_hint()
        self._update_cert_label()
        self.protocol('WM_DELETE_WINDOW', self._on_close)
        self.after(120, self._poll)

    # ---------- 变量 ----------
    def _build_variables(self) -> None:
        self.var_listen_host = tk.StringVar()
        self.var_wss_port = tk.StringVar()
        self.var_ws_port = tk.StringVar()
        self.var_target = tk.StringVar()
        self.var_use_srv = tk.BooleanVar()
        self.var_rewrite_host = tk.BooleanVar()
        self.var_eagler_translate = tk.BooleanVar(value=True)
        self.var_routes = tk.StringVar()
        self.var_cert_dir = tk.StringVar()
        self.var_cert_common_name = tk.StringVar()
        self.var_cert_extra = tk.StringVar()
        self.var_cert_days = tk.StringVar()
        self.var_cert_generator = tk.StringVar()
        self.var_log_level = tk.StringVar()
        self.var_heartbeat = tk.StringVar()
        self.var_connect_timeout = tk.StringVar()
        self.var_max_payload = tk.StringVar()
        self.var_status = tk.StringVar(value='已停止')
        self.var_endpoint = tk.StringVar(value='')
        self.var_cert_info = tk.StringVar(value='')
        self.var_stat_active = tk.StringVar(value='0')
        self.var_stat_total = tk.StringVar(value='0')
        self.var_stat_up = tk.StringVar(value='0 B')
        self.var_stat_down = tk.StringVar(value='0 B')
        self.var_stat_uptime = tk.StringVar(value='0:00')
        self.var_auto_scroll = tk.BooleanVar(value=True)

    # ---------- 菜单 ----------
    def _build_menu(self) -> None:
        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=0)
        file_menu.add_command(label='保存配置', command=self._save_config)
        file_menu.add_command(label='打开工作目录', command=self._open_workdir)
        file_menu.add_separator()
        file_menu.add_command(label='退出', command=self._on_close)
        menu.add_cascade(label='文件', menu=file_menu)

        tool_menu = tk.Menu(menu, tearoff=0)
        tool_menu.add_command(label='复制 wss 地址', command=self._copy_endpoint)
        tool_menu.add_command(label='打开状态页', command=self._open_status_page)
        tool_menu.add_command(label='安装证书到系统信任库', command=self._install_certificate)
        menu.add_cascade(label='工具', menu=tool_menu)

        help_menu = tk.Menu(menu, tearoff=0)
        help_menu.add_command(label='使用说明', command=self._show_help)
        help_menu.add_command(label='关于', command=self._show_about)
        menu.add_cascade(label='帮助', menu=help_menu)
        # 注意: self.config 是配置对象, 会遮蔽 Tk.config() 方法, 这里显式调用基类实现
        tk.Misc.config(self, menu=menu)

    # ---------- 界面 ----------
    def _build_ui(self) -> None:
        outer = ttk.Frame(self, padding=(10, 8, 10, 6))
        outer.pack(fill='both', expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(5, weight=1)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky='ew')
        header.columnconfigure(1, weight=1)
        ttk.Label(header, text=APP_NAME, font=(None, 14, 'bold')).grid(row=0, column=0, sticky='w')
        ttk.Label(header, text='把普通 Minecraft 服务器转换为本地 wss:// 端点, 供 MCJS 等浏览器端客户端连接',
                  foreground='#555555').grid(row=0, column=1, sticky='w', padx=(12, 0))
        self.lbl_status = ttk.Label(header, textvariable=self.var_status, width=12, anchor='center',
                                    foreground='#c02b2b')
        self.lbl_status.grid(row=0, column=2, sticky='e')

        self._build_basic(outer)
        self._build_cert(outer)
        self._build_advanced(outer)
        self._build_actions(outer)

        # 日志区
        log_frame = ttk.LabelFrame(outer, text='运行日志', padding=(8, 6))
        log_frame.grid(row=5, column=0, sticky='nsew', pady=(8, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = ScrolledText(log_frame, height=12, wrap='none', state='disabled',
                                     font=('Consolas', 9))
        self.log_text.grid(row=0, column=0, sticky='nsew')
        for level, color in LOG_COLORS.items():
            self.log_text.tag_configure(level, foreground=color)
        self.log_text.tag_configure('time', foreground='#8a8a8a')

        tools = ttk.Frame(log_frame)
        tools.grid(row=1, column=0, sticky='ew', pady=(6, 0))
        ttk.Button(tools, text='清空日志', command=self._clear_log).pack(side='left')
        ttk.Checkbutton(tools, text='自动滚动', variable=self.var_auto_scroll).pack(side='left', padx=(8, 0))
        ttk.Label(tools, text='提示: 双击日志可复制全部内容',
                  foreground='#777777').pack(side='right')

        self._build_status_bar(outer)

    def _build_basic(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text='基本设置', padding=(8, 6))
        frame.grid(row=1, column=0, sticky='ew', pady=(10, 0))
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(3, weight=1)

        ttk.Label(frame, text='监听地址').grid(row=0, column=0, sticky='w', padx=(0, 6), pady=3)
        ttk.Entry(frame, textvariable=self.var_listen_host, width=18).grid(row=0, column=1, sticky='ew', pady=3)
        ttk.Label(frame, text='wss 端口').grid(row=0, column=2, sticky='e', padx=(12, 6))
        self.entry_wss_port = NumericEntry(frame, textvariable=self.var_wss_port, width=8,
                                           max_length=5)
        self.entry_wss_port.grid(row=0, column=3, sticky='w')
        ttk.Label(frame, text='ws 端口(0=关闭)').grid(row=0, column=4, sticky='e', padx=(12, 6))
        self.entry_ws_port = NumericEntry(frame, textvariable=self.var_ws_port, width=8,
                                          max_length=5)
        self.entry_ws_port.grid(row=0, column=5, sticky='w')

        ttk.Label(frame, text='转发目标').grid(row=1, column=0, sticky='w', padx=(0, 6), pady=3)
        ttk.Entry(frame, textvariable=self.var_target).grid(row=1, column=1, columnspan=3, sticky='ew')
        ttk.Checkbutton(frame, text='不带端口时按 SRV 解析', variable=self.var_use_srv).grid(
            row=1, column=4, columnspan=2, sticky='e', padx=(8, 0))

        ttk.Label(frame, text='路径映射').grid(row=2, column=0, sticky='nw', padx=(0, 6), pady=(6, 3))
        self.text_routes = tk.Text(frame, height=3, width=40, wrap='none')
        self.text_routes.grid(row=2, column=1, columnspan=5, sticky='ew', pady=(6, 3))
        self.text_routes.bind('<<Modified>>', self._on_routes_modified)
        ttk.Label(frame, text='每行一条, 格式: 路径=目标, 例如 /mc244=mc244.com',
                  foreground='#777777').grid(row=3, column=1, columnspan=5, sticky='w', pady=(0, 2))

    def _build_cert(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text='证书(wss:// 需要, 首次运行自动生成)', padding=(8, 6))
        frame.grid(row=2, column=0, sticky='ew', pady=(10, 0))
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(3, weight=1)

        ttk.Label(frame, text='证书目录').grid(row=0, column=0, sticky='w', padx=(0, 6), pady=3)
        ttk.Entry(frame, textvariable=self.var_cert_dir, width=18).grid(row=0, column=1, sticky='w')
        ttk.Label(frame, text='名称(CN)').grid(row=0, column=2, sticky='e', padx=(12, 6))
        ttk.Entry(frame, textvariable=self.var_cert_common_name, width=16).grid(row=0, column=3, sticky='w')
        ttk.Label(frame, text='有效期(天)').grid(row=0, column=4, sticky='e', padx=(12, 6))
        self.entry_cert_days = NumericEntry(frame, textvariable=self.var_cert_days, width=8,
                                            max_length=5)
        self.entry_cert_days.grid(row=0, column=5, sticky='w')

        ttk.Label(frame, text='额外名称').grid(row=1, column=0, sticky='w', padx=(0, 6), pady=3)
        ttk.Entry(frame, textvariable=self.var_cert_extra).grid(
            row=1, column=1, columnspan=3, sticky='ew')
        ttk.Label(frame, text='生成器').grid(row=1, column=4, sticky='e', padx=(12, 6))
        generator_box = ttk.Combobox(frame, textvariable=self.var_cert_generator, width=10,
                                     values=('auto', 'python', 'openssl'), state='readonly')
        generator_box.grid(row=1, column=5, sticky='w')

        ttk.Label(frame, textvariable=self.var_cert_info, foreground='#555555').grid(
            row=2, column=0, columnspan=6, sticky='w', pady=(4, 2))
        ttk.Label(frame, text='在 MCJS 中填写:').grid(row=3, column=0, sticky='w', pady=(4, 2))
        ttk.Label(frame, textvariable=self.var_endpoint, font=(None, 10, 'bold'),
                  foreground='#0b6e4f').grid(row=3, column=1, sticky='w')
        buttons = ttk.Frame(frame)
        buttons.grid(row=3, column=2, columnspan=4, sticky='e')
        ttk.Button(buttons, text='重新生成证书', command=self._regenerate_certificate).pack(side='left')
        ttk.Button(buttons, text='安装到系统信任库', command=self._install_certificate).pack(side='left', padx=6)
        ttk.Button(buttons, text='打开证书目录', command=self._open_certdir).pack(side='left')

    def _build_advanced(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text='高级', padding=(8, 6))
        frame.grid(row=3, column=0, sticky='ew', pady=(10, 0))
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(3, weight=1)
        frame.columnconfigure(5, weight=1)

        ttk.Label(frame, text='日志级别').grid(row=0, column=0, sticky='w', padx=(0, 6))
        ttk.Combobox(frame, textvariable=self.var_log_level, width=8, state='readonly',
                     values=('debug', 'info', 'warn', 'error')).grid(row=0, column=1, sticky='w')
        ttk.Label(frame, text='心跳(秒, 0=关闭)').grid(row=0, column=2, sticky='e', padx=(12, 6))
        self.entry_heartbeat = NumericEntry(frame, textvariable=self.var_heartbeat, width=8,
                                            max_length=6)
        self.entry_heartbeat.grid(row=0, column=3, sticky='w')
        ttk.Label(frame, text='连接超时(秒)').grid(row=0, column=4, sticky='e', padx=(12, 6))
        self.entry_timeout = NumericEntry(frame, textvariable=self.var_connect_timeout, width=8,
                                          max_length=7, allow_decimal=True)
        self.entry_timeout.grid(row=0, column=5, sticky='w')
        ttk.Label(frame, text='单帧上限(MB)').grid(row=0, column=6, sticky='e', padx=(12, 6))
        self.entry_max_payload = NumericEntry(frame, textvariable=self.var_max_payload, width=8,
                                              max_length=4)
        self.entry_max_payload.grid(row=0, column=7, sticky='w')

        ttk.Checkbutton(frame, text='按目标域名改写握手地址(服务器按地址校验/分流时勾选)',
                        variable=self.var_rewrite_host).grid(row=1, column=0, columnspan=8,
                                                             sticky='w', pady=(6, 0))
        ttk.Checkbutton(frame, text='浏览器客户端协议翻译(EaglercraftX/MCJS 系客户端必需)',
                        variable=self.var_eagler_translate).grid(
                            row=2, column=0, columnspan=8, sticky='w', pady=(2, 0))

    def _build_actions(self, parent: ttk.Frame) -> None:
        frame = ttk.Frame(parent)
        frame.grid(row=4, column=0, sticky='ew', pady=(10, 0))

        self.btn_start = ttk.Button(frame, text='启动服务', command=self._start)
        self.btn_start.pack(side='left')
        self.btn_stop = ttk.Button(frame, text='停止服务', command=self._stop, state='disabled')
        self.btn_stop.pack(side='left', padx=6)
        ttk.Button(frame, text='复制 wss 地址', command=self._copy_endpoint).pack(side='left', padx=(18, 0))
        ttk.Button(frame, text='保存配置', command=self._save_config).pack(side='left', padx=6)
        ttk.Button(frame, text='恢复默认配置', command=self._reset_defaults).pack(side='left')
        ttk.Button(frame, text='打开状态页', command=self._open_status_page).pack(side='right')

    def _build_status_bar(self, parent: ttk.Frame) -> None:
        frame = ttk.Frame(parent, relief='sunken', borderwidth=1)
        frame.grid(row=6, column=0, sticky='ew', pady=(10, 0))
        items = (('活动连接', self.var_stat_active), ('累计连接', self.var_stat_total),
                 ('上行', self.var_stat_up), ('下行', self.var_stat_down),
                 ('运行时长', self.var_stat_uptime))
        for index, (label, variable) in enumerate(items):
            frame.columnconfigure(index, weight=1)
            cell = ttk.Frame(frame)
            cell.grid(row=0, column=index, sticky='w', padx=10, pady=3)
            ttk.Label(cell, text=label, foreground='#777777').pack(side='left', padx=(0, 6))
            ttk.Label(cell, textvariable=variable).pack(side='left')

    # ---------- 表单读写 ----------
    def _load_form(self) -> None:
        config = self.config
        self.var_listen_host.set(config.listen_host)
        self.entry_wss_port.set_value(str(config.wss_port))
        self.entry_ws_port.set_value(str(config.ws_port))
        self.var_target.set(config.target)
        self.var_use_srv.set(bool(config.use_srv))
        self.var_rewrite_host.set(bool(getattr(config, 'rewrite_handshake_host', False)))
        self.var_eagler_translate.set(bool(getattr(config, 'eagler_translate', True)))
        self.var_cert_dir.set(config.cert_dir)
        self.var_cert_common_name.set(config.cert_common_name)
        self.var_cert_extra.set(', '.join(config.cert_extra_names or []))
        self.entry_cert_days.set_value(str(config.cert_days))
        self.var_cert_generator.set(config.cert_generator)
        self.var_log_level.set(config.log_level)
        self.entry_heartbeat.set_value(str(config.heartbeat_sec))
        self.entry_timeout.set_value(str(config.connect_timeout))
        self.entry_max_payload.set_value(str(config.max_payload_mb))
        self.text_routes.delete('1.0', 'end')
        self.text_routes.insert('1.0', config_module.format_routes_text(config.routes))
        self.text_routes.edit_modified(False)

    def _on_routes_modified(self, _event=None) -> None:
        if self.text_routes.edit_modified():
            self.text_routes.edit_modified(False)

    def _collect_form(self) -> config_module.Config:
        """把界面上的内容收集成配置对象。

        数字类字段只接受数字(输入框本身就拦了非法字符), 这里再做一次严格解析:
        遇到空值或脏值直接抛 ValueError, 交给调用方弹出提示, 绝不静默套用默认值。
        """

        def as_int(variable, label, fallback=None):
            text = str(variable.get()).strip()
            if not text:
                if fallback is None:
                    raise ValueError('「%s」不能为空' % label)
                return fallback
            if not (text.isascii() and text.isdigit()):
                raise ValueError('「%s」只能是数字, 当前值是: %s' % (label, text))
            return int(text)

        def as_float(variable, label, fallback=0.0):
            text = str(variable.get()).strip()
            if not text:
                return fallback
            if not set(text) <= set('0123456789.'):
                raise ValueError('「%s」只能是数字, 当前值是: %s' % (label, text))
            try:
                return float(text)
            except ValueError:
                raise ValueError('「%s」不是有效的数字: %s' % (label, text)) from None

        routes_text = self.text_routes.get('1.0', 'end')
        routes = config_module.parse_routes_text(routes_text) if routes_text.strip() else {}
        extra = [item.strip() for item in self.var_cert_extra.get().replace(',', ' ').split() if item.strip()]
        self.config.listen_host = self.var_listen_host.get().strip() or '127.0.0.1'
        self.config.wss_port = as_int(self.var_wss_port, 'wss 端口')
        self.config.ws_port = as_int(self.var_ws_port, 'ws 端口')
        self.config.target = self.var_target.get().strip() or 'mc244.com'
        self.config.use_srv = bool(self.var_use_srv.get())
        self.config.rewrite_handshake_host = bool(self.var_rewrite_host.get())
        self.config.eagler_translate = bool(self.var_eagler_translate.get())
        self.config.routes = routes
        self.config.tls_enabled = True  # wss:// 是本工具的用途, 始终启用
        self.config.cert_dir = self.var_cert_dir.get().strip() or 'certs'
        self.config.cert_common_name = self.var_cert_common_name.get().strip() or 'localhost'
        self.config.cert_extra_names = extra
        self.config.cert_days = max(1, as_int(self.var_cert_days, '证书有效期', fallback=3650))
        self.config.cert_generator = self.var_cert_generator.get().strip() or 'auto'
        self.config.log_level = self.var_log_level.get().strip() or 'info'
        self.config.heartbeat_sec = max(0, as_int(self.var_heartbeat, '心跳间隔', fallback=30))
        self.config.connect_timeout = max(1.0, as_float(self.var_connect_timeout, '连接超时', fallback=10.0))
        self.config.max_payload_mb = max(1, as_int(self.var_max_payload, '单帧上限', fallback=16))
        for label, port in (('wss 端口', self.config.wss_port), ('ws 端口', self.config.ws_port)):
            if not 0 <= port <= 65535:
                raise ValueError('「%s」必须在 0~65535 之间, 当前值是: %d' % (label, port))
        return self.config

    def _refresh_target_hint(self, *_args) -> None:
        try:
            config = self._collect_form()
        except ValueError:
            self.var_endpoint.set('(请先填写端口)')
            return
        url = config.wss_url()
        self.var_endpoint.set(url or '(未启用监听)')

    # ---------- 启动 / 停止 ----------
    def _start(self) -> None:
        if self.server is not None and self.server.running:
            return
        try:
            config = self._collect_form()
        except ValueError as exc:
            messagebox.showerror('配置有误', str(exc))
            return
        problems = config.validate()
        if problems:
            messagebox.showerror('配置有误', '\n'.join('· ' + item for item in problems))
            return
        try:
            config.save()
        except OSError as exc:
            self._append_log('warn', '配置保存失败: %s' % exc)

        self._clear_log()
        self.logger = Logger(config.log_level, callback=self._enqueue_log, echo=True)
        self.logger.info('%s v%s 正在启动...' % (APP_NAME, VERSION))
        self.logger.info('转发目标: %s' % config.describe_target())
        self.server = ProxyServer(config, self.logger)
        self.btn_start.configure(state='disabled')
        self.btn_stop.configure(state='normal')
        self._set_status('启动中')
        threading.Thread(target=self._start_server, daemon=True).start()

    def _set_status(self, text: str, color: str | None = None) -> None:
        """状态栏文字与颜色: 颜色要改在 Label 控件上(StringVar 没有 configure)。"""
        self.var_status.set(text)
        if color:
            self.lbl_status.configure(foreground=color)

    def _start_server(self) -> None:
        assert self.server is not None and self.logger is not None
        server = self.server
        logger = self.logger
        try:
            info = server.start()
        except Exception as exc:
            logger.error('启动失败: %s' % exc)
            self.enqueue_ui(self._on_start_failed, str(exc))
            return
        logger.info('wss 监听地址: %s' % (info.get('wss_url') or '(未启用)'))
        for listener in info.get('listeners', []):
            if listener.startswith('ws://'):
                logger.info('备用明文监听: %s (页面本身是 http:// 时也可以用)' % listener)
        certificate = info.get('certificate')
        if certificate:
            logger.info('证书指纹 SHA-256: %s' % certificate['thumbprint'])
            logger.info('如浏览器提示证书不受信任, 请点【安装到系统信任库】后重启浏览器。')
        self.enqueue_ui(self._on_started)

    def _on_started(self) -> None:
        self._set_status('运行中', '#0b6e4f')
        self.btn_start.configure(state='disabled')
        self.btn_stop.configure(state='normal')
        self._refresh_target_hint()
        self._update_cert_label()

    def _on_start_failed(self, message: str) -> None:
        self.server = None
        self._set_status('启动失败', '#c02b2b')
        self.btn_start.configure(state='normal')
        self.btn_stop.configure(state='disabled')
        messagebox.showerror('启动失败', message)

    def _stop(self) -> None:
        server = self.server
        if server is None:
            return
        self._set_status('停止中')
        self.btn_stop.configure(state='disabled')

        def _worker() -> None:
            try:
                server.stop()
            finally:
                self.enqueue_ui(self._on_stopped)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_stopped(self) -> None:
        self.server = None
        self._set_status('已停止', '#c02b2b')
        self.btn_start.configure(state='normal')
        self.btn_stop.configure(state='disabled')
        for variable in (self.var_stat_active, self.var_stat_total, self.var_stat_up,
                         self.var_stat_down, self.var_stat_uptime):
            variable.set('0')

    # ---------- 日志 ----------
    def _enqueue_log(self, level: str, text: str) -> None:
        self.log_queue.put((level, text))

    def enqueue_ui(self, function, *args) -> None:
        """把界面更新安排到主线程执行。"""
        try:
            self.after(0, lambda: function(*args))
        except tk.TclError:  # 窗口已关闭
            pass

    def _append_log(self, level: str, text: str) -> None:
        self.log_text.configure(state='normal')
        self.log_text.insert('end', text + '\n', level)
        if self.var_auto_scroll.get():
            self.log_text.see('end')
        self.log_text.configure(state='disabled')

    def _clear_log(self) -> None:
        self.log_text.configure(state='normal')
        self.log_text.delete('1.0', 'end')
        self.log_text.configure(state='disabled')

    def _poll(self) -> None:
        while True:
            try:
                level, text = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self._append_log(level, text)
        self._refresh_stats()
        if not self._closing:
            try:
                self.after(150, self._poll)
            except tk.TclError:
                pass

    def _refresh_stats(self) -> None:
        server = self.server
        if server is None or not server.running:
            return
        snapshot = server.stats.snapshot()
        self.var_stat_active.set(str(snapshot['active']))
        self.var_stat_total.set(str(snapshot['total']))
        self.var_stat_up.set(human_bytes(snapshot['bytes_to_server']))
        self.var_stat_down.set(human_bytes(snapshot['bytes_to_client']))
        self.var_stat_uptime.set(human_duration(snapshot['uptime']))

    # ---------- 证书 ----------
    def _cert_paths(self) -> tuple[Path, Path]:
        cert_dir = resolve_path(self.var_cert_dir.get().strip() or 'certs')
        return certs.certificate_paths(cert_dir)

    def _cert_options(self) -> dict:
        """读取证书相关输入, 输入不合法时退回默认值而不是抛异常。"""
        try:
            days = int(self.var_cert_days.get().strip() or 3650)
        except ValueError:
            days = 3650
        extra = [item for item in self.var_cert_extra.get().replace(',', ' ').split() if item]
        return {
            'common_name': self.var_cert_common_name.get().strip() or 'localhost',
            'extra_names': extra,
            'days': max(1, days),
            'generator': self.var_cert_generator.get().strip() or 'auto',
        }

    def _update_cert_label(self) -> None:
        cert_path, key_path = self._cert_paths()
        info = certs.inspect_certificate(cert_path, key_path) if cert_path.exists() else None
        if info is None:
            self.var_cert_info.set('尚未生成证书 —— 启动服务时会自动签发一张自签名证书')
            return
        names = ', '.join(info.get('alt_names', ())) or 'localhost, 127.0.0.1, ::1'
        self.var_cert_info.set('文件: %s\n指纹 SHA-256: %s\n覆盖名称: %s'
                               % (cert_path, info['thumbprint'], names))

    def _regenerate_certificate(self) -> None:
        if self.server is not None and self.server.running:
            messagebox.showinfo('请先停止服务', '重新生成证书需要先停止服务。')
            return
        if not messagebox.askyesno('重新生成证书', '将删除现有证书并重新签发一张, 需要继续吗?'):
            return
        cert_path, key_path = self._cert_paths()
        deleted = False
        for path in (cert_path, key_path):
            try:
                path.unlink()
                deleted = True
            except FileNotFoundError:
                pass
            except OSError as exc:
                messagebox.showerror('删除失败', str(exc))
                return
        logger = self.logger or Logger(self.var_log_level.get().strip() or 'info',
                                       callback=self._enqueue_log, echo=False)
        try:
            certs.generate_certificate(cert_path.parent, logger=logger, **self._cert_options())
        except Exception as exc:
            messagebox.showerror('生成失败', str(exc))
            return
        self._update_cert_label()
        messagebox.showinfo('完成', '证书已重新生成。%s'
                            % ('已删除旧证书。' if deleted else ''))

    def _install_certificate(self) -> None:
        cert_path, _key_path = self._cert_paths()
        if not cert_path.exists():
            if not messagebox.askyesno('尚未生成证书', '还没有证书文件, 是否现在生成并导入?'):
                return
            logger = self.logger or Logger(self.var_log_level.get().strip() or 'info',
                                           callback=self._enqueue_log, echo=False)
            try:
                certs.generate_certificate(cert_path.parent, logger=logger, **self._cert_options())
            except Exception as exc:
                messagebox.showerror('生成失败', str(exc))
                return
            self._update_cert_label()
        self.var_status.set('导入证书中')
        threading.Thread(target=self._install_certificate_worker, daemon=True).start()

    def _install_certificate_worker(self) -> None:
        cert_path, _key_path = self._cert_paths()
        try:
            ok, message = certs.install_to_trust_store(cert_path, logger=self.logger)
        except Exception as exc:
            ok, message = False, str(exc)
        if self.logger is not None and message:
            self.logger.info('certutil 输出: %s' % message)
        self.enqueue_ui(self._on_certificate_installed, ok, message)

    def _on_certificate_installed(self, ok: bool, message: str) -> None:
        self._update_cert_label()
        if ok:
            self._set_status('运行中' if (self.server and self.server.running) else '已停止',
                             '#0b6e4f' if (self.server and self.server.running) else '#c02b2b')
            messagebox.showinfo(
                '导入成功',
                '证书已加入当前用户的"受信任的根证书颁发机构"。\n\n'
                '请重启浏览器(Chrome / Edge 立即生效, Firefox 需要在\n'
                '设置 → 隐私与安全 → 证书 → 查看证书 中再单独导入一次)。')
        else:
            messagebox.showerror('导入失败', message or '未知错误')

    def _open_certdir(self) -> None:
        cert_path, _key_path = self._cert_paths()
        cert_path.parent.mkdir(parents=True, exist_ok=True)
        self._open_path(cert_path.parent)

    # ---------- 其它按钮 ----------
    def _copy_endpoint(self) -> None:
        try:
            url = self._collect_form().wss_url()
        except ValueError as exc:
            messagebox.showerror('配置有误', str(exc))
            return
        if not url:
            messagebox.showwarning('没有可用地址', '请先设置 wss 端口')
            return
        self.clipboard_clear()
        self.clipboard_append(url)
        self.update_idletasks()
        self._append_log('info', '已复制到剪贴板: %s' % url)

    def _open_status_page(self) -> None:
        try:
            config = self._collect_form()
        except ValueError as exc:
            messagebox.showerror('配置有误', str(exc))
            return
        if self.server is None or not self.server.running:
            messagebox.showinfo('未运行', '请先启动服务, 再打开状态页。')
            return
        port = int(config.ws_port) if int(config.ws_port) > 0 else int(config.wss_port)
        scheme = 'http' if int(config.ws_port) > 0 else 'https'
        host = config.listen_host if config.listen_host not in ('0.0.0.0', '') else '127.0.0.1'
        url = '%s://%s:%d/' % (scheme, host, port)
        webbrowser.open(url)

    def _save_config(self) -> None:
        try:
            config = self._collect_form()
        except ValueError as exc:
            messagebox.showerror('配置有误', str(exc))
            return
        try:
            path = config.save()
        except OSError as exc:
            messagebox.showerror('保存失败', str(exc))
            return
        self._append_log('info', '配置已保存: %s' % path)

    def _reset_defaults(self) -> None:
        if not messagebox.askyesno('恢复默认配置', '将把界面上的设置恢复为默认值(不覆盖已保存的配置文件), 继续吗?'):
            return
        self.config = config_module.Config()
        self._load_form()
        self._update_cert_label()
        self._refresh_target_hint()

    def _open_workdir(self) -> None:
        self._open_path(app_dir())

    @staticmethod
    def _open_path(path: Path) -> None:
        try:
            path.mkdir(parents=True, exist_ok=True)
            if sys.platform == 'win32':
                os.startfile(str(path))  # type: ignore[attr-defined]
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', str(path)])
            else:
                subprocess.Popen(['xdg-open', str(path)])
        except Exception as exc:
            messagebox.showerror('打开失败', str(exc))

    def _show_help(self) -> None:
        messagebox.showinfo('使用说明', HELP_TEXT)

    def _show_about(self) -> None:
        messagebox.showinfo(
            '关于',
            '%s v%s\n\n'
            '把普通 Minecraft 服务器(例如 Hypixel)转换为本地 wss:// 端点,\n'
            '让 MCJS 等浏览器端客户端可以连接 —— 浏览器只允许建立 wss:// 连接。\n\n'
            '转发过程不解析、不修改任何游戏数据, 字节流与原版客户端直连一致。\n'
            '工作目录: %s' % (APP_NAME, VERSION, app_dir()))

    # ---------- 退出 ----------
    def _on_close(self) -> None:
        self._closing = True
        try:
            config = self._collect_form()
            config.save()
        except Exception:
            pass
        server = self.server
        if server is not None and server.running:
            try:
                server.stop()
            except Exception:
                pass
        self.destroy()


def main() -> int:
    app = BridgeApp()
    app.mainloop()
    return 0