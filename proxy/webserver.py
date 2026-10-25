"""Run the Flask Web UI in a daemon thread, at most once per process.

The window, the command line and the browser page all share one Web UI: the
first caller starts it and receives the URL, later callers receive the same
URL without binding a second port.  ``werkzeug.serving.make_server`` is used
instead of ``Flask.run`` so the listener can be shut down and rebound when the
user changes the bind address or port in the settings.

Ports are probed before the server starts, so a busy default port (8765)
simply moves to the next free one instead of failing inside a worker thread
where nobody would see the error.  A configured port of 0 asks the operating
system to pick one.
"""

from __future__ import annotations

import socket
import threading

DEFAULT_HOST = '127.0.0.1'
DEFAULT_PORT = 8765
PORT_SCAN = 20

_lock = threading.RLock()
_server = None
_thread: threading.Thread | None = None
_url = ''
_host = ''
_port = 0
_error = ''


def _port_free(host: str, port: int) -> bool:
    family = socket.AF_INET6 if ':' in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as sock:
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def _display_host(host: str) -> str:
    host = (host or DEFAULT_HOST).strip() or DEFAULT_HOST
    if host in ('0.0.0.0', '::', '[::]'):
        return '127.0.0.1'
    if ':' in host and not host.startswith('['):
        return '[%s]' % host
    return host


def _make_url(host: str, port: int) -> str:
    return 'http://%s:%d/' % (_display_host(host), int(port))


def _config_defaults() -> tuple[str, int]:
    try:
        from .runtime import get_manager

        config = get_manager().config
        return ((config.web_host or DEFAULT_HOST).strip() or DEFAULT_HOST,
                int(config.web_port))
    except Exception:
        return DEFAULT_HOST, DEFAULT_PORT


def _stop_locked() -> None:
    """Shut the current server down; the caller holds ``_lock``."""
    global _server, _thread, _url, _host, _port
    server = _server
    _server = None
    if server is not None:
        try:
            server.shutdown()
        except Exception:
            pass
        try:
            server.server_close()
        except Exception:
            pass
    thread = _thread
    _thread = None
    if thread is not None and thread.is_alive() and thread is not threading.current_thread():
        thread.join(timeout=3.0)
    _url = ''
    _host = ''
    _port = 0
    try:
        from .runtime import get_manager

        get_manager().web_url = ''
    except Exception:
        pass


def start_web_ui(host: str | None = None, port: int | None = None,
                 force: bool = False) -> tuple[str, str]:
    """Start the Web UI; returns ``(url, error)``, one of them empty.

    With *force* the current listener is replaced even when the requested
    address is unchanged (used by the restart button).
    """
    global _server, _thread, _url, _host, _port, _error

    default_host, default_port = _config_defaults()
    host = (host if host is not None else default_host).strip() or DEFAULT_HOST
    try:
        requested = int(port) if port is not None else int(default_port)
    except (TypeError, ValueError):
        requested = DEFAULT_PORT
    requested = max(0, min(65535, requested))

    with _lock:
        if _server is not None and _thread is not None and _thread.is_alive():
            if not force and _host == host and _port == requested:
                return _url, ''
            _stop_locked()

        try:
            from .web import create_app

            app = create_app()
        except Exception as exc:      # a broken Web UI must not kill the caller
            _error = str(exc)
            return '', _error

        candidates = [0] if requested == 0 else [
            item for item in range(requested, min(65535, requested + PORT_SCAN) + 1)
            if item == 0 or _port_free(host, item)]
        if not candidates:
            _error = 'no free port in range %d-%d' % (requested, requested + PORT_SCAN)
            return '', _error

        last_error = ''
        for candidate in candidates:
            try:
                from werkzeug.serving import make_server

                server = make_server(host, candidate, app, threaded=True)
            except Exception as exc:
                last_error = str(exc)
                continue
            actual = int(server.server_port)
            _server = server
            _host = host
            _port = actual
            _url = _make_url(host, actual)
            _error = ''
            _thread = threading.Thread(target=server.serve_forever,
                                       name='web-ui', daemon=True)
            _thread.start()
            try:
                from .runtime import get_manager

                get_manager().web_url = _url
            except Exception:
                pass
            return _url, ''

        _error = last_error or 'the Web UI could not bind %s:%d' % (host, requested)
        return '', _error


def restart_web_ui(host: str | None = None,
                   port: int | None = None) -> tuple[str, str]:
    """Stop the current listener and bind the requested address."""
    return start_web_ui(host, port, force=True)


def stop_web_ui() -> None:
    """Stop the Web UI; safe to call when it is not running."""
    global _error
    with _lock:
        _stop_locked()
        _error = ''


def current_url() -> str:
    return _url


def current_address() -> tuple[str, int]:
    return _host, _port


def last_error() -> str:
    return _error
