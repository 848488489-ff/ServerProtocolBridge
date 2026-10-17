"""Small shared helpers: path resolution and byte/duration formatting."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def app_dir() -> Path:
    """Directory the program lives in.

    When frozen into an EXE this is the folder containing the executable (the
    place the user double-clicked); when run from source it is the project root.
    """
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resolve_path(value: str | os.PathLike[str], base: Path | None = None) -> Path:
    """Turn a configured path into an absolute one; relative paths are based on
    ``base`` (the program directory by default)."""
    path = Path(value).expanduser()
    if path.is_absolute():
        return path
    return (base or app_dir()) / path


def human_bytes(value: float) -> str:
    """Format a byte count into a human-readable string."""
    value = float(value)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if abs(value) < 1024 or unit == 'TB':
            if unit == 'B':
                return '%d B' % int(value)
            return '%.2f %s' % (value, unit)
        value /= 1024.0
    return '%.2f TB' % value


def human_duration(seconds: float) -> str:
    """Format a number of seconds as hours:minutes:seconds."""
    seconds = int(max(0, seconds))
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return '%d:%02d:%02d' % (hours, minutes, secs)
    return '%d:%02d' % (minutes, secs)
