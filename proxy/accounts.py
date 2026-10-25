"""Account management: offline / third-party (Yggdrasil) / Microsoft.

The account list lives in ``accounts.json`` inside the standard per-user data
directory (see :func:`utils.data_dir`) -- never next to the executable: the
file survives moving or reinstalling the program, and on Windows it lands in
%APPDATA% like every other programme's data.

Everything here is deliberately blocking (plain ``urllib``, no asyncio): the
GUI runs these calls from worker threads, and the proxy pushes its translation
layer through ``asyncio.to_thread`` for the same reason.  Callers that must
not block (the event loop) always go through those two doors.

Account kinds:

* ``offline``    -- a fixed player name; the UUID is derived offline (MD5 of
                    "OfflinePlayer:<name>"), which is exactly what an
                    offline-mode server computes for itself;
* ``thirdparty`` -- third-party account providers that expose a compatible
                    authenticate / refresh / session-join API (the protocol
                    commonly called Yggdrasil or authlib-injector).  These are
                    not necessarily skin sites: any provider offering those
                    endpoints works;
* ``microsoft``  -- a real Minecraft account: device-code sign-in (the user
                    types a short code at microsoft.com/link while this
                    program polls for the result), then the Xbox Live / XSTS
                    exchange, Minecraft token and session join at Mojang.

When an account is active the translator uses its exact name and UUID and --
for the two authenticated kinds -- registers the session join in the client's
place while answering the server's encryption request, so servers that really
check with the session service let the browser client through.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import urllib.error
import urllib.request
import uuid as uuid_module
import warnings
from dataclasses import dataclass, field
from pathlib import Path

from .i18n import tr
from .logger import NullLogger
from .utils import data_dir
from .version import VERSION

KIND_OFFLINE = 'offline'
KIND_THIRDPARTY = 'thirdparty'
KIND_MICROSOFT = 'microsoft'
KINDS = (KIND_OFFLINE, KIND_THIRDPARTY, KIND_MICROSOFT)

STORE_FILENAME = 'accounts.json'

OPEN_TIMEOUT = 10.0               # seconds per HTTP request
USER_AGENT = 'wss-proxy (ServerProtocolBridge/%s)' % VERSION
TOKEN_MARGIN = 120.0              # refresh this many seconds before expiry






SESSION_JOIN_URL = 'https://sessionserver.mojang.com/session/minecraft/join'


class AccountError(Exception):
    """A user-presentable account problem (message already translated).

    ``code`` carries the service's own error token when there was one
    (OAuth codes such as ``authorization_pending``, Yggdrasil's
    ``ForbiddenOperationException``, Mojang's ``NOT_FOUND``); ``xerr`` carries
    an Xbox XSTS error number.  Callers switch on these.
    """

    def __init__(self, message: str, code: str = '', xerr: int = 0) -> None:
        super().__init__(message)
        self.code = code
        self.xerr = xerr


@dataclass
class Account:
    """One account as stored in accounts.json."""

    kind: str = KIND_OFFLINE
    id: str = ''                    # local identifier assigned by the store
    username: str = ''              # in-game name
    uuid: str = ''                  # profile UUID (with or without dashes)
    authserver: str = ''            # third-party service root
    password: str = ''              # third-party only (needed to sign in again)
    access_token: str = ''          # third-party accessToken / Minecraft token
    client_token: str = ''          # third-party clientToken
    refresh_token: str = ''         # Microsoft OAuth refresh token
    token_expires: float = 0.0      # unix time the access token goes stale

    # ---------- derived ----------
    @property
    def uuid_bytes(self) -> bytes | None:
        text = (self.uuid or '').strip().replace('-', '').lower()
        if len(text) != 32:
            return None
        try:
            return bytes.fromhex(text)
        except ValueError:
            return None

    @property
    def label(self) -> str:
        """Short human-readable identification, e.g. "Steve (Microsoft)"."""
        return '%s (%s)' % (self.username or '?', tr('accounts.kind.' + self.kind))

    def joinable(self) -> bool:
        """Whether a session join makes sense for this account."""
        return self.kind in (KIND_MICROSOFT, KIND_THIRDPARTY)

    # ---------- serialization ----------
    def to_json(self) -> dict:
        return {
            'kind': self.kind, 'id': self.id, 'username': self.username,
            'uuid': self.uuid, 'authserver': self.authserver,
            'password': self.password, 'access_token': self.access_token,
            'client_token': self.client_token, 'refresh_token': self.refresh_token,
            'token_expires': self.token_expires,
        }

    @classmethod
    def from_json(cls, data: dict) -> 'Account':
        account = cls()
        if not isinstance(data, dict):
            return account
        kind = str(data.get('kind') or KIND_OFFLINE).strip().lower()
        account.kind = kind if kind in KINDS else KIND_OFFLINE
        account.id = str(data.get('id') or '')
        account.username = str(data.get('username') or '')
        account.uuid = str(data.get('uuid') or '')
        account.authserver = str(data.get('authserver') or '')
        account.password = str(data.get('password') or '')
        account.access_token = str(data.get('access_token') or '')
        account.client_token = str(data.get('client_token') or '')
        account.refresh_token = str(data.get('refresh_token') or '')
        try:
            account.token_expires = float(data.get('token_expires') or 0.0)
        except (TypeError, ValueError):
            account.token_expires = 0.0
        return account


@dataclass
class AccountStore:
    """The whole accounts.json document."""

    accounts: list[Account] = field(default_factory=list)
    active: str = ''                # id of the selected account ('' = none)

    def get(self, account_id: str) -> Account | None:
        for account in self.accounts:
            if account.id == account_id:
                return account
        return None

    def by_name(self, text: str) -> Account | None:
        target = (text or '').strip()
        if not target:
            return None
        for account in self.accounts:
            if account.id == target:
                return account
        lowered = target.lower()
        for account in self.accounts:
            if account.username.lower() == lowered:
                return account
        return None

    def to_json(self) -> dict:
        return {'accounts': [account.to_json() for account in self.accounts],
                'active': self.active}

    @classmethod
    def from_json(cls, data: dict) -> 'AccountStore':
        store = cls()
        if not isinstance(data, dict):
            return store
        items = data.get('accounts')
        if isinstance(items, list):
            store.accounts = [Account.from_json(item) for item in items
                              if isinstance(item, dict)]
        store.active = str(data.get('active') or '')
        return store


# ---------- store on disk ----------
def store_path() -> Path:
    return data_dir() / STORE_FILENAME


def load_store(path: Path | None = None) -> AccountStore:
    target = path or store_path()
    try:
        raw = target.read_text(encoding='utf-8-sig')
    except FileNotFoundError:
        return AccountStore()
    except OSError:
        return AccountStore()
    try:
        return AccountStore.from_json(json.loads(raw))
    except ValueError:
        return AccountStore()


def save_store(store: AccountStore, path: Path | None = None) -> Path:
    target = path or store_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(store.to_json(), ensure_ascii=False, indent=2) + '\n'
    target.write_text(payload, encoding='utf-8')
    return target


def add_account(account: Account) -> Account:
    """Store a new account (or overwrite one with the same id)."""
    store = load_store()
    if not account.id:
        account.id = uuid_module.uuid4().hex[:12]
    store.accounts = [item for item in store.accounts if item.id != account.id]
    store.accounts.append(account)
    save_store(store)
    return account


def replace_account(account: Account) -> Account:
    """Write refreshed tokens/fields of a listed account back to disk."""
    store = load_store()
    for index, item in enumerate(store.accounts):
        if item.id == account.id:
            store.accounts[index] = account
            save_store(store)
            return account
    return add_account(account)


def remove_account(account_id: str) -> bool:
    store = load_store()
    remaining = [item for item in store.accounts if item.id != account_id]
    if len(remaining) == len(store.accounts):
        return False
    store.accounts = remaining
    if store.active == account_id:
        store.active = ''
    save_store(store)
    return True


def set_active(account_id: str) -> None:
    store = load_store()
    store.active = account_id if store.get(account_id) else ''
    save_store(store)


def active_account() -> Account | None:
    store = load_store()
    return store.get(store.active)


def find_account(text: str) -> Account | None:
    return load_store().by_name(text)


def _persist(account: Account) -> None:
    """Save refreshed tokens back, but only when the account is listed."""
    if not account.id:
        return
    store = load_store()
    for index, item in enumerate(store.accounts):
        if item.id == account.id:
            store.accounts[index] = account
            save_store(store)
            return






































# ---------- session join ----------
def join_hash(server_id: str, secret: bytes, public_key_der: bytes) -> str:
    """The hash both sides compute for a session join (SHA-1 of server id,
    shared secret and public key)."""
    return hashlib.sha1(server_id.encode('utf-8') + secret + public_key_der).hexdigest()


def _join_url(account: Account) -> str:
    if account.kind == KIND_MICROSOFT:
        return SESSION_JOIN_URL
    return account.authserver.rstrip('/') + '/sessionserver/session/minecraft/join'


def _force_refresh(account: Account, log=None) -> None:
    """Renew tokens after the session service rejected them."""
    if account.kind == KIND_MICROSOFT:
        microsoft_refresh(account, log)
        return
    if thirdparty_refresh(account):
        return
    if account.password:
        fresh = thirdparty_authenticate(account.authserver, account.username,
                                        account.password)
        account.access_token = fresh.access_token
        account.client_token = fresh.client_token
        if fresh.uuid:
            account.uuid = fresh.uuid
        if fresh.username:
            account.username = fresh.username
        return
    raise AccountError(tr('accounts.error.need_login'))


def join_session(account: Account, server_hash: str, log=None) -> None:
    """Register the server join with the session service, in the client's place.

    The login starts while the proxy answers the encryption request; the join
    must be there before that answer arrives, otherwise a checking server
    kicks the player.  Microsoft accounts refresh their token before every
    join (and the rotated refresh token is saved immediately), because a
    token that merely looks unexpired locally may already have been
    invalidated by Microsoft.  Raises AccountError when the refresh or join
    fails (expired sign-in, wrong account, no game ownership, network
    trouble); the caller shows that text to the player and closes the
    connection.
    """
    if not account.joinable():
        return
    profile = (account.uuid or '').strip().replace('-', '').lower()
    if len(profile) != 32:
        raise AccountError(tr('accounts.error.no_uuid'))
    url = _join_url(account)
    if account.kind == KIND_MICROSOFT:
        # Forced, not "if expiring": this is the one place where a stale
        # Microsoft token turns into a confusing kick.
        microsoft_refresh(account, log)
    else:
        thirdparty_ensure_token(account)
    last: AccountError | None = None
    for attempt in (1, 2):
        try:
            _request_json(url, {'accessToken': account.access_token,
                                'selectedProfile': profile,
                                'serverId': server_hash})
            _persist(account)              # keep any refreshed tokens
            return
        except AccountError as exc:
            last = exc
            if attempt == 1:
                # The fresh token was still rejected (race with another
                # session, or the service rotated it again); renew once.
                _force_refresh(account, log)
    if last is not None:
        raise last
    raise AccountError(tr('accounts.error.need_login'))

# Auth backends live in accounts_auth (split for file size); re-export
# the public names so callers keep using accounts.microsoft_* / .thirdparty_*.
from .accounts_auth import microsoft_device_start, microsoft_device_poll, microsoft_refresh, microsoft_ensure_token, thirdparty_authenticate, thirdparty_validate, thirdparty_refresh, thirdparty_ensure_token  # noqa: F401
