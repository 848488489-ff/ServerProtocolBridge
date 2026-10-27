"""Bridge web and endpoint actions: the web auth button, opening the browser UI, endpoint copying, path openers, the queued-thread helper and window close.  Split from gui_ctk.py for file size.

Method bodies are unchanged; they are methods of BridgeApp, reached
through ``self``.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import tkinter as tk
from . import webauth
from .gui_ctk import (MUTED, SUCCESS, WARN, _open_url)
from .i18n import tr
from pathlib import Path
from tkinter import messagebox
class BridgeWeb:
    """BridgeWeb mixin for BridgeApp."""
    def _apply_web_auth_button(self) -> None:
        """Apply the access-password fields.

        This is the only action that may write or clear the stored password.  The
        switch and the two text fields only record the user's *intent*; saving
        the configuration or restarting the Web UI used to run them through here
        too, which let an incidental "switch off" wipe a password that was never
        meant to be removed.
        """
        enabled = bool(self.var_web_password.get())
        password = self.var_web_password_value.get()
        confirm = self.var_web_password_confirm.get()
        try:
            if enabled:
                if password or confirm:
                    if password != confirm:
                        messagebox.showerror(tr('gui.error.title'),
                                             tr('gui.error.password_mismatch'),
                                             parent=self)
                        return
                    if len(password) < 4:
                        messagebox.showerror(tr('gui.error.title'),
                                             tr('gui.error.password_short'),
                                             parent=self)
                        return
                    webauth.set_password(password)
                    self._log(tr('gui.log.web_password_on'))
                elif not webauth.has_password():
                    messagebox.showerror(tr('gui.error.title'),
                                         tr('gui.error.password_required'),
                                         parent=self)
                    return
                else:
                    # The hash exists but is stored disabled: the switch is on, so
                    # put it into force without making the user retype it.
                    if not webauth.is_enabled():
                        webauth.enable()
                    self.var_web_password.set(True)
                    self._log(tr('gui.log.web_password_kept'))
            elif webauth.is_enabled():
                # Wiping the hash is irreversible, so ask first.
                if not messagebox.askyesno(tr('gui.confirm.title'),
                                           tr('gui.confirm.web_password_off'),
                                           parent=self):
                    return
                webauth.disable()
                self.var_web_password.set(False)
                self._log(tr('gui.log.web_password_off'))
        except OSError:
            # web_auth.json exists but cannot be read: fail the whole action
            # instead of silently writing over it (that is what wiped a stored
            # password before).  Nothing was changed.
            messagebox.showerror(tr('gui.error.title'),
                                 tr('gui.error.web_auth_unreadable'),
                                 parent=self)
            return
        # The fields are deliberately left in place: a password entry that
        # empties itself the moment you confirm it looks like the password was
        # lost, and there is no way to check what was just stored.  They are
        # cleared by _load_form when the page is rebuilt.
        self._seen_revision = self.manager.revision
        self._refresh_web_auth_label()
    def _refresh_web_auth_label(self) -> None:
        """Say whether the Web UI is actually protected right now."""
        label = getattr(self, 'web_auth_label', None)
        if label is None:
            return
        auth = webauth.state()
        if auth['enabled']:
            text, color = tr('gui.status.web_password_on'), SUCCESS
        elif auth['has_password']:
            text, color = tr('gui.status.web_password_stored'), WARN
        else:
            text, color = tr('gui.status.web_password_off'), MUTED
        try:
            label.configure(text=text, text_color=color)
        except tk.TclError:
            pass
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
        """Apply the bind fields and rebind the Web UI listener.

        Deliberately leaves the access password alone: a restart is a listener
        operation, and treating it as a chance to apply the password fields is
        what cleared passwords the user had just set.
        """
        try:
            config = self._collect_form()
        except ValueError as exc:
            messagebox.showerror(tr('gui.error.title'), str(exc), parent=self)
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
