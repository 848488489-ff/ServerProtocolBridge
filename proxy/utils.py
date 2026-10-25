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


# Folder name under the per-user data directory; deliberately without spaces.
DATA_FOLDER = 'ServerProtocolBridge'


def data_dir() -> Path:
    """The standard per-user data directory of this program (cross-platform).

    Windows: %APPDATA%\\ServerProtocolBridge
    macOS:   ~/Library/Application Support/ServerProtocolBridge
    Linux:   $XDG_DATA_HOME/ServerProtocolBridge (or ~/.local/share/...)

    Files that belong to the user rather than to the installation (the account
    list, for one) live here: moving or reinstalling the EXE cannot lose them.
    The SPB_DATA_DIR environment variable overrides the location outright,
    which tests and portable installs use.
    """
    override = (os.environ.get('SPB_DATA_DIR') or '').strip()
    if override:
        return Path(override).expanduser()
    if os.name == 'nt':
        base = (os.environ.get('APPDATA') or '').strip()
        root = Path(base) if base else Path.home() / 'AppData' / 'Roaming'
    elif sys.platform == 'darwin':
        root = Path.home() / 'Library' / 'Application Support'
    else:
        base = (os.environ.get('XDG_DATA_HOME') or '').strip()
        root = Path(base) if base else Path.home() / '.local' / 'share'
    return root / DATA_FOLDER


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
