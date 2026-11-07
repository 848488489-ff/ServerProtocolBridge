"""Desktop shell that hosts the Web UI in a native OS window (pywebview).

The interface is the existing Flask Web UI; this module only puts it in a
native, resizable window.  No tkinter / CustomTkinter: pywebview drives the OS
webview (Edge WebView2 on Windows, WKWebView on macOS, WebKitGTK on Linux), so
one code base runs on every platform and the packaged binary stays small
because the webview engine and the .NET runtime are system components.

The window never owns the service: :class:`proxy.runtime.ServiceManager` does,
exactly as the browser Web UI always has.  That is what lets a browser tab and
the embedded window share one proxy and one log.

If pywebview or its platform backend is unavailable (a Linux box without
WebKitGTK, a stripped Windows without the WebView2 runtime, a missing
``pywebview`` package), the Web UI is opened in the default browser instead so
the program still works.
"""

from __future__ import annotations

import sys

DEFAULT_WIDTH = 1160
DEFAULT_HEIGHT = 790
MIN_WIDTH = 1020
MIN_HEIGHT = 690

# The live pywebview window (set in main); a browser-only run leaves it None.
# Kept at module scope so the language switcher in the Web UI can update the
# native title in place instead of only ever setting it once at startup.
_window = None


def update_window_title() -> None:
    """Refresh the native window title to match the current language.

    The Web UI changes the language at runtime; without this the OS title bar
    keeps the language it was created with.  Safe to call from the Flask
    thread: pywebview dispatches set_title to its own UI thread.
    """
    global _window
    if _window is None:
        return
    try:
        _window.set_title(_window_title())
    except Exception:
        pass


def _start_web_ui(host=None, port=None) -> tuple[str, str]:
    """Start the Flask Web UI; returns ``(url, error)``."""
    from .config import Config
    from .webserver import start_web_ui

    try:
        defaults = Config.load()
        host = (host if host is not None else (defaults.web_host or '127.0.0.1'))
        port = int(port) if port is not None else int(defaults.web_port)
    except Exception:
        host = host or '127.0.0.1'
        port = int(port) if port is not None else 8765
    return start_web_ui(host, port)


def _write_stderr(message: str) -> None:
    """Write to stderr even when it is None.

    The packaged EXE is built with ``--windowed`` (GUI subsystem), so Windows
    gives it no console and ``sys.stderr`` / ``sys.stdout`` are ``None``.  A
    bare ``sys.stderr.write(...)`` then raises ``AttributeError`` and kills the
    launch before the window ever appears (the classic "works the second time"
    bug: the first run hits an error path, the second does not).  Route every
    diagnostic here instead.
    """
    stream = getattr(sys, 'stderr', None)
    if stream is not None:
        try:
            stream.write(message)
            stream.flush()
            return
        except (AttributeError, OSError, ValueError):
            pass
    # Fall back to a file so the message is never silently lost.
    try:
        import os
        import tempfile
        path = os.path.join(tempfile.gettempdir(), 'server-protocol-bridge.log')
        with open(path, 'a', encoding='utf-8', errors='replace') as handle:
            handle.write(message)
    except Exception:
        pass


def _print(message: str) -> None:
    """Print to stdout when a console exists; otherwise discard safely."""
    stream = getattr(sys, 'stdout', None)
    if stream is None:
        _write_stderr(message + '\n')
        return
    try:
        print(message)
    except (AttributeError, OSError, ValueError):
        _write_stderr(message + '\n')


def _window_title() -> str:
    from .config import Config
    from .i18n import set_language, tr

    try:
        set_language(Config.load().language)
    except Exception:
        pass
    return tr('core.app_name')


def _open_browser(url: str) -> None:
    import webbrowser

    try:
        webbrowser.open(url)
    except Exception:
        pass


def _message_box(title: str, message: str) -> None:
    """Show a native message box (Windows) or fall back to a terminal line.

    Used for startup errors and the "port was busy, used a different one"
    notice: these happen before (or around) the webview window, so a plain
    stderr line alone is easy to miss on a GUI double-click.
    """
    try:
        import ctypes

        # 0x10 = MB_ICONERROR, 0x40 = MB_ICONINFORMATION, 0x0 = MB_OK.
        ctypes.windll.user32.MessageBoxW(None, message, title, 0x10)
        return
    except Exception:
        pass
    _write_stderr('%s: %s\n' % (title, message))


def main(host=None, port=None) -> int:
    """Start the Web UI and show it in a native window; 0 on success."""
    url, error = _start_web_ui(host, port)
    if error or not url:
        message = 'Web UI could not start:\n%s' % (error or 'unknown error')
        _write_stderr(message + '\n')
        _message_box('Server Protocol Bridge', message)
        return 1

    # If the configured port was busy we fell back to another one; tell the
    # user which port is actually in use instead of silently serving elsewhere.
    try:
        from . import webserver

        if webserver.port_was_adjusted():
            requested = webserver.requested_port()
            actual = webserver.current_address()[1]
            note = ('Port %d was already in use, so the Web UI is on %d.\n'
                    'The settings page has been updated to match.' % (requested, actual))
            _write_stderr(note + '\n')
            _message_box('Server Protocol Bridge', note)
    except Exception:
        pass

    title = _window_title()

    try:
        import webview
    except ImportError:
        _print('pywebview is not installed; opening the Web UI in your browser.')
        _open_browser(url)
        return 0

    try:
        global _window
        _window = webview.create_window(
            title, url,
            width=DEFAULT_WIDTH, height=DEFAULT_HEIGHT,
            min_size=(MIN_WIDTH, MIN_HEIGHT),
            # pywebview disables text selection by default.  The log page is
            # meant to be read and copied out of, so turn selection back on for
            # the whole embedded page (Ctrl+C then works like a browser).
            text_select=True,
        )
        # Blocks until the window is closed.  Returning then lets the process
        # exit, which takes the Flask daemon thread (and the proxy) with it.
        webview.start()
    except Exception as exc:
        # WebView2 runtime missing on Windows, or the GTK/WebKit backend
        # missing on Linux: the program still works through a browser tab.
        _write_stderr(
            'Embedded window unavailable (%s); opening the Web UI in your browser.\n' % exc)
        _open_browser(url)
        return 0
    return 0
