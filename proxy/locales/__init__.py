"""English-only translation table, merged from the per-area modules.

Each locale module exposes an ``EN`` dict (see ``proxy.i18n``).  There is no
Chinese table; the project is deliberately English-only.
"""

from __future__ import annotations

from . import core, gui, proxy, tls, translator, update, web

LOCALE_MODULES = (core, gui, proxy, translator, tls, update, web)

EN: dict = {}

for _module in LOCALE_MODULES:
    EN.update(_module.EN)

__all__ = ['EN', 'LOCALE_MODULES']
