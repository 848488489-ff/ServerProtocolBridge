"""Shared runtime for the GUI and the Web UI.

Both interfaces drive one process-wide :class:`ServiceManager`: the window and
the browser page therefore start, stop and monitor the very same proxy, and a
log line written by the forwarding core shows up in both places.  The manager
also gives the Web UI read/write access to the live configuration object, so a
change saved in the browser is already in effect in the window (and vice
versa) without either side owning a copy.

Nothing here imports Tk or Flask: the module must stay importable in command
line mode and cheap to import from the Web UI thread.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

from . import config as config_module
from .i18n import set_language, tr
from .logger import LEVELS, Logger
from .version import VERSION

STOPPED = 'stopped'
STARTING = 'starting'
RUNNING = 'running'
STOPPING = 'stopping'
ERROR = 'error'


class LogHub:
    """Thread-safe recent-log buffer with a monotonic sequence number.

    ``seq`` only ever grows; a reader passes the last sequence it saw and gets
    exactly the lines added afterwards.  ``clear`` empties the buffer without
    resetting the counter, so a reader that missed the clear does not silently
    start receiving nothing.
    """

    def __init__(self, limit: int = 4000) -> None:
        self._lines: deque[tuple[int, str, str]] = deque(maxlen=limit)
        self._seq = 0
        self._lock = threading.Lock()

    @property
    def seq(self) -> int:
        with self._lock:
            return self._seq

    def add(self, level: str, text: str) -> None:
        with self._lock:
            self._seq += 1
            self._lines.append((self._seq, level, text))

    def snapshot(self, since: int = 0, limit: int | None = None) -> list[dict]:
        with self._lock:
            lines = [{'seq': seq, 'level': level, 'text': text}
                     for seq, level, text in self._lines if seq > since]
        if limit is not None and len(lines) > limit:
            lines = lines[-limit:]
        return lines

    def set_limit(self, limit: int) -> None:
        """Change how many lines are kept, applied immediately.

        ``deque`` cannot change ``maxlen`` in place, so the ring is rebuilt with
        the new cap.  Everything still in the old buffer is carried over, newest
        last; when the new cap is smaller the oldest lines are dropped, which is
        exactly what the user asked for when they lowered it.
        """
        limit = max(1, int(limit))
        with self._lock:
            self._lines = deque(self._lines, maxlen=limit)

    def clear(self) -> None:
        with self._lock:
            self._lines.clear()


class ServiceManager:
    """Owns the configuration, the logger and the running proxy."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.config = config_module.Config.load()
        set_language(self.config.language)
        self.hub = LogHub(self.config.log_max_lines)
        self.logger: Logger | None = None
        self.server = None
        self._state = STOPPED
        self._error = ''
        self._revision = 0
        self._started_at = 0.0
        self.web_url = ''

    # ---------- configuration ----------
    @property
    def revision(self) -> int:
        with self._lock:
            return self._revision

    def reload_config(self) -> config_module.Config:
        """Re-read config.json (used when another process edited it)."""
        with self._lock:
            config = config_module.Config.load()
            self.config = config
            set_language(config.language)
            if self.logger is not None:
                self.logger.set_level(config.log_level)
            self.hub.set_limit(config.log_max_lines)
            self._revision += 1
            return config

    def save_config(self, config: config_module.Config | None = None) -> config_module.Config:
        """Store *config*, activate its language and return the live object."""
        with self._lock:
            config = config or self.config
            self.config = config
            set_language(config.language)
            if self.logger is not None:
                self.logger.set_level(config.log_level)
            self.hub.set_limit(config.log_max_lines)
            self._revision += 1
            try:
                config.save()
            except OSError as exc:
                self.hub.add('warn', tr('gui.log.config_save_failed', error=exc))
            return config

    def set_log_limit(self, limit: int) -> int:
        """Resize the log buffer the next time a line arrives.

        The hub caps itself, so nothing is discarded here; the caller only tells
        it how many lines to keep from now on.  Returns the value applied.
        """
        limit = max(1, int(limit))
        self.hub.set_limit(limit)
        return limit

    # ---------- state ----------
    @property
    def state(self) -> str:
        with self._lock:
            return self._state

    @property
    def running(self) -> bool:
        with self._lock:
            return self._state == RUNNING

    @property
    def error(self) -> str:
        with self._lock:
            return self._error

    def set_state(self, state: str, error: str = '') -> None:
        with self._lock:
            self._state = state
            if error:
                self._error = error

    # ---------- service ----------
    def start(self, config: config_module.Config | None = None) -> tuple[bool, str]:
        """Start the proxy in a worker thread.

        Returns ``(ok, message)``; *message* is a user-presentable reason when
        the request was refused (already running, invalid configuration).
        """
        with self._lock:
            if self._state in (STARTING, RUNNING, STOPPING):
                return False, tr('runtime.busy')
            config = config or self.config
            problems = config.validate()
            if problems:
                return False, '\n'.join('· ' + item for item in problems)
            try:
                from .proxy import ProxyServer
            except Exception as exc:  # missing optional dependency
                return False, tr('gui.log.start_failed', error=exc)

            self.config = config
            set_language(config.language)
            self._revision += 1
            try:
                config.save()
            except OSError as exc:
                self.hub.add('warn', tr('gui.log.config_save_failed', error=exc))

            self.hub.add('info', '')
            self.logger = Logger(config.log_level, callback=self.hub.add, echo=True)
            self.logger.info(tr('gui.log.starting', name=tr('core.app_name'),
                                version=VERSION))
            self.logger.info(tr('gui.log.target', target=config.describe_target()))
            self.server = ProxyServer(config, self.logger)
            self._error = ''
            self._state = STARTING
            self._started_at = 0.0

        thread = threading.Thread(target=self._run_start, name='bridge-start',
                                  daemon=True)
        thread.start()
        return True, ''

    def _run_start(self) -> None:
        server = self.server
        logger = self.logger
        if server is None or logger is None:
            return
        try:
            info = server.start()
        except Exception as exc:
            logger.error(tr('gui.log.start_failed', error=exc))
            with self._lock:
                self.server = None
                self._state = ERROR
                self._error = str(exc)
            return
        logger.info(tr('gui.log.listening',
                       url=info.get('wss_url') or tr('gui.endpoint.disabled')))
        if getattr(self.config, 'startup_notice', True):
            logger.warning(tr('core.startup_notice_immature'))
        for listener in info.get('listeners', []):
            if listener.startswith('ws://'):
                logger.info(tr('gui.log.fallback_listener', url=listener))
        certificate = info.get('certificate')
        if certificate:
            logger.info(tr('gui.log.cert_fingerprint',
                           thumbprint=certificate['thumbprint']))
            logger.info(tr('gui.log.cert_trust_hint'))
        with self._lock:
            if self.server is server:
                self._state = RUNNING
                self._started_at = time.time()

    def stop(self, wait: bool = False) -> bool:
        """Stop the proxy; returns False when there was nothing to stop."""
        with self._lock:
            server = self.server
            if server is None or self._state in (STOPPED, ERROR):
                self._state = STOPPED
                self.server = None
                return False
            self._state = STOPPING

        def worker() -> None:
            try:
                server.stop()
            except Exception as exc:
                self.hub.add('error', str(exc))
                self.hub.add('info', tr('proxy.log.stopped'))
            finally:
                with self._lock:
                    if self.server is server:
                        self.server = None
                    self._state = STOPPED
                    self._started_at = 0.0

        if wait:
            worker()
            return True
        threading.Thread(target=worker, name='bridge-stop', daemon=True).start()
        return True

    def shutdown(self) -> None:
        """Blocking stop used on program exit."""
        with self._lock:
            server = self.server
        if server is None:
            return
        try:
            self.stop(wait=True)
        except Exception:
            pass

    # ---------- status ----------
    def status(self) -> dict:
        with self._lock:
            state = self._state
            error = self._error
            server = self.server
            config = self.config
            revision = self._revision
            started_at = self._started_at
        snapshot = {'active': 0, 'total': 0, 'bytes_to_server': 0,
                    'bytes_to_client': 0, 'uptime': 0.0}
        listeners: list[str] = []
        wss_url = None
        certificate = None
        if server is not None:
            try:
                snapshot = server.stats.snapshot()
                listeners = list(getattr(server, 'listeners', []) or [])
                live = server.describe()
                listeners = list(live.get('listeners') or [])
                wss_url = live.get('wss_url')
                certificate = live.get('certificate')
            except Exception:
                pass
        if not wss_url:
            wss_url = config.wss_url()
        if not listeners:
            listeners = config.listeners()
        if not snapshot.get('uptime') and started_at:
            snapshot['uptime'] = max(0.0, time.time() - started_at)
        return {
            'version': VERSION,
            'state': state,
            'running': state == RUNNING,
            'error': error,
            'revision': revision,
            'config': config.to_dict(),
            'endpoint': wss_url,
            'listeners': listeners,
            'target': config.describe_target(),
            'certificate': certificate,
            'web_url': self.web_url,
            'stats': snapshot,
        }


_manager: ServiceManager | None = None
_manager_lock = threading.Lock()


def get_manager() -> ServiceManager:
    """Return the process-wide manager, creating it on first use."""
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = ServiceManager()
        return _manager


def log_levels() -> tuple[str, ...]:
    return tuple(LEVELS)
