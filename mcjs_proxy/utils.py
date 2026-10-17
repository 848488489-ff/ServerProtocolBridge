"""通用小工具: 路径解析、字节数/时长格式化。"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def app_dir() -> Path:
    """程序所在目录。

    打包成 EXE 之后用 EXE 所在目录(用户双击的地方), 从源码运行时用项目根目录。
    """
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resolve_path(value: str | os.PathLike[str], base: Path | None = None) -> Path:
    """把配置里的路径解析成绝对路径, 相对路径以 base(默认程序目录)为基准。"""
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (base or app_dir()) / path


def human_bytes(value: float) -> str:
    """把字节数格式化成便于阅读的形式。"""
    value = float(value)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if abs(value) < 1024 or unit == 'TB':
            if unit == 'B':
                return '%d B' % int(value)
            return '%.2f %s' % (value, unit)
        value /= 1024.0
    return '%.2f TB' % value


def human_duration(seconds: float) -> str:
    """把秒数格式化成 时:分:秒。"""
    seconds = int(max(0, seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return '%d:%02d:%02d' % (hours, minutes, secs)
    return '%d:%02d' % (minutes, secs)