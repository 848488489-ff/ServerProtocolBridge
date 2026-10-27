"""Bridge page plumbing: page creation and selection, scroll-wheel routing between pages, dropdown teardown and the small widget factories every form reuses.  Split from gui_ctk.py for file size.

Method bodies are unchanged; they are methods of BridgeApp, reached
through ``self``.
"""

from __future__ import annotations

import customtkinter as ctk
import tkinter as tk
from .gui_ctk import (ACCENT, CARD_BG, CARD_BORDER, FIELD_BG, MUTED, SIDEBAR_HOVER, TEXT)
from .i18n import tr
class BridgePages:
    """BridgePages mixin for BridgeApp."""
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
        # A wheel gesture interrupted by a page change would otherwise carry
        # its partial delta onto the new page and make it jump as soon as the
        # user scrolls again.
        for canvas in list(self.scroll_canvases):
            scroller = getattr(canvas, '_smooth_wheel', None)
            if scroller is not None:
                try:
                    scroller.reset()
                except Exception:
                    pass
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
    def _password_row(self, body, row: int, label: str, entry,
                      hint: str | None = None) -> int:
        """A labelled entry with its own show/hide button.

        ``_field_row`` only has two grid columns, so the entry keeps column 1
        and the button takes column 2 instead of stealing column 1's width with
        a columnspan.  Every other field row still spans 0..1 as before.
        """
        ctk.CTkLabel(body, text=label, font=self.font_body, text_color=TEXT,
                     anchor='w').grid(row=row, column=0, sticky='w',
                                      padx=(0, 14), pady=5)
        entry.grid(row=row, column=1, sticky='ew', pady=5)
        button = ctk.CTkButton(body, text=tr('gui.button.web_auth_show'), width=96,
                               height=28, font=self.font_small, fg_color='transparent',
                               border_width=1, border_color=CARD_BORDER, text_color=MUTED,
                               hover_color=SIDEBAR_HOVER)
        # Hand the button itself, not the page: _toggle_password_visibility
        # flips the button label between show/hide, which requires the widget.
        button.configure(command=lambda: self._toggle_password_visibility(entry, button))
        button.grid(row=row, column=2, sticky='e', padx=(8, 0), pady=5)
        row += 1
        if hint:
            ctk.CTkLabel(body, text=hint, font=self.font_small, text_color=MUTED,
                         anchor='w', justify='left').grid(
                row=row, column=0, columnspan=3, sticky='w', pady=(0, 4))
            row += 1
        return row
    def _option_menu(self, parent, variable, values, command=None) -> ctk.CTkOptionMenu:
        return ctk.CTkOptionMenu(
            parent, variable=variable, values=values, command=command, height=30,
            font=self.font_body, fg_color=FIELD_BG, button_color=FIELD_BG,
            button_hover_color=SIDEBAR_HOVER, text_color=TEXT,
            dropdown_fg_color=CARD_BG, dropdown_text_color=TEXT,
            dropdown_hover_color=SIDEBAR_HOVER)
    def _rebuild_pages(self) -> None:
        """Drop the page bodies and rebuild only the one that is visible.

        The other pages are created lazily the next time they are shown, so
        their cost is paid only once and only when it is actually needed.
        """
        page = self.current_page if self.current_page in self.page_builders else 'control'
        self._destroy_pages()
        self._select_page(page)
        self._load_form(self.cfg)
        self._render_log()
    def _destroy_pages(self) -> None:
        for child in list(self.page_host.winfo_children()):
            try:
                child.destroy()
            except tk.TclError:
                pass
        self.pages = {}
        self.scroll_canvases = []
        # Any cached settings tab was a child of the page that just went away.
        self._settings_tab_cache = {}
        self.routes_host = None
        self.routes_empty_label = None
        self.routes_add_button = None
    def _refresh_shell(self) -> None:
        """Rebuild the sidebar and header in place, leaving the pages alone.

        The shell holds only a couple of dozen widgets, so rebuilding it in
        place retranslates it quickly and never blanks the window the way
        destroying the whole toplevel does.
        """
        for menu in (getattr(self, 'theme_menu', None),
                     getattr(self, 'language_menu', None)):
            if menu is not None:
                self._teardown_dropdowns(menu)
        for child in list(self.sidebar.winfo_children()):
            try:
                child.destroy()
            except tk.TclError:
                pass
        self.nav_buttons = {}
        self._build_sidebar()

        for child in list(self.main.winfo_children()):
            if child is self.page_host:
                continue
            try:
                child.destroy()
            except tk.TclError:
                pass
        self._build_header()
        self._pill_state = ''
        self._update_pill(self.manager.status().get('state') or 'stopped')
        self.title(self._window_title())
    @staticmethod
    def _teardown_dropdowns(menu) -> None:
        """Close a CustomTkinter option menu's dropdown without touching it.

        CTk's own destroy callback destroys the dropdown widget, and destroying
        a widget that owns bound callbacks raises inside the very teardown it is
        running.  Dropping the reference first keeps the teardown quiet.
        """
        try:
            menu._drawn_dropdown_widget = None
        except Exception:
            pass
        dropdown = getattr(menu, '_current_dropdown_widget', None)
        if dropdown is None:
            return
        try:
            for child in list(dropdown.winfo_children()):
                child.destroy()
        except tk.TclError:
            pass
        try:
            dropdown.destroy()
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
