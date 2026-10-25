"""Wheel scrolling shared by the Tk widgets and CustomTkinter.

One wheel notch is applied as a single scroll step, and the scrollable canvas is
invalidated right after.  On Windows with Tk 9 the canvas does not repaint the
region an embedded window item vacated, so an animated scroll (several partial
scrolls per notch) leaves a stale copy of the previous frame behind -- the "ghost"
of the page offset.  Doing the whole step at once and then forcing a full canvas
invalidation removes it, and scrolling stays fast because a notch costs one
scroll plus one redraw instead of six or eight of each.

Three entry points:

``enable(widget)``          -- bind the wheel directly to a widget that has
                               ``yview_scroll`` (Tk Text, Treeview, CustomTkinter
                               CTkTextbox, ...).
``SmoothWheel``             -- the scrolling object itself; the GUI attaches one
                               to a canvas and routes wheel events itself, which
                               is what makes nested scroll areas behave.
``enable_tree(root)``       -- walk a widget tree and enable every Text and
                               Treeview (kept for compatibility).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk as _ttk
from typing import Any, Callable


def wheel_notches(event: Any) -> int:
    """Convert a platform wheel event into notches (positive = scroll up)."""
    number = getattr(event, 'num', None)
    if number == 4:
        return 1
    if number == 5:
        return -1
    try:
        delta = int(getattr(event, 'delta', 0) or 0)
    except (TypeError, ValueError):
        return 0
    if delta == 0:
        return 0
    # Windows reports ±120 per notch, macOS reports small values (±1..±10)
    if abs(delta) >= 120:
        return -delta // 120
    return -1 if delta > 0 else 1


class SmoothWheel:
    """One notch = one scroll step, for one scrollable target.

    ``scroll`` receives a signed number of "units" (whatever the target
    understands); ``scheduler`` is any widget the step can be deferred through
    (the target itself normally).  ``wheel`` is a Tk event handler and returns
    ``'break'``.
    """

    def __init__(self, scroll: Callable[[int], None], scheduler: Any = None,
                 units_per_notch: int = 4) -> None:
        self._scroll = scroll
        self._scheduler = scheduler
        self.units_per_notch = units_per_notch

    # ---------- event handler ----------
    def wheel(self, event: Any) -> str:
        notches = wheel_notches(event)
        if notches:
            self.apply(notches * self.units_per_notch)
        return 'break'

    # ---------- scroll ----------
    def apply(self, units: int) -> None:
        if not units:
            return
        try:
            self._scroll(int(units))
        except tk.TclError:
            return
        self._repaint()

    def _repaint(self) -> None:
        """Force the canvas to redraw so the scroll leaves no stale pixels.

        ``yview_moveto`` at the already-current position changes nothing about the
        scroll position, but it runs Tk's canvas scrollview code, which moves
        every embedded window item and invalidates the whole canvas.  That is the
        difference between a clean scroll and a ghost of the previous frame.
        """
        target = self._scheduler
        if not isinstance(target, tk.Canvas):
            return
        view = getattr(target, 'yview', None)
        moveto = getattr(target, 'yview_moveto', None)
        if view is None or moveto is None:
            return
        try:
            moveto(view()[0])
        except tk.TclError:
            pass

    def reset(self) -> None:
        """Nothing is pending anymore; kept for the callers that still ask."""


def enable(widget: Any, units_per_notch: int = 4) -> None:
    """Bind wheel scrolling directly to *widget* (Text / Treeview / CTkTextbox)."""
    if getattr(widget, '_smooth_wheel', None) is not None:
        return
    wheel = SmoothWheel(lambda units: widget.yview_scroll(units, 'units'), widget,
                        units_per_notch)
    setattr(widget, '_smooth_wheel', wheel)
    for sequence in ('<MouseWheel>', '<Button-4>', '<Button-5>'):
        try:
            widget.bind(sequence, wheel.wheel, add='+')
        except tk.TclError:
            pass


def enable_tree(root: Any) -> int:
    """Enable wheel scrolling on every Text and Treeview below *root*."""
    count = 0
    try:
        children = root.winfo_children()
    except Exception:
        return 0
    for child in children:
        if isinstance(child, (tk.Text, _ttk.Treeview)):
            enable(child)
            count += 1
        count += enable_tree(child)
    return count
