"""Auth backends for accounts.py: Microsoft (mcauth) and third-party.

Split out of accounts.py for file size.  Function bodies are unchanged;
shared names (Account, _persist, ...) come from accounts via a bottom-of-
file re-export there, so callers always use ``accounts.microsoft_*`` /
``accounts.thirdparty_*``.
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

from .accounts import Account, AccountError, _persist, KIND_OFFLINE, KIND_THIRDPARTY, KIND_MICROSOFT, KINDS, STORE_FILENAME, OPEN_TIMEOUT, USER_AGENT, TOKEN_MARGIN, SESSION_JOIN_URL, data_dir, tr, NullLogger, VERSION

# The Microsoft sign-in (device code -> Xbox Live -> XSTS -> Minecraft token
# -> profile) is handled by mcauth3, which ships its own public client id:
# no application registration, no client secret and no redirect address are
# involved.  Both mcauth3 and requests pull in a sizeable import graph, so they
# are loaded on the first Microsoft sign-in instead of while the GUI starts.
# The rest of the program (offline accounts, third-party accounts, the proxy)
# keeps working when the package is absent.
MCMSA = None
MCAuthError = None
OAuthError = None
requests = None
_mcauth_attempted = False
_mcauth_lock = threading.Lock()
# Microsoft rotates refresh tokens on every use.  Serialise refreshes so two
# browser tabs cannot both consume the same token and leave one of them with
# a credential Microsoft has already invalidated.
_TOKEN_LOCK = threading.Lock()
def _load_mcauth() -> None:
    """Import the optional Microsoft dependencies once, on first use."""
    global MCMSA, MCAuthError, OAuthError, requests, _mcauth_attempted
    if _mcauth_attempted:
        return
    with _mcauth_lock:
        if _mcauth_attempted:
            return
        _mcauth_attempted = True
        try:
            with warnings.catch_warnings():
                # requests 2.32 checks its optional dependencies at import time
                # and warns about newer urllib3 / charset-normalizer builds;
                # the calls used here are unaffected.
                warnings.simplefilter('ignore')
                from mcauth3 import (MCMSA as _MCMSA,
                                     MCAuthError as _MCAuthError,
                                     OAuthError as _OAuthError)
                import requests as _requests
        except ImportError:
            return
        MCMSA = _MCMSA
        MCAuthError = _MCAuthError
        OAuthError = _OAuthError
        requests = _requests
def _mcauth_error_types() -> tuple[type[BaseException], ...]:
    """Exception classes that the optional Microsoft stack can raise.

    Evaluated when an exception is handled, after :func:`_load_mcauth` has
    populated the globals.  An empty tuple is valid and simply lets anything
    unexpected propagate.
    """
    types: list[type[BaseException]] = []
    if MCAuthError is not None:
        types.append(MCAuthError)
    if requests is not None:
        types.append(requests.RequestException)
    return tuple(types)
# ---------- HTTP plumbing ----------
def _service_error(code: int, raw: bytes) -> AccountError:
    payload = None
    try:
        payload = json.loads(raw.decode('utf-8', 'replace'))
    except ValueError:
        payload = None
    payload = payload if isinstance(payload, dict) else {}
    error_code = str(payload.get('error') or payload.get('errorType') or '')
    # 'Message' is the capitalised field of the Xbox answers
    detail = str(payload.get('errorMessage') or payload.get('Message')
                 or payload.get('error_description') or payload.get('message')
                 or payload.get('error') or '')
    try:
        xerr = int(payload.get('XErr') or 0)
    except (TypeError, ValueError):
        xerr = 0
    if not detail:
        detail = tr('accounts.error.unknown')
    return AccountError(tr('accounts.error.http', code=code, detail=detail),
                        code=error_code, xerr=xerr)
def _run(request: urllib.request.Request, timeout: float) -> dict:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(262144)
    except urllib.error.HTTPError as exc:
        body = b''
        try:
            body = exc.read(262144)
        except OSError:
            body = b''
        finally:
            exc.close()
        raise _service_error(exc.code, body) from None
    except urllib.error.URLError as exc:
        raise AccountError(tr('accounts.error.network', error=exc.reason)) from None
    except OSError as exc:                     # timeouts, DNS, socket errors
        raise AccountError(tr('accounts.error.network', error=exc)) from None
    if not raw:
        return {}
    try:
        payload = json.loads(raw.decode('utf-8', 'replace'))
    except ValueError:
        raise AccountError(tr('accounts.error.bad_response')) from None
    return payload if isinstance(payload, dict) else {}
def _request_json(url: str, payload: dict | None = None,
                  headers: dict | None = None, timeout: float = OPEN_TIMEOUT) -> dict:
    """POST a JSON body (or GET when payload is None) and return the JSON answer."""
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8') if payload is not None else None
    merged = {'User-Agent': USER_AGENT, 'Accept': 'application/json'}
    if payload is not None:
        merged['Content-Type'] = 'application/json'
    merged.update(headers or {})
    return _run(urllib.request.Request(url, data=body, headers=merged), timeout)
# ---------- third-party (Yggdrasil / authlib-injector) ----------
def _ygg_url(authserver: str, endpoint: str) -> str:
    return authserver.rstrip('/') + '/authserver/' + endpoint
def _check_authserver(authserver: str) -> str:
    base = (authserver or '').strip().rstrip('/')
    if not base.lower().startswith(('http://', 'https://')):
        raise AccountError(tr('accounts.thirdparty.bad_url'))
    return base
def _thirdparty_account(base: str, data: dict, fallback_name: str,
                        password: str) -> Account:
    access = str(data.get('accessToken') or '')
    if not access:
        raise AccountError(tr('accounts.error.bad_response'))
    profile = data.get('selectedProfile')
    if not isinstance(profile, dict):
        available = data.get('availableProfiles')
        profile = available[0] if isinstance(available, list) and available else None
    if not isinstance(profile, dict) or not profile.get('id'):
        raise AccountError(tr('accounts.thirdparty.no_profile'))
    return Account(
        kind=KIND_THIRDPARTY, id='',
        username=str(profile.get('name') or fallback_name),
        uuid=str(profile.get('id') or ''),
        authserver=base, password=password,
        access_token=access,
        client_token=str(data.get('clientToken') or ''))
def thirdparty_authenticate(authserver: str, username: str,
                            password: str) -> Account:
    """Sign in at a compatible third-party service and build an account from the answer."""
    base = _check_authserver(authserver)
    data = _request_json(_ygg_url(base, 'authenticate'), {
        'agent': {'name': 'Minecraft', 'version': 1},
        'username': username, 'password': password,
        'clientToken': uuid_module.uuid4().hex,
        'requestUser': False})
    return _thirdparty_account(base, data, username, password)
def thirdparty_validate(account: Account) -> bool:
    if not account.access_token:
        return False
    try:
        _request_json(_ygg_url(account.authserver, 'validate'), {
            'accessToken': account.access_token,
            'clientToken': account.client_token})
        return True
    except AccountError:
        return False
def thirdparty_refresh(account: Account) -> bool:
    """Extend the token's lifetime; False when the service says no."""
    if not account.access_token:
        return False
    try:
        data = _request_json(_ygg_url(account.authserver, 'refresh'), {
            'accessToken': account.access_token,
            'clientToken': account.client_token,
            'requestUser': False})
    except AccountError:
        return False
    access = str(data.get('accessToken') or '')
    if not access:
        return False
    account.access_token = access
    account.client_token = str(data.get('clientToken') or account.client_token)
    profile = data.get('selectedProfile')
    if isinstance(profile, dict):
        if profile.get('name'):
            account.username = str(profile['name'])
        if profile.get('id'):
            account.uuid = str(profile['id'])
    return True
def thirdparty_ensure_token(account: Account) -> None:
    """Make sure a valid access token is on the account; raise when impossible."""
    if account.access_token and thirdparty_validate(account):
        return
    if thirdparty_refresh(account):
        return
    if account.password:
        fresh = thirdparty_authenticate(account.authserver, account.username,
                                        account.password)
        account.username = fresh.username or account.username
        account.uuid = fresh.uuid or account.uuid
        account.access_token = fresh.access_token
        account.client_token = fresh.client_token
        return
    raise AccountError(tr('accounts.error.need_login'))
# ---------- Microsoft (sign-in through mcauth3) ----------
def _mcauth_client(verify: bool = True):
    """A fresh mcauth3 client carrying its built-in public client id.

    ``verify`` is only turned off after the user answered the certificate
    prompt; the decision is made in the GUI, never by the library.
    """
    if MCMSA is None and not _mcauth_attempted:
        _load_mcauth()
    if MCMSA is None:
        raise AccountError(tr('accounts.ms.library_missing'))
    client = MCMSA()
    if not verify:
        client.session.verify = False
        try:
            import urllib3

            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:              # the warning filter is a nicety only
            pass
    return client
def _mcauth_failure(exc: Exception) -> AccountError:
    """Translate a library / HTTP failure into a presentable error."""
    if requests is not None and isinstance(exc, requests.exceptions.SSLError):
        # The caller may offer to retry without the certificate check.
        return AccountError(tr('accounts.ms.ssl_failed', detail=exc),
                            code='ssl')
    if MCAuthError is not None and isinstance(exc, MCAuthError):
        message = str(exc) or tr('accounts.error.unknown')
        lowered = message.lower()
        if 'aadsts70000' in lowered or ('device_code' in lowered and 'already' in lowered):
            return AccountError(tr('accounts.ms.code_used'), code='code_used')
        return AccountError(message)
    response = getattr(exc, 'response', None)
    status = getattr(response, 'status_code', 0)
    if status:
        return AccountError(tr('accounts.error.http', code=status,
                               detail=str(exc)))
    return AccountError(tr('accounts.error.network', error=exc))
def _account_from_mcauth(result: dict) -> Account:
    """The library's answer -> the account this program stores."""
    tokens = result.get('tokens') or {}
    profile = result.get('profile') or {}
    name = str(profile.get('name') or '')
    profile_id = str(profile.get('id') or '')
    if not name or not profile_id:
        raise AccountError(tr('accounts.ms.no_character'))
    try:
        expires = float(tokens.get('expires_in') or 86400.0)
    except (TypeError, ValueError):
        expires = 86400.0
    return Account(
        kind=KIND_MICROSOFT, id='', username=name, uuid=profile_id,
        access_token=str(tokens.get('minecraft_access_token') or ''),
        refresh_token=str(tokens.get('microsoft_refresh_token') or ''),
        token_expires=time.time() + expires - TOKEN_MARGIN)
def microsoft_device_start(verify: bool = True) -> dict:
    """Ask Microsoft for a device code (the user types it at microsoft.com/link).

    The answer carries ``device_code`` (for the polling below), ``user_code``
    and ``verification_uri`` (what the dialog shows the user), plus
    ``expires_in`` and ``interval``.  ``verify=False`` skips the certificate
    check (only after the user agreed to that).
    """
    client = _mcauth_client(verify)
    try:
        info = client.start_auth()
    except _mcauth_error_types() as exc:
        raise _mcauth_failure(exc) from None
    if not isinstance(info, dict) or not info.get('device_code'):
        raise AccountError(tr('accounts.error.bad_response'))
    return info
def microsoft_device_poll(info: dict, verify: bool = True) -> Account:
    """Wait for the browser sign-in; the library then runs the whole chain.

    This blocks until the user finishes (or the code expires), so the GUI
    calls it from a worker thread.  A closed dialog simply stops listening:
    the account is only stored while the dialog is still open.
    """
    client = _mcauth_client(verify)
    try:
        result = client.finish_auth(info)
    except _mcauth_error_types() as exc:
        raise _mcauth_failure(exc) from None
    return _account_from_mcauth(result)
def microsoft_refresh(account: Account, log=None, verify: bool = True) -> None:
    """Renew the Minecraft token from the stored MSA refresh token."""
    with _TOKEN_LOCK:
        _microsoft_refresh_locked(account, log, verify)
def _microsoft_refresh_locked(account: Account, log=None, verify: bool = True) -> None:
    """The actual refresh, serialised by :data:`_TOKEN_LOCK`.

    Microsoft refresh tokens are single-use credentials that rotate on every
    use, so the fresh token is written back to accounts.json immediately.  A
    failure is wrapped with context: the caller shows it to the player and
    closes the connection instead of silently trying a stale token.
    """
    if account.id:
        # Another connection may have refreshed this account while this one
        # was waiting for the lock; use the newest rotated token.
        try:
            latest = load_store().get(account.id)
        except Exception:
            latest = None
        if latest is not None and latest.refresh_token and \
                latest.refresh_token != account.refresh_token:
            account.refresh_token = latest.refresh_token
    if not account.refresh_token:
        raise AccountError(tr('accounts.ms.refresh_failed',
                              error=tr('accounts.error.need_login')))
    client = _mcauth_client(verify)
    try:
        result = client.refresh_auth(account.refresh_token)
    except OAuthError:
        raise AccountError(tr('accounts.ms.refresh_failed',
                              error=tr('accounts.error.need_login'))) from None
    except _mcauth_error_types() as exc:
        failure = _mcauth_failure(exc)
        raise AccountError(tr('accounts.ms.refresh_failed', error=failure),
                           code=failure.code, xerr=failure.xerr) from None
    fresh = _account_from_mcauth(result)
    account.username = fresh.username or account.username
    account.uuid = fresh.uuid or account.uuid
    account.access_token = fresh.access_token
    account.refresh_token = fresh.refresh_token or account.refresh_token
    account.token_expires = fresh.token_expires
    _persist(account)
    logger = log or NullLogger()
    logger.info(tr('accounts.ms.refreshed', name=account.username))
def microsoft_ensure_token(account: Account, log=None) -> None:
    if account.access_token and time.time() < account.token_expires:
        return
    microsoft_refresh(account, log)
