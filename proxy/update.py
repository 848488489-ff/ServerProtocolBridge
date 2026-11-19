"""Cloud version check.

The program asks a small HTTPS endpoint for the latest published version and
compares it with the version that is running:

    GET https://<endpoint>/     ->  {"version": "1.1.5",
                                     "download_url": "https://.../setup.exe",
                                     "source_url": "https://.../source.zip",
                                     "min_version": "1.1.0",
                                     "force_update": false,
                                     "release_date": "2026-10-19",
                                     "changelog": "...",
                                     "file_size": 28665610}

Only the known fields are read -- ``version``, the optional download and source
links, release notes, and the update policy fields (``min_version``, which is
the oldest build still supported, and ``force_update``, which marks this single
release as mandatory).  Anything else in the document is ignored, and every
optional field may be missing or hold junk, so the endpoint can grow new fields
or drop them without breaking older builds.  The links are opened in the browser
and never fetched by this program itself.

Nothing is sent besides the request itself, there is no caching and no retry
loop: one plain GET with a timeout.
"""

from __future__ import annotations

import json
import re
import threading
import urllib.error
import urllib.request
from urllib.parse import urljoin

from .i18n import get_language, tr
from .version import VERSION

# Public endpoint that announces the newest release: a plain static file on
# Cloudflare Pages (see the update section of the README for the
# expected document).  *.pages.dev is reachable from mainland China, unlike
# *.workers.dev, which is DNS-poisoned there.
#
# This address is compiled into the program and is not a setting: it is never
# read from config.json, and no window or command-line option edits it, so an
# installed copy always asks the official endpoint.  Listing several URLs here
# (comma separated, tried in order -- see check()) is a decision made when the
# program is built, not something a user can influence.
PAGES_UPDATE_URL = 'https://banbengengxinjiancha.pages.dev/api/version.json'
DEFAULT_UPDATE_URL = PAGES_UPDATE_URL

# The endpoint may sit on the other side of the planet, so give it room: the
# check runs in the background everywhere, waiting a few extra seconds costs
# nothing.
TIMEOUT_SEC = 20.0
MAX_ANSWER_BYTES = 64 * 1024

# Known fields, with the spellings a hand-written endpoint is likely to use
VERSION_KEYS = ('version', 'latest', 'latest_version', 'tag_name', 'name')
PAGE_KEYS = ('download_page', 'page_url', 'download_url', 'page', 'url', 'html_url', 'download')
SOURCE_KEYS = ('source_url', 'source_download', 'source_code', 'source_archive', 'source')
NOTES_KEYS = ('notes', 'changelog', 'body', 'message', 'description')
# A release note may be published once per language.  The check picks the one
# that matches the interface and otherwise keeps the plain field (which is the
# original, Chinese-only spelling).
NOTES_EN_KEYS = ('changelog_en', 'notes_en', 'changelog_english', 'description_en')
NOTES_ZH_KEYS = ('changelog_zh', 'notes_zh', 'changelog_chinese', 'description_zh')
MIN_VERSION_KEYS = ('min_version', 'minimum_version', 'min_supported')
FORCE_KEYS = ('force_update', 'force', 'required', 'mandatory')
DATE_KEYS = ('release_date', 'date', 'published', 'published_at', 'released')
SIZE_KEYS = ('file_size', 'size', 'bytes', 'length')

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


def _localized_notes(payload: dict, fallback: str) -> str:
    """The changelog in the language of the interface, else the plain field."""
    keys = NOTES_ZH_KEYS if get_language() == 'zh' else NOTES_EN_KEYS
    return _first_string(payload, keys) or fallback


def _clean_url(value: str, base_url: str = '') -> str:
    """Keep only an http(s) URL; resolve a same-site relative path against the
    endpoint that published it.

    The value ends up in the user's browser, so a malformed field or a
    ``javascript:`` / ``file:`` scheme must not be passed through.  A plain
    ``/downloads/build.zip`` is useful when the release and its downloads live on
    the same static host; it is resolved into an absolute URL and never sent to
    the browser still relative.
    """
    text = value.strip()
    if re.fullmatch(r'https?://\S+', text, re.IGNORECASE):
        return text
    if text.startswith('/') and not text.startswith('//') and '\\' not in text \
            and ':' not in text and re.fullmatch(r'[^\s"<>]+', text):
        if base_url.startswith(('http://', 'https://')):
            try:
                resolved = urljoin(base_url, text)
            except ValueError:
                resolved = ''
            if resolved.startswith(('http://', 'https://')):
                return resolved
    return ''


def _first_bool(payload: dict, keys) -> bool:
    """First flag among *keys*, accepting JSON booleans, numbers and words.

    A site written by hand may publish ``"force_update": "true"`` or ``1``
    instead of a real boolean, so the usual spellings count.  Junk means false:
    a check must never force an update because of a typo.
    """
    for key in keys:
        if key not in payload:
            continue
        value = payload[key]
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in ('true', 'yes', 'on', '1', 'required')
        return False
    return False


def _first_int(payload: dict, keys) -> int:
    """First non-negative whole number among *keys*; strings must be plain digits."""
    for key in keys:
        if key not in payload:
            continue
        value = payload[key]
        if isinstance(value, bool):
            return 0
        if isinstance(value, int):
            return max(0, value)
        if isinstance(value, float):
            return max(0, int(value))
        if isinstance(value, str) and value.strip().replace(',', '').isdigit():
            return int(value.strip().replace(',', ''))
        return 0
    return 0


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

    Returns the release document as a dictionary with ``version``, ``page``,
    ``source``, ``notes`` and the policy fields ``min_version``,
    ``force_update``, ``release_date`` and ``file_size``.  Optional
    entries fall back to ``''`` / ``0`` / ``False`` when the endpoint does not
    send them.
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

    version, page, source, notes = '', '', '', ''
    min_version, release_date, file_size = '', '', 0
    force_update = False
    try:
        payload = json.loads(text)
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        version = _first_string(payload, VERSION_KEYS)
        page = _clean_url(_first_string(payload, PAGE_KEYS), base_url=url)
        source = _clean_url(_first_string(payload, SOURCE_KEYS), base_url=url)
        notes = _localized_notes(payload, _first_string(payload, NOTES_KEYS))
        min_version = _first_string(payload, MIN_VERSION_KEYS)
        release_date = _first_string(payload, DATE_KEYS)
        file_size = _first_int(payload, SIZE_KEYS)
        force_update = _first_bool(payload, FORCE_KEYS)
    else:
        # Plain text (e.g. a file holding nothing but "1.1")
        version = text.splitlines()[0].strip()

    if not version:
        raise UpdateError(tr('update.error.no_version', url=url))
    parse_version(version)                     # reject junk right away
    if min_version:
        try:
            parse_version(min_version)
        except UpdateError:
            min_version = ''                   # a broken floor must not block updates
    return {'version': version, 'page': page, 'source': source, 'notes': notes,
            'min_version': min_version, 'force_update': force_update,
            'release_date': release_date,
            'file_size': file_size}


def _must_update(latest: dict, current: str) -> bool:
    """Decide whether the running build has to be replaced.

    The site has two independent ways to insist: ``force_update`` for this one
    release, and ``min_version`` -- the oldest build that is still supported, so
    anything older than that must update no matter what the release says.  A
    failed comparison is not an order to update.
    """
    if not latest.get('newer'):
        return False
    if latest.get('force_update'):
        return True
    minimum = latest.get('min_version') or ''
    if not minimum:
        return False
    try:
        return is_newer(minimum, current)
    except UpdateError:
        return False


def check(urls: str = DEFAULT_UPDATE_URL, current: str = VERSION,
          timeout: float = TIMEOUT_SEC) -> dict:
    """Ask the endpoint(s) and compare the answer with the running version.

    *urls* may name several endpoints (separated by commas or whitespace); they
    are tried in order and the first one that answers wins, so a mirror that is
    reachable locally can be put in front of a host that is blocked there.

    Returns the release dictionary from :func:`fetch_latest` plus ``current``,
    ``newer`` (is the published version later than the running one), ``url``
    (the endpoint that answered) and ``must_update`` (the published policy says
    this build is no longer acceptable).  Raises UpdateError when none of the
    endpoints can be reached or understood -- callers decide how loud to be
    about that (a failed check is not an error of the program itself).
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
        latest['must_update'] = _must_update(latest, current)
        return latest
    if len(candidates) == 1:
        raise last_error
    raise UpdateError(tr('update.error.all_failed', count=len(candidates), error=last_error))


def check_async(url: str = DEFAULT_UPDATE_URL, current: str = VERSION, timeout: float = TIMEOUT_SEC,
                callback=None) -> threading.Thread:
    """Run :func:`check` in a daemon thread and hand the outcome to *callback*.

    The callback receives either the result dictionary or the UpdateError, so a
    failing check can never take the program down with it.  Call sites pass it
    as ``callback=...``: handed over as the *timeout*, the check ran and nobody
    was ever told about the answer.  Returns the thread (already started),
    mostly so tests can join it.
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
