"""Bridge log page and the shared log drain, trim and render paths, the runtime refresh, the status pill and the Tk poll loop.  Split from gui_ctk.py for file size.

Method bodies are unchanged; they are methods of BridgeApp, reached
through ``self``.
"""

from __future__ import annotations

import customtkinter as ctk
import tkinter as tk
from . import config as config_module
from .gui_ctk import (ACCENT, CARD_BG, CARD_BORDER, DANGER, LOG_COLORS, LOG_LEVELS, LOG_LINE_LIMIT, MUTED, SIDEBAR_HOVER, SUCCESS, TEXT, WARN, log_level_code, log_level_label)
from .i18n import (get_language, set_language, tr)
from .runtime import (ERROR, RUNNING, STARTING, STOPPING)
from .smoothscroll import SmoothWheel
from .utils import (human_bytes, human_duration)
class BridgeLog:
    """BridgeLog mixin for BridgeApp."""
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
        self._option_menu(toolbar, self.var_log_filter,
                          [log_level_label(code) for code in LOG_LEVELS],
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
        selected = log_level_code(self.var_log_filter.get())
        try:
            self.log_text.configure(state='normal')
            for item in items:
                if selected != 'all' and item['level'] != selected:
                    continue
                self.log_text.insert('end', item['text'] + '\n', item['level'])
            self._trim_log()
            self.log_text.configure(state='disabled')
            if self.var_auto_scroll.get():
                self.log_text.see('end')
        except tk.TclError:
            pass
    def _trim_log(self) -> None:
        """Drop the oldest lines so the log widget cannot grow without bound.

        Counting lines is a constant-time ``index()`` call, so this is cheap
        enough to run on every drain.  The hub already caps its own buffer;
        without this the widget would outlive every entry it had ever been sent.
        """
        inner = self.log_text._textbox
        try:
            lines = int(inner.index('end-1c').split('.')[0])
        except (tk.TclError, ValueError, AttributeError):
            return
        excess = lines - LOG_LINE_LIMIT
        if excess <= 0:
            return
        try:
            inner.delete('1.0', '%d.0' % (excess + 1))
        except tk.TclError:
            pass
    def _render_log(self) -> None:
        if not hasattr(self, 'log_text'):
            return
        items = self.manager.hub.snapshot(0)
        self._log_seq = items[-1]['seq'] if items else 0
        selected = log_level_code(self.var_log_filter.get())
        try:
            self.log_text.configure(state='normal')
            self.log_text.delete('1.0', 'end')
            for item in items[-LOG_LINE_LIMIT:]:
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
        # The reschedule is in a finally: if any refresh ever raises, polling
        # must not silently stop.  A stale widget reference raising TclError was
        # exactly the case that used to stop it.
        try:
            self._drain_logs()
            self._refresh_runtime()
        except tk.TclError:
            pass
        finally:
            if not self._closing:
                self._poll_id = self.after(250, self._poll)
    @staticmethod
    def _alive(widget) -> bool:
        """True when a widget still exists; destroyed ones raise TclError."""
        try:
            return widget is not None and widget.winfo_exists()
        except tk.TclError:
            return False
    def _refresh_runtime(self) -> None:
        status = self.manager.status()
        self._update_pill(status['state'])

        state = status['state']
        if self._alive(getattr(self, 'btn_start', None)):
            try:
                self.btn_start.configure(
                    state='disabled' if state in (STARTING, RUNNING, STOPPING)
                    else 'normal')
                self.btn_stop.configure(
                    state='normal' if state in (STARTING, RUNNING) else 'disabled')
            except tk.TclError:
                pass

        stats = status.get('stats') or {}
        values = {
            'active': str(stats.get('active', 0)),
            'total': str(stats.get('total', 0)),
            'up': human_bytes(stats.get('bytes_to_server', 0)),
            'down': human_bytes(stats.get('bytes_to_client', 0)),
            'uptime': human_duration(stats.get('uptime', 0)),
        }
        for name, label in (getattr(self, 'stat_labels', {}) or {}).items():
            if not self._alive(label):
                continue
            text = values.get(name, '0')
            try:
                if label.cget('text') != text:
                    label.configure(text=text)
            except tk.TclError:
                pass

        if self._alive(getattr(self, 'web_label', None)):
            url = self.manager.web_url
            text = tr('gui.web.running', url=url) if url else tr('gui.web.hint')
            try:
                if self.web_label.cget('text') != text:
                    self.web_label.configure(text=text)
            except tk.TclError:
                pass
        if self._alive(getattr(self, 'web_settings_label', None)):
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
                self._refresh_shell()
                self._rebuild_pages()
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
