"""Per-monitor DPI awareness, armed before the first window is allocated.

The desktop shell uses the OS webview (pywebview), whose window is DPI-aware
natively, but the process must still declare awareness before any window exists
or Windows bitmap-stretches the first frames.  Calling :func:`activate` at
import time (before pywebview allocates its window) fixes the ordering and
upgrades to per-monitor v2, which is the modern contract: the non-client area
scales and moving the window between monitors does not snap.

The call is idempotent and platform-agnostic off Windows.  It uses only ctypes,
so this module never pulls in tkinter or CustomTkinter.
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
    """Arm DPI awareness.  Call before any window is created."""
    return _set_process_awareness()
