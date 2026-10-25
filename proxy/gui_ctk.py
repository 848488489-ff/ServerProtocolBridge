"""CustomTkinter GUI for Server Protocol Bridge.

The window is a small dashboard: a fixed sidebar for navigation, a header with
the live service state and one scrollable page per area (control, settings,
accounts, certificate, log, about).  All widgets use CustomTkinter so the
light/dark/system appearance applies everywhere, and every scroll area moves
with an eased wheel handler from :mod:`proxy.smoothscroll`.

The window never owns the service: :class:`proxy.runtime.ServiceManager` does.
That is what lets the Web UI start or stop the same proxy and lets both
interfaces show one shared log.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from . import accounts, certs, config as config_module, eagler, icon, update, webauth
from .i18n import (LANGUAGES, get_language, language_code, language_label,
                   set_language, tr, tr_in)
from .runtime import ERROR, RUNNING, STARTING, STOPPING, get_manager
from .smoothscroll import SmoothWheel
from .third_party import COMPONENTS, STDLIB_MODULES
from .utils import app_dir, human_bytes, human_duration, resolve_path
from .version import VERSION

# ---------- palette ----------
# Every colour that has a tuple follows the CustomTkinter appearance mode
# automatically: (light, dark).  Solid values are semantic and shared.
APP_BG = ('#eef1f6', '#0d1014')
SIDEBAR_BG = ('#e3e8f0', '#141920')
SIDEBAR_HOVER = ('#d7deea', '#1e242e')
CARD_BG = ('#ffffff', '#1a1f27')
CARD_BORDER = ('#d8dfe9', '#262d38')
FIELD_BG = ('#f4f6fa', '#11151b')
TEXT = ('#151c26', '#e9eef6')
MUTED = ('#5d6878', '#8b95a7')
ACCENT = '#2f6fed'
ACCENT_HOVER = '#2559c9'
SUCCESS = '#159a63'
DANGER = '#d64545'
WARN = '#c27508'

LOG_COLORS = {'debug': '#7c8798', 'info': '#2f6fed', 'warn': '#c27508',
              'error': '#d64545'}
LOG_LEVELS = ('all', 'debug', 'info', 'warn', 'error')

THEME_LABEL_KEYS = {'light': 'gui.theme.light', 'dark': 'gui.theme.dark',
                    'system': 'gui.theme.system'}
RESOURCE_PACK_MODE_LABEL_KEYS = {
    code: 'gui.resource_pack_mode.' + code for code in config_module.RESOURCE_PACK_MODES}
SPOOF_LABEL_KEYS = {code: 'gui.spoof.' + code for code in config_module.SPOOF_CLIENTS}
CERT_GENERATORS = ('auto', 'python', 'openssl')


def _font_family() -> str:
    if sys.platform == 'win32':
        return 'Microsoft YaHei UI'
    if sys.platform == 'darwin':
        return 'PingFang SC'
    return 'Noto Sans CJK SC'


def _label_for(code: str, keys: dict, fallback: str) -> str:
    key = keys.get((code or '').strip().lower())
    return tr(key) if key else (code or fallback)


def _code_for(label: str, keys: dict, fallback: str) -> str:
    text = (label or '').strip()
    for code, key in keys.items():
        for language in LANGUAGES:
            if tr_in(language, key) == text:
                return code
    return text.lower() or fallback


def theme_label(code: str) -> str:
    return _label_for(code, THEME_LABEL_KEYS, 'system')


def theme_code(label: str) -> str:
    return _code_for(label, THEME_LABEL_KEYS, 'system')


def spoof_label(code: str) -> str:
    return _label_for(code, SPOOF_LABEL_KEYS, 'off')


def spoof_code(label: str) -> str:
    return _code_for(label, SPOOF_LABEL_KEYS, 'off')


def resource_pack_mode_label(code: str) -> str:
    return _label_for(code, RESOURCE_PACK_MODE_LABEL_KEYS, 'forward')


def resource_pack_mode_code(label: str) -> str:
    return _code_for(label, RESOURCE_PACK_MODE_LABEL_KEYS, 'forward')


def generator_label(code: str) -> str:
    return {'auto': 'Auto', 'python': 'Python', 'openssl': 'OpenSSL'}.get(
        (code or 'auto').strip().lower(), 'Auto')


def generator_code(label: str) -> str:
    text = (label or '').strip().lower()
    for code in CERT_GENERATORS:
        if generator_label(code).lower() == text:
            return code
    return text if text in CERT_GENERATORS else 'auto'


def _open_url(url: str, on_failure=None) -> None:
    """Open a URL in the default browser without blocking the Tk thread."""
    def run() -> None:
        try:
            if not webbrowser.open(url):
                raise OSError(url)
        except Exception:
            if on_failure is not None:
                on_failure()

    threading.Thread(target=run, daemon=True).start()


class ScrollPage(ctk.CTkFrame):
    """A page whose content scrolls smoothly with the wheel.

    A plain Tk canvas sits under the content because CustomTkinter's own
    scrollable frame grabs the wheel globally; this one is found by walking up
    from the widget under the pointer (see ``BridgeApp._dispatch_wheel``), so
    nested pages and the log box never fight over the same event.
    """

    def __init__(self, master, app: 'BridgeApp') -> None:
        super().__init__(master, fg_color='transparent')
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0,
                                bg=app.canvas_color(), yscrollincrement=22)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        self.scrollbar = ctk.CTkScrollbar(self, command=self.canvas.yview)
        self.scrollbar.grid(row=0, column=1, sticky='ns', padx=(4, 0))
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.body = ctk.CTkFrame(self.canvas, fg_color='transparent')
        self.window = self.canvas.create_window((0, 0), window=self.body, anchor='nw')
        self.body.grid_columnconfigure(0, weight=1)
        self.body.bind('<Configure>', self._on_body_configure)
        self.canvas.bind('<Configure>', self._on_canvas_configure)
        wheel = SmoothWheel(lambda units: self.canvas.yview_scroll(units, 'units'),
                            self.canvas, units_per_notch=3)
        self.canvas._smooth_wheel = wheel
        self.body._smooth_wheel = wheel
        app.scroll_canvases.append(self.canvas)

    def _on_body_configure(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))

    def _on_canvas_configure(self, event) -> None:
        self.canvas.itemconfigure(self.window, width=event.width)
        self._on_body_configure()


class BridgeApp(ctk.CTk):
    """Main window."""

    def __init__(self) -> None:
        ctk.ThemeManager.theme['CTkFont']['family'] = _font_family()
        ctk.ThemeManager.theme['CTkFont']['size'] = 13
        super().__init__()

        self.manager = get_manager()
        self.cfg = self.manager.config
        set_language(self.cfg.language)
        self._appearance = (self.cfg.theme if self.cfg.theme in config_module.THEME_MODES
                            else 'system')
        ctk.set_appearance_mode(self._appearance)

        self.title('%s  v%s' % (tr('core.app_name'), VERSION))
        self.geometry('1160x790')
        self.minsize(1020, 690)
        self.configure(fg_color=APP_BG)
        icon.apply(self)

        self.scroll_canvases: list[tk.Canvas] = []
        self.pages: dict[str, ctk.CTkFrame] = {}
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        self.current_page = 'control'
        self._closing = False
        self._loading_form = False
        self._log_seq = 0
        self._seen_revision = self.manager.revision
        self._selected_account = ''
        self._pill_state = ''
        self._update_outcome: dict | None = None
        self._update_checking = False
        self._banner_url = ''

        self._build_fonts()
        self._build_variables()
        self._build_shell()
        # Build the control page first so _load_form() has an endpoint label to
        # update; otherwise the address row stays blank until the first poll.
        self._select_page('control')
        self._load_form(self.cfg)
        self._render_log()
        self._drain_logs()

        for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            self.bind_all(sequence, self._dispatch_wheel, add='+')
        self.protocol('WM_DELETE_WINDOW', self._on_close)
        self._poll_id = self.after(250, self._poll)
        self.after(450, self._ensure_web_ui)
        self.after(700, lambda: self._check_update(manual=False))

    # ---------- palette helpers ----------
    @staticmethod
    def _pick(color):
        if isinstance(color, tuple):
            return color[1] if ctk.get_appearance_mode() == 'Dark' else color[0]
        return color

    def canvas_color(self) -> str:
        return self._pick(APP_BG)

    def _retheme_canvases(self) -> None:
        color = self.canvas_color()
        for canvas in list(self.scroll_canvases):
            try:
                canvas.configure(bg=color)
            except tk.TclError:
                pass

    # ---------- fonts ----------
    def _build_fonts(self) -> None:
        family = _font_family()
        self.font_brand = ctk.CTkFont(family=family, size=17, weight='bold')
        self.font_nav = ctk.CTkFont(family=family, size=13)
        self.font_h1 = ctk.CTkFont(family=family, size=23, weight='bold')
        self.font_h2 = ctk.CTkFont(family=family, size=14, weight='bold')
        self.font_h3 = ctk.CTkFont(family=family, size=13, weight='bold')
        self.font_body = ctk.CTkFont(family=family, size=13)
        self.font_small = ctk.CTkFont(family=family, size=12)
        self.font_mono = ctk.CTkFont(family='Consolas', size=12)
        self.font_code = ctk.CTkFont(family='Consolas', size=15, weight='bold')

    # ---------- variables ----------
    def _build_variables(self) -> None:
        self.var_listen_host = tk.StringVar()
        self.var_wss_port = tk.StringVar()
        self.var_ws_port = tk.StringVar()
        self.var_target = tk.StringVar()
        self.var_language = tk.StringVar()
        self.var_theme = tk.StringVar(value=theme_label('system'))
        self.var_use_srv = tk.BooleanVar(value=True)
        self.var_rewrite_host = tk.BooleanVar()
        self.var_eagler_translate = tk.BooleanVar(value=True)
        self.var_login_ack = tk.BooleanVar(value=True)
        self.var_resource_pack_mode = tk.StringVar(value=resource_pack_mode_label('forward'))
        self.var_auto_exit = tk.BooleanVar(value=True)
        self.var_server_brand = tk.StringVar()
        self.var_server_brand_version = tk.StringVar()
        self.var_spoof_client = tk.StringVar(value=spoof_label('off'))
        self.var_spoof_brand = tk.StringVar()
        self.var_routes = tk.StringVar()
        self.var_log_level = tk.StringVar(value='info')
        self.var_heartbeat = tk.StringVar()
        self.var_connect_timeout = tk.StringVar()
        self.var_max_payload = tk.StringVar()
        self.var_status_cache = tk.BooleanVar(value=True)
        self.var_status_cache_ttl = tk.StringVar()
        self.var_cert_dir = tk.StringVar()
        self.var_cert_common_name = tk.StringVar()
        self.var_cert_extra = tk.StringVar()
        self.var_cert_days = tk.StringVar()
        self.var_cert_generator = tk.StringVar(value=generator_label('auto'))
        self.var_web_host = tk.StringVar(value='127.0.0.1')
        self.var_web_port = tk.StringVar(value='8765')
        self.var_web_password = tk.BooleanVar()
        self.var_web_password_value = tk.StringVar()
        self.var_web_password_confirm = tk.StringVar()
        self.var_update_check = tk.BooleanVar(value=True)
        self.var_auto_scroll = tk.BooleanVar(value=True)
        self.var_log_filter = tk.StringVar(value='all')
        for variable in (self.var_listen_host, self.var_wss_port, self.var_ws_port):
            variable.trace_add('write', self._on_endpoint_input)

    # ---------- shell ----------
    def _build_shell(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=228, corner_radius=0, fg_color=SIDEBAR_BG)
        self.sidebar.grid(row=0, column=0, sticky='nsew')
        self.sidebar.grid_propagate(False)
        self._build_sidebar()

        self.main = ctk.CTkFrame(self, fg_color='transparent')
        self.main.grid(row=0, column=1, sticky='nsew')
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(2, weight=1)

        self._build_header()

        self.page_host = ctk.CTkFrame(self.main, fg_color='transparent')
        self.page_host.grid(row=2, column=0, sticky='nsew', padx=22, pady=(0, 18))
        self.page_host.grid_columnconfigure(0, weight=1)
        self.page_host.grid_rowconfigure(0, weight=1)

        self.page_builders = {
            'control': self._build_control_page,
            'settings': self._build_settings_page,
            'accounts': self._build_accounts_page,
            'cert': self._build_cert_page,
            'log': self._build_log_page,
            'about': self._build_about_page,
        }

    def _build_sidebar(self) -> None:
        self.sidebar.grid_columnconfigure(0, weight=1)
        self.sidebar.grid_rowconfigure(2, weight=1)

        brand = ctk.CTkFrame(self.sidebar, fg_color='transparent')
        brand.grid(row=0, column=0, sticky='ew', padx=18, pady=(22, 14))
        ctk.CTkLabel(brand, text=tr('core.app_name'), font=self.font_brand,
                     text_color=TEXT, anchor='w', justify='left',
                     wraplength=190).pack(fill='x')
        ctk.CTkLabel(brand, text='v%s' % VERSION, font=self.font_small,
                     text_color=MUTED, anchor='w').pack(fill='x', pady=(2, 0))

        nav = ctk.CTkFrame(self.sidebar, fg_color='transparent')
        nav.grid(row=1, column=0, sticky='ew', padx=10)
        items = (
            ('control', 'gui.nav.control'),
            ('settings', 'gui.nav.settings'),
            ('accounts', 'gui.nav.accounts'),
            ('cert', 'gui.nav.cert'),
            ('log', 'gui.nav.log'),
            ('about', 'gui.nav.about'),
        )
        for name, key in items:
            button = ctk.CTkButton(
                nav, text=tr(key), font=self.font_nav, anchor='w', height=38,
                corner_radius=8, fg_color='transparent', text_color=TEXT,
                hover_color=SIDEBAR_HOVER,
                command=lambda page=name: self._select_page(page))
            button.pack(fill='x', pady=2)
            self.nav_buttons[name] = button

        quick = ctk.CTkFrame(self.sidebar, fg_color='transparent')
        quick.grid(row=3, column=0, sticky='ew', padx=16, pady=(10, 18))
        ctk.CTkLabel(quick, text=tr('gui.label.theme'), font=self.font_small,
                     text_color=MUTED, anchor='w').pack(fill='x')
        self.theme_menu = ctk.CTkOptionMenu(
            quick, variable=self.var_theme,
            values=[theme_label(code) for code in config_module.THEME_MODES],
            command=self._on_theme_selected, height=28, font=self.font_small,
            fg_color=FIELD_BG, button_color=FIELD_BG,
            button_hover_color=SIDEBAR_HOVER,
            text_color=TEXT, dropdown_fg_color=CARD_BG,
            dropdown_text_color=TEXT, dropdown_hover_color=SIDEBAR_HOVER)
        self.theme_menu.pack(fill='x', pady=(3, 10))
        ctk.CTkLabel(quick, text=tr('gui.language'), font=self.font_small,
                     text_color=MUTED, anchor='w').pack(fill='x')
        self.language_menu = ctk.CTkOptionMenu(
            quick, variable=self.var_language,
            values=[language_label(code) for code in LANGUAGES],
            command=self._on_language_selected, height=28, font=self.font_small,
            fg_color=FIELD_BG, button_color=FIELD_BG,
            button_hover_color=SIDEBAR_HOVER,
            text_color=TEXT, dropdown_fg_color=CARD_BG,
            dropdown_text_color=TEXT, dropdown_hover_color=SIDEBAR_HOVER)
        self.language_menu.pack(fill='x', pady=(3, 0))

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self.main, fg_color='transparent')
        header.grid(row=0, column=0, sticky='ew', padx=22, pady=(18, 12))
        header.grid_columnconfigure(0, weight=1)

        self.title_label = ctk.CTkLabel(header, text='', font=self.font_h1,
                                        text_color=TEXT, anchor='w')
        self.title_label.grid(row=0, column=0, sticky='w')
        self.subtitle_label = ctk.CTkLabel(header, text='', font=self.font_small,
                                           text_color=MUTED, anchor='w')
        self.subtitle_label.grid(row=1, column=0, sticky='w', pady=(2, 0))

        right = ctk.CTkFrame(header, fg_color='transparent')
        right.grid(row=0, column=1, rowspan=2, sticky='e')
        self.status_pill = ctk.CTkLabel(right, text=tr('gui.status.stopped'),
                                        font=self.font_h3, corner_radius=11,
                                        fg_color=MUTED, text_color='#ffffff',
                                        width=96, height=26)
        self.status_pill.pack(side='right', padx=(10, 0))
        self.update_button = ctk.CTkButton(
            right, text=tr('gui.update.button_check'), font=self.font_small,
            height=30, width=124, fg_color='transparent', border_width=1,
            border_color=CARD_BORDER, text_color=TEXT, hover_color=SIDEBAR_HOVER,
            command=self._check_update_manual)
        self.update_button.pack(side='right')

        self.banner = ctk.CTkFrame(self.main, fg_color=('#fff4e5', '#2a2113'),
                                   corner_radius=10, border_width=1,
                                   border_color=('#f0c98a', '#4a3a1c'))
        self.banner.grid(row=1, column=0, sticky='ew', padx=22, pady=(0, 10))
        self.banner.grid_columnconfigure(0, weight=1)
        self.banner_label = ctk.CTkLabel(
            self.banner, text='', font=self.font_small, text_color=TEXT,
            anchor='w', justify='left', wraplength=760)
        self.banner_label.grid(row=0, column=0, sticky='w', padx=14, pady=10)
        self.banner_button = ctk.CTkButton(
            self.banner, text=tr('gui.update.button_open'), font=self.font_small,
            height=28, width=120, fg_color=ACCENT, hover_color=ACCENT_HOVER,
            command=self._open_banner_url)
        self.banner_button.grid(row=0, column=1, padx=12, pady=8)
        self.banner.grid_remove()

    # ---------- page helpers ----------
    def _ensure_page(self, name: str):
        """Build a page the first time it is shown (keeps start-up fast)."""
        page = self.pages.get(name)
        if page is not None:
            return page
        # An interrupted rebuild must not leave an old page stacked above the
        # new one; drop anything the page map does not know about.
        known = set(self.pages.values())
        for child in list(self.page_host.winfo_children()):
            if child not in known:
                child.destroy()
        builder = self.page_builders.get(name) or self._build_control_page
        page = builder(self.page_host)
        page.grid(row=0, column=0, sticky='nsew')
        self.pages[name] = page
        return page

    def _select_page(self, name: str) -> None:
        if name not in self.page_builders:
            name = 'control'
        page = self._ensure_page(name)
        for key, other in self.pages.items():
            if key == name:
                other.grid()
            else:
                other.grid_remove()
        # Hide anything that is still gridded but no longer in the map (for
        # example a page left behind by a language rebuild).
        for child in list(self.page_host.winfo_children()):
            if child is not page:
                child.grid_remove()
        for key, button in self.nav_buttons.items():
            selected = key == name
            button.configure(fg_color=ACCENT if selected else 'transparent',
                             text_color='#ffffff' if selected else TEXT)
        titles = {
            'control': ('gui.nav.control', 'gui.page.control.subtitle'),
            'settings': ('gui.nav.settings', 'gui.page.settings.subtitle'),
            'accounts': ('gui.nav.accounts', 'gui.page.accounts.subtitle'),
            'cert': ('gui.nav.cert', 'gui.page.cert.subtitle'),
            'log': ('gui.nav.log', 'gui.page.log.subtitle'),
            'about': ('gui.nav.about', 'gui.page.about.subtitle'),
        }
        title_key, subtitle_key = titles.get(name, ('gui.nav.control', ''))
        self.title_label.configure(text=tr(title_key))
        self.subtitle_label.configure(text=tr(subtitle_key) if subtitle_key else '')
        self.current_page = name
        if name == 'accounts':
            self._refresh_accounts()
        elif name == 'cert':
            self._refresh_cert()

    def _card(self, parent, title: str | None = None,
              pady=(0, 14)) -> tuple[ctk.CTkFrame, ctk.CTkFrame]:
        card = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=12,
                            border_width=1, border_color=CARD_BORDER)
        card.pack(fill='x', pady=pady)
        if title:
            ctk.CTkLabel(card, text=title, font=self.font_h2, text_color=TEXT,
                         anchor='w').pack(fill='x', padx=16, pady=(12, 2))
        body = ctk.CTkFrame(card, fg_color='transparent')
        body.pack(fill='x', padx=16, pady=(8, 14))
        body.grid_columnconfigure(1, weight=1)
        return card, body

    def _entry(self, parent, variable, **kwargs) -> ctk.CTkEntry:
        return ctk.CTkEntry(parent, textvariable=variable, height=32,
                            font=self.font_body, fg_color=FIELD_BG,
                            border_color=CARD_BORDER, text_color=TEXT, **kwargs)

    def _field_row(self, body, row: int, label: str, widget,
                   hint: str | None = None) -> int:
        ctk.CTkLabel(body, text=label, font=self.font_body, text_color=TEXT,
                     anchor='w').grid(row=row, column=0, sticky='w',
                                      padx=(0, 14), pady=5)
        widget.grid(row=row, column=1, sticky='ew', pady=5)
        row += 1
        if hint:
            ctk.CTkLabel(body, text=hint, font=self.font_small, text_color=MUTED,
                         anchor='w', justify='left').grid(
                row=row, column=0, columnspan=2, sticky='w', pady=(0, 4))
            row += 1
        return row

    def _switch_row(self, body, row: int, text: str, variable,
                    hint: str | None = None) -> int:
        ctk.CTkSwitch(body, text=text, variable=variable, font=self.font_body,
                      text_color=TEXT, progress_color=ACCENT,
                      switch_width=40, switch_height=20).grid(
            row=row, column=0, columnspan=2, sticky='w', pady=4)
        row += 1
        if hint:
            ctk.CTkLabel(body, text=hint, font=self.font_small, text_color=MUTED,
                         anchor='w', justify='left').grid(
                row=row, column=0, columnspan=2, sticky='w', pady=(0, 4))
            row += 1
        return row

    def _option_menu(self, parent, variable, values, command=None) -> ctk.CTkOptionMenu:
        return ctk.CTkOptionMenu(
            parent, variable=variable, values=values, command=command, height=30,
            font=self.font_body, fg_color=FIELD_BG, button_color=FIELD_BG,
            button_hover_color=SIDEBAR_HOVER, text_color=TEXT,
            dropdown_fg_color=CARD_BG, dropdown_text_color=TEXT,
            dropdown_hover_color=SIDEBAR_HOVER)

    # ---------- control page ----------
    def _build_control_page(self, master) -> ScrollPage:
        page = ScrollPage(master, self)
        body = page.body

        _card, card = self._card(body, tr('gui.section.connection'))
        row = 0
        row = self._field_row(card, row, tr('gui.label.target'),
                              self._entry(card, self.var_target),
                              tr('gui.hint.endpoint'))

        ports = ctk.CTkFrame(card, fg_color='transparent')
        ctk.CTkLabel(card, text=tr('gui.label.listen_host'), font=self.font_body,
                     text_color=TEXT, anchor='w').grid(row=row, column=0,
                                                       sticky='w', padx=(0, 14), pady=5)
        ports.grid(row=row, column=1, sticky='ew', pady=5)
        ports.grid_columnconfigure(0, weight=1)
        self._entry(ports, self.var_listen_host).grid(row=0, column=0, sticky='ew')
        ctk.CTkLabel(ports, text=tr('gui.label.wss_port'), font=self.font_small,
                     text_color=MUTED).grid(row=0, column=1, padx=(10, 4))
        self._entry(ports, self.var_wss_port, width=64).grid(row=0, column=2)
        ctk.CTkLabel(ports, text=tr('gui.label.ws_port'), font=self.font_small,
                     text_color=MUTED).grid(row=0, column=3, padx=(10, 4))
        self._entry(ports, self.var_ws_port, width=64).grid(row=0, column=4)
        row += 1
        row = self._switch_row(card, row, tr('gui.label.use_srv'), self.var_use_srv)

        endpoint_row = ctk.CTkFrame(card, fg_color=FIELD_BG, corner_radius=8)
        endpoint_row.grid(row=row, column=0, columnspan=2, sticky='ew', pady=(8, 2))
        endpoint_row.grid_columnconfigure(0, weight=1)
        self.endpoint_label = ctk.CTkLabel(endpoint_row, text='',
                                           font=self.font_code, text_color=SUCCESS,
                                           anchor='w')
        self.endpoint_label.grid(row=0, column=0, sticky='w', padx=12, pady=8)
        ctk.CTkButton(endpoint_row, text=tr('gui.button.copy'), width=78,
                      height=28, font=self.font_small, fg_color=ACCENT,
                      hover_color=ACCENT_HOVER,
                      command=self._copy_endpoint).grid(row=0, column=1,
                                                        padx=8, pady=6)

        _card, actions = self._card(body, tr('gui.section.actions'))
        buttons = ctk.CTkFrame(actions, fg_color='transparent')
        buttons.grid(row=0, column=0, columnspan=2, sticky='ew')
        self.btn_start = ctk.CTkButton(buttons, text=tr('gui.button.start'),
                                       width=110, height=34, font=self.font_h3,
                                       fg_color=SUCCESS, hover_color='#0f7a4d',
                                       command=self._start)
        self.btn_start.pack(side='left')
        self.btn_stop = ctk.CTkButton(buttons, text=tr('gui.button.stop'),
                                      width=110, height=34, font=self.font_h3,
                                      fg_color=DANGER, hover_color='#b13737',
                                      state='disabled', command=self._stop)
        self.btn_stop.pack(side='left', padx=(8, 0))
        ctk.CTkButton(buttons, text=tr('gui.button.save_config'), width=118,
                      height=34, font=self.font_body, fg_color='transparent',
                      border_width=1, border_color=CARD_BORDER, text_color=TEXT,
                      hover_color=SIDEBAR_HOVER,
                      command=self._save_config).pack(side='left', padx=(8, 0))
        ctk.CTkButton(buttons, text=tr('gui.button.reset_defaults'), width=118,
                      height=34, font=self.font_body, fg_color='transparent',
                      border_width=1, border_color=CARD_BORDER, text_color=TEXT,
                      hover_color=SIDEBAR_HOVER,
                      command=self._reset_defaults).pack(side='left', padx=(8, 0))
        ctk.CTkButton(buttons, text=tr('gui.button.open_web'), width=118,
                      height=34, font=self.font_body, fg_color=ACCENT,
                      hover_color=ACCENT_HOVER,
                      command=self._open_web).pack(side='right', padx=(24, 0))
        self.web_label = ctk.CTkLabel(actions, text='', font=self.font_small,
                                      text_color=MUTED, anchor='w')
        self.web_label.grid(row=1, column=0, columnspan=2, sticky='w',
                            pady=(10, 0))

        _card, stats = self._card(body, tr('gui.section.status'), pady=(0, 0))
        tiles = ctk.CTkFrame(stats, fg_color='transparent')
        tiles.grid(row=0, column=0, columnspan=2, sticky='ew')
        self.stat_labels: dict[str, ctk.CTkLabel] = {}
        for index, (name, key) in enumerate((
                ('active', 'gui.stat.active'), ('total', 'gui.stat.total'),
                ('up', 'gui.stat.up'), ('down', 'gui.stat.down'),
                ('uptime', 'gui.stat.uptime'))):
            tiles.grid_columnconfigure(index, weight=1)
            tile = ctk.CTkFrame(tiles, fg_color=FIELD_BG, corner_radius=8)
            tile.grid(row=0, column=index, sticky='ew',
                      padx=(0 if index == 0 else 6, 0))
            value = ctk.CTkLabel(tile, text='0', font=self.font_h2,
                                 text_color=TEXT, anchor='w')
            value.pack(fill='x', padx=12, pady=(8, 0))
            ctk.CTkLabel(tile, text=tr(key), font=self.font_small,
                         text_color=MUTED, anchor='w').pack(fill='x', padx=12,
                                                            pady=(0, 8))
            self.stat_labels[name] = value
        return page

    # ---------- settings page ----------
    def _build_settings_page(self, master) -> ScrollPage:
        page = ScrollPage(master, self)
        body = page.body

        bar = ctk.CTkFrame(body, fg_color='transparent')
        bar.pack(fill='x', pady=(0, 12))
        ctk.CTkButton(bar, text=tr('gui.button.save_config'), width=140,
                      height=34, font=self.font_h3, fg_color=ACCENT,
                      hover_color=ACCENT_HOVER,
                      command=self._save_config).pack(side='left')
        ctk.CTkButton(bar, text=tr('gui.button.reset_defaults'), width=126,
                      height=34, font=self.font_body, fg_color='transparent',
                      border_width=1, border_color=CARD_BORDER, text_color=TEXT,
                      hover_color=SIDEBAR_HOVER,
                      command=self._reset_defaults).pack(side='left', padx=8)
        ctk.CTkLabel(bar, text=tr('gui.hint.endpoint'), font=self.font_small,
                     text_color=MUTED).pack(side='right')

        _card, general = self._card(body, tr('gui.settings.tab.connection'))
        row = 0
        row = self._field_row(general, row, tr('gui.language'),
                              self._option_menu(general, self.var_language,
                                                [language_label(code) for code in LANGUAGES],
                                                self._on_language_selected))
        row = self._field_row(general, row, tr('gui.label.theme'),
                              self._option_menu(general, self.var_theme,
                                                [theme_label(code) for code in config_module.THEME_MODES],
                                                self._on_theme_selected))

        _card, forwarding = self._card(body, tr('gui.section.forwarding'))
        row = 0
        row = self._field_row(forwarding, row, tr('gui.label.server_brand'),
                              self._entry(forwarding, self.var_server_brand))
        row = self._field_row(forwarding, row, tr('gui.label.server_brand_version'),
                              self._entry(forwarding, self.var_server_brand_version))
        row = self._field_row(forwarding, row, tr('gui.label.spoof_client'),
                              self._option_menu(forwarding, self.var_spoof_client,
                                                [spoof_label(code) for code in config_module.SPOOF_CLIENTS]))
        row = self._field_row(forwarding, row, tr('gui.label.spoof_brand'),
                              self._entry(forwarding, self.var_spoof_brand),
                              tr('gui.hint.spoof_brand'))
        ctk.CTkLabel(forwarding, text=tr('gui.label.routes'), font=self.font_body,
                     text_color=TEXT, anchor='nw').grid(row=row, column=0,
                                                        sticky='nw', padx=(0, 14),
                                                        pady=5)
        self.routes_box = ctk.CTkTextbox(forwarding, height=76, font=self.font_mono,
                                         fg_color=FIELD_BG, border_width=1,
                                         border_color=CARD_BORDER, text_color=TEXT)
        self.routes_box.grid(row=row, column=1, sticky='ew', pady=5)
        row += 1
        ctk.CTkLabel(forwarding, text=tr('gui.hint.routes'), font=self.font_small,
                     text_color=MUTED, anchor='w').grid(row=row, column=0,
                                                        columnspan=2, sticky='w')

        _card, protocol = self._card(body, tr('gui.section.protocol'))
        row = 0
        row = self._switch_row(protocol, row, tr('gui.label.rewrite_host'),
                               self.var_rewrite_host)
        row = self._switch_row(protocol, row, tr('gui.label.eagler_translate'),
                               self.var_eagler_translate)
        row = self._switch_row(protocol, row, tr('gui.label.login_ack'),
                               self.var_login_ack)
        row = self._field_row(protocol, row, tr('gui.label.resource_pack_mode'),
                              self._option_menu(protocol, self.var_resource_pack_mode,
                                                [resource_pack_mode_label(code)
                                                 for code in config_module.RESOURCE_PACK_MODES]))
        row = self._switch_row(protocol, row, tr('gui.label.auto_exit'),
                               self.var_auto_exit)

        _card, runtime = self._card(body, tr('gui.section.runtime'))
        row = 0
        row = self._field_row(runtime, row, tr('gui.label.log_level'),
                              self._option_menu(runtime, self.var_log_level,
                                                list(('debug', 'info', 'warn', 'error'))))
        row = self._field_row(runtime, row, tr('gui.label.heartbeat'),
                              self._entry(runtime, self.var_heartbeat, width=120))
        row = self._field_row(runtime, row, tr('gui.label.connect_timeout'),
                              self._entry(runtime, self.var_connect_timeout, width=120))
        row = self._field_row(runtime, row, tr('gui.label.max_payload'),
                              self._entry(runtime, self.var_max_payload, width=120))
        row = self._switch_row(runtime, row, tr('gui.label.status_cache'),
                               self.var_status_cache, tr('gui.label.status_cache_hint'))
        row = self._field_row(runtime, row, tr('gui.label.status_cache_ttl'),
                              self._entry(runtime, self.var_status_cache_ttl, width=120))
        row = self._switch_row(runtime, row, tr('gui.label.update_check'),
                               self.var_update_check)

        _card, web = self._card(body, tr('gui.section.web'))
        row = 0
        row = self._field_row(web, row, tr('gui.label.web_host'),
                              self._entry(web, self.var_web_host))
        row = self._field_row(web, row, tr('gui.label.web_port'),
                              self._entry(web, self.var_web_port, width=120),
                              tr('gui.hint.web_bind'))
        row = self._switch_row(web, row, tr('gui.label.web_password'),
                               self.var_web_password,
                               tr('gui.hint.web_password'))
        row = self._field_row(web, row, tr('gui.label.web_password_new'),
                              self._entry(web, self.var_web_password_value,
                                          show='*'))
        row = self._field_row(web, row, tr('gui.label.web_password_confirm'),
                              self._entry(web, self.var_web_password_confirm,
                                          show='*'),
                              tr('gui.hint.web_password_keep'))
        web_actions = ctk.CTkFrame(web, fg_color='transparent')
        web_actions.grid(row=row, column=0, columnspan=2, sticky='w', pady=(6, 0))
        ctk.CTkButton(web_actions, text=tr('gui.button.web_restart'), width=132,
                      height=30, font=self.font_small, fg_color='transparent',
                      border_width=1, border_color=CARD_BORDER, text_color=TEXT,
                      hover_color=SIDEBAR_HOVER,
                      command=self._restart_web).pack(side='left')
        self.web_settings_label = ctk.CTkLabel(
            web_actions, text='', font=self.font_small, text_color=MUTED,
            anchor='w')
        self.web_settings_label.pack(side='left', padx=12)

        _card, certificate = self._card(body, tr('gui.section.certificate'),
                                         pady=(0, 0))
        row = 0
        row = self._field_row(certificate, row, tr('gui.label.cert_dir'),
                              self._entry(certificate, self.var_cert_dir))
        row = self._field_row(certificate, row, tr('gui.label.cert_cn'),
                              self._entry(certificate, self.var_cert_common_name))
        row = self._field_row(certificate, row, tr('gui.label.cert_extra'),
                              self._entry(certificate, self.var_cert_extra))
        row = self._field_row(certificate, row, tr('gui.label.cert_days'),
                              self._entry(certificate, self.var_cert_days, width=120))
        row = self._field_row(certificate, row, tr('gui.label.cert_generator'),
                              self._option_menu(certificate, self.var_cert_generator,
                                                [generator_label(code)
                                                 for code in CERT_GENERATORS]))
        return page

    # ---------- accounts page ----------
    def _build_accounts_page(self, master) -> ScrollPage:
        page = ScrollPage(master, self)
        body = page.body

        _card, card = self._card(body, tr('gui.settings.tab.accounts'))
        add_row = ctk.CTkFrame(card, fg_color='transparent')
        add_row.grid(row=0, column=0, columnspan=2, sticky='w')
        ctk.CTkButton(add_row, text=tr('gui.accounts.add.offline'), width=120,
                      height=32, font=self.font_small, fg_color=ACCENT,
                      hover_color=ACCENT_HOVER,
                      command=self._add_offline_account).pack(side='left')
        ctk.CTkButton(add_row, text=tr('gui.accounts.add.thirdparty'), width=120,
                      height=32, font=self.font_small, fg_color='transparent',
                      border_width=1, border_color=CARD_BORDER, text_color=TEXT,
                      hover_color=SIDEBAR_HOVER,
                      command=self._add_thirdparty_account).pack(side='left', padx=8)
        ctk.CTkButton(add_row, text=tr('gui.accounts.add.microsoft'), width=120,
                      height=32, font=self.font_small, fg_color='transparent',
                      border_width=1, border_color=CARD_BORDER, text_color=TEXT,
                      hover_color=SIDEBAR_HOVER,
                      command=self._add_microsoft_account).pack(side='left')

        manage_row = ctk.CTkFrame(card, fg_color='transparent')
        manage_row.grid(row=1, column=0, columnspan=2, sticky='w', pady=(8, 0))
        ctk.CTkButton(manage_row, text=tr('gui.accounts.button.active'), width=120,
                      height=30, font=self.font_small, fg_color='transparent',
                      border_width=1, border_color=CARD_BORDER, text_color=TEXT,
                      hover_color=SIDEBAR_HOVER,
                      command=self._set_account_active).pack(side='left')
        ctk.CTkButton(manage_row, text=tr('gui.accounts.button.clear'), width=120,
                      height=30, font=self.font_small, fg_color='transparent',
                      border_width=1, border_color=CARD_BORDER, text_color=TEXT,
                      hover_color=SIDEBAR_HOVER,
                      command=self._clear_active_account).pack(side='left', padx=8)
        ctk.CTkButton(manage_row, text=tr('gui.accounts.button.remove'), width=120,
                      height=30, font=self.font_small, fg_color='transparent',
                      border_width=1, border_color=CARD_BORDER, text_color=DANGER,
                      hover_color=('#fbe9e9', '#3a1e1e'),
                      command=self._remove_account).pack(side='left')

        self.accounts_body = ctk.CTkFrame(card, fg_color='transparent')
        self.accounts_body.grid(row=2, column=0, columnspan=2, sticky='ew',
                                pady=(10, 0))

        ctk.CTkLabel(card, text=tr('gui.accounts.hint'), font=self.font_small,
                     text_color=MUTED, anchor='w', justify='left',
                     wraplength=780).grid(row=3, column=0, columnspan=2,
                                          sticky='w', pady=(10, 4))
        data_row = ctk.CTkFrame(card, fg_color='transparent')
        data_row.grid(row=4, column=0, columnspan=2, sticky='w')
        ctk.CTkLabel(data_row, text=tr('gui.accounts.data_dir',
                                       path=accounts.store_path()),
                     font=self.font_small, text_color=MUTED).pack(side='left')
        ctk.CTkButton(data_row, text=tr('gui.accounts.button.open_dir'),
                      width=110, height=28, font=self.font_small,
                      fg_color='transparent', border_width=1,
                      border_color=CARD_BORDER, text_color=TEXT,
                      hover_color=SIDEBAR_HOVER,
                      command=self._open_data_dir).pack(side='left', padx=10)
        self._refresh_accounts()
        return page

    def _refresh_accounts(self) -> None:
        if not hasattr(self, 'accounts_body'):
            return
        for child in list(self.accounts_body.winfo_children()):
            child.destroy()
        store = accounts.load_store()
        if not store.accounts:
            ctk.CTkLabel(self.accounts_body, text=tr('gui.accounts.none'),
                         font=self.font_body, text_color=MUTED,
                         anchor='w').pack(fill='x', pady=8)
            return
        for account in store.accounts:
            active = account.id == store.active
            selected = account.id == self._selected_account
            uuid_text = (account.uuid or '').strip() or '—'
            if len(uuid_text) > 13:
                uuid_text = uuid_text[:8] + '…'
            text = '%s  %s   ·   %s   ·   %s' % (
                '●' if active else '○', account.username or '?',
                tr('accounts.kind.' + account.kind), uuid_text)
            button = ctk.CTkButton(
                self.accounts_body, text=text, anchor='w', height=34,
                font=self.font_body, corner_radius=7, text_color=TEXT,
                fg_color=('#e5efff', '#1d2838') if selected else 'transparent',
                hover_color=('#dbe7f7', '#242d3a'),
                command=lambda account_id=account.id: self._select_account(account_id))
            button.pack(fill='x', pady=1)

    def _select_account(self, account_id: str) -> None:
        self._selected_account = account_id
        self._refresh_accounts()

    def _selected_account_object(self):
        if not self._selected_account:
            return None
        return accounts.load_store().get(self._selected_account)

    def _set_account_active(self) -> None:
        account = self._selected_account_object()
        if account is None:
            messagebox.showinfo(tr('gui.accounts.col.name'),
                                tr('gui.accounts.need_selection'), parent=self)
            return
        accounts.set_active(account.id)
        self._refresh_accounts()
        self._log(tr('gui.accounts.selected', name=account.username))

    def _clear_active_account(self) -> None:
        accounts.set_active('')
        self._refresh_accounts()
        self._log(tr('gui.accounts.cleared'))

    def _remove_account(self) -> None:
        account = self._selected_account_object()
        if account is None:
            messagebox.showinfo(tr('gui.accounts.remove.title'),
                                tr('gui.accounts.need_selection'), parent=self)
            return
        if not messagebox.askyesno(tr('gui.accounts.remove.title'),
                                   tr('gui.accounts.remove.ask', name=account.username),
                                   parent=self):
            return
        accounts.remove_account(account.id)
        self._selected_account = ''
        self._refresh_accounts()
        self._log(tr('gui.accounts.removed', name=account.username))

    def _open_data_dir(self) -> None:
        path = accounts.store_path().parent
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror(tr('gui.error.title'), str(exc), parent=self)
            return
        self._open_path(path)

    # ---------- certificate page ----------
    def _build_cert_page(self, master) -> ScrollPage:
        page = ScrollPage(master, self)
        body = page.body

        _card, card = self._card(body, tr('gui.section.certificate'))
        self.cert_info_label = ctk.CTkLabel(
            card, text='', font=self.font_small, text_color=TEXT, anchor='w',
            justify='left', wraplength=780)
        self.cert_info_label.grid(row=0, column=0, columnspan=2, sticky='w')
        self.cert_status_label = ctk.CTkLabel(
            card, text='', font=self.font_small, text_color=MUTED, anchor='w',
            justify='left', wraplength=780)
        self.cert_status_label.grid(row=1, column=0, columnspan=2, sticky='w',
                                    pady=(6, 0))
        buttons = ctk.CTkFrame(card, fg_color='transparent')
        buttons.grid(row=2, column=0, columnspan=2, sticky='w', pady=(12, 0))
        ctk.CTkButton(buttons, text=tr('gui.button.regen_cert'), width=132,
                      height=32, font=self.font_small, fg_color=ACCENT,
                      hover_color=ACCENT_HOVER,
                      command=self._regenerate_certificate).pack(side='left')
        ctk.CTkButton(buttons, text=tr('gui.button.install_cert'), width=132,
                      height=32, font=self.font_small, fg_color='transparent',
                      border_width=1, border_color=CARD_BORDER, text_color=TEXT,
                      hover_color=SIDEBAR_HOVER,
                      command=self._install_certificate).pack(side='left', padx=8)
        ctk.CTkButton(buttons, text=tr('gui.button.open_cert_dir'), width=120,
                      height=32, font=self.font_small, fg_color='transparent',
                      border_width=1, border_color=CARD_BORDER, text_color=TEXT,
                      hover_color=SIDEBAR_HOVER,
                      command=self._open_certdir).pack(side='left')
        ctk.CTkLabel(card, text=tr('gui.cert.hint'), font=self.font_small,
                     text_color=MUTED, anchor='w', justify='left',
                     wraplength=780).grid(row=3, column=0, columnspan=2,
                                          sticky='w', pady=(10, 0))
        self._refresh_cert()
        return page

    # ---------- log page ----------
    def _build_log_page(self, master) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(master, fg_color='transparent')
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        toolbar = ctk.CTkFrame(frame, fg_color='transparent')
        toolbar.grid(row=0, column=0, sticky='ew', pady=(0, 8))
        ctk.CTkButton(toolbar, text=tr('gui.log.clear'), width=90, height=30,
                      font=self.font_small, fg_color='transparent',
                      border_width=1, border_color=CARD_BORDER, text_color=TEXT,
                      hover_color=SIDEBAR_HOVER,
                      command=self._clear_log).pack(side='left')
        ctk.CTkSwitch(toolbar, text=tr('gui.log.auto_scroll'),
                      variable=self.var_auto_scroll, font=self.font_small,
                      text_color=TEXT, progress_color=ACCENT,
                      switch_width=40, switch_height=20).pack(side='left', padx=14)
        ctk.CTkLabel(toolbar, text=tr('gui.label.log_level'),
                     font=self.font_small, text_color=MUTED).pack(side='left',
                                                                 padx=(8, 6))
        self._option_menu(toolbar, self.var_log_filter, list(LOG_LEVELS),
                          self._on_log_filter).pack(side='left')
        ctk.CTkLabel(toolbar, text=tr('gui.log.hint'), font=self.font_small,
                     text_color=MUTED).pack(side='right')

        self.log_text = ctk.CTkTextbox(
            frame, wrap='none', font=self.font_mono, fg_color=CARD_BG,
            border_width=1, border_color=CARD_BORDER, text_color=TEXT,
            corner_radius=10, activate_scrollbars=True)
        self.log_text.grid(row=1, column=0, sticky='nsew')
        inner = self.log_text._textbox
        for level, color in LOG_COLORS.items():
            inner.tag_configure(level, foreground=color)
        wheel = SmoothWheel(lambda units: self.log_text.yview_scroll(units, 'units'),
                            inner, units_per_notch=3)
        inner._smooth_wheel = wheel
        for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            inner.bind(sequence, wheel.wheel, add='+')
        self.log_text.configure(state='disabled')
        return frame

    def _on_log_filter(self, _value=None) -> None:
        self._render_log()

    # ---------- about page ----------
    def _build_about_page(self, master) -> ScrollPage:
        page = ScrollPage(master, self)
        body = page.body

        _card, head = self._card(body, '%s  v%s' % (tr('core.app_name'), VERSION))
        ctk.CTkLabel(head, text=tr('gui.about.blurb'), font=self.font_body,
                     text_color=TEXT, anchor='w', justify='left',
                     wraplength=780).grid(row=0, column=0, columnspan=2,
                                          sticky='w')
        ctk.CTkLabel(head, text=tr('gui.about.project_license'),
                     font=self.font_small, text_color=MUTED, anchor='w',
                     justify='left', wraplength=780).grid(
            row=1, column=0, columnspan=2, sticky='w', pady=(4, 0))

        _card, card = self._card(body, tr('gui.about.components'), pady=(0, 0))
        row = 0
        for component in COMPONENTS:
            text = '%s   ·   %s' % (component['name'], component['license'])
            self._component_button(card, row, text, str(component['url']))
            row += 1
        ctk.CTkLabel(card, text=tr('gui.about.stdlib'), font=self.font_h3,
                     text_color=MUTED, anchor='w').grid(
            row=row, column=0, columnspan=2, sticky='w', pady=(10, 2))
        row += 1
        for module in STDLIB_MODULES:
            self._component_button(
                card, row, '   %s' % module,
                'https://docs.python.org/3/library/%s.html' % module)
            row += 1
        ctk.CTkLabel(card, text=tr('gui.about.hint'), font=self.font_small,
                     text_color=MUTED, anchor='w').grid(
            row=row, column=0, columnspan=2, sticky='w', pady=(10, 0))
        return page

    def _component_button(self, parent, row: int, text: str, url: str) -> None:
        button = ctk.CTkButton(
            parent, text=text, anchor='w', height=26, font=self.font_small,
            fg_color='transparent', hover_color=SIDEBAR_HOVER, text_color=TEXT,
            command=lambda: _open_url(url))
        button.grid(row=row, column=0, columnspan=2, sticky='ew')

    # ---------- form I/O ----------
    def _load_form(self, config: config_module.Config | None = None) -> None:
        config = config if config is not None else self.cfg
        self.cfg = config
        self._loading_form = True
        try:
            self.var_listen_host.set(config.listen_host)
            self.var_wss_port.set(str(config.wss_port))
            self.var_ws_port.set(str(config.ws_port))
            self.var_target.set(config.target)
            self.var_use_srv.set(bool(config.use_srv))
            self.var_rewrite_host.set(bool(config.rewrite_handshake_host))
            self.var_eagler_translate.set(bool(config.eagler_translate))
            self.var_login_ack.set(bool(config.login_ack))
            self.var_resource_pack_mode.set(
                resource_pack_mode_label(config.resource_pack_mode))
            self.var_auto_exit.set(bool(config.auto_exit))
            self.var_server_brand.set(config.server_brand)
            self.var_server_brand_version.set(config.server_brand_version)
            self.var_spoof_client.set(spoof_label(config.spoof_client))
            self.var_spoof_brand.set(config.spoof_brand)
            self.var_routes.set(config_module.format_routes_text(config.routes))
            self.var_log_level.set(config.log_level)
            self.var_heartbeat.set(str(config.heartbeat_sec))
            self.var_connect_timeout.set(str(config.connect_timeout))
            self.var_max_payload.set(str(config.max_payload_mb))
            self.var_status_cache.set(bool(config.status_cache))
            self.var_status_cache_ttl.set(str(config.status_cache_ttl))
            self.var_cert_dir.set(config.cert_dir)
            self.var_cert_common_name.set(config.cert_common_name)
            self.var_cert_extra.set(', '.join(config.cert_extra_names or []))
            self.var_cert_days.set(str(config.cert_days))
            self.var_cert_generator.set(generator_label(config.cert_generator))
            self.var_web_host.set(config.web_host)
            self.var_web_port.set(str(config.web_port))
            auth = webauth.state()
            self.var_web_password.set(auth['enabled'])
            self.var_web_password_value.set('')
            self.var_web_password_confirm.set('')
            self.var_update_check.set(bool(config.update_check))
            self.var_language.set(language_label(config.language))
            self.var_theme.set(theme_label(config.theme))
            if hasattr(self, 'routes_box'):
                self.routes_box.delete('1.0', 'end')
                self.routes_box.insert('1.0', self.var_routes.get())
        finally:
            self._loading_form = False
        self._refresh_endpoint()
        self._refresh_cert()

    def _collect_form(self) -> config_module.Config:
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
                raise ValueError(tr('gui.error.invalid_number', label=label,
                                    value=text)) from None

        config = self.cfg
        extra = [item.strip() for item in
                 self.var_cert_extra.get().replace(',', ' ').split() if item.strip()]
        routes_text = (self.routes_box.get('1.0', 'end-1c')
                       if hasattr(self, 'routes_box') else self.var_routes.get())
        self.var_routes.set(routes_text)
        config.listen_host = self.var_listen_host.get().strip() or '127.0.0.1'
        config.wss_port = as_int(self.var_wss_port, tr('gui.field.wss_port'))
        config.ws_port = as_int(self.var_ws_port, tr('gui.field.ws_port'))
        config.target = self.var_target.get().strip()
        config.use_srv = bool(self.var_use_srv.get())
        config.rewrite_handshake_host = bool(self.var_rewrite_host.get())
        config.eagler_translate = bool(self.var_eagler_translate.get())
        config.login_ack = bool(self.var_login_ack.get())
        config.resource_pack_mode = resource_pack_mode_code(
            self.var_resource_pack_mode.get())
        config.auto_exit = bool(self.var_auto_exit.get())
        config.server_brand = self.var_server_brand.get().strip()
        config.server_brand_version = self.var_server_brand_version.get().strip()
        config.spoof_client = spoof_code(self.var_spoof_client.get())
        config.spoof_brand = self.var_spoof_brand.get().strip()
        config.routes = config_module.parse_routes_text(routes_text)
        config.log_level = self.var_log_level.get().strip() or 'info'
        config.heartbeat_sec = max(0, as_int(self.var_heartbeat,
                                             tr('gui.field.heartbeat'), fallback=30))
        config.connect_timeout = max(1.0, as_float(
            self.var_connect_timeout, tr('gui.field.connect_timeout'), fallback=10.0))
        config.max_payload_mb = max(1, as_int(self.var_max_payload,
                                              tr('gui.field.max_payload'), fallback=16))
        config.status_cache = bool(self.var_status_cache.get())
        config.status_cache_ttl = max(1, min(86400, as_int(
            self.var_status_cache_ttl, tr('gui.field.status_cache_ttl'),
            fallback=30)))
        config.tls_enabled = True
        config.cert_dir = self.var_cert_dir.get().strip() or 'certs'
        config.cert_common_name = self.var_cert_common_name.get().strip() or 'localhost'
        config.cert_extra_names = extra
        config.cert_days = max(1, as_int(self.var_cert_days,
                                         tr('gui.field.cert_days'), fallback=3650))
        config.cert_generator = generator_code(self.var_cert_generator.get())
        config.web_host = self.var_web_host.get().strip() or '127.0.0.1'
        config.web_port = as_int(self.var_web_port, tr('gui.field.web_port'))
        config.update_check = bool(self.var_update_check.get())
        config.language = language_code(self.var_language.get())
        config.theme = theme_code(self.var_theme.get())
        for label, port in ((tr('gui.field.wss_port'), config.wss_port),
                            (tr('gui.field.ws_port'), config.ws_port),
                            (tr('gui.field.web_port'), config.web_port)):
            if not 0 <= port <= 65535:
                raise ValueError(tr('gui.error.port_range', label=label, value=port))
        return config

    def _on_endpoint_input(self, *_args) -> None:
        self._refresh_endpoint()

    def _refresh_endpoint(self, *_args) -> None:
        if self._loading_form or not hasattr(self, 'endpoint_label'):
            return
        try:
            wss_port = int(self.var_wss_port.get().strip() or 0)
            ws_port = int(self.var_ws_port.get().strip() or 0)
        except ValueError:
            text = tr('gui.endpoint.need_port')
        else:
            host = self.var_listen_host.get().strip() or '127.0.0.1'
            if wss_port > 0:
                text = 'wss://%s:%d' % (host, wss_port)
            elif ws_port > 0:
                text = 'ws://%s:%d' % (host, ws_port)
            else:
                text = tr('gui.endpoint.disabled')
        try:
            self.endpoint_label.configure(text=text)
        except tk.TclError:
            pass

    # ---------- language / theme ----------
    def _on_language_selected(self, _label=None) -> None:
        code = language_code(self.var_language.get())
        if code == get_language():
            return
        try:
            config = self._collect_form()
        except ValueError:
            config = self.cfg
        config.language = code
        set_language(code)
        self.manager.save_config(config)
        self.cfg = self.manager.config
        self._seen_revision = self.manager.revision
        self._rebuild()

    def _on_theme_selected(self, _label=None) -> None:
        code = theme_code(self.var_theme.get())
        try:
            config = self._collect_form()
        except ValueError:
            config = self.cfg
            config.theme = code
        config.theme = code
        self.manager.save_config(config)
        self.cfg = self.manager.config
        self._seen_revision = self.manager.revision
        self._apply_appearance(code)

    def _apply_appearance(self, mode: str) -> None:
        mode = mode if mode in config_module.THEME_MODES else 'system'
        if mode != self._appearance:
            ctk.set_appearance_mode(mode)
            self._appearance = mode
        self._retheme_canvases()

    def _rebuild(self) -> None:
        page = self.current_page
        for child in list(self.winfo_children()):
            child.destroy()
        self.scroll_canvases = []
        self.pages = {}
        self.nav_buttons = {}
        self.title('%s  v%s' % (tr('core.app_name'), VERSION))
        self._build_shell()
        self._select_page(page if page in self.page_builders else 'control')
        self._load_form(self.cfg)
        self._render_log()

    # ---------- service actions ----------
    def _start(self) -> None:
        try:
            config = self._collect_form()
        except ValueError as exc:
            messagebox.showerror(tr('gui.error.title'), str(exc), parent=self)
            return
        ok, message = self.manager.start(config)
        if not ok:
            messagebox.showerror(tr('gui.error.title'), message, parent=self)
            return
        self.cfg = self.manager.config
        self._seen_revision = self.manager.revision
        self._update_pill('starting')

    def _stop(self) -> None:
        self.manager.stop()
        self._update_pill('stopping')

    def _save_config(self) -> None:
        try:
            config = self._collect_form()
        except ValueError as exc:
            messagebox.showerror(tr('gui.error.title'), str(exc), parent=self)
            return
        if not self._apply_web_auth():
            return
        old = self.manager.config
        web_changed = ((old.web_host or '').strip() != (config.web_host or '').strip()
                       or int(old.web_port) != int(config.web_port))
        self.manager.save_config(config)
        self.cfg = self.manager.config
        self._seen_revision = self.manager.revision
        self._log(tr('gui.log.config_saved', path=config_module.CONFIG_PATH))
        if web_changed:
            self._restart_web_listener(self.cfg.web_host, self.cfg.web_port)

    def _apply_web_auth(self) -> bool:
        """Apply the access-password fields; returns False on invalid input."""
        enabled = bool(self.var_web_password.get())
        password = self.var_web_password_value.get()
        confirm = self.var_web_password_confirm.get()
        if enabled:
            if password or confirm:
                if password != confirm:
                    messagebox.showerror(tr('gui.error.title'),
                                         tr('gui.error.password_mismatch'),
                                         parent=self)
                    return False
                if len(password) < 4:
                    messagebox.showerror(tr('gui.error.title'),
                                         tr('gui.error.password_short'),
                                         parent=self)
                    return False
                webauth.set_password(password)
                self._log(tr('gui.log.web_password_on'))
            elif not webauth.has_password():
                messagebox.showerror(tr('gui.error.title'),
                                     tr('gui.error.password_required'),
                                     parent=self)
                return False
        elif webauth.is_enabled():
            webauth.disable()
            self._log(tr('gui.log.web_password_off'))
        self.var_web_password_value.set('')
        self.var_web_password_confirm.set('')
        return True

    def _reset_defaults(self) -> None:
        if not messagebox.askyesno(tr('gui.dialog.reset.title'),
                                   tr('gui.dialog.reset.ask'), parent=self):
            return
        old = self.manager.config
        self.cfg = config_module.Config()
        set_language(self.cfg.language)
        self.manager.save_config(self.cfg)
        self._seen_revision = self.manager.revision
        self._apply_appearance(self.cfg.theme)
        self._rebuild()
        if ((old.web_host or '').strip() != self.cfg.web_host
                or int(old.web_port) != int(self.cfg.web_port)):
            self._restart_web_listener(self.cfg.web_host, self.cfg.web_port)

    # ---------- log ----------
    def _log(self, message: str, level: str = 'info') -> None:
        self.manager.hub.add(level, message)

    def _drain_logs(self) -> None:
        items = self.manager.hub.snapshot(self._log_seq)
        if not items:
            return
        self._log_seq = items[-1]['seq']
        if not hasattr(self, 'log_text'):
            return
        selected = self.var_log_filter.get()
        try:
            self.log_text.configure(state='normal')
            for item in items:
                if selected != 'all' and item['level'] != selected:
                    continue
                self.log_text.insert('end', item['text'] + '\n', item['level'])
            self.log_text.configure(state='disabled')
            if self.var_auto_scroll.get():
                self.log_text.see('end')
        except tk.TclError:
            pass

    def _render_log(self) -> None:
        if not hasattr(self, 'log_text'):
            return
        items = self.manager.hub.snapshot(0)
        self._log_seq = items[-1]['seq'] if items else 0
        selected = self.var_log_filter.get()
        try:
            self.log_text.configure(state='normal')
            self.log_text.delete('1.0', 'end')
            for item in items[-1200:]:
                if selected != 'all' and item['level'] != selected:
                    continue
                self.log_text.insert('end', item['text'] + '\n', item['level'])
            self.log_text.configure(state='disabled')
            if self.var_auto_scroll.get():
                self.log_text.see('end')
        except tk.TclError:
            pass

    def _clear_log(self) -> None:
        self.manager.hub.clear()
        self._render_log()

    # ---------- polling ----------
    def _poll(self) -> None:
        if self._closing:
            return
        try:
            self._drain_logs()
            self._refresh_runtime()
            self._poll_id = self.after(250, self._poll)
        except tk.TclError:
            pass

    def _refresh_runtime(self) -> None:
        status = self.manager.status()
        self._update_pill(status['state'])

        state = status['state']
        if hasattr(self, 'btn_start'):
            self.btn_start.configure(
                state='disabled' if state in (STARTING, RUNNING, STOPPING) else 'normal')
            self.btn_stop.configure(
                state='normal' if state in (STARTING, RUNNING) else 'disabled')

        stats = status.get('stats') or {}
        if hasattr(self, 'stat_labels'):
            values = {
                'active': str(stats.get('active', 0)),
                'total': str(stats.get('total', 0)),
                'up': human_bytes(stats.get('bytes_to_server', 0)),
                'down': human_bytes(stats.get('bytes_to_client', 0)),
                'uptime': human_duration(stats.get('uptime', 0)),
            }
            for name, label in self.stat_labels.items():
                text = values.get(name, '0')
                try:
                    if label.cget('text') != text:
                        label.configure(text=text)
                except tk.TclError:
                    pass

        if hasattr(self, 'web_label'):
            url = self.manager.web_url
            text = tr('gui.web.running', url=url) if url else tr('gui.web.hint')
            try:
                if self.web_label.cget('text') != text:
                    self.web_label.configure(text=text)
            except tk.TclError:
                pass
        if hasattr(self, 'web_settings_label'):
            url = self.manager.web_url
            text = tr('gui.web.running', url=url) if url else tr('gui.web.hint')
            try:
                if self.web_settings_label.cget('text') != text:
                    self.web_settings_label.configure(text=text)
            except tk.TclError:
                pass

        if status['revision'] != self._seen_revision:
            self._seen_revision = status['revision']
            config = self.manager.config
            language = (config.language or '').lower()
            if language != get_language():
                set_language(language)
                self.cfg = config
                self._rebuild()
                return
            self.cfg = config
            self._load_form(config)
            self._apply_appearance(config.theme)

        if self.cfg.theme != self._appearance and self.cfg.theme in config_module.THEME_MODES:
            self._apply_appearance(self.cfg.theme)

    def _update_pill(self, state: str) -> None:
        if state == self._pill_state:
            return
        self._pill_state = state
        keys = {STARTING: 'gui.status.starting', RUNNING: 'gui.status.running',
                STOPPING: 'gui.status.stopping', ERROR: 'gui.status.start_failed'}
        colors = {STARTING: WARN, RUNNING: SUCCESS, STOPPING: WARN, ERROR: DANGER}
        if hasattr(self, 'status_pill'):
            try:
                self.status_pill.configure(text=tr(keys.get(state, 'gui.status.stopped')),
                                           fg_color=colors.get(state, MUTED))
            except tk.TclError:
                pass

    # ---------- wheel routing ----------
    def _dispatch_wheel(self, event):
        try:
            widget = self.winfo_containing(event.x_root, event.y_root)
        except (tk.TclError, AttributeError):
            widget = None
        while widget is not None:
            scroller = getattr(widget, '_smooth_wheel', None)
            if scroller is not None:
                return scroller.wheel(event)
            widget = getattr(widget, 'master', None)
        return None

    # ---------- other buttons ----------
    def _copy_endpoint(self) -> None:
        try:
            url = self._collect_form().wss_url()
        except ValueError as exc:
            messagebox.showerror(tr('gui.error.title'), str(exc), parent=self)
            return
        if not url:
            messagebox.showwarning(tr('gui.dialog.no_endpoint.title'),
                                   tr('gui.dialog.no_endpoint.text'), parent=self)
            return
        self.clipboard_clear()
        self.clipboard_append(url)
        self.update_idletasks()
        self._log(tr('gui.log.copied', text=url))

    def _ensure_web_ui(self) -> None:
        """Start the Web UI once, quietly, so the status page always exists."""
        if self.manager.web_url:
            return
        from .webserver import start_web_ui
        url, error = start_web_ui(self.cfg.web_host, self.cfg.web_port)
        if url:
            self.manager.web_url = url
            self._log(tr('gui.log.web_started', url=url), 'debug')
        else:
            self._log(tr('gui.web.failed', error=error), 'debug')

    def _open_web(self) -> None:
        from .webserver import start_web_ui
        url, error = start_web_ui(self.cfg.web_host, self.cfg.web_port)
        if not url:
            messagebox.showerror(tr('gui.web.title'),
                                 tr('gui.web.failed', error=error), parent=self)
            return
        self.manager.web_url = url
        self._log(tr('gui.log.web_started', url=url))
        _open_url(url)

    def _restart_web(self) -> None:
        """Apply the bind fields and rebind the Web UI listener."""
        try:
            config = self._collect_form()
        except ValueError as exc:
            messagebox.showerror(tr('gui.error.title'), str(exc), parent=self)
            return
        if not self._apply_web_auth():
            return
        self.manager.save_config(config)
        self.cfg = self.manager.config
        self._seen_revision = self.manager.revision
        self._restart_web_listener(self.cfg.web_host, self.cfg.web_port)

    def _restart_web_listener(self, host: str, port: int) -> None:
        from .webserver import restart_web_ui

        def run() -> None:
            url, error = restart_web_ui(host, port)
            self._enqueue(lambda: self._on_web_restarted(url, error))

        threading.Thread(target=run, name='web-ui-restart', daemon=True).start()

    def _on_web_restarted(self, url: str, error: str) -> None:
        if url:
            self.manager.web_url = url
            self._log(tr('gui.log.web_started', url=url))
        else:
            self._log(tr('gui.web.failed', error=error), 'warn')
            if not self._closing:
                messagebox.showerror(tr('gui.web.title'),
                                     tr('gui.web.failed', error=error), parent=self)

    def _open_workdir(self) -> None:
        self._open_path(app_dir())

    def _open_path(self, path: Path) -> None:
        def run() -> None:
            try:
                path.mkdir(parents=True, exist_ok=True)
                if sys.platform == 'win32':
                    os.startfile(str(path))  # type: ignore[attr-defined]
                elif sys.platform == 'darwin':
                    subprocess.Popen(['open', str(path)])
                else:
                    subprocess.Popen(['xdg-open', str(path)])
            except Exception as exc:
                self._enqueue(lambda message=str(exc): messagebox.showerror(
                    tr('gui.dialog.open_failed'), message, parent=self))
        threading.Thread(target=run, daemon=True).start()

    def _enqueue(self, function, *args) -> None:
        if self._closing:
            return
        try:
            self.after(0, lambda: function(*args))
        except (tk.TclError, RuntimeError):
            pass

    # ---------- certificate ----------
    def _cert_paths(self) -> tuple[Path, Path]:
        cert_dir = resolve_path(self.var_cert_dir.get().strip() or 'certs')
        return certs.certificate_paths(cert_dir)

    def _cert_options(self) -> dict:
        try:
            days = int(self.var_cert_days.get().strip() or 3650)
        except ValueError:
            days = 3650
        extra = [item for item in
                 self.var_cert_extra.get().replace(',', ' ').split() if item]
        return {
            'common_name': self.var_cert_common_name.get().strip() or 'localhost',
            'extra_names': extra,
            'days': max(1, days),
            'generator': generator_code(self.var_cert_generator.get()),
        }

    def _cert_logger(self):
        if self.manager.logger is not None:
            return self.manager.logger
        from .logger import Logger
        return Logger(self.var_log_level.get().strip() or 'info',
                      callback=self.manager.hub.add, echo=False)

    def _refresh_cert(self) -> None:
        if not hasattr(self, 'cert_info_label'):
            return
        try:
            cert_path, key_path = self._cert_paths()
        except Exception:
            return
        info = certs.inspect_certificate(cert_path, key_path) if cert_path.exists() else None
        if info is None:
            text = tr('gui.cert.info_missing')
        else:
            names = ', '.join(info.get('alt_names') or ()) or 'localhost, 127.0.0.1, ::1'
            text = tr('gui.cert.info', file=cert_path,
                      thumbprint=info['thumbprint'], names=names)
        try:
            self.cert_info_label.configure(text=text)
        except tk.TclError:
            pass

    def _regenerate_certificate(self) -> None:
        if self.manager.running:
            messagebox.showinfo(tr('gui.dialog.need_stop.title'),
                                tr('gui.dialog.need_stop.text'), parent=self)
            return
        if not messagebox.askyesno(tr('gui.dialog.regen.title'),
                                   tr('gui.dialog.regen.confirm'), parent=self):
            return
        cert_path, key_path = self._cert_paths()
        for path in (cert_path, key_path):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                messagebox.showerror(tr('gui.dialog.delete_failed'), str(exc),
                                     parent=self)
                return
        try:
            certs.generate_certificate(cert_path.parent,
                                       logger=self._cert_logger(),
                                       **self._cert_options())
        except Exception as exc:
            messagebox.showerror(tr('gui.dialog.generate_failed'), str(exc),
                                 parent=self)
            return
        self._refresh_cert()
        messagebox.showinfo(tr('gui.dialog.regen.done_title'),
                            tr('gui.dialog.regen.done'), parent=self)

    def _install_certificate(self) -> None:
        cert_path, _key_path = self._cert_paths()
        if not cert_path.exists():
            if not messagebox.askyesno(tr('gui.dialog.cert_missing.title'),
                                       tr('gui.dialog.cert_missing.ask'), parent=self):
                return
            try:
                certs.generate_certificate(cert_path.parent,
                                           logger=self._cert_logger(),
                                           **self._cert_options())
            except Exception as exc:
                messagebox.showerror(tr('gui.dialog.generate_failed'), str(exc),
                                     parent=self)
                return
            self._refresh_cert()
        if hasattr(self, 'cert_status_label'):
            self.cert_status_label.configure(text=tr('gui.status.installing_cert'))

        def worker() -> None:
            try:
                ok, message = certs.install_to_trust_store(cert_path,
                                                           logger=self.manager.logger)
            except Exception as exc:
                ok, message = False, str(exc)
            self._enqueue(self._on_certificate_installed, ok, message)

        threading.Thread(target=worker, daemon=True).start()

    def _on_certificate_installed(self, ok: bool, message: str) -> None:
        self._refresh_cert()
        if hasattr(self, 'cert_status_label'):
            self.cert_status_label.configure(text='')
        if ok:
            messagebox.showinfo(tr('gui.dialog.install_ok.title'),
                                tr('gui.dialog.install_ok.text'), parent=self)
        else:
            messagebox.showerror(tr('gui.dialog.install_failed'),
                                 message or tr('gui.dialog.unknown_error'),
                                 parent=self)

    def _open_certdir(self) -> None:
        cert_path, _key_path = self._cert_paths()
        self._open_path(cert_path.parent)

    # ---------- accounts: add dialogs ----------
    def _add_offline_account(self) -> None:
        dialog = ctk.CTkInputDialog(text=tr('gui.accounts.offline.prompt'),
                                    title=tr('gui.accounts.add.offline'))
        name = dialog.get_input()
        if not name:
            return
        name = name.strip()
        if not eagler.USERNAME_PATTERN.match(name):
            messagebox.showerror(tr('gui.accounts.add.offline'),
                                 tr('gui.accounts.offline.bad_name'), parent=self)
            return
        account = accounts.add_account(
            accounts.Account(kind=accounts.KIND_OFFLINE, username=name))
        self._selected_account = account.id
        self._refresh_accounts()
        self._log(tr('gui.accounts.added_offline', name=name))

    def _add_thirdparty_account(self) -> None:
        dialog = ctk.CTkToplevel(self)
        dialog.title(tr('gui.accounts.thirdparty.title'))
        dialog.geometry('500x380')
        dialog.transient(self)
        frame = ctk.CTkFrame(dialog, fg_color='transparent')
        frame.pack(fill='both', expand=True, padx=18, pady=16)
        frame.grid_columnconfigure(1, weight=1)

        var_server = tk.StringVar()
        var_user = tk.StringVar()
        var_pass = tk.StringVar()
        for index, (key, variable, secret) in enumerate((
                ('gui.accounts.thirdparty.server', var_server, False),
                ('gui.accounts.thirdparty.username', var_user, False),
                ('gui.accounts.thirdparty.password', var_pass, True))):
            ctk.CTkLabel(frame, text=tr(key), font=self.font_body,
                         text_color=TEXT, anchor='w').grid(
                row=index, column=0, sticky='w', padx=(0, 10), pady=6)
            entry = self._entry(frame, variable)
            if secret:
                entry.configure(show='*')
            entry.grid(row=index, column=1, sticky='ew', pady=6)

        ctk.CTkLabel(frame, text=tr('gui.accounts.thirdparty.note'),
                     font=self.font_small, text_color=MUTED, anchor='w',
                     justify='left', wraplength=440).grid(
            row=3, column=0, columnspan=2, sticky='w', pady=(2, 6))
        ctk.CTkLabel(frame, text=tr('gui.accounts.legal'), font=self.font_small,
                     text_color=MUTED, anchor='w', justify='left',
                     wraplength=440).grid(row=4, column=0, columnspan=2,
                                          sticky='w', pady=(0, 6))
        status = ctk.CTkLabel(frame, text='', font=self.font_small,
                              text_color=MUTED, anchor='w')
        status.grid(row=5, column=0, columnspan=2, sticky='w')
        buttons = ctk.CTkFrame(frame, fg_color='transparent')
        buttons.grid(row=6, column=0, columnspan=2, sticky='e', pady=(10, 0))
        ok_button = ctk.CTkButton(buttons, text=tr('gui.accounts.thirdparty.submit'),
                                  width=110, height=32, font=self.font_small,
                                  fg_color=ACCENT, hover_color=ACCENT_HOVER,
                                  command=lambda: submit())
        ok_button.pack(side='right')
        ctk.CTkButton(buttons, text=tr('gui.settings.close'), width=90, height=32,
                      font=self.font_small, fg_color='transparent',
                      border_width=1, border_color=CARD_BORDER, text_color=TEXT,
                      hover_color=SIDEBAR_HOVER,
                      command=dialog.destroy).pack(side='right', padx=8)

        def failure(message: str) -> None:
            if dialog.winfo_exists():
                ok_button.configure(state='normal')
                status.configure(text='')
                messagebox.showerror(tr('gui.accounts.thirdparty.title'), message,
                                     parent=dialog)

        def success(account) -> None:
            accounts.add_account(account)
            self._selected_account = account.id
            self._refresh_accounts()
            self._log(tr('gui.accounts.thirdparty.added', name=account.username))
            if dialog.winfo_exists():
                dialog.destroy()

        def submit() -> None:
            server = var_server.get().strip()
            user = var_user.get().strip()
            password = var_pass.get()
            if not (server and user and password):
                messagebox.showerror(tr('gui.accounts.thirdparty.title'),
                                     tr('gui.accounts.thirdparty.missing'),
                                     parent=dialog)
                return
            ok_button.configure(state='disabled')
            status.configure(text=tr('gui.accounts.thirdparty.busy'))

            def worker() -> None:
                try:
                    account = accounts.thirdparty_authenticate(server, user, password)
                except Exception as exc:
                    self._enqueue(failure, str(exc))
                    return
                self._enqueue(success, account)

            threading.Thread(target=worker, daemon=True).start()

        dialog.bind('<Return>', lambda _event: submit())
        dialog.bind('<Escape>', lambda _event: dialog.destroy())
        dialog.grab_set()

    def _add_microsoft_account(self) -> None:
        dialog = ctk.CTkToplevel(self)
        dialog.title(tr('gui.accounts.ms.title'))
        dialog.geometry('540x360')
        dialog.transient(self)
        frame = ctk.CTkFrame(dialog, fg_color='transparent')
        frame.pack(fill='both', expand=True, padx=18, pady=16)

        ctk.CTkLabel(frame, text=tr('gui.accounts.ms.intro'), font=self.font_body,
                     text_color=TEXT, anchor='w', justify='left',
                     wraplength=480).pack(fill='x')
        code_row = ctk.CTkFrame(frame, fg_color='transparent')
        code_row.pack(fill='x', pady=(12, 0))
        ctk.CTkLabel(code_row, text=tr('gui.accounts.ms.code_label'),
                     font=self.font_body, text_color=MUTED).pack(side='left')
        var_code = tk.StringVar(value='--------')
        ctk.CTkLabel(code_row, textvariable=var_code, font=self.font_code,
                     text_color=ACCENT).pack(side='left', padx=(10, 0))
        var_link = tk.StringVar(value='')
        link = self._entry(frame, var_link)
        link.configure(state='readonly')
        link.pack(fill='x', pady=(10, 0))
        status = ctk.CTkLabel(frame, text=tr('gui.accounts.ms.starting'),
                              font=self.font_small, text_color=MUTED, anchor='w',
                              justify='left', wraplength=480)
        status.pack(fill='x', pady=(10, 0))
        buttons = ctk.CTkFrame(frame, fg_color='transparent')
        buttons.pack(fill='x', pady=(12, 0))
        stopped = threading.Event()

        def close() -> None:
            stopped.set()
            dialog.destroy()

        def open_link() -> None:
            if var_link.get():
                _open_url(var_link.get(), lambda: self._enqueue(
                    lambda: messagebox.showinfo(tr('gui.accounts.ms.title'),
                                                tr('gui.accounts.ms.open_failed'),
                                                parent=dialog)))

        def copy_code() -> None:
            self.clipboard_clear()
            self.clipboard_append(var_code.get())
            self.update_idletasks()
            status.configure(text=tr('gui.accounts.ms.code_copied'))

        def show(info) -> None:
            if not dialog.winfo_exists():
                return
            var_code.set(str(info.get('user_code') or ''))
            var_link.set(str(info.get('verification_uri') or ''))
            status.configure(text=tr('gui.accounts.ms.waiting'))
            open_link()

        def failure(message: str, verify: bool) -> None:
            if not dialog.winfo_exists():
                return
            lowered = message.lower()
            if verify and ('ssl' in lowered or 'certificate' in lowered):
                if messagebox.askyesno(tr('gui.accounts.ms.ssl_title'),
                                       tr('gui.accounts.ms.ssl_ask'),
                                       parent=dialog):
                    status.configure(text=tr('gui.accounts.ms.retrying_ssl'))
                    stopped.clear()
                    threading.Thread(target=worker, args=(False,),
                                     daemon=True).start()
                    return
            var_code.set('--------')
            var_link.set('')
            status.configure(text=message, text_color=DANGER)

        def done(account) -> None:
            accounts.add_account(account)
            self._selected_account = account.id
            self._refresh_accounts()
            self._log(tr('gui.accounts.ms.added', name=account.username))
            stopped.set()
            if dialog.winfo_exists():
                dialog.destroy()

        def worker(verify: bool = True) -> None:
            if stopped.is_set():
                return
            try:
                info = accounts.microsoft_device_start(verify)
            except Exception as exc:
                self._enqueue(failure, str(exc), verify)
                return
            self._enqueue(show, info)
            try:
                account = accounts.microsoft_device_poll(info, verify)
            except Exception as exc:
                self._enqueue(failure, str(exc), verify)
                return
            if not stopped.is_set():
                self._enqueue(done, account)

        ctk.CTkButton(buttons, text=tr('gui.accounts.ms.copy'), width=110,
                      height=32, font=self.font_small, fg_color=ACCENT,
                      hover_color=ACCENT_HOVER,
                      command=copy_code).pack(side='left')
        ctk.CTkButton(buttons, text=tr('gui.accounts.ms.open'), width=110,
                      height=32, font=self.font_small, fg_color='transparent',
                      border_width=1, border_color=CARD_BORDER, text_color=TEXT,
                      hover_color=SIDEBAR_HOVER,
                      command=open_link).pack(side='left', padx=8)
        ctk.CTkButton(buttons, text=tr('gui.settings.close'), width=90, height=32,
                      font=self.font_small, fg_color='transparent',
                      border_width=1, border_color=CARD_BORDER, text_color=TEXT,
                      hover_color=SIDEBAR_HOVER,
                      command=close).pack(side='right')
        dialog.protocol('WM_DELETE_WINDOW', close)
        dialog.bind('<Escape>', lambda _event: close())
        dialog.grab_set()
        threading.Thread(target=worker, daemon=True).start()

    # ---------- updates ----------
    def _check_update_manual(self) -> None:
        self._check_update(manual=True)

    def _check_update(self, manual: bool = False) -> None:
        if self._update_checking:
            return
        if not manual and not self.cfg.update_check:
            return
        self._update_manual = manual
        self._update_checking = True
        if hasattr(self, 'update_button'):
            self.update_button.configure(state='disabled',
                                         text=tr('gui.update.checking'))
        if manual:
            self._log(tr('gui.update.checking'))
        update.check_async(
            update.DEFAULT_UPDATE_URL, VERSION,
            callback=lambda outcome: self._enqueue(self._on_update_result, outcome))

    def _on_update_result(self, outcome) -> None:
        self._update_checking = False
        if hasattr(self, 'update_button'):
            self.update_button.configure(state='normal',
                                         text=tr('gui.update.button_check'))
        if isinstance(outcome, update.UpdateError):
            message = tr('gui.update.failed', error=outcome)
            self._log(message, 'debug')
            if getattr(self, '_update_manual', False):
                messagebox.showinfo(tr('gui.update.title'), message, parent=self)
            return
        if not outcome.get('newer'):
            message = tr('gui.update.up_to_date', version=outcome.get('current', VERSION))
            self._log(message, 'info')
            if getattr(self, '_update_manual', False):
                messagebox.showinfo(tr('gui.update.title'), message, parent=self)
            return
        self._update_outcome = outcome
        key = ('gui.update.must_update' if outcome.get('must_update')
               else 'gui.update.available')
        message = tr(key, version=outcome.get('version', '?'),
                     current=outcome.get('current', VERSION))
        self._log(message, 'warn')
        self._show_banner(message, bool(outcome.get('must_update')),
                          (outcome.get('page') or '').strip())

    def _show_banner(self, text: str, warn: bool, url: str = '') -> None:
        if not hasattr(self, 'banner'):
            return
        self._banner_url = url
        self.banner_label.configure(text=text)
        self.banner.configure(
            fg_color=('#ffe9e9', '#2a1616') if warn else ('#fff4e5', '#2a2113'),
            border_color=('#e7a7a7', '#5a2a2a') if warn else ('#f0c98a', '#4a3a1c'))
        if self._banner_url:
            self.banner_button.grid()
        else:
            self.banner_button.grid_remove()
        self.banner.grid()

    def _open_banner_url(self) -> None:
        if self._banner_url:
            _open_url(self._banner_url)

    # ---------- shutdown ----------
    def _on_close(self) -> None:
        self._closing = True
        try:
            self.manager.save_config(self._collect_form())
        except Exception:
            pass
        try:
            if getattr(self, '_poll_id', None):
                self.after_cancel(self._poll_id)
        except Exception:
            pass
        try:
            self.manager.shutdown()
        except Exception:
            pass
        self.destroy()


def main() -> int:
    app = BridgeApp()
    app.mainloop()
    return 0





