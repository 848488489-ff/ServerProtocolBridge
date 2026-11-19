"""English-only text lookup.

All user-visible text is English.  There is deliberately no i18n / multi
language support: ``tr`` returns the English entry for a key, falling back
to the key itself.  Comments, identifiers, log levels and protocol strings
stay English regardless of the setting.

The ``LANGUAGES`` tuple keeps ``'auto'`` for backward compatibility (an old
config may hold ``language: auto``), but every code resolves to English --
there is no second language to select.
"""

from __future__ import annotations

from .locales import EN

# Language codes accepted in config.  'auto' is accepted for backward
# compatibility but always resolves to English.
LANGUAGES = ('en', 'auto')
DEFAULT_LANGUAGE = 'en'

_current = DEFAULT_LANGUAGE


def set_language(code: str) -> str:
    """Set the active language; any code resolves to English."""
    global _current
    _current = DEFAULT_LANGUAGE
    return _current


def get_language() -> str:
    """Return the active language code (always ``'en'``)."""
    return _current


def language_label(code: str | None = None) -> str:
    """The label shown in a language selector (English only)."""
    chosen = (code or _current).strip().lower()
    if chosen not in LANGUAGES:
        chosen = DEFAULT_LANGUAGE
    return tr('gui.language.' + chosen)


def language_code(label: str) -> str:
    """Map a selector label back to a language code (English only)."""
    text = (label or '').strip()
    if text == tr('gui.language.en') or text.lower() == 'en':
        return 'en'
    if text.lower() == 'auto':
        return 'auto'
    return DEFAULT_LANGUAGE


def tr(key: str, **values) -> str:
    """Look up *key* in English and fill in ``values``."""
    return tr_in(DEFAULT_LANGUAGE, key, **values)


def tr_in(language_code: str, key: str, **values) -> str:
    """Look up *key* in English regardless of *language_code*."""
    text = EN.get(key, key)
    if values:
        try:
            return text % values
        except (KeyError, TypeError, ValueError):
            # A broken template must never take the program down: show the
            # raw template so the mistake is obvious and easy to fix.
            return text
    return text


def has(key: str, code: str | None = None) -> bool:
    """True when *key* has an English entry."""
    return key in EN


def missing_keys(code: str) -> list:
    """Keys that exist in English (kept for tooling compatibility)."""
    return []
