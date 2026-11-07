"""Windows taskbar identity (AppUserModelID).

The process icon comes from the EXE's own resource (PyInstaller ``--icon``), so
no runtime image handling is needed.  What still has to be done before any
window is shown is giving the process a stable AppUserModelID: without one
Windows groups the app under its host executable (python.exe when run from
source) and shows that program's icon in the taskbar instead of the EXE icon.

Everything here is ctypes-only and platform-agnostic off Windows; there is no
tkinter dependency, so this module can be imported by the CLI and the desktop
shell alike.
"""

from __future__ import annotations

import sys


def init_app_id() -> None:
    """Give the process a stable AppUserModelID before any window is shown.

    No-op off Windows; on Windows the shell call is made directly and any
    failure propagates to the caller, which is best placed to report it without
    aborting startup.
    """
    if sys.platform != 'win32':
        return
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
        'ServerProtocolBridge.1')
