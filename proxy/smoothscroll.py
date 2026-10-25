"""Eased wheel scrolling shared by the Tk widgets and CustomTkinter.

Tk's native wheel handler jumps a fixed number of lines in one frame.  This
module keeps the same scrollable widgets but spreads the jump over a handful
of animation frames with an ease-out curve, so a notch of the wheel glides to
a stop instead of teleporting.

Three entry points:

``enable(widget)``          -- bind the wheel directly to a widget that has
                              ``yview_scroll`` (Tk Text, Treeview, CustomTkinter
                              CTkTextbox, ...).
``SmoothWheel``             -- the animation object itself; the GUI attaches
                              one to a canvas and routes wheel events itself,
                              which is what makes nested scroll areas behave.
``enable_tree(root)``       -- walk a widget tree and enable every Text and
                              Treeview (kept for compatibility).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk as _ttk
from typing import Any, Callable

_FRAME_MS = 16
_EASE_DIVISOR = 4
_MAX_STEP = 3


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
    """Ease-out scrolling for one scrollable target.

    ``scroll`` receives a signed number of "units" (whatever the target
    understands); ``scheduler`` is any widget used for ``after`` (the target
    itself normally).  ``wheel`` is a Tk event handler and returns ``'break'``.
    """

    def __init__(self, scroll: Callable[[int], None], scheduler: Any = None,
                 units_per_notch: int = 4) -> None:
        self._scroll = scroll
        self._scheduler = scheduler
        self.units_per_notch = units_per_notch
        self._target = 0
        self._applied = 0
        self._job = None

    # ---------- event handler ----------
    def wheel(self, event: Any) -> str:
        notches = wheel_notches(event)
        if notches:
            self._target += notches * self.units_per_notch
            if self._job is None:
                self._tick()
        return 'break'

    # ---------- animation ----------
    def _tick(self) -> None:
        remaining = self._target - self._applied
        if remaining == 0:
            self._job = None
            return
        step = int(round(remaining / _EASE_DIVISOR))
        if step == 0:
            step = 1 if remaining > 0 else -1
        step = max(-_MAX_STEP, min(_MAX_STEP, step))
        try:
            self._scroll(step)
        except tk.TclError:
            self._job = None
            return
        self._applied += step
        scheduler = self._scheduler
        if scheduler is None:
            self._job = None
            return
        try:
            self._job = scheduler.after(_FRAME_MS, self._tick)
        except tk.TclError:
            self._job = None

    def reset(self) -> None:
        """Forget pending movement (used when the target is rebuilt)."""
        self._target = self._applied
        if self._job is not None:
            try:
                self._scheduler.after_cancel(self._job)
            except Exception:
                pass
            self._job = None


def enable(widget: Any, units_per_notch: int = 4) -> None:
    """Bind eased wheel scrolling directly to *widget* (Text / Treeview / CTkTextbox)."""
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
    """Enable smooth scrolling on every Text and Treeview below *root*."""
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
