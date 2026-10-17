"""Translation tables, merged into one dictionary per language.

Each locale module owns the keys of the modules it translates (see the module
docstring of ``proxy.i18n``).  Keeping one file per area lets several
people (or agents) work on the translations without touching each other.
"""

from __future__ import annotations

from . import core, gui, proxy, tls, translator, update

LOCALE_MODULES = (core, gui, proxy, translator, tls, update)

EN: dict = {}
ZH: dict = {}

for _module in LOCALE_MODULES:
    EN.update(_module.EN)
    ZH.update(_module.ZH)

__all__ = ['EN', 'ZH', 'LOCALE_MODULES']
