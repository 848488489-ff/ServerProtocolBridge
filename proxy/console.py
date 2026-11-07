"""Console support for the Windows windowed (GUI-subsystem) build.

PyInstaller's ``--windowed`` bootloader is ``runw.exe``: a GUI-subsystem
executable.  Windows does not attach it to the console that launched it, and
Python's ``sys.stdout`` / ``sys.stderr`` are ``None``, so command-line flags
run but print nowhere.  That made ``--version``, ``--help``, ``--selftest``,
``--check`` and ``--no-gui`` look completely broken in a terminal.

``AttachConsole(ATTACH_PARENT_PROCESS)`` puts the process back on the parent
console.  The standard streams are then reopened on ``CONOUT$`` / ``CONIN$``,
or on the inherited pipe/file handles when the caller redirected output.  A
GUI launch from Explorer has no parent console, so the call simply returns
False and the window opens as before.
"""

from __future__ import annotations

import os
import sys

_ATTACHED = False

_ATTACH_PARENT_PROCESS = 0xFFFFFFFF
_STD_INPUT_HANDLE = -10
_STD_OUTPUT_HANDLE = -11
_STD_ERROR_HANDLE = -12
_ERROR_ACCESS_DENIED = 5
_DUPLICATE_SAME_ACCESS = 0x00000002


def _open_device(name: str, mode: str):
    try:
        return open(name, mode, encoding='utf-8', errors='replace', buffering=1)
    except OSError:
        return None


def _open_std_handle(kernel32, msvcrt, wintypes, ctypes, std_id: int, mode: str):
    """Duplicate an inherited standard handle and wrap it as a Python stream.

    Duplicating matters: ``open_osfhandle`` takes ownership of the descriptor,
    and closing the wrapper must not close the process-wide standard handle.
    """
    handle = kernel32.GetStdHandle(std_id)
    invalid = ctypes.c_void_p(-1).value
    if not handle or handle == invalid:
        return None
    process = kernel32.GetCurrentProcess()
    duplicate = wintypes.HANDLE()
    if not kernel32.DuplicateHandle(
            process, handle, process, ctypes.byref(duplicate),
            0, False, _DUPLICATE_SAME_ACCESS):
        return None
    flags = os.O_WRONLY if 'w' in mode else os.O_RDONLY
    try:
        fd = msvcrt.open_osfhandle(duplicate.value, flags)
    except OSError:
        kernel32.CloseHandle(duplicate)
        return None
    try:
        return os.fdopen(fd, mode, encoding='utf-8', errors='replace', buffering=1)
    except Exception:
        try:
            os.close(fd)
        except OSError:
            pass
        return None


def _replace_stream(kernel32, msvcrt, wintypes, ctypes,
                    name: str, std_id: int, mode: str, device: str) -> None:
    current = getattr(sys, name, None)
    if current is not None:
        try:
            current.fileno()
            return                      # already usable (console build / redirect)
        except (AttributeError, OSError, ValueError):
            pass
    stream = _open_std_handle(kernel32, msvcrt, wintypes, ctypes, std_id, mode)
    if stream is None:
        stream = _open_device(device, mode)
    if stream is not None:
        setattr(sys, name, stream)


def attach_parent_console(create_if_missing: bool = False) -> bool:
    """Attach to the console that launched this GUI-subsystem process.

    Returns True when a console is available for the standard streams.  Safe to
    call more than once; it does nothing off Windows or when running from
    source with a normal Python interpreter.

    When *create_if_missing* is True and there is no parent console to attach
    to, ``AllocConsole`` creates one.  That is the only way a GUI-subsystem
    process started from a terminal that does not hand it a console (PowerShell
    ``&``, some ``cmd /c`` paths) can print at all.  The created console is
    left **visible**: this function is only called for CLI/--web-ui runs, which
    must show their output (--help, --version, the access URL).  A double-click
    from Explorer never calls it, so no console window appears behind the GUI.
    """
    global _ATTACHED
    if _ATTACHED:
        return True
    if not sys.platform.startswith('win') or not getattr(sys, 'frozen', False):
        return False
    try:
        import ctypes
        import msvcrt
        from ctypes import wintypes
    except Exception:
        return False

    try:
        kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel32.AttachConsole.argtypes = [wintypes.DWORD]
        kernel32.AttachConsole.restype = wintypes.BOOL
        kernel32.GetStdHandle.argtypes = [wintypes.DWORD]
        kernel32.GetStdHandle.restype = wintypes.HANDLE
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.DuplicateHandle.argtypes = [
            wintypes.HANDLE, wintypes.HANDLE, wintypes.HANDLE,
            ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD,
            wintypes.BOOL, wintypes.DWORD]
        kernel32.DuplicateHandle.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        kernel32.SetConsoleOutputCP.argtypes = [wintypes.UINT]
        kernel32.SetConsoleCP.argtypes = [wintypes.UINT]
        kernel32.AllocConsole.restype = wintypes.BOOL
        kernel32.GetConsoleWindow.restype = wintypes.HWND

        attached = bool(kernel32.AttachConsole(_ATTACH_PARENT_PROCESS))
        if not attached and create_if_missing:
            if kernel32.AllocConsole():
                # Leave the console visible: CLI output (--help/--version/URL)
                # must be seen.  Only the GUI double-click path skips this
                # function entirely, so no console appears behind the window.
                attached = True
        if attached:
            # The program is UTF-8 internally.  Without this, Chinese log lines
            # written to CONOUT$ are decoded with the OEM code page and turn
            # into mojibake.
            kernel32.SetConsoleOutputCP(65001)
            kernel32.SetConsoleCP(65001)
        # When AttachConsole fails we still try to reopen the standard streams
        # from whatever handle the process inherited (a GUI-subsystem process
        # started from a terminal can carry valid console handles even though
        # AttachConsole reports failure, e.g. PowerShell launching it, or when
        # the parent console is owned by a --console sibling).  Skipping this
        # left --version/--help printing nowhere.  The fallback CONOUT$ open
        # only succeeds when a console actually exists; a plain double-click
        # from Explorer has none, so the GUI opens as before.
    except Exception:
        return False

    _replace_stream(kernel32, msvcrt, wintypes, ctypes,
                    'stdin', _STD_INPUT_HANDLE, 'r', 'CONIN$')
    _replace_stream(kernel32, msvcrt, wintypes, ctypes,
                    'stdout', _STD_OUTPUT_HANDLE, 'w', 'CONOUT$')
    _replace_stream(kernel32, msvcrt, wintypes, ctypes,
                    'stderr', _STD_ERROR_HANDLE, 'w', 'CONOUT$')
    _ATTACHED = True
    return True
