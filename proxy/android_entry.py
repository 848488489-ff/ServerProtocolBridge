"""Android entry point (Chaquopy).

The desktop build opens the control panel in a native pywebview window, but
pywebview is not available on Android.  The interface is therefore the same
Flask Web UI, served on 127.0.0.1 and rendered in an Android WebView.  The
proxy service itself is owned by the Web UI's ServiceManager, exactly as on
the desktop: the user starts it from the panel.

``MainActivity`` calls :func:`start_web_ui` after ``Python.start()`` and loads
the returned URL into the WebView.
"""

from __future__ import annotations


def start_web_ui() -> str:
    """Start the Flask Web UI and return its URL (for the WebView).

    Raises ``RuntimeError`` if the Web UI cannot bind.  The WebView can only
    reach a loopback address inside the app process, so a configured host that
    is not loopback is forced back to 127.0.0.1.
    """
    from .config import Config
    from .webserver import start_web_ui as _start_web_ui

    try:
        defaults = Config.load()
        host = defaults.web_host or '127.0.0.1'
        port = int(defaults.web_port)
    except Exception:
        host, port = '127.0.0.1', 8765
    if host not in ('127.0.0.1', 'localhost', '::1'):
        host = '127.0.0.1'
    url, error = _start_web_ui(host, port)
    if error or not url:
        raise RuntimeError('Web UI could not start: %s' % (error or 'unknown error'))
    return url
