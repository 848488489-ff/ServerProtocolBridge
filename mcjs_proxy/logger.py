"""日志。

同一份日志可以同时输出到控制台(命令行模式 / 带控制台的 EXE)与回调函数(图形界面)。
回调在任意线程被调用, 界面侧只需要把文本丢进队列即可。
"""

from __future__ import annotations

import sys
import threading
import time

LEVELS = {'debug': 10, 'info': 20, 'warn': 30, 'error': 40}
LEVEL_LABELS = {'debug': '调试', 'info': '信息', 'warn': '警告', 'error': '错误'}


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
        text = '[%s] [%s] %s' % (stamp, LEVEL_LABELS.get(level, level), message)
        if self.callback is not None:
            try:
                self.callback(level, text)
            except Exception:  # 界面回调异常不应该影响转发
                pass
        if self.echo:
            stream = self.stream if self.stream is not None else sys.stdout
            if stream is None:  # pythonw / --windowed 打包时可能为 None
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
    """什么都不做的日志器, 供测试与库调用使用。"""

    def __init__(self):
        super().__init__(level='error', echo=False)