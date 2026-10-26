"""Optional access password for the Web UI.

The password is never stored in ``config.json``: only a salted PBKDF2 hash
lives in ``web_auth.json`` next to the configuration, and the session signing
key is generated once and kept there as well.  The password is disabled by
default, so a fresh install opens the page directly, exactly as before.

Login attempts are rate limited in memory: after five failures from the same
address the next attempt is refused for thirty seconds.  The limit is not
persisted because restarting the process already clears every session.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from collections import deque
from pathlib import Path

from .utils import config_dir

AUTH_FILENAME = 'web_auth.json'
ITERATIONS = 240_000
LOCK_AFTER = 5
LOCK_SECONDS = 30.0

_lock = threading.RLock()
_failures: dict[str, deque[float]] = {}


def auth_path() -> Path:
    """Next to ``config.json``, in the user's configuration folder."""
    return config_dir() / AUTH_FILENAME


def _default_state() -> dict:
    return {'enabled': False, 'salt': '', 'hash': '', 'iterations': ITERATIONS,
            'secret': ''}


def _read() -> dict:
    path = auth_path()
    state = _default_state()
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return state
    if not isinstance(payload, dict):
        return state
    for key in ('salt', 'hash', 'secret'):
        value = payload.get(key)
        if isinstance(value, str):
            state[key] = value
    state['enabled'] = bool(payload.get('enabled'))
    try:
        state['iterations'] = max(100_000, int(payload.get('iterations', ITERATIONS)))
    except (TypeError, ValueError):
        state['iterations'] = ITERATIONS
    return state


def _write(state: dict) -> None:
    path = auth_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n',
                         encoding='utf-8')
    temporary.replace(path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def state() -> dict:
    """Public view used by both interfaces; never exposes the hash."""
    with _lock:
        data = _read()
    return {'enabled': bool(data['enabled'] and data['hash']),
            'has_password': bool(data['hash'])}


def is_enabled() -> bool:
    return state()['enabled']


def has_password() -> bool:
    return state()['has_password']


def set_password(password: str) -> None:
    """Enable the password and replace the stored hash."""
    if not password:
        raise ValueError('empty password')
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt,
                                 ITERATIONS)
    with _lock:
        data = _read()
        data.update(enabled=True, salt=salt.hex(), hash=digest.hex(),
                    iterations=ITERATIONS)
        _write(data)
    clear_failures('')


def enable() -> None:
    """Put the stored hash into force without asking for the password again.

    ``set_password`` always rewrites the hash, so there is no way to turn an
    existing hash on without making the user retype it.  Without this the switch
    could read "on" while ``web_auth.json`` still said ``enabled: false``, and
    the Web UI would open without asking for a password at all.
    """
    with _lock:
        data = _read()
        if data['hash']:
            data['enabled'] = True
            _write(data)


def disable() -> None:
    with _lock:
        data = _read()
        data.update(enabled=False, salt='', hash='')
        _write(data)
    clear_failures('')


def verify(password: str) -> bool:
    with _lock:
        data = _read()
    if not data['hash'] or not data['salt']:
        return False
    try:
        salt = bytes.fromhex(data['salt'])
        expected = bytes.fromhex(data['hash'])
        iterations = int(data['iterations'])
    except (TypeError, ValueError):
        return False
    digest = hashlib.pbkdf2_hmac('sha256', (password or '').encode('utf-8'),
                                 salt, iterations)
    return hmac.compare_digest(digest, expected)


def secret_key() -> bytes:
    """Persistent Flask session key; generated on first use."""
    with _lock:
        data = _read()
        secret = data.get('secret') or ''
        if len(secret) < 32:
            secret = secrets.token_hex(32)
            data['secret'] = secret
            _write(data)
    return secret.encode('ascii')


# ---------------------------------------------------------------------------
# Login throttling
# ---------------------------------------------------------------------------

def _recent(key: str) -> deque[float]:
    bucket = _failures.get(key)
    if bucket is None:
        bucket = deque(maxlen=LOCK_AFTER)
        _failures[key] = bucket
    return bucket


def throttle_remaining(key: str) -> int:
    """Seconds the caller still has to wait, or zero when it may try."""
    with _lock:
        bucket = _failures.get(key)
        if not bucket or len(bucket) < LOCK_AFTER:
            return 0
        elapsed = time.monotonic() - bucket[-1]
    remaining = LOCK_SECONDS - elapsed
    return max(0, int(remaining) + (1 if remaining > 0 else 0))


def record_failure(key: str) -> None:
    with _lock:
        _recent(key).append(time.monotonic())


def clear_failures(key: str) -> None:
    with _lock:
        if key:
            _failures.pop(key, None)
        else:
            _failures.clear()
