"""Bridge accounts page: rendering the list, selecting and removing accounts and opening the data directory.  Split from gui_ctk.py for file size.

Method bodies are unchanged; they are methods of BridgeApp, reached
through ``self``.
"""

from __future__ import annotations

import customtkinter as ctk
from . import accounts
from .gui_ctk import (ACCENT, ACCENT_HOVER, CARD_BORDER, DANGER, MUTED, SIDEBAR_HOVER, ScrollPage, TEXT)
from .i18n import tr
from tkinter import messagebox
class BridgeAccounts:
    """BridgeAccounts mixin for BridgeApp."""
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
