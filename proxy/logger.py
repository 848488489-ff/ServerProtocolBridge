"""Logging.

A single log stream can go to the console (command line mode / console EXE) and
to a callback (GUI) at the same time.  The callback may be invoked from any
thread; the GUI side only needs to push the text into a queue.
"""

from __future__ import annotations

import sys
import threading
import time

from .i18n import tr

LEVELS = {'debug': 10, 'info': 20, 'warn': 30, 'error': 40}
# Translation key of the tag shown in each log line.  The level identifiers
# themselves are protocol content and never change; only the displayed tag
# follows the active language.  The lookup happens per line, so a runtime
# language switch in the GUI applies to all subsequent lines as well.
LEVEL_LABEL_KEYS = {'debug': 'core.log.debug', 'info': 'core.log.info',
                    'warn': 'core.log.warn', 'error': 'core.log.error'}


class Logger:
    def __init__(self, level: str = 'info', callback=None, stream=None, echo: bool = True):
        self.level = level if level in LEVELS else 'info'
        self.callback = callback
        self.stream = stream
        self.echo = echo
        self._lock = threading.Lock()

    def set_level(self, level: str) -> None:
        if level in LEVELS:
            self.level = level

    def enabled(self, level: str) -> bool:
        return LEVELS.get(level, 20) >= LEVELS.get(self.level, 20)

    def _emit(self, level: str, message: str) -> None:
        if not self.enabled(level):
            return
        stamp = time.strftime('%H:%M:%S')
        key = LEVEL_LABEL_KEYS.get(level)
        label = tr(key) if key else level
        text = '[%s] [%s] %s' % (stamp, label, message)
        if self.callback is not None:
            try:
                self.callback(level, text)
            except Exception:  # a GUI callback error must not break forwarding
                pass
        if self.echo:
            stream = self.stream if self.stream is not None else sys.stdout
            if stream is None:  # may be None under pythonw / a --windowed build
                return
            try:
                with self._lock:
                    print(text, file=stream, flush=True)
            except Exception:
                pass

    def debug(self, message: str) -> None:
        self._emit('debug', message)

    def info(self, message: str) -> None:
        self._emit('info', message)

    def warn(self, message: str) -> None:
        self._emit('warn', message)

    def error(self, message: str) -> None:
        self._emit('error', message)


class NullLogger(Logger):
    """A logger that does nothing, used by tests and library callers."""

    def __init__(self):
        super().__init__(level='error', echo=False)
