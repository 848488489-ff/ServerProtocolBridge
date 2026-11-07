#!/usr/bin/env python3
"""Server Protocol Bridge -- program entry point.

Running it (or double-clicking the EXE) opens the Web UI in a native window
(pywebview shell); add --no-gui to run in command line mode.

    python main.py
    python main.py --no-gui --target play.example.net --port 8443
    python main.py --check
    python main.py --web-ui                  # Web UI only
    python main.py --web-ui --gui            # window and Web UI
    python main.py --web-ui --web-port 9000  # pick the browser port
"""

from __future__ import annotations

import sys

# Options that select the command line interface.  The Web UI switches are
# deliberately not in this tuple: they choose an interface, they do not want
# the CLI parser.
CLI_FLAGS = ('--no-gui', '--cli', '--check', '--selftest', '--install-cert',
             '--version', '--check-update', '--update-url', '--no-update-check',
             '--help', '-h')


def _use_cli(argv) -> bool:
    for item in argv:
        if item in CLI_FLAGS:
            return True
        if item.startswith('--target') or item.startswith('--config'):
            return True
    return False


def _option(argv, name: str, default: str) -> str:
    """Return ``--name value`` or ``--name=value`` from the command line."""
    for index, item in enumerate(argv):
        if item == name and index + 1 < len(argv):
            return argv[index + 1]
        if item.startswith(name + '='):
            return item.split('=', 1)[1]
    return default


def _write_stderr(message: str) -> None:
    """Write to stderr without crashing when it is None (--windowed build)."""
    stream = getattr(sys, 'stderr', None)
    if stream is not None:
        try:
            stream.write(message)
            stream.flush()
            return
        except (AttributeError, OSError, ValueError):
            pass
    try:
        import os
        import tempfile
        with open(os.path.join(tempfile.gettempdir(), 'server-protocol-bridge.log'),
                  'a', encoding='utf-8', errors='replace') as handle:
            handle.write(message)
    except Exception:
        pass


def _print(message: str) -> None:
    """Print when a console exists; otherwise log to the temp file."""
    stream = getattr(sys, 'stdout', None)
    if stream is not None:
        try:
            print(message)
            return
        except (AttributeError, OSError, ValueError):
            pass
    _write_stderr(message + '\n')


def _install_safe_streams() -> None:
    """Make ``print`` / ``sys.stderr.write`` safe in the windowed build.

    The released EXE is built with ``--windowed`` (GUI subsystem): Windows gives
    it no console, so ``sys.stdout`` and ``sys.stderr`` are ``None``.  Any code
    that does ``print(...)`` or ``sys.stderr.write(...)`` then raises
    ``AttributeError: 'NoneType' object has no attribute 'write'`` and kills the
    launch -- which is exactly the "works the second time" bug, because the
    first run reaches an error path that writes to stderr and the second does
    not.  Installing real file-backed fallback streams here, before any other
    module can print, makes every ``print`` / ``write`` safe everywhere.
    """
    if not getattr(sys, 'frozen', False):
        return  # running from source: a real console is present
    for name in ('stdout', 'stderr'):
        current = getattr(sys, name, None)
        if current is not None:
            try:
                current.fileno()
                continue  # already a usable stream (console attached)
            except (AttributeError, OSError, ValueError):
                pass
        setattr(sys, name, _fallback_stream())


def _fallback_stream():
    """A text stream that appends to the temp log; never None, never raises."""
    import io
    import os
    import tempfile

    try:
        path = os.path.join(tempfile.gettempdir(), 'server-protocol-bridge.log')
        handle = open(path, 'a', encoding='utf-8', errors='replace', buffering=1)
        return handle
    except Exception:
        return io.StringIO()


def main() -> int:
    argv = sys.argv[1:]

    # A --windowed build has sys.stdout/stderr == None.  Install safe fallback
    # streams *before* anything can print, so no module can crash on a write.
    _install_safe_streams()

    # The released EXE is built with --windowed, which is a GUI-subsystem
    # binary: Windows does not attach it to the console that launched it and
    # sys.stdout/stderr are None, so --version and friends printed nowhere.
    # Attaching to the parent console restores normal CLI behaviour.  When there
    # is no parent console to attach to (PowerShell &, some cmd paths -- cmd /c
    # launches a GUI binary asynchronously and exits before it runs) the CLI run
    # creates its own visible console so the output has somewhere to go and can
    # be read.  A double-click from Explorer takes neither path: it never enters
    # the CLI branch, so no console window appears behind the GUI.
    if _use_cli(argv):
        from proxy.console import attach_parent_console

        attach_parent_console(create_if_missing=True)
    elif '--web-ui' in argv:
        from proxy.console import attach_parent_console

        # --web-ui prints the access URL, so it needs a console too; the GUI
        # window (when requested) opens afterwards.
        attach_parent_console(create_if_missing=True)

    # DPI awareness must be armed before any Tk window is allocated; see
    # proxy.dpi for why CTk's own activation is too late.
    from proxy.dpi import activate as _activate_dpi
    from proxy.icon import init_app_id as _init_app_id

    _activate_dpi()
    try:
        _init_app_id()
    except (OSError, AttributeError) as exc:  # cosmetic: taskbar falls back to the host icon
        _write_stderr('AppUserModelID not set: %s\n' % exc)

    if _use_cli(argv):
        from proxy.cli import main as cli_main
        return cli_main(argv)

    web_requested = '--web-ui' in argv
    gui_requested = '--no-gui' not in argv and ('--gui' in argv or not web_requested)

    # A console-subsystem build (PyInstaller --console) keeps CLI output working
    # from PowerShell/cmd, but a plain double-click would leave a black console
    # window behind the GUI.  Detach from it here so the GUI launches cleanly;
    # CLI runs already returned above and keep their console.  A --web-ui run
    # still needs its console until the URL has been printed below, so it is
    # only detached when a native window is actually about to open.
    if sys.platform.startswith('win') and getattr(sys, 'frozen', False) and not web_requested:
        try:
            import ctypes
            ctypes.windll.kernel32.FreeConsole()
        except Exception:
            pass

    if web_requested:
        from proxy.webserver import start_web_ui

        try:
            from proxy.config import Config

            defaults = Config.load()
            default_host, default_port = defaults.web_host, str(defaults.web_port)
        except Exception:
            default_host, default_port = '127.0.0.1', '8765'
        host = _option(argv, '--web-host', default_host)
        try:
            port = int(_option(argv, '--web-port', default_port))
        except ValueError:
            port = int(default_port) if default_port.isdigit() else 8765
        url, error = start_web_ui(host, port)
        if url:
            _print('Web UI: %s' % url)
        else:
            _write_stderr('Web UI could not start: %s\n' % error)

    if gui_requested:
        # The desktop UI is the Web UI in a native window (pywebview); there is
        # no tkinter/CustomTkinter to fall back on.  If the webview backend is
        # unavailable the shell opens the Web UI in the default browser itself.
        from proxy.gui_shell import main as gui_main

        return gui_main()

    if web_requested:
        import time
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            _print('\nShutting down...')
            return 0

    return 0


if __name__ == '__main__':
    sys.exit(main())
