"""Bridge dialogs for adding an offline, third-party or Microsoft account.  Split from gui_ctk.py for file size.

Method bodies are unchanged; they are methods of BridgeApp, reached
through ``self``.
"""

from __future__ import annotations

import customtkinter as ctk
import threading
import tkinter as tk
from . import (accounts, eagler, icon)
from .gui_ctk import (ACCENT, ACCENT_HOVER, CARD_BORDER, DANGER, MUTED, SIDEBAR_HOVER, TEXT, _open_url)
from .i18n import tr
from tkinter import messagebox
class BridgeAccountsAdd:
    """BridgeAccountsAdd mixin for BridgeApp."""
    # ---------- accounts: add dialogs ----------
    def _add_offline_account(self) -> None:
        dialog = ctk.CTkInputDialog(text=tr('gui.accounts.offline.prompt'),
                                    title=tr('gui.accounts.add.offline'))
        raw = dialog.get_input()
        if not raw:
            return
        name = eagler.usable_name(raw)
        if not name:
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
        icon.apply(dialog, report=lambda message: self._log(message, 'warn'))
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
        icon.apply(dialog, report=lambda message: self._log(message, 'warn'))
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
                                       tr('gui.accounts.ms.ssl_ask', detail=message),
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
