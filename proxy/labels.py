"""Code <-> display-label mapping for the picker dropdowns.

Every picker (spoof client, resource-pack mode, certificate generator, log
level, log limit, theme) edits a code and shows a human label in the active
language.  These helpers convert in both directions and are used wherever a
dropdown is built; the Web UI renders the same choices through its i18n set, so
this module is the shared source of truth for the option lists.

The functions are pure (no Tk, no CustomTkinter): the desktop shell and the
tests can both import them without starting a GUI.
"""

from __future__ import annotations

from . import config as config_module
from .i18n import tr, tr_in

LOG_LEVELS = ('all', 'debug', 'info', 'warn', 'error')
# How many log lines the hub keeps.  Offered as presets so the choice is one
# click, but the picker also accepts a plain number: log_limit_code falls back
# to whatever text the user typed, so a 7500 is as valid as one of these.
LOG_LINE_LIMITS = ('1000', '4000', '10000', '20000', '50000')

CERT_GENERATORS = ('auto', 'python', 'openssl')

THEME_LABEL_KEYS = {'light': 'gui.theme.light', 'dark': 'gui.theme.dark',
                    'system': 'gui.theme.system'}
RESOURCE_PACK_MODE_LABEL_KEYS = {
    code: 'gui.resource_pack_mode.' + code for code in config_module.RESOURCE_PACK_MODES}
SPOOF_LABEL_KEYS = {code: 'gui.spoof.' + code for code in config_module.SPOOF_CLIENTS}
GENERATOR_LABEL_KEYS = {code: 'gui.cert_generator.' + code for code in CERT_GENERATORS}
LOG_LEVEL_LABEL_KEYS = {code: 'gui.log_level.' + code for code in LOG_LEVELS}
LOG_LIMIT_LABEL_KEYS = {code: 'gui.log_limit.' + code for code in LOG_LINE_LIMITS}


def _label_for(code: str, keys: dict, fallback: str) -> str:
    key = keys.get((code or '').strip().lower())
    return tr(key) if key else (code or fallback)


def _code_for(label: str, keys: dict, fallback: str) -> str:
    text = (label or '').strip()
    for code, key in keys.items():
        # 'auto' is not a table; only the real languages are scanned.
        for language in ('en', 'zh'):
            if tr_in(language, key) == text:
                return code
    return text.lower() or fallback


def theme_label(code: str) -> str:
    return _label_for(code, THEME_LABEL_KEYS, 'system')


def theme_code(label: str) -> str:
    return _code_for(label, THEME_LABEL_KEYS, 'system')


def spoof_label(code: str) -> str:
    return _label_for(code, SPOOF_LABEL_KEYS, 'off')


def spoof_code(label: str) -> str:
    return _code_for(label, SPOOF_LABEL_KEYS, 'off')


def resource_pack_mode_label(code: str) -> str:
    return _label_for(code, RESOURCE_PACK_MODE_LABEL_KEYS, 'forward')


def resource_pack_mode_code(label: str) -> str:
    return _code_for(label, RESOURCE_PACK_MODE_LABEL_KEYS, 'forward')


def generator_label(code: str) -> str:
    return _label_for(code, GENERATOR_LABEL_KEYS, 'auto')


def generator_code(label: str) -> str:
    return _code_for(label, GENERATOR_LABEL_KEYS, 'auto')


def log_level_label(code: str) -> str:
    return _label_for(code, LOG_LEVEL_LABEL_KEYS, 'all')


def log_level_code(label: str) -> str:
    return _code_for(label, LOG_LEVEL_LABEL_KEYS, 'all')


def log_limit_label(code: str) -> str:
    return _label_for(str(code), LOG_LIMIT_LABEL_KEYS, '4000')


def log_limit_code(label: str) -> int:
    """The line count behind a log-limit picker value.

    A preset label comes back as its number; free text does too when it parses
    as an integer, and anything else falls back to the default so a wrong entry
    never disables the cap.
    """
    text = str(label or '').strip()
    if text.isdigit():
        value = int(text)
    else:
        value = _code_for(text, LOG_LIMIT_LABEL_KEYS, '4000')
        value = int(value) if str(value).isdigit() else 4000
    return max(50, min(100000, value))
