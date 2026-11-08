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

import locale
import os

from .locales import EN, ZH

# 语言代码按菜单顺序排列。'auto' 表示跟随系统语言；它本身不是翻译表，
# set_language() 会把它解析成 'en' 或 'zh'。
LANGUAGES = ('auto', 'en', 'zh')
DEFAULT_LANGUAGE = 'en'

_TABLES = {'en': EN, 'zh': ZH}
_current = DEFAULT_LANGUAGE


def _system_language() -> str:
    """把系统语言归一到程序支持的两种语言，无法判断时回退英文。"""
    code = ''
    try:
        code = (locale.getdefaultlocale()[0] or '')
    except Exception:
        code = ''
    if not code:
        code = os.environ.get('LANG', '') or os.environ.get('LC_ALL', '')
    return 'zh' if str(code).lower().startswith('zh') else 'en'


def set_language(code: str) -> str:
    """激活一种语言；未知代码静默回退到默认语言。"""
    global _current
    code = (code or '').strip().lower()
    if code not in LANGUAGES:
        code = DEFAULT_LANGUAGE
    _current = _system_language() if code == 'auto' else code
    return _current


def get_language() -> str:
    """返回当前实际生效的语言代码（``'en'`` 或 ``'zh'``）。"""
    return _current


def language_label(code: str | None = None) -> str:
    """语言选择器里显示的名称，跟随当前界面语言翻译。

    'auto' 在英文界面显示 Auto，在中文界面显示“自动”；'zh' 在英文界面
    显示 Chinese (simplified)，在中文界面显示“简体中文”。
    """
    code = (code or _current).strip().lower()
    if code not in LANGUAGES:
        code = DEFAULT_LANGUAGE
    return tr('gui.language.' + code)


def language_code(label: str) -> str:
    """GUI 下拉框的反向查找（也接受语言代码本身）。"""
    text = (label or '').strip()
    for code in LANGUAGES:
        for table_language in ('en', 'zh'):
            if text == tr_in(table_language, 'gui.language.' + code):
                return code
    text = text.lower()
    return text if text in LANGUAGES else DEFAULT_LANGUAGE


def tr(key: str, **values) -> str:
    """Translate ``key`` into the active language and fill in ``values``."""
    return tr_in(_current, key, **values)


def tr_in(language_code: str, key: str, **values) -> str:
    """Translate ``key`` into *language_code* without changing the active language.

    This is for small reverse lookups -- a combobox may still hold a label
    rendered in the previous language for one event, and mapping it back must
    not depend on which language happens to be active at that instant.
    """
    table = _TABLES.get((language_code or '').strip().lower(), _TABLES[DEFAULT_LANGUAGE])
    text = table.get(key)
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
