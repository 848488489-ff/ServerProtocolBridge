"""Bridge about page: the component list, its Tk styling and the hover and click handling.  Split from gui_ctk.py for file size.

Method bodies are unchanged; they are methods of BridgeApp, reached
through ``self``.
"""

from __future__ import annotations

import customtkinter as ctk
import tkinter as tk
from . import dpi
from .gui_ctk import (ACCENT, CARD_BORDER, FIELD_BG, MUTED, SIDEBAR_HOVER, ScrollPage, TEXT, _open_url, _style_map, _style_opt)
from .i18n import tr
from .third_party import (COMPONENTS, STDLIB_MODULES)
from .version import VERSION
from tkinter import ttk
class BridgeAbout:
    """BridgeAbout mixin for BridgeApp."""
    # ---------- about page ----------
    def _build_about_page(self, master) -> ScrollPage:
        page = ScrollPage(master, self)
        body = page.body

        _card, head = self._card(body, '%s  v%s' % (tr('core.app_name'), VERSION))
        ctk.CTkLabel(head, text=tr('gui.about.blurb'), font=self.font_body,
                     text_color=TEXT, anchor='w', justify='left',
                     wraplength=780).grid(row=0, column=0, columnspan=2,
                                          sticky='w')
        ctk.CTkButton(
            head, text=tr('gui.about.project_license'), anchor='w', height=24,
            font=self.font_small, fg_color='transparent', hover_color=SIDEBAR_HOVER,
            text_color=MUTED, command=lambda: _open_url('https://unlicense.org')).grid(
            row=1, column=0, columnspan=2, sticky='w', pady=(4, 0))

        # A real list widget -- not 55 buttons, and not a block of monospace
        # text.  55 CTkButtons were about 165 Tk widgets on one card; a text
        # box read like a terminal.  ttk.Treeview is one native control that
        # only paints the rows it can see.
        _card, card = self._card(body, tr('gui.about.components'))
        self._build_component_list(card)
        ctk.CTkLabel(card, text=tr('gui.about.hint'), font=self.font_small,
                     text_color=MUTED, anchor='w').grid(
            row=1, column=0, columnspan=2, sticky='w', pady=(10, 0))

        # The project license, in full, so nobody has to leave the window to see
        # what they are agreeing to.
        _card, license_card = self._card(body, tr('gui.about.license_title'),
                                         pady=(0, 0))
        self.license_text = ctk.CTkTextbox(
            license_card, height=400, wrap='word', font=self.font_small,
            fg_color=FIELD_BG, border_width=1, border_color=CARD_BORDER,
            text_color=MUTED, corner_radius=8, activate_scrollbars=True)
        self.license_text.grid(row=0, column=0, columnspan=2, sticky='nsew')
        self.license_text.insert('1.0', tr('gui.about.license_text'))
        self.license_text.configure(state='disabled')
        return page
    def _build_component_list(self, parent) -> None:
        """The third-party component table.

        The height spans every row, so the enclosing scroll area owns all the
        scrolling: the wheel never has to pick between the page and an inner
        scrollbar.  A tree view only paints the rows in view, so the cost does
        not grow with the number of entries.
        """
        rows = len(COMPONENTS) + 1 + len(STDLIB_MODULES)
        self.about_tree = ttk.Treeview(
            parent, columns=('name', 'license'), show='headings',
            selectmode='browse', height=rows, style='About.Treeview')
        # ttk is outside CTk's scaling, so every pixel value is scaled by hand.
        self.about_tree.column('name', width=dpi.scale(self, 340),
                               minwidth=dpi.scale(self, 160),
                               anchor='w', stretch=False)
        self.about_tree.column('license', width=dpi.scale(self, 340),
                               minwidth=dpi.scale(self, 140),
                               anchor='w', stretch=True)
        self.about_tree.heading('name', text=tr('gui.about.column_component'))
        self.about_tree.heading('license', text=tr('gui.about.column_license'))
        self.about_tree.grid(row=0, column=0, columnspan=2, sticky='nsew')

        self._about_urls = {}
        for component in COMPONENTS:
            iid = self.about_tree.insert(
                '', 'end', tags=('link',),
                values=(component['name'], component['license']))
            self._about_urls[iid] = str(component['url'])
        self.about_tree.insert('', 'end', tags=('header',),
                               values=(tr('gui.about.stdlib'), ''))
        for module in STDLIB_MODULES:
            iid = self.about_tree.insert('', 'end', tags=('link',),
                                         values=('     %s' % module, ''))
            self._about_urls[iid] = (
                'https://docs.python.org/3/library/%s.html' % module)

        self._style_component_list()
        self.about_tree.bind('<Motion>', self._on_about_motion)
        self.about_tree.bind('<Button-1>', self._on_about_click)
    def _style_component_list(self) -> None:
        """Give the tree view the page's colours for the current appearance.

        ttk does not follow CustomTkinter's appearance mode, so the colours are
        resolved for the mode in force; _retheme_canvases calls this again when
        the theme flips, because the list may be sitting cached off-screen.
        """
        tree = getattr(self, 'about_tree', None)
        if tree is None:
            return
        try:
            if not tree.winfo_exists():
                return
        except tk.TclError:
            return

        style = ttk.Style()
        try:
            # 'clam' is the only Tcl theme that lets you paint the headings
            # flat.  Tk 9 dropped the Tcl themes, so fall back to whatever is
            # in use -- the explicit configure() below still applies.
            style.theme_use('clam')
        except tk.TclError:
            pass

        # Each call is guarded on its own: Tk validates every option before
        # applying any of them, so one option Tk 9 no longer knows would silently
        # drop the colours as well.  ttk never scales on its own, so the font and
        # the row height are scaled for the window's DPI here.  The font is kept
        # on self: ttk stores the font name only, and a collected object drops it.
        tree_font = dpi.scaled_font(self.font_small, self)
        self._tree_font = tree_font
        _style_opt(style, 'About.Treeview',
                   background=self._pick(FIELD_BG),
                   fieldbackground=self._pick(FIELD_BG),
                   foreground=self._pick(TEXT),
                   borderwidth=0, relief='flat',
                   rowheight=dpi.scale(self, 28),
                   font=tree_font)
        _style_opt(style, 'About.Treeview.Heading',
                   background=self._pick(FIELD_BG),
                   foreground=self._pick(MUTED),
                   relief='flat', font=tree_font)
        _style_map(style, 'About.Treeview',
                   background=[('selected', ACCENT)],
                   foreground=[('selected', '#ffffff')])
        _style_map(style, 'About.Treeview.Heading',
                   foreground=[('active', self._pick(TEXT))])
        try:
            tree.tag_configure('header', foreground=self._pick(MUTED))
        except tk.TclError:
            pass
    def _about_row_tags(self, event) -> tuple[str, tuple]:
        """(iid, tags) of the row under an event, or ('', ())."""
        tree = getattr(self, 'about_tree', None)
        if tree is None:
            return '', ()
        try:
            iid = tree.identify_row(int(event.y))
        except (tk.TclError, ValueError, AttributeError):
            return '', ()
        if not iid:
            return '', ()
        return iid, tuple(tree.item(iid).get('tags') or ())
    def _on_about_motion(self, event=None) -> None:
        _iid, tags = self._about_row_tags(event)
        tree = getattr(self, 'about_tree', None)
        if tree is not None:
            tree.configure(cursor='hand2' if 'link' in tags else '')
    def _on_about_click(self, event=None) -> None:
        iid, tags = self._about_row_tags(event)
        if 'link' not in tags:
            return
        url = getattr(self, '_about_urls', {}).get(iid, '')
        if url:
            _open_url(url)
