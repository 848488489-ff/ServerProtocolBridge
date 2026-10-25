"""Bridge form I/O: loading the config into the widgets, collecting it back, language and theme selection, and the start, stop and save actions.  Split from gui_ctk.py for file size.

Method bodies are unchanged; they are methods of BridgeApp, reached
through ``self``.
"""

from __future__ import annotations

import customtkinter as ctk
import tkinter as tk
from . import (config as config_module, webauth)
from .gui_ctk import (generator_code, generator_label, log_level_code, log_level_label, log_limit_code, log_limit_label, resource_pack_mode_code, resource_pack_mode_label, spoof_code, spoof_label, theme_code, theme_label)
from .i18n import (get_language, language_code, language_label, set_language, tr)
from tkinter import messagebox
class BridgeForm:
    """BridgeForm mixin for BridgeApp."""
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
            self._fill_route_rows(config.routes)
            self.var_log_level.set(log_level_label(config.log_level))
            self.var_log_limit.set(log_limit_label(str(config.log_max_lines)))
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
        finally:
            self._loading_form = False
        self._refresh_endpoint()
        self._refresh_cert()
        self._refresh_web_auth_label()
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
        routes_text = self._route_rows_text()
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
        config.log_level = log_level_code(self.var_log_level.get())
        if config.log_level not in ('debug', 'info', 'warn', 'error'):
            config.log_level = 'info'
        config.log_max_lines = log_limit_code(self.var_log_limit.get())
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
        self._refresh_shell()
        self._rebuild_pages()
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
        old = self.manager.config
        web_changed = ((old.web_host or '').strip() != (config.web_host or '').strip()
                       or int(old.web_port) != int(config.web_port))
        self.manager.save_config(config)
        self.cfg = self.manager.config
        self._seen_revision = self.manager.revision
        if web_changed:
            self._restart_web_listener(self.cfg.web_host, self.cfg.web_port)
        self._log(tr('gui.log.config_saved', path=self.cfg.config_path))
    def _toggle_password_visibility(self, entry, button) -> None:
        """Show or hide the password entry the button belongs to.

        ``show=''`` reveals the characters; ``show='*'`` masks them again.  Each
        button tracks only its own entry, so the confirm field stays masked while
        the new-password field is revealed.
        """
        try:
            entry.configure(show='*' if entry.cget('show') == '' else '')
        except tk.TclError:
            return
        try:
            shown = str(entry.cget('show')) == ''
            button.configure(text=tr('gui.button.web_auth_hide') if shown
                             else tr('gui.button.web_auth_show'))
        except tk.TclError:
            pass
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
        self._refresh_shell()
        self._rebuild_pages()
        if ((old.web_host or '').strip() != self.cfg.web_host
                or int(old.web_port) != int(self.cfg.web_port)):
            self._restart_web_listener(self.cfg.web_host, self.cfg.web_port)
