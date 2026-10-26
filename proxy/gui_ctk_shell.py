"""Bridge window skeleton: construction, the first paint, theme and DPI handling, the font table, the Tk variables and the sidebar/header shell.  Split from gui_ctk.py for file size.

Method bodies are unchanged; they are methods of BridgeApp, reached
through ``self``.
"""

from __future__ import annotations

import customtkinter as ctk
import tkinter as tk
from . import (config as config_module, dpi, icon)
from .gui_ctk import (ACCENT, ACCENT_HOVER, APP_BG, CARD_BG, CARD_BORDER, FIELD_BG, MUTED, SETTINGS_TABS, SIDEBAR_BG, SIDEBAR_HOVER, TEXT, _font_family, generator_label, log_level_label, log_limit_label, resource_pack_mode_label, spoof_label, theme_label)
from .i18n import (LANGUAGES, language_label, set_language, tr)
from .runtime import get_manager
from .version import VERSION
class BridgeShell:
    """BridgeShell mixin for BridgeApp."""
    def __init__(self) -> None:
        # Arm DPI awareness before CTk allocates the root window; CTk only does
        # it afterwards, so the first frames would otherwise be painted by a
        # process that still reports itself as unaware.
        dpi.activate()

        ctk.ThemeManager.theme['CTkFont']['family'] = _font_family()
        ctk.ThemeManager.theme['CTkFont']['size'] = 13
        super().__init__()

        self.manager = get_manager()
        self.cfg = self.manager.config
        set_language(self.cfg.language)
        self._appearance = (self.cfg.theme if self.cfg.theme in config_module.THEME_MODES
                            else 'system')
        ctk.set_appearance_mode(self._appearance)

        self.title(self._window_title())
        self.geometry('1160x790')
        self.minsize(1020, 690)
        self.configure(fg_color=APP_BG)
        icon.apply(self, report=lambda message: self._log(message, 'warn'))

        self.scroll_canvases: list[tk.Canvas] = []
        self.pages: dict[str, ctk.CTkFrame] = {}
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        self._settings_tab_cache: dict[str, ctk.CTkFrame] = {}
        self.current_page = 'control'
        self._closing = False
        self._loading_form = False
        self._log_seq = 0
        self._seen_revision = self.manager.revision
        self._selected_account = ''
        self._pill_state = ''
        self._post_first_paint = False
        self._update_outcome: dict | None = None
        self._update_checking = False
        self._banner_url = ''

        self._build_fonts()
        self._build_variables()
        self._build_shell()

        # CTk rescales its own widgets when the window crosses to a monitor with
        # a different factor, but it never visits the raw tk surfaces -- the
        # scroll canvases and the component table.  Follow along.
        dpi.watch(self, self._on_dpi_change)

        for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
            self.bind_all(sequence, self._dispatch_wheel, add='+')
        self.protocol('WM_DELETE_WINDOW', self._on_close)
        self._poll_id = self.after(250, self._poll)
        self.after(450, self._ensure_web_ui)
        self.after(700, lambda: self._check_update(manual=False))

        # The shell is enough on the first paint; the dashboard, the form and
        # the log buffer come in the next few ticks.  Doing them inside the
        # constructor held up the window until every widget existed.
        self.after(0, self._after_first_paint)
    def _after_first_paint(self) -> None:
        """Fill the shell that was just shown, starting with the dashboard."""
        if self._closing or self._post_first_paint:
            return
        self._post_first_paint = True
        self._select_page(self.current_page or 'control')
        self._load_form(self.cfg)
        self._render_log()
        self._drain_logs()
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
        # ttk ignores the appearance mode, so a component table that is cached
        # off-screen when the theme flips would keep the old colours.
        self._style_component_list()
    def _on_dpi_change(self, *_ignored) -> None:
        """Re-apply the DPI factor to the surfaces CTk does not manage.

        CTk's update loop fires this when the window crosses to a monitor with a
        different scaling level; its own widgets rescale automatically, but the
        scroll canvases and the component table keep their old pixel values.
        """
        for canvas in list(self.scroll_canvases):
            try:
                if canvas.winfo_exists():
                    canvas.configure(yscrollincrement=dpi.scale(self, 22))
            except tk.TclError:
                pass
        self._apply_tree_geometry()
    def _apply_tree_geometry(self) -> None:
        """Set the component table's column widths for the current DPI."""
        tree = getattr(self, 'about_tree', None)
        if tree is None:
            return
        try:
            if not tree.winfo_exists():
                return
        except tk.TclError:
            return
        tree.column('name', width=dpi.scale(self, 340),
                    minwidth=dpi.scale(self, 160))
        tree.column('license', width=dpi.scale(self, 340),
                    minwidth=dpi.scale(self, 140))
        self._style_component_list()
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
        self.var_log_level = tk.StringVar(value=log_level_label('info'))
        self.var_log_limit = tk.StringVar(value=log_limit_label('4000'))
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
        self.var_log_filter = tk.StringVar(value=log_level_label('all'))
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

        self.settings_tab_builders = {
            key: getattr(self, '_settings_tab_' + key) for key, _label in SETTINGS_TABS
        }
    def _window_title(self) -> str:
        """Title bar text; recomputed on every language switch, since the bar
        is not part of the widget tree that ``_refresh_shell`` rebuilds."""
        return '%s  v%s' % (tr('core.app_name'), VERSION)
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
