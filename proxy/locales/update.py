"""Translations for ``proxy/update.py`` (cloud version check)."""

from __future__ import annotations

EN = {
    'update.error.bad_version': 'cannot read a version number from %(text)r',
    'update.error.http': 'the update endpoint %(url)s answered HTTP %(code)d',
    'update.error.network': 'cannot reach the update endpoint %(url)s: %(error)s',
    'update.error.empty': 'the update endpoint %(url)s returned an empty document',
    'update.error.no_version': 'no version field in the answer from %(url)s',
    'update.error.no_url': 'no update endpoint is configured',
    'update.error.all_failed': 'none of the %(count)d update endpoints answered '
                               '(last error: %(error)s)',
}

