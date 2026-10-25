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

import customtkinter as ctk
import sys
import threading
import tkinter as tk
import webbrowser
from . import (config as config_module, dpi, icon, update)
from .i18n import (LANGUAGES, tr, tr_in)
from .smoothscroll import SmoothWheel
from .version import VERSION
from tkinter import (messagebox, ttk)
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
# How many log lines the hub keeps.  Offered as presets so the choice is one
# click, but the picker also accepts a plain number: log_limit_code falls back
# to whatever text the user typed, so a 7500 is as valid as one of these.
LOG_LINE_LIMITS = ('1000', '4000', '10000', '20000', '50000')
# The log text widget is not the LogHub: the hub caps itself at 4000 entries, but
# the widget only ever grew, so a long busy session left tens of thousands of
# lines in one tk.Text and every repaint got slower.  Both render paths keep the
# newest LOG_LINE_LIMIT lines.
LOG_LINE_LIMIT = 1200

THEME_LABEL_KEYS = {'light': 'gui.theme.light', 'dark': 'gui.theme.dark',
                    'system': 'gui.theme.system'}
RESOURCE_PACK_MODE_LABEL_KEYS = {
    code: 'gui.resource_pack_mode.' + code for code in config_module.RESOURCE_PACK_MODES}
SPOOF_LABEL_KEYS = {code: 'gui.spoof.' + code for code in config_module.SPOOF_CLIENTS}
CERT_GENERATORS = ('auto', 'python', 'openssl')
GENERATOR_LABEL_KEYS = {code: 'gui.cert_generator.' + code for code in CERT_GENERATORS}
LOG_LEVEL_LABEL_KEYS = {code: 'gui.log_level.' + code for code in LOG_LEVELS}
LOG_LIMIT_LABEL_KEYS = {code: 'gui.log_limit.' + code for code in LOG_LINE_LIMITS}

# (key, title key) of the settings cards, in display order.  Only one card is in
# the widget tree at a time; see _build_settings_page for why.
SETTINGS_TABS = (
    ('forward', 'gui.section.forwarding'),
    ('protocol', 'gui.section.protocol'),
    ('runtime', 'gui.section.runtime'),
    ('web', 'gui.section.web'),
    ('cert', 'gui.section.certificate'),
)


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
    return _label_for(code, GENERATOR_LABEL_KEYS, 'auto')


def generator_code(label: str) -> str:
    return _code_for(label, GENERATOR_LABEL_KEYS, 'auto')


def log_level_label(code: str) -> str:
    return _label_for(code, LOG_LEVEL_LABEL_KEYS, 'all')


def log_level_code(label: str) -> str:
    return _code_for(label, LOG_LEVEL_LABEL_KEYS, 'all')


def log_limit_label(code: str) -> str:
    return _label_for(str(code), LOG_LIMIT_LABEL_KEYS, '4000')


def log_limit_code(label: str) -> int:
    """The line count behind a log-limit picker value.

    A preset label comes back as its number; free text does too when it parses
    as an integer, and anything else falls back to the default so a wrong entry
    never disables the cap.
    """
    text = str(label or '').strip()
    if text.isdigit():
        value = int(text)
    else:
        value = _code_for(text, LOG_LIMIT_LABEL_KEYS, '4000')
        value = int(value) if str(value).isdigit() else 4000
    return max(50, min(100000, value))


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


def _style_opt(style: ttk.Style, name: str, **options) -> None:
    """style.configure() that degrades by option instead of all-or-nothing.

    Tk checks every option before applying any of them, so a single option that
    this Tk build no longer recognises would drop the whole call -- colours and
    fonts along with it.  Retrying without each option keeps everything Tk
    still accepts.
    """
    keys = list(options)
    for skip in range(len(keys), -1, -1):
        subset = {k: options[k] for k in keys[:skip]}
        try:
            style.configure(name, **subset)
            return
        except tk.TclError:
            continue


def _style_map(style: ttk.Style, name: str, **states) -> None:
    """style.map() with the same tolerant behaviour as _style_opt."""
    keys = list(states)
    for skip in range(len(keys), -1, -1):
        subset = {k: states[k] for k in keys[:skip]}
        try:
            style.map(name, **subset)
            return
        except tk.TclError:
            continue


def _no_idle(*_args, **_kwargs) -> None:
    """Placeholder for tk.Misc.update_idletasks while a widget is mid-draw."""
    return None


# ---------------------------------------------------------------------------
# CustomTkinter's CTkOptionMenu._draw and CTkScrollbar._draw both end with
# self._canvas.update_idletasks() (ctk_optionmenu.py:223, ctk_scrollbar.py:168).
# That call is global: it flushes every pending <Configure> in the window, and
# each CTk widget's _update_dimensions_event can post more Configure events
# while doing so.  A scrollbar's set() callback already runs inside idle
# processing -- it fires whenever the canvas scrollregion changes, which is on
# every body resize -- so the flush re-enters idle processing and the work
# multiplies.  cProfile on one settings tab switch took 0.85 s:
#
#      4/1   0.499 s   ctk_scrollbar.py:135(_draw)   <- called from set()
#      5/1   0.548 s   tkinter update_idletasks
#    114/9   0.510 s   tkinter __call__ (the queued handlers)
#
# Neither _draw depends on the flush: both only read _current_width /
# _current_height and colour state, all of which _set_dimensions sets before
# _draw runs, and the canvas already has an explicit size.  The queued
# configure events still run -- once -- when the mainloop gets to them.
# ---------------------------------------------------------------------------

_SCROLLBAR_DRAW = ctk.CTkScrollbar._draw
_OPTIONMENU_DRAW = ctk.CTkOptionMenu._draw


def _draw_without_flush(draw, self, no_color_updates=False):
    """Run a CTk _draw with its trailing global idle flush suppressed."""
    canvas = getattr(self, '_canvas', None)
    if canvas is None or canvas.update_idletasks is _no_idle:
        # No canvas yet, or an outer _draw already suppressed the flush.
        return draw(self, no_color_updates)
    flush = canvas.update_idletasks
    canvas.update_idletasks = _no_idle
    try:
        return draw(self, no_color_updates)
    finally:
        canvas.update_idletasks = flush


ctk.CTkScrollbar._draw = lambda self, no_color_updates=False: \
    _draw_without_flush(_SCROLLBAR_DRAW, self, no_color_updates)
ctk.CTkOptionMenu._draw = lambda self, no_color_updates=False: \
    _draw_without_flush(_OPTIONMENU_DRAW, self, no_color_updates)

# ---------------------------------------------------------------------------
# Same trap a step further up the call chain.  Every CTk widget's
# _set_appearance_mode ends with super().update_idletasks()
# (ctk_base_class.py:223 and the widget-level overrides), and
# ctk.set_appearance_mode() calls it on all of them.  So flipping the theme
# was 259 individual global flushes -- measured at 430 ms here for a 430 ms
# window redraw, most of it the flushes themselves.  The draw already applied
# the new colours; only the layout was being force-settled 259 times.
# ---------------------------------------------------------------------------

_APPEARANCE_CLASSES = (ctk.CTkFrame, ctk.CTkLabel, ctk.CTkButton, ctk.CTkEntry,
                       ctk.CTkSwitch, ctk.CTkOptionMenu, ctk.CTkTextbox,
                       ctk.CTkScrollableFrame, ctk.CTkScrollbar, ctk.CTkProgressBar)

for _cls in _APPEARANCE_CLASSES:
    _orig = getattr(_cls, '_set_appearance_mode')

    def _wrapped(self, mode_string, _orig=_orig):
        flush = self.update_idletasks
        self.update_idletasks = _no_idle
        try:
            return _orig(self, mode_string)
        finally:
            self.update_idletasks = flush

    _cls._set_appearance_mode = _wrapped


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
        # Raw tk.Canvas, which CTk never scales -- the increment is set from the
        # window's DPI factor so a wheel notch moves the same visual distance at
        # any scaling level.
        self.canvas = tk.Canvas(self, highlightthickness=0, bd=0,
                                bg=app.canvas_color(),
                                yscrollincrement=dpi.scale(app, 22))
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


from .gui_ctk_shell import BridgeShell
from .gui_ctk_pages import BridgePages
from .gui_ctk_control import BridgeControl
from .gui_ctk_settings import BridgeSettings
from .gui_ctk_accounts import BridgeAccounts
from .gui_ctk_accounts_add import BridgeAccountsAdd
from .gui_ctk_cert import BridgeCert
from .gui_ctk_log import BridgeLog
from .gui_ctk_form import BridgeForm
from .gui_ctk_web import BridgeWeb
from .gui_ctk_about import BridgeAbout


class BridgeApp(BridgeShell, BridgePages, BridgeControl, BridgeSettings, BridgeAccounts, BridgeAccountsAdd, BridgeCert, BridgeLog, BridgeForm, BridgeWeb, BridgeAbout, ctk.CTk):
    """Main window."""


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


def main() -> int:
    try:
        icon.init_app_id()
    except (OSError, AttributeError) as exc:  # cosmetic: taskbar falls back to the host icon
        import sys as _sys
        _sys.stderr.write('AppUserModelID not set: %s\n' % exc)
    app = BridgeApp()
    app.mainloop()
    return 0

