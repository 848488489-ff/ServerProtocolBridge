"""Runtime language switching for every piece of user-visible text.

Design
------
* Translation tables live next to this module in ``proxy/locales/*.py``.
  Every locale module exposes two plain dicts, ``EN`` and ``ZH``, whose keys
  are dotted identifiers grouped by the module that uses them (``gui.*``,
  ``proxy.*``, ``translator.*``, ``tls.*``, ``core.*``, ...).
* ``tr('module.key', **values)`` looks the text up in the active language,
  falls back to English, and finally to the key itself -- a missing entry
  never crashes anything, it simply renders in English.
* Table values use *named* printf placeholders (``'已连接 %(host)s'``) and
  call sites pass the values as keywords: ``tr('proxy.connected', host=...)``.
  A translation must reuse exactly the same placeholder names.
* Only user-visible text is translated. Comments, identifiers, log levels
  and protocol strings (brands, subprotocol names, HTTP headers, service
  ids) stay English no matter what language is selected.

Typical usage::

    from .i18n import tr

    self.log.info(tr('proxy.listening', url=url))
    label.configure(text=tr('gui.label.target'))

The active language is a process-wide setting; the GUI / CLI read it from
``Config.language`` at start-up and the GUI may switch it at runtime.
"""

from __future__ import annotations

from .locales import EN, ZH

# Language codes in menu order; English is the default for the program.
LANGUAGES = ('en', 'zh')
DEFAULT_LANGUAGE = 'en'

# Human readable names for the language picker (never translated themselves).
LANGUAGE_LABELS = {
    'en': 'English',
    'zh': '中文',
}

_TABLES = {'en': EN, 'zh': ZH}
_current = DEFAULT_LANGUAGE


def set_language(code: str) -> str:
    """Activate a language; unknown codes silently fall back to the default."""
    global _current
    code = (code or '').strip().lower()
    if code not in LANGUAGES:
        code = DEFAULT_LANGUAGE
    _current = code
    return _current


def get_language() -> str:
    """Return the code of the active language (``'en'`` or ``'zh'``)."""
    return _current


def language_label(code: str | None = None) -> str:
    """Display name of a language code (defaults to the active one)."""
    return LANGUAGE_LABELS.get(code or _current, LANGUAGE_LABELS[DEFAULT_LANGUAGE])


def language_code(label: str) -> str:
    """Reverse lookup used by GUI comboboxes (accepts a code as well)."""
    text = (label or '').strip()
    for code, name in LANGUAGE_LABELS.items():
        if text == name:
            return code
    text = text.lower()
    return text if text in LANGUAGES else DEFAULT_LANGUAGE


def tr(key: str, **values) -> str:
    """Translate ``key`` into the active language and fill in ``values``."""
    text = _TABLES[_current].get(key)
    if text is None:
        text = EN.get(key, key)
    if values:
        try:
            return text % values
        except (KeyError, TypeError, ValueError):
            # A broken translation must never take the program down: show the
            # raw template so the mistake is obvious and easy to fix.
            return text
    return text


def has(key: str, code: str | None = None) -> bool:
    """True when ``key`` has an entry in the given (or active) language."""
    return key in _TABLES.get(code or _current, {})


def missing_keys(code: str) -> list:
    """Keys that exist in English but are not translated yet (for tooling)."""
    table = _TABLES.get(code, {})
    return sorted(key for key in EN if key not in table)
