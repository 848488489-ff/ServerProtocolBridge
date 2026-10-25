"""Bridge settings page and its forward, protocol, runtime, web and certificate tabs.  Split from gui_ctk.py for file size.

Method bodies are unchanged; they are methods of BridgeApp, reached
through ``self``.
"""

from __future__ import annotations

import customtkinter as ctk
from . import config as config_module
from .gui_ctk import (ACCENT, ACCENT_HOVER, CARD_BORDER, CERT_GENERATORS, LOG_LEVELS, LOG_LINE_LIMITS, MUTED, SETTINGS_TABS, SIDEBAR_HOVER, ScrollPage, TEXT, generator_label, log_level_label, log_limit_label, resource_pack_mode_label, spoof_label)
from .i18n import tr
class BridgeSettings:
    """BridgeSettings mixin for BridgeApp."""
    # ---------- settings page ----------
    def _build_settings_page(self, master) -> ScrollPage:
        """Settings page, one card at a time under a tab bar.

        The six cards used to sit on a single 161-widget scroll area.  Rendering
        them all at once froze the window for two seconds and left every scroll
        notch repainting hundreds of canvas items.  Only the selected card is in
        the tree now, so the first click is quick and scrolling stays smooth.

        Field values live in the StringVars rather than the widgets, so switching
        tabs never loses anything the user has typed.
        """
        page = ScrollPage(master, self)
        body = page.body

        bar = ctk.CTkFrame(body, fg_color='transparent')
        bar.pack(fill='x', pady=(0, 12))
        ctk.CTkButton(bar, text=tr('gui.button.save_config'), width=140,
                      height=34, font=self.font_h3, fg_color=ACCENT,
                      hover_color=ACCENT_HOVER,
                      command=self._save_config).pack(side='left')
        ctk.CTkButton(bar, text=tr('gui.button.reset_defaults'), width=126,
                      height=34, font=self.font_body, fg_color='transparent',
                      border_width=1, border_color=CARD_BORDER, text_color=TEXT,
                      hover_color=SIDEBAR_HOVER,
                      command=self._reset_defaults).pack(side='left', padx=8)
        ctk.CTkLabel(bar, text=tr('gui.hint.endpoint'), font=self.font_small,
                     text_color=MUTED).pack(side='right')

        tabs_bar = ctk.CTkFrame(body, fg_color='transparent')
        tabs_bar.pack(fill='x', pady=(0, 12))
        self.settings_tab_buttons = {}
        for key, label_key in SETTINGS_TABS:
            button = ctk.CTkButton(
                tabs_bar, text=tr(label_key), height=30, font=self.font_small,
                fg_color='transparent', border_width=1, border_color=CARD_BORDER,
                text_color=TEXT, hover_color=SIDEBAR_HOVER,
                command=lambda key=key: self._select_settings_tab(key))
            button.pack(side='left', padx=(0, 6))
            self.settings_tab_buttons[key] = button

        self.settings_tab_host = ctk.CTkFrame(body, fg_color='transparent')
        self.settings_tab_host.pack(fill='x')
        self._select_settings_tab('forward')
        return page
    def _select_settings_tab(self, key: str) -> None:
        """Show one settings card, building it once and then keeping it.

        Rebuilding the card on every click cost half a second: each CTk widget
        paints a dozen or so anti-aliased canvas shapes and a card holds about
        forty.  The built card is now kept in place and only
        grid_forget()-ed when another tab is shown, so a revisit is instant.
        A forgotten widget stays out of the layout, so the scroll body still
        measures only the visible card and the scroll repaint stays as cheap as
        when every card was destroyed -- grid_forget() is what avoids repeating
        the five-cards-on-one-canvas problem the tabs were introduced for.
        """
        host = self.settings_tab_host
        frame = self._settings_tab_cache.get(key)
        if frame is None:
            frame = ctk.CTkFrame(host, fg_color='transparent')
            frame.grid(row=0, column=0, sticky='nsew')
            builder = self.settings_tab_builders.get(key) or \
                self.settings_tab_builders['forward']
            builder(frame)
            self._settings_tab_cache[key] = frame
        elif not frame.winfo_ismapped():
            frame.grid(row=0, column=0, sticky='nsew')
        for other in self._settings_tab_cache.values():
            if other is not frame and other.winfo_ismapped():
                other.grid_forget()
        for tab_key, button in self.settings_tab_buttons.items():
            selected = tab_key == key
            button.configure(fg_color=ACCENT if selected else 'transparent',
                             text_color='#ffffff' if selected else TEXT,
                             border_color=ACCENT if selected else CARD_BORDER)
    def _settings_tab_forward(self, host) -> None:
        _card, forwarding = self._card(host, tr('gui.section.forwarding'))
        row = 0
        row = self._field_row(forwarding, row, tr('gui.label.server_brand'),
                              self._entry(forwarding, self.var_server_brand))
        row = self._field_row(forwarding, row, tr('gui.label.server_brand_version'),
                              self._entry(forwarding, self.var_server_brand_version))
        row = self._field_row(forwarding, row, tr('gui.label.spoof_client'),
                              self._option_menu(forwarding, self.var_spoof_client,
                                                [spoof_label(code)
                                                 for code in config_module.SPOOF_CLIENTS]))
        row = self._field_row(forwarding, row, tr('gui.label.spoof_brand'),
                              self._entry(forwarding, self.var_spoof_brand),
                              tr('gui.hint.spoof_brand'))
        ctk.CTkLabel(forwarding, text=tr('gui.label.routes'), font=self.font_body,
                     text_color=TEXT, anchor='nw').grid(row=row, column=0,
                                                        sticky='nw', padx=(0, 14),
                                                        pady=5)
        # The route editor is a list of "path + server" rows instead of a text
        # blob: each row is either used as a route or ignored, so the user
        # never has to remember the path=target format.
        self.routes_host = ctk.CTkFrame(forwarding, fg_color='transparent')
        self.routes_host.grid(row=row, column=1, sticky='ew', pady=5)
        self._rebuild_route_rows()
        row += 1
        ctk.CTkLabel(forwarding, text=tr('gui.hint.routes'), font=self.font_small,
                     text_color=MUTED, anchor='w').grid(row=row, column=0,
                                                        columnspan=2, sticky='w')
    def _settings_tab_protocol(self, host) -> None:
        _card, protocol = self._card(host, tr('gui.section.protocol'))
        row = 0
        row = self._switch_row(protocol, row, tr('gui.label.rewrite_host'),
                               self.var_rewrite_host)
        row = self._switch_row(protocol, row, tr('gui.label.eagler_translate'),
                               self.var_eagler_translate)
        row = self._switch_row(protocol, row, tr('gui.label.login_ack'),
                               self.var_login_ack)
        row = self._field_row(protocol, row, tr('gui.label.resource_pack_mode'),
                              self._option_menu(protocol, self.var_resource_pack_mode,
                                                [resource_pack_mode_label(code)
                                                 for code in
                                                 config_module.RESOURCE_PACK_MODES]))
        row = self._switch_row(protocol, row, tr('gui.label.auto_exit'),
                               self.var_auto_exit)
    def _settings_tab_runtime(self, host) -> None:
        _card, runtime = self._card(host, tr('gui.section.runtime'))
        row = 0
        row = self._field_row(runtime, row, tr('gui.label.log_level'),
                              self._option_menu(runtime, self.var_log_level,
                                                [log_level_label(code)
                                                 for code in LOG_LEVELS]))
        row = self._field_row(runtime, row, tr('gui.label.log_max_lines'),
                              self._option_menu(runtime, self.var_log_limit,
                                                [log_limit_label(code)
                                                 for code in LOG_LINE_LIMITS]),
                              tr('gui.hint.log_max_lines'))
        row = self._field_row(runtime, row, tr('gui.label.heartbeat'),
                              self._entry(runtime, self.var_heartbeat, width=120))
        row = self._field_row(runtime, row, tr('gui.label.connect_timeout'),
                              self._entry(runtime, self.var_connect_timeout, width=120))
        row = self._field_row(runtime, row, tr('gui.label.max_payload'),
                              self._entry(runtime, self.var_max_payload, width=120))
        row = self._switch_row(runtime, row, tr('gui.label.status_cache'),
                               self.var_status_cache,
                               tr('gui.label.status_cache_hint'))
        row = self._field_row(runtime, row, tr('gui.label.status_cache_ttl'),
                              self._entry(runtime, self.var_status_cache_ttl, width=120))
        row = self._switch_row(runtime, row, tr('gui.label.update_check'),
                               self.var_update_check)
    def _settings_tab_web(self, host) -> None:
        _card, web = self._card(host, tr('gui.section.web'))
        row = 0
        row = self._field_row(web, row, tr('gui.label.web_host'),
                              self._entry(web, self.var_web_host))
        row = self._field_row(web, row, tr('gui.label.web_port'),
                              self._entry(web, self.var_web_port, width=120),
                              tr('gui.hint.web_bind'))
        row = self._switch_row(web, row, tr('gui.label.web_password'),
                               self.var_web_password,
                               tr('gui.hint.web_password'))
        row = self._password_row(web, row, tr('gui.label.web_password_new'),
                                 self._entry(web, self.var_web_password_value,
                                             show='*'))
        row = self._password_row(web, row, tr('gui.label.web_password_confirm'),
                                 self._entry(web, self.var_web_password_confirm,
                                             show='*'),
                                 tr('gui.hint.web_password_keep'))
        web_actions = ctk.CTkFrame(web, fg_color='transparent')
        web_actions.grid(row=row, column=0, columnspan=2, sticky='w', pady=(6, 0))
        ctk.CTkButton(web_actions, text=tr('gui.button.web_auth_apply'), width=108,
                      height=30, font=self.font_small, fg_color=ACCENT,
                      hover_color=ACCENT_HOVER, text_color='#ffffff',
                      command=self._apply_web_auth_button).pack(side='left')
        ctk.CTkButton(web_actions, text=tr('gui.button.web_restart'), width=118,
                      height=30, font=self.font_small, fg_color='transparent',
                      border_width=1, border_color=CARD_BORDER, text_color=TEXT,
                      hover_color=SIDEBAR_HOVER,
                      command=self._restart_web).pack(side='left', padx=(8, 0))
        self.web_auth_label = ctk.CTkLabel(
            web_actions, text='', font=self.font_small, text_color=MUTED,
            anchor='w')
        self.web_auth_label.pack(side='left', padx=12)
        self.web_settings_label = ctk.CTkLabel(
            web_actions, text='', font=self.font_small, text_color=MUTED,
            anchor='w')
        self.web_settings_label.pack(side='left', padx=12)
    def _settings_tab_cert(self, host) -> None:
        _card, certificate = self._card(host, tr('gui.section.certificate'),
                                        pady=(0, 0))
        row = 0
        row = self._field_row(certificate, row, tr('gui.label.cert_dir'),
                              self._entry(certificate, self.var_cert_dir))
        row = self._field_row(certificate, row, tr('gui.label.cert_cn'),
                              self._entry(certificate, self.var_cert_common_name))
        row = self._field_row(certificate, row, tr('gui.label.cert_extra'),
                              self._entry(certificate, self.var_cert_extra))
        row = self._field_row(certificate, row, tr('gui.label.cert_days'),
                              self._entry(certificate, self.var_cert_days, width=120))
        row = self._field_row(certificate, row, tr('gui.label.cert_generator'),
                              self._option_menu(certificate, self.var_cert_generator,
                                                [generator_label(code)
                                                 for code in CERT_GENERATORS]))
