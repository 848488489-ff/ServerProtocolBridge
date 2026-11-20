"""Translation tables, single source of truth.

The single source of truth is ``proxy.locales.strings``; this package simply
re-exports its ``EN`` and ``ZH`` tables so ``proxy.i18n`` keeps its import
(``from .locales import EN, ZH``).
"""

from __future__ import annotations

from .strings import EN, ZH

__all__ = ['EN', 'ZH']
