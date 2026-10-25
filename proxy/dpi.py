"""DPI awareness for the window, armed before Tk has allocated one.

CustomTkinter marks the process DPI-aware only inside ``CTk.__init__`` -- and
there it does so *after* ``tkinter.Tk.__init__`` has already created the root
window, so the first frames are painted by a process that still reports itself
as DPI-unaware and are then bitmap-stretched.  It also uses
``SetProcessDpiAwareness(2)``, i.e. per-monitor awareness **v1**, whose
non-client area (title bar) does not scale and whose cross-monitor move shows a
visible snap.

Calling :func:`activate` at import time -- before any Tk window exists -- fixes
the ordering and upgrades to per-monitor v2, which is the modern contract.  The
call is idempotent, so it is safe to repeat: ``main()`` calls it first, and
:class:`~proxy.gui_ctk.BridgeApp` calls it again just before ``super().__init__()``
covers the case where that module is used directly without going through
``main()``.

CTk's own scale factor is re-used rather than recomputed, so a value produced by
:func:`scale` always matches the value CTk applies to its widgets.
:func:`watch` hooks into CTk's existing per-monitor update loop, so raw Tk
surfaces that CTk never touches can be rescaled when the window moves to a
monitor with a different factor.
"""

from __future__ import annotations

import sys

_WINDOWS = sys.platform.startswith('win')

# DPI_AWARENESS_CONTEXT constants as HANDLE values.  Per-monitor v2 is preferred
# because its non-client area scales and moving the window between monitors with
# different scaling does not snap.
_CONTEXT_V2 = -4
_CONTEXT_PER_MONITOR = -3
_CONTEXT_SYSTEM = -2

# DPI_TYPE_EFFECTIVE_DPI, for GetDpiForMonitor.
_EFFECTIVE_DPI = 0


def _set_process_awareness() -> bool:
    """Set process DPI awareness; return True when it was accepted.

    Tries ``SetProcessDpiAwarenessContext`` first because it is the only call
    that can express per-monitor v2.  Older Windows has no such entry point, so
    fall back to the shcore flag and finally to the legacy system-aware call.
    """
    if not _WINDOWS:
        return False
    import ctypes

    for context in (_CONTEXT_V2, _CONTEXT_PER_MONITOR, _CONTEXT_SYSTEM):
        try:
            if ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(context)):
                return True
        except (AttributeError, OSError):
            continue

    try:
        if ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0:
            return True
        if ctypes.windll.shcore.SetProcessDpiAwareness(1) == 0:
            return True
    except (AttributeError, OSError):
        pass

    try:
        ctypes.windll.user32.SetProcessDPIAware()
        return True
    except (AttributeError, OSError):
        return False


def activate() -> bool:
    """Arm DPI awareness.  Call before any Tk window is created."""
    return _set_process_awareness()


def _window_scale(window) -> float:
    """CTk's scale factor for *window*, matching exactly what CTk applies."""
    try:
        from customtkinter.windows.widgets.scaling.scaling_tracker import ScalingTracker

        return float(ScalingTracker.get_window_scaling(window)) or 1.0
    except Exception:
        return 1.0


def get_scaling(window=None) -> float:
    """Current DPI scale factor (1.0 at 100%).

    Pass the Tk window when possible so the answer is CTk's own factor.  With no
    window -- before it exists -- the primary monitor's DPI is read directly,
    which is what CTk will report once the window does exist.
    """
    if window is not None:
        return _window_scale(window)
    if not _WINDOWS:
        return 1.0
    import ctypes

    try:
        from ctypes import wintypes

        handle = ctypes.windll.user32.MonitorFromWindow(0, 2)
        x, y = wintypes.UINT(), wintypes.UINT()
        ctypes.windll.shcore.GetDpiForMonitor(handle, _EFFECTIVE_DPI,
                                              ctypes.pointer(x), ctypes.pointer(y))
    except (AttributeError, OSError):
        return 1.0
    if not x.value:
        return 1.0
    return x.value / 96.0


def scale(window, value) -> int:
    """Scale one pixel value to the window's DPI."""
    factor = _window_scale(window)
    return int(round(value * factor))


def scaled_font(font, window):
    """CTkFont -> Tk font at the window's DPI, for ttk.

    ttk is never visited by CTk's scaling pass, so handing it a CTkFont object
    hands it the *unscaled* size: a 13 px face renders at 13 physical pixels
    while the rest of the window renders at 26.  Rebuild the same face at the
    scaled pixel size.  The caller must keep the result alive -- Tk holds only a
    name, not a reference.
    """
    from tkinter import font as tkfont

    factor = _window_scale(window)
    size = int(round(font.cget('size') * factor))
    return tkfont.Font(family=font.cget('family'), size=-abs(size),
                       weight=font.cget('weight'), slant=font.cget('slant'),
                       underline=bool(font.cget('underline')),
                       overstrike=bool(font.cget('overstrike')))


def watch(window, callback) -> bool:
    """Call *callback(widget_scale, window_scale)* when the window's DPI changes.

    Registers the callback on CTk's scaling tracker, which already polls every
    100 ms and re-applies scaling when the window crosses to another monitor.
    Returns False when the platform or CTk version cannot support it.
    """
    try:
        from customtkinter.windows.widgets.scaling.scaling_tracker import ScalingTracker

        ScalingTracker.add_widget(callback, window)
        return True
    except Exception:
        return False
