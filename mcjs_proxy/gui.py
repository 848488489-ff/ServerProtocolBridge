"""tkinter GUI.

The window only configures things and displays state; the forwarding itself
runs in ProxyServer's background threads, and log lines travel back to the
main thread through a queue, so the UI never freezes.
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
from . import update
from .i18n import LANGUAGES, get_language, language_code, language_label, set_language, tr
from .logger import Logger
from .proxy import ProxyServer
from .utils import app_dir, human_bytes, human_duration, resolve_path
from .version import VERSION

LOG_COLORS = {
    'debug': '#6a6a6a',
    'info': '#1c1c1c',
    'warn': '#b06000',
    'error': '#c02b2b',
}


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
    """Entry widget that only accepts digits.

    Non-digit characters (CJK text, letters, spaces, full-width digits) are
    rejected already at the keystroke/paste stage, so a port field can never
    end up holding e.g. Chinese characters.  With ``allow_decimal=True`` a
    single ASCII decimal point is allowed as well.
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
            return True                      # clearing the field before retyping is fine
        if not proposed.isascii():
            return False                     # full-width digits, CJK text, ...: always reject
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
        """Set the value programmatically with validation switched off.

        A dirty value from an old config file must not trigger a Tk
        validation warning while the field is being populated.
        """
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
        self.config = config_module.Config.load()
        # The saved language has to be active before the first string is built.
        set_language(self.config.language)
        self.title('%s  v%s' % (tr('core.app_name'), VERSION))
        self.geometry('960x720')
        self.minsize(900, 660)
        _apply_font(self)

        self.log_queue: 'queue.Queue[tuple[str, str]]' = queue.Queue()
        self.logger: Logger | None = None
        self.server: ProxyServer | None = None
        self._closing = False
        self._update_outcome: dict | None = None   # last successful version check

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
        # The window is usable long before the answer arrives, so the check runs
        # in the background and only ever adds a line to the header.
        self.after(600, self._check_updates)

    # ---------- Variables ----------
    def _build_variables(self) -> None:
        self.var_listen_host = tk.StringVar()
        self.var_wss_port = tk.StringVar()
        self.var_ws_port = tk.StringVar()
        self.var_target = tk.StringVar()
        self.var_language = tk.StringVar()
        self.var_use_srv = tk.BooleanVar()
        self.var_rewrite_host = tk.BooleanVar()
        self.var_eagler_translate = tk.BooleanVar(value=True)
        self.var_cert_dir = tk.StringVar()
        self.var_cert_common_name = tk.StringVar()
        self.var_cert_extra = tk.StringVar()
        self.var_cert_days = tk.StringVar()
        self.var_cert_generator = tk.StringVar()
        self.var_log_level = tk.StringVar()
        self.var_heartbeat = tk.StringVar()
        self.var_connect_timeout = tk.StringVar()
        self.var_max_payload = tk.StringVar()
        self.var_status = tk.StringVar(value=tr('gui.status.stopped'))
        self.var_endpoint = tk.StringVar(value='')
        self.var_cert_info = tk.StringVar(value='')
        self.var_stat_active = tk.StringVar(value='0')
        self.var_stat_total = tk.StringVar(value='0')
        self.var_stat_up = tk.StringVar(value='0 B')
        self.var_stat_down = tk.StringVar(value='0 B')
        self.var_stat_uptime = tk.StringVar(value='0:00')
        self.var_auto_scroll = tk.BooleanVar(value=True)
        # Cached status-bar state.  It lives outside the widgets so the bar
        # can be restored verbatim after a language switch rebuilds them.
        self._status_key = 'gui.status.stopped'
        self._status_color = '#c02b2b'

    # ---------- Menu ----------
    def _build_menu(self) -> None:
        menu = tk.Menu(self)
        file_menu = tk.Menu(menu, tearoff=0)
        file_menu.add_command(label=tr('gui.menu.save_config'), command=self._save_config)
        file_menu.add_command(label=tr('gui.menu.open_workdir'), command=self._open_workdir)
        file_menu.add_separator()
        file_menu.add_command(label=tr('gui.menu.quit'), command=self._on_close)
        menu.add_cascade(label=tr('gui.menu.file'), menu=file_menu)

        tool_menu = tk.Menu(menu, tearoff=0)
        tool_menu.add_command(label=tr('gui.menu.copy_endpoint'), command=self._copy_endpoint)
        tool_menu.add_command(label=tr('gui.menu.status_page'), command=self._open_status_page)
        tool_menu.add_command(label=tr('gui.menu.install_cert'), command=self._install_certificate)
        menu.add_cascade(label=tr('gui.menu.tools'), menu=tool_menu)

        help_menu = tk.Menu(menu, tearoff=0)
        help_menu.add_command(label=tr('gui.menu.check_update'), command=self._check_updates_manual)
        help_menu.add_command(label=tr('gui.help.title'), command=self._show_help)
        help_menu.add_command(label=tr('gui.about.title'), command=self._show_about)
        menu.add_cascade(label=tr('gui.menu.help'), menu=help_menu)
        # Note: self.config is the configuration object and shadows Tk's
        # config() method, so the base class implementation is called explicitly.
        tk.Misc.config(self, menu=menu)

    # ---------- UI ----------
    def _build_ui(self) -> None:
        self.title('%s  v%s' % (tr('core.app_name'), VERSION))
        outer = ttk.Frame(self, padding=(10, 8, 10, 6))
        outer.pack(fill='both', expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(5, weight=1)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky='ew')
        header.columnconfigure(1, weight=1)
        ttk.Label(header, text=tr('core.app_name'), font=(None, 14, 'bold')).grid(
            row=0, column=0, sticky='w')
        ttk.Label(header, text=tr('core.tagline'), foreground='#555555').grid(
            row=0, column=1, sticky='w', padx=(12, 0))
        self.lbl_status = ttk.Label(header, textvariable=self.var_status, width=12, anchor='center',
                                    foreground=self._status_color)
        self.lbl_status.grid(row=0, column=2, sticky='e')
        # "A newer release is available" line under the header; it is only
        # gridded when there is news (see _apply_update_banner), so a start with
        # nothing to report looks exactly like before.
        self.lbl_update = ttk.Label(header, text='', foreground='#b26b00')

        self._build_basic(outer)
        self._build_cert(outer)
        self._build_advanced(outer)
        self._build_actions(outer)

        # Log area
        log_frame = ttk.LabelFrame(outer, text=tr('gui.log_frame'), padding=(8, 6))
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
        ttk.Button(tools, text=tr('gui.log.clear'), command=self._clear_log).pack(side='left')
        ttk.Checkbutton(tools, text=tr('gui.log.auto_scroll'),
                        variable=self.var_auto_scroll).pack(side='left', padx=(8, 0))
        ttk.Label(tools, text=tr('gui.log.hint'),
                  foreground='#777777').pack(side='right')

        self._build_status_bar(outer)
        self._apply_update_banner()

    def _build_basic(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text=tr('gui.group.basic'), padding=(8, 6))
        frame.grid(row=1, column=0, sticky='ew', pady=(10, 0))
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(3, weight=1)

        ttk.Label(frame, text=tr('gui.language')).grid(row=0, column=0, sticky='w',
                                                      padx=(0, 6), pady=3)
        self.language_box = ttk.Combobox(frame, textvariable=self.var_language, width=10,
                                         values=[language_label(code) for code in LANGUAGES],
                                         state='readonly')
        self.language_box.grid(row=0, column=1, sticky='w', pady=3)
        self.language_box.bind('<<ComboboxSelected>>', self._switch_language)

        ttk.Label(frame, text=tr('gui.label.listen_host')).grid(row=1, column=0, sticky='w',
                                                                padx=(0, 6), pady=3)
        ttk.Entry(frame, textvariable=self.var_listen_host, width=18).grid(
            row=1, column=1, sticky='ew', pady=3)
        ttk.Label(frame, text=tr('gui.label.wss_port')).grid(row=1, column=2, sticky='e',
                                                             padx=(12, 6))
        self.entry_wss_port = NumericEntry(frame, textvariable=self.var_wss_port, width=8,
                                           max_length=5)
        self.entry_wss_port.grid(row=1, column=3, sticky='w')
        ttk.Label(frame, text=tr('gui.label.ws_port')).grid(row=1, column=4, sticky='e',
                                                            padx=(12, 6))
        self.entry_ws_port = NumericEntry(frame, textvariable=self.var_ws_port, width=8,
                                          max_length=5)
        self.entry_ws_port.grid(row=1, column=5, sticky='w')

        ttk.Label(frame, text=tr('gui.label.target')).grid(row=2, column=0, sticky='w',
                                                           padx=(0, 6), pady=3)
        ttk.Entry(frame, textvariable=self.var_target).grid(row=2, column=1, columnspan=3,
                                                            sticky='ew')
        ttk.Checkbutton(frame, text=tr('gui.label.use_srv'), variable=self.var_use_srv).grid(
            row=2, column=4, columnspan=2, sticky='e', padx=(8, 0))

    def _build_cert(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text=tr('gui.group.cert'), padding=(8, 6))
        frame.grid(row=2, column=0, sticky='ew', pady=(10, 0))
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(3, weight=1)

        ttk.Label(frame, text=tr('gui.label.cert_dir')).grid(row=0, column=0, sticky='w',
                                                             padx=(0, 6), pady=3)
        ttk.Entry(frame, textvariable=self.var_cert_dir, width=18).grid(row=0, column=1,
                                                                        sticky='w')
        ttk.Label(frame, text=tr('gui.label.cert_cn')).grid(row=0, column=2, sticky='e',
                                                            padx=(12, 6))
        ttk.Entry(frame, textvariable=self.var_cert_common_name, width=16).grid(row=0, column=3,
                                                                                sticky='w')
        ttk.Label(frame, text=tr('gui.label.cert_days')).grid(row=0, column=4, sticky='e',
                                                              padx=(12, 6))
        self.entry_cert_days = NumericEntry(frame, textvariable=self.var_cert_days, width=8,
                                            max_length=5)
        self.entry_cert_days.grid(row=0, column=5, sticky='w')

        ttk.Label(frame, text=tr('gui.label.cert_extra')).grid(row=1, column=0, sticky='w',
                                                               padx=(0, 6), pady=3)
        ttk.Entry(frame, textvariable=self.var_cert_extra).grid(
            row=1, column=1, columnspan=3, sticky='ew')
        ttk.Label(frame, text=tr('gui.label.cert_generator')).grid(row=1, column=4, sticky='e',
                                                                   padx=(12, 6))
        generator_box = ttk.Combobox(frame, textvariable=self.var_cert_generator, width=10,
                                     values=('auto', 'python', 'openssl'), state='readonly')
        generator_box.grid(row=1, column=5, sticky='w')

        ttk.Label(frame, textvariable=self.var_cert_info, foreground='#555555').grid(
            row=2, column=0, columnspan=6, sticky='w', pady=(4, 2))
        ttk.Label(frame, text=tr('gui.label.cert_fill')).grid(row=3, column=0, sticky='w',
                                                              pady=(4, 2))
        ttk.Label(frame, textvariable=self.var_endpoint, font=(None, 10, 'bold'),
                  foreground='#0b6e4f').grid(row=3, column=1, sticky='w')
        buttons = ttk.Frame(frame)
        buttons.grid(row=3, column=2, columnspan=4, sticky='e')
        ttk.Button(buttons, text=tr('gui.button.regen_cert'),
                   command=self._regenerate_certificate).pack(side='left')
        ttk.Button(buttons, text=tr('gui.button.install_cert'),
                   command=self._install_certificate).pack(side='left', padx=6)
        ttk.Button(buttons, text=tr('gui.button.open_cert_dir'),
                   command=self._open_certdir).pack(side='left')

    def _build_advanced(self, parent: ttk.Frame) -> None:
        frame = ttk.LabelFrame(parent, text=tr('gui.group.advanced'), padding=(8, 6))
        frame.grid(row=3, column=0, sticky='ew', pady=(10, 0))
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(3, weight=1)
        frame.columnconfigure(5, weight=1)

        ttk.Label(frame, text=tr('gui.label.log_level')).grid(row=0, column=0, sticky='w',
                                                              padx=(0, 6))
        ttk.Combobox(frame, textvariable=self.var_log_level, width=8, state='readonly',
                     values=('debug', 'info', 'warn', 'error')).grid(row=0, column=1, sticky='w')
        ttk.Label(frame, text=tr('gui.label.heartbeat')).grid(row=0, column=2, sticky='e',
                                                              padx=(12, 6))
        self.entry_heartbeat = NumericEntry(frame, textvariable=self.var_heartbeat, width=8,
                                            max_length=6)
        self.entry_heartbeat.grid(row=0, column=3, sticky='w')
        ttk.Label(frame, text=tr('gui.label.connect_timeout')).grid(row=0, column=4, sticky='e',
                                                                    padx=(12, 6))
        self.entry_timeout = NumericEntry(frame, textvariable=self.var_connect_timeout, width=8,
                                          max_length=7, allow_decimal=True)
        self.entry_timeout.grid(row=0, column=5, sticky='w')
        ttk.Label(frame, text=tr('gui.label.max_payload')).grid(row=0, column=6, sticky='e',
                                                                padx=(12, 6))
        self.entry_max_payload = NumericEntry(frame, textvariable=self.var_max_payload, width=8,
                                              max_length=4)
        self.entry_max_payload.grid(row=0, column=7, sticky='w')

        ttk.Checkbutton(frame, text=tr('gui.label.rewrite_host'),
                        variable=self.var_rewrite_host).grid(row=1, column=0, columnspan=8,
                                                             sticky='w', pady=(6, 0))
        ttk.Checkbutton(frame, text=tr('gui.label.eagler_translate'),
                        variable=self.var_eagler_translate).grid(
                            row=2, column=0, columnspan=8, sticky='w', pady=(2, 0))

    def _build_actions(self, parent: ttk.Frame) -> None:
        frame = ttk.Frame(parent)
        frame.grid(row=4, column=0, sticky='ew', pady=(10, 0))

        self.btn_start = ttk.Button(frame, text=tr('gui.button.start'), command=self._start)
        self.btn_start.pack(side='left')
        self.btn_stop = ttk.Button(frame, text=tr('gui.button.stop'), command=self._stop,
                                   state='disabled')
        self.btn_stop.pack(side='left', padx=6)
        ttk.Button(frame, text=tr('gui.button.copy_endpoint'),
                   command=self._copy_endpoint).pack(side='left', padx=(18, 0))
        ttk.Button(frame, text=tr('gui.button.save_config'),
                   command=self._save_config).pack(side='left', padx=6)
        ttk.Button(frame, text=tr('gui.button.reset_defaults'),
                   command=self._reset_defaults).pack(side='left')
        ttk.Button(frame, text=tr('gui.button.status_page'),
                   command=self._open_status_page).pack(side='right')

    def _build_status_bar(self, parent: ttk.Frame) -> None:
        frame = ttk.Frame(parent, relief='sunken', borderwidth=1)
        frame.grid(row=6, column=0, sticky='ew', pady=(10, 0))
        items = ((tr('gui.stat.active'), self.var_stat_active),
                 (tr('gui.stat.total'), self.var_stat_total),
                 (tr('gui.stat.up'), self.var_stat_up),
                 (tr('gui.stat.down'), self.var_stat_down),
                 (tr('gui.stat.uptime'), self.var_stat_uptime))
        for index, (label, variable) in enumerate(items):
            frame.columnconfigure(index, weight=1)
            cell = ttk.Frame(frame)
            cell.grid(row=0, column=index, sticky='w', padx=10, pady=3)
            ttk.Label(cell, text=label, foreground='#777777').pack(side='left', padx=(0, 6))
            ttk.Label(cell, textvariable=variable).pack(side='left')

    # ---------- Form I/O ----------
    def _load_form(self, config: config_module.Config | None = None) -> None:
        config = self.config if config is None else config
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
        self.var_language.set(language_label(config.language))

    def _collect_form(self) -> config_module.Config:
        """Collect the form contents into the configuration object.

        Numeric fields only accept digits (the entries themselves already
        block bogus characters), and this parses them strictly once more:
        an empty or dirty value raises ValueError for the caller to report,
        never a silent fallback to the default.
        """

        def as_int(variable, label, fallback=None):
            text = str(variable.get()).strip()
            if not text:
                if fallback is None:
                    raise ValueError(tr('gui.error.empty', label=label))
                return fallback
            if not (text.isascii() and text.isdigit()):
                raise ValueError(tr('gui.error.not_number', label=label, value=text))
            return int(text)

        def as_float(variable, label, fallback=0.0):
            text = str(variable.get()).strip()
            if not text:
                return fallback
            if not set(text) <= set('0123456789.'):
                raise ValueError(tr('gui.error.not_number', label=label, value=text))
            try:
                return float(text)
            except ValueError:
                raise ValueError(tr('gui.error.invalid_number', label=label, value=text)) from None

        extra = [item.strip() for item in self.var_cert_extra.get().replace(',', ' ').split()
                 if item.strip()]
        self.config.listen_host = self.var_listen_host.get().strip() or '127.0.0.1'
        self.config.wss_port = as_int(self.var_wss_port, tr('gui.field.wss_port'))
        self.config.ws_port = as_int(self.var_ws_port, tr('gui.field.ws_port'))
        self.config.target = self.var_target.get().strip()
        self.config.use_srv = bool(self.var_use_srv.get())
        self.config.rewrite_handshake_host = bool(self.var_rewrite_host.get())
        self.config.eagler_translate = bool(self.var_eagler_translate.get())
        self.config.tls_enabled = True  # wss:// is the whole point of this tool: always on
        self.config.cert_dir = self.var_cert_dir.get().strip() or 'certs'
        self.config.cert_common_name = self.var_cert_common_name.get().strip() or 'localhost'
        self.config.cert_extra_names = extra
        self.config.cert_days = max(1, as_int(self.var_cert_days, tr('gui.field.cert_days'),
                                              fallback=3650))
        self.config.cert_generator = self.var_cert_generator.get().strip() or 'auto'
        self.config.log_level = self.var_log_level.get().strip() or 'info'
        self.config.heartbeat_sec = max(0, as_int(self.var_heartbeat, tr('gui.field.heartbeat'),
                                                  fallback=30))
        self.config.connect_timeout = max(1.0, as_float(self.var_connect_timeout,
                                                        tr('gui.field.connect_timeout'),
                                                        fallback=10.0))
        self.config.max_payload_mb = max(1, as_int(self.var_max_payload,
                                                   tr('gui.field.max_payload'), fallback=16))
        self.config.language = language_code(self.var_language.get())
        for label, port in ((tr('gui.field.wss_port'), self.config.wss_port),
                            (tr('gui.field.ws_port'), self.config.ws_port)):
            if not 0 <= port <= 65535:
                raise ValueError(tr('gui.error.port_range', label=label, value=port))
        return self.config

    def _refresh_target_hint(self, *_args) -> None:
        try:
            config = self._collect_form()
        except ValueError:
            self.var_endpoint.set(tr('gui.endpoint.need_port'))
            return
        url = config.wss_url()
        self.var_endpoint.set(url or tr('gui.endpoint.disabled'))

    # ---------- Language switching ----------
    def _switch_language(self, _event=None) -> None:
        """Apply the combobox selection and rebuild the whole window in place."""
        code = language_code(self.var_language.get())
        if code == get_language():
            return
        try:
            try:
                config = self._collect_form()
            except ValueError:
                config = self.config
            config.language = code
            set_language(code)
            self._rebuild_ui(config)
        except Exception as exc:
            # A failed rebuild must never take the window down with it.
            messagebox.showerror(tr('gui.dialog.switch_failed'), str(exc))

    def _rebuild_ui(self, config: config_module.Config) -> None:
        """Recreate every widget in place, e.g. after a language switch.

        Tk widgets cannot retranslate their text live, so the whole tree is
        destroyed and built again.  Only state that lives outside the widgets
        -- the log text, the window geometry and the server session -- is
        carried over by hand.
        """
        log_text = self.log_text.get('1.0', 'end-1c')
        geometry = self.geometry()
        for child in list(self.winfo_children()):
            child.destroy()
        self._build_menu()
        self._build_ui()
        self._load_form(config)
        if log_text:
            self.log_text.configure(state='normal')
            self.log_text.insert('1.0', log_text)
            self.log_text.configure(state='disabled')
            if self.var_auto_scroll.get():
                self.log_text.see('end')
        self.geometry(geometry)
        self._restore_status()
        self._refresh_target_hint()
        self._update_cert_label()
        if self.server is not None:
            # The freshly built buttons always start out "stopped"; bring
            # back the state of the session that is still alive.
            self.btn_start.configure(state='disabled')
            if self._status_key != 'gui.status.stopping':
                self.btn_stop.configure(state='normal')

    # ---------- Start / stop ----------
    def _start(self) -> None:
        if self.server is not None and self.server.running:
            return
        try:
            config = self._collect_form()
        except ValueError as exc:
            messagebox.showerror(tr('gui.error.title'), str(exc))
            return
        problems = config.validate()
        if problems:
            messagebox.showerror(tr('gui.error.title'), '\n'.join('· ' + item for item in problems))
            return
        try:
            config.save()
        except OSError as exc:
            self._append_log('warn', tr('gui.log.config_save_failed', error=exc))

        self._clear_log()
        self.logger = Logger(config.log_level, callback=self._enqueue_log, echo=True)
        self.logger.info(tr('gui.log.starting', name=tr('core.app_name'), version=VERSION))
        self.logger.info(tr('gui.log.target', target=config.describe_target()))
        self.server = ProxyServer(config, self.logger)
        self.btn_start.configure(state='disabled')
        self.btn_stop.configure(state='normal')
        self._set_status('gui.status.starting')
        threading.Thread(target=self._start_server, daemon=True).start()

    def _set_status(self, key: str, color: str | None = None) -> None:
        """Set the status-bar text via a translation key, plus its colour.

        The colour lives on the Label widget itself (a StringVar has no
        configure).  Key and colour are cached so the bar can be restored
        unchanged after a language switch has rebuilt the widgets.
        """
        self._status_key = key
        if color:
            self._status_color = color
        self.var_status.set(tr(key))
        self.lbl_status.configure(foreground=self._status_color)

    def _restore_status(self) -> None:
        """Re-apply the cached status text and colour to a rebuilt status bar."""
        self.var_status.set(tr(self._status_key))
        self.lbl_status.configure(foreground=self._status_color)

    def _start_server(self) -> None:
        assert self.server is not None and self.logger is not None
        server = self.server
        logger = self.logger
        try:
            info = server.start()
        except Exception as exc:
            logger.error(tr('gui.log.start_failed', error=exc))
            self.enqueue_ui(self._on_start_failed, str(exc))
            return
        logger.info(tr('gui.log.listening', url=info.get('wss_url') or tr('gui.endpoint.disabled')))
        for listener in info.get('listeners', []):
            if listener.startswith('ws://'):
                logger.info(tr('gui.log.fallback_listener', url=listener))
        certificate = info.get('certificate')
        if certificate:
            logger.info(tr('gui.log.cert_fingerprint', thumbprint=certificate['thumbprint']))
            logger.info(tr('gui.log.cert_trust_hint'))
        self.enqueue_ui(self._on_started)

    def _on_started(self) -> None:
        self._set_status('gui.status.running', '#0b6e4f')
        self.btn_start.configure(state='disabled')
        self.btn_stop.configure(state='normal')
        self._refresh_target_hint()
        self._update_cert_label()

    def _on_start_failed(self, message: str) -> None:
        self.server = None
        self._set_status('gui.status.start_failed', '#c02b2b')
        self.btn_start.configure(state='normal')
        self.btn_stop.configure(state='disabled')
        messagebox.showerror(tr('gui.status.start_failed'), message)

    def _stop(self) -> None:
        server = self.server
        if server is None:
            return
        self._set_status('gui.status.stopping')
        self.btn_stop.configure(state='disabled')

        def _worker() -> None:
            try:
                server.stop()
            finally:
                self.enqueue_ui(self._on_stopped)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_stopped(self) -> None:
        self.server = None
        self._set_status('gui.status.stopped', '#c02b2b')
        self.btn_start.configure(state='normal')
        self.btn_stop.configure(state='disabled')
        for variable in (self.var_stat_active, self.var_stat_total, self.var_stat_up,
                         self.var_stat_down, self.var_stat_uptime):
            variable.set('0')

    # ---------- Log ----------
    def _enqueue_log(self, level: str, text: str) -> None:
        self.log_queue.put((level, text))

    def enqueue_ui(self, function, *args) -> None:
        """Schedule a UI update to run on the main thread."""
        try:
            self.after(0, lambda: function(*args))
        except tk.TclError:  # the window is already gone
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

    # ---------- Certificate ----------
    def _cert_paths(self) -> tuple[Path, Path]:
        cert_dir = resolve_path(self.var_cert_dir.get().strip() or 'certs')
        return certs.certificate_paths(cert_dir)

    def _cert_options(self) -> dict:
        """Read the certificate inputs, falling back to defaults on bad input."""
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
            self.var_cert_info.set(tr('gui.cert.info_missing'))
            return
        names = ', '.join(info.get('alt_names', ())) or 'localhost, 127.0.0.1, ::1'
        self.var_cert_info.set(tr('gui.cert.info', file=cert_path,
                                  thumbprint=info['thumbprint'], names=names))

    def _regenerate_certificate(self) -> None:
        if self.server is not None and self.server.running:
            messagebox.showinfo(tr('gui.dialog.need_stop.title'), tr('gui.dialog.need_stop.text'))
            return
        if not messagebox.askyesno(tr('gui.dialog.regen.title'), tr('gui.dialog.regen.confirm')):
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
                messagebox.showerror(tr('gui.dialog.delete_failed'), str(exc))
                return
        logger = self.logger or Logger(self.var_log_level.get().strip() or 'info',
                                       callback=self._enqueue_log, echo=False)
        try:
            certs.generate_certificate(cert_path.parent, logger=logger, **self._cert_options())
        except Exception as exc:
            messagebox.showerror(tr('gui.dialog.generate_failed'), str(exc))
            return
        self._update_cert_label()
        messagebox.showinfo(tr('gui.dialog.regen.done_title'),
                            tr('gui.dialog.regen.done_deleted') if deleted
                            else tr('gui.dialog.regen.done'))

    def _install_certificate(self) -> None:
        cert_path, _key_path = self._cert_paths()
        if not cert_path.exists():
            if not messagebox.askyesno(tr('gui.dialog.cert_missing.title'),
                                       tr('gui.dialog.cert_missing.ask')):
                return
            logger = self.logger or Logger(self.var_log_level.get().strip() or 'info',
                                           callback=self._enqueue_log, echo=False)
            try:
                certs.generate_certificate(cert_path.parent, logger=logger, **self._cert_options())
            except Exception as exc:
                messagebox.showerror(tr('gui.dialog.generate_failed'), str(exc))
                return
            self._update_cert_label()
        self._set_status('gui.status.installing_cert')
        threading.Thread(target=self._install_certificate_worker, daemon=True).start()

    def _install_certificate_worker(self) -> None:
        cert_path, _key_path = self._cert_paths()
        try:
            ok, message = certs.install_to_trust_store(cert_path, logger=self.logger)
        except Exception as exc:
            ok, message = False, str(exc)
        if self.logger is not None and message:
            self.logger.info(tr('gui.log.certutil', output=message))
        self.enqueue_ui(self._on_certificate_installed, ok, message)

    def _on_certificate_installed(self, ok: bool, message: str) -> None:
        self._update_cert_label()
        if ok:
            running = self.server is not None and self.server.running
            self._set_status('gui.status.running' if running else 'gui.status.stopped',
                             '#0b6e4f' if running else '#c02b2b')
            messagebox.showinfo(tr('gui.dialog.install_ok.title'),
                                tr('gui.dialog.install_ok.text'))
        else:
            messagebox.showerror(tr('gui.dialog.install_failed'),
                                 message or tr('gui.dialog.unknown_error'))

    def _open_certdir(self) -> None:
        cert_path, _key_path = self._cert_paths()
        cert_path.parent.mkdir(parents=True, exist_ok=True)
        self._open_path(cert_path.parent)

    # ---------- Other buttons ----------
    def _copy_endpoint(self) -> None:
        try:
            url = self._collect_form().wss_url()
        except ValueError as exc:
            messagebox.showerror(tr('gui.error.title'), str(exc))
            return
        if not url:
            messagebox.showwarning(tr('gui.dialog.no_endpoint.title'),
                                   tr('gui.dialog.no_endpoint.text'))
            return
        self.clipboard_clear()
        self.clipboard_append(url)
        self.update_idletasks()
        self._append_log('info', tr('gui.log.copied', text=url))

    def _open_status_page(self) -> None:
        try:
            config = self._collect_form()
        except ValueError as exc:
            messagebox.showerror(tr('gui.error.title'), str(exc))
            return
        if self.server is None or not self.server.running:
            messagebox.showinfo(tr('gui.dialog.not_running.title'),
                                tr('gui.dialog.not_running.text'))
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
            messagebox.showerror(tr('gui.error.title'), str(exc))
            return
        try:
            path = config.save()
        except OSError as exc:
            messagebox.showerror(tr('gui.dialog.save_failed'), str(exc))
            return
        self._append_log('info', tr('gui.log.config_saved', path=path))

    def _reset_defaults(self) -> None:
        if not messagebox.askyesno(tr('gui.dialog.reset.title'), tr('gui.dialog.reset.ask')):
            return
        self.config = config_module.Config()
        self._load_form()
        self._update_cert_label()
        self._refresh_target_hint()
        if get_language() != language_code(self.var_language.get()):
            # The defaults carry the default language, so apply it right away.
            self._switch_language()

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
            messagebox.showerror(tr('gui.dialog.open_failed'), str(exc))

    def _show_help(self) -> None:
        messagebox.showinfo(tr('gui.help.title'), tr('gui.help.text'))

    def _show_about(self) -> None:
        messagebox.showinfo(
            tr('gui.about.title'),
            tr('gui.about.text', name=tr('core.app_name'), version=VERSION, workdir=app_dir()))

    # ---------- Cloud version check ----------
    def _check_updates(self) -> None:
        """Startup check: silent, the outcome only shows up when there is news."""
        if self._closing or not self.config.update_check:
            return
        self._start_update_check(manual=False)

    def _check_updates_manual(self) -> None:
        """Menu entry: ask the endpoint and always report what came back."""
        self._start_update_check(manual=True)

    def _start_update_check(self, manual: bool) -> None:
        url = (self.config.update_url or '').strip()
        if not url:
            if manual:
                messagebox.showinfo(tr('gui.update.title'), tr('gui.update.disabled'))
            return
        if manual:
            self._enqueue_log('info', tr('gui.update.checking'))
        # Never on the UI thread: the request has its own timeout and the window
        # keeps working while it runs.
        update.check_async(url, VERSION,
                           lambda outcome: self.enqueue_ui(self._on_update_result, outcome, manual))

    def _on_update_result(self, outcome, manual: bool) -> None:
        """Runs on the UI thread once the background check is done."""
        if self._closing:
            return
        if isinstance(outcome, update.UpdateError):
            message = tr('gui.update.failed', error=outcome)
            self._enqueue_log('debug', message)
            if manual:
                messagebox.showwarning(tr('gui.update.title'), message)
            return
        current = outcome.get('current', VERSION)
        if not outcome.get('newer'):
            message = tr('gui.update.up_to_date', version=current)
            self._enqueue_log('info', message)
            if manual:
                messagebox.showinfo(tr('gui.update.title'), message)
            return
        page = (outcome.get('page') or '').strip()
        self._update_outcome = outcome
        self._apply_update_banner()
        self._enqueue_log('warn', tr('gui.update.available', version=outcome['version'],
                                     current=current))
        if page:
            self._enqueue_log('info', tr('core.cli.update_page', url=page))
        if manual:
            if page:
                ask = tr('gui.update.ask', version=outcome['version'], current=current,
                         url=page)
                if messagebox.askyesno(tr('gui.update.title'), ask):
                    webbrowser.open(page)
            else:
                messagebox.showinfo(tr('gui.update.title'),
                                    tr('gui.update.available', version=outcome['version'],
                                       current=current))

    def _apply_update_banner(self) -> None:
        """Show (or refresh) the "newer release" line; a language switch rebuilds it."""
        outcome = self._update_outcome
        if not outcome or self._closing:
            return
        text = tr('gui.update.banner', version=outcome.get('version', '?'),
                  current=outcome.get('current', VERSION))
        page = (outcome.get('page') or '').strip()
        if page:
            text += '  ' + tr('gui.update.banner_page')
            self.lbl_update.configure(cursor='hand2')
            self.lbl_update.bind('<Button-1>', lambda _event: webbrowser.open(page))
        self.lbl_update.configure(text=text)
        self.lbl_update.grid(row=1, column=0, columnspan=3, sticky='w', pady=(2, 0))

    # ---------- Shutdown ----------
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
