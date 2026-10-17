"""Cloud version check.

The program asks a small HTTPS endpoint for the latest published version and
compares it with the version that is running:

    GET https://<endpoint>/     ->  {"version": "1.1",
                                     "download_page": "https://.../download"}

Only the known fields are read (``version`` plus the optional download page and
release notes); anything else in the document is ignored, and every optional
field may be missing -- the endpoint can grow new fields or drop them without
breaking older builds.  The link is opened in the browser and never fetched by
this program itself.

Nothing is sent besides the request itself, there is no caching and no retry
loop: one plain GET with a timeout.
"""

from __future__ import annotations

import json
import re
import threading
import urllib.error
import urllib.request

from .i18n import tr
from .version import VERSION

# Public endpoint that announces the newest release: a plain static file on
# Cloudflare Pages (see the "云端版本检查" section of the README for the
# expected document).  *.pages.dev is reachable from mainland China, unlike
# *.workers.dev, which is DNS-poisoned there.  Several URLs may be listed,
# separated by commas, and are tried in order (see check()), so a mirror that
# works on the local network can be put in front of this one.
PAGES_UPDATE_URL = 'https://banbengengxinjiancha.pages.dev/version.json'
DEFAULT_UPDATE_URL = PAGES_UPDATE_URL

# The endpoint may sit on the other side of the planet, so give it room: the
# check runs in the background everywhere, waiting a few extra seconds costs
# nothing.
TIMEOUT_SEC = 20.0
MAX_ANSWER_BYTES = 64 * 1024

# Known fields, with the spellings a hand-written endpoint is likely to use
VERSION_KEYS = ('version', 'latest', 'latest_version', 'tag_name', 'name')
PAGE_KEYS = ('download_page', 'page_url', 'download_url', 'page', 'url', 'html_url', 'download')
NOTES_KEYS = ('notes', 'changelog', 'body', 'message', 'description')

# Request identity: the public endpoint may gate on it, so it always mentions
# "wss-proxy" (and still names the program, so server logs stay readable).
USER_AGENT = 'wss-proxy (ServerProtocolBridge/%s)' % VERSION

VERSION_TOKEN = re.compile(r'v?(\d+(?:\.\d+)*)')


class UpdateError(Exception):
    """The latest version could not be determined (network, HTTP or format)."""


def parse_version(text: str) -> tuple[int, ...]:
    """Turn a version string into a tuple of numbers for comparison.

    Only the leading ``1.2.3`` part matters; a leading "v" and any suffix such
    as "-beta" are ignored, so both "v1.1" and "1.1.0" compare as (1, 1, 0).
    """
    match = VERSION_TOKEN.search(str(text or ''))
    if not match:
        raise UpdateError(tr('update.error.bad_version', text=text))
    return tuple(int(part) for part in match.group(1).split('.'))


def is_newer(candidate: str, current: str = VERSION) -> bool:
    """True when *candidate* is a later version than *current*."""
    newest = parse_version(candidate)
    running = parse_version(current)
    length = max(len(newest), len(running))
    newest += (0,) * (length - len(newest))
    running += (0,) * (length - len(running))
    return newest > running


def _first_string(payload: dict, keys) -> str:
    """First non-empty string among *keys*; unknown fields are ignored."""
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ''


def split_urls(text) -> list[str]:
    """Split a configured endpoint list (commas, spaces or newlines separate).

    Several endpoints are useful because one host can be blocked for some users
    and reachable for others (``*.workers.dev`` is a good example), so the list
    is tried in order and the first one that answers wins.
    """
    if isinstance(text, (list, tuple)):
        items = [str(item) for item in text]
    else:
        items = re.split(r'[\s,]+', str(text or ''))
    return [item.strip() for item in items if item.strip()]


def fetch_latest(url: str, timeout: float = TIMEOUT_SEC) -> dict:
    """Fetch and parse the endpoint.

    Returns ``{'version': str, 'page': str, 'notes': str}``; the optional
    entries are empty strings when the endpoint does not send them.
    """
    request = urllib.request.Request(
        url, headers={'User-Agent': USER_AGENT,
                      'Accept': 'application/json, text/plain, */*'})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read(MAX_ANSWER_BYTES)
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()                            # HTTPError doubles as the response object
        raise UpdateError(tr('update.error.http', code=code, url=url)) from None
    except urllib.error.URLError as exc:
        raise UpdateError(tr('update.error.network', url=url, error=exc.reason)) from None
    except OSError as exc:                     # timeouts, DNS and socket errors
        raise UpdateError(tr('update.error.network', url=url, error=exc)) from None

    text = raw.decode('utf-8', 'replace').strip()
    if not text:
        raise UpdateError(tr('update.error.empty', url=url))

    version, page, notes = '', '', ''
    try:
        payload = json.loads(text)
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        version = _first_string(payload, VERSION_KEYS)
        page = _first_string(payload, PAGE_KEYS)
        notes = _first_string(payload, NOTES_KEYS)
    else:
        # Plain text (e.g. a file holding nothing but "1.1")
        version = text.splitlines()[0].strip()

    if not version:
        raise UpdateError(tr('update.error.no_version', url=url))
    parse_version(version)                     # reject junk right away
    return {'version': version, 'page': page, 'notes': notes}


def check(urls: str = DEFAULT_UPDATE_URL, current: str = VERSION,
          timeout: float = TIMEOUT_SEC) -> dict:
    """Ask the endpoint(s) and compare the answer with the running version.

    *urls* may name several endpoints (separated by commas or whitespace); they
    are tried in order and the first one that answers wins, so a mirror that is
    reachable locally can be put in front of a host that is blocked there.

    Returns ``{'version', 'page', 'notes', 'current', 'newer', 'url'}``, where
    ``url`` is the endpoint that answered.  Raises UpdateError when none of them
    can be reached or understood -- callers decide how loud to be about that (a
    failed check is not an error of the program itself).
    """
    candidates = split_urls(urls)
    if not candidates:
        raise UpdateError(tr('update.error.no_url'))
    last_error: UpdateError | None = None
    for url in candidates:
        try:
            latest = fetch_latest(url, timeout)
        except UpdateError as exc:
            last_error = exc
            continue
        latest['url'] = url
        latest['current'] = current
        latest['newer'] = is_newer(latest['version'], current)
        return latest
    if len(candidates) == 1:
        raise last_error
    raise UpdateError(tr('update.error.all_failed', count=len(candidates), error=last_error))


def check_async(url: str = DEFAULT_UPDATE_URL, current: str = VERSION, timeout: float = TIMEOUT_SEC,
                callback=None) -> threading.Thread:
    """Run :func:`check` in a daemon thread and hand the outcome to *callback*.

    The callback receives either the result dictionary or the UpdateError, so a
    failing check can never take the program down with it.  Returns the thread
    (already started), mostly so tests can join it.
    """
    def worker() -> None:
        try:
            outcome = check(url, current, timeout)
        except UpdateError as exc:
            outcome = exc
        except Exception as exc:                    # anything unexpected: report, do not raise
            outcome = UpdateError(str(exc))
        if callback is not None:
            callback(outcome)

    thread = threading.Thread(target=worker, name='update-check', daemon=True)
    thread.start()
    return thread
