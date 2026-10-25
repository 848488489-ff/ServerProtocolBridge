"""Bridge control page and the path-route editor.  Split from gui_ctk.py for file size.

Method bodies are unchanged; they are methods of BridgeApp, reached
through ``self``.
"""

from __future__ import annotations

import customtkinter as ctk
import tkinter as tk
from .gui_ctk import (ACCENT, ACCENT_HOVER, CARD_BORDER, DANGER, FIELD_BG, MUTED, SIDEBAR_HOVER, SUCCESS, ScrollPage, TEXT)
from .i18n import tr
class BridgeControl:
    """BridgeControl mixin for BridgeApp."""
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
    # ---------- path route editor ----------
    def _route_pairs(self):
        """(path_var, target_var) of every route row.

        Row widgets die when the forwarding card is rebuilt on a tab switch, but
        the variables outlive them, so the values the user typed are always
        reachable no matter which settings card is on screen.
        """
        return [(path_var, target_var) for _row, path_var, target_var
                in list(getattr(self, 'routes_rows', []))]
    def _route_editor(self):
        """Route rows whose widgets are still in the tree, else an empty list."""
        host = getattr(self, 'routes_host', None)
        if host is None:
            return []
        try:
            alive = host.winfo_exists()
        except tk.TclError:
            alive = False
        if not alive:
            return []
        rows = []
        for row, path_var, target_var in self._route_pairs():
            try:
                if row.winfo_exists():
                    rows.append((row, path_var, target_var))
            except tk.TclError:
                pass
        return rows
    def _add_route_row(self, path: str = '', target: str = '',
                       path_var: tk.StringVar | None = None,
                       target_var: tk.StringVar | None = None) -> None:
        """Add one route row, reusing existing variables when they are given.

        Reusing them is what keeps the values across a tab switch: the card is
        rebuilt and the entries are simply rebound to the same variables.
        """
        row = ctk.CTkFrame(self.routes_host, fg_color='transparent')
        path_var = path_var or tk.StringVar(value=path)
        target_var = target_var or tk.StringVar(value=target)
        ctk.CTkEntry(row, textvariable=path_var, height=30, font=self.font_body,
                     fg_color=FIELD_BG, border_color=CARD_BORDER, text_color=TEXT,
                     placeholder_text='/lobby').grid(
            row=0, column=0, sticky='ew', padx=(0, 8))
        ctk.CTkEntry(row, textvariable=target_var, height=30, font=self.font_body,
                     fg_color=FIELD_BG, border_color=CARD_BORDER, text_color=TEXT,
                     placeholder_text='play.example.net:25565').grid(
            row=0, column=1, sticky='ew', padx=(0, 8))
        ctk.CTkButton(row, text='×', width=32, height=30, font=self.font_small,
                      fg_color='transparent', border_width=1, border_color=CARD_BORDER,
                      text_color=MUTED, hover_color=SIDEBAR_HOVER,
                      command=lambda frame=row: self._remove_route_row(frame)).grid(
            row=0, column=2, sticky='e')
        row.grid_columnconfigure(0, weight=1)
        row.grid_columnconfigure(1, weight=1)
        row.pack(fill='x', pady=3)
        self.routes_rows.append((row, path_var, target_var))
        self._ensure_route_controls()
        self._refresh_routes_empty()
    def _ensure_route_controls(self) -> None:
        """Create the empty hint and the add button of the route editor."""
        if getattr(self, 'routes_empty_label', None) is None:
            self.routes_empty_label = ctk.CTkLabel(
                self.routes_host, text=tr('gui.hint.routes_empty'),
                font=self.font_small, text_color=MUTED, anchor='w')
            self.routes_empty_label.pack(fill='x')
        if getattr(self, 'routes_add_button', None) is None:
            self.routes_add_button = ctk.CTkButton(
                self.routes_host, text=tr('gui.button.route_add'), height=30,
                width=124, font=self.font_small, fg_color='transparent',
                border_width=1, border_color=CARD_BORDER, text_color=TEXT,
                hover_color=SIDEBAR_HOVER,
                command=lambda: self._add_route_row('', ''))
            self.routes_add_button.pack(fill='x', anchor='w', pady=(4, 0))
    def _remove_route_row(self, frame) -> None:
        self.routes_rows = [(row, path_var, target_var) for row, path_var, target_var
                            in self.routes_rows if row is not frame]
        try:
            frame.destroy()
        except tk.TclError:
            pass
        self._refresh_routes_empty()
    def _refresh_routes_empty(self) -> None:
        label = getattr(self, 'routes_empty_label', None)
        if label is None:
            return
        try:
            if not label.winfo_exists():
                return
            label.pack_forget() if self._route_pairs() else label.pack(fill='x')
        except tk.TclError:
            pass
    def _clear_route_rows(self) -> None:
        for row, _path_var, _target_var in self._route_editor():
            try:
                row.destroy()
            except tk.TclError:
                pass
        self.routes_rows = []
    def _rebuild_route_rows(self) -> None:
        """Recreate the row widgets, reusing the values already entered."""
        pairs = list(self._route_pairs())
        self.routes_rows = []
        for path_var, target_var in pairs:
            self._add_route_row(path_var=path_var, target_var=target_var)
        if not pairs:
            routes = getattr(self, 'cfg', None)
            for path, target in (getattr(routes, 'routes', None) or {}).items():
                self._add_route_row(str(path or ''), str(target or ''))
        self._ensure_route_controls()
        self._refresh_routes_empty()
    def _fill_route_rows(self, routes: dict) -> None:
        """Replace the route rows from a freshly loaded configuration."""
        host = getattr(self, 'routes_host', None)
        if host is None:
            return
        try:
            alive = host.winfo_exists()
        except tk.TclError:
            alive = False
        if not alive:
            return
        self.routes_rows = []
        for path, target in (routes or {}).items():
            self._add_route_row(str(path or ''), str(target or ''))
        self._ensure_route_controls()
        self._refresh_routes_empty()
    def _route_rows_text(self) -> str:
        """The route rows as editable text.

        A row with exactly one side filled is reported, not skipped: dropping it
        silently meant the entry disappeared without a message and the route was
        simply never applied.  A fully blank row is still ignored.
        """
        lines = []
        for path_var, target_var in self._route_pairs():
            path = path_var.get().strip()
            target = target_var.get().strip()
            if not path and not target:
                continue
            if not path:
                raise ValueError(tr('core.config.route_missing_path'))
            if not target:
                raise ValueError(tr('core.config.route_missing_target', path=path))
            lines.append('%s=%s' % (path, target))
        return '\n'.join(lines)
