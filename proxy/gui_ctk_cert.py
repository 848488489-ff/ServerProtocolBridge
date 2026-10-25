"""Bridge certificate page: certificate paths, generator selection, regeneration and OS installation.  Split from gui_ctk.py for file size.

Method bodies are unchanged; they are methods of BridgeApp, reached
through ``self``.
"""

from __future__ import annotations

import customtkinter as ctk
import threading
import tkinter as tk
from . import certs
from .gui_ctk import (ACCENT, ACCENT_HOVER, CARD_BORDER, MUTED, SIDEBAR_HOVER, ScrollPage, TEXT, generator_code, log_level_code)
from .i18n import tr
from .utils import resolve_path
from pathlib import Path
from tkinter import messagebox
class BridgeCert:
    """BridgeCert mixin for BridgeApp."""
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
        return Logger(log_level_code(self.var_log_level.get()),
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
