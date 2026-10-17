"""Translations for ``mcjs_proxy/update.py`` (cloud version check)."""

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

ZH = {
    'update.error.bad_version': '从 %(text)r 里读不出版本号',
    'update.error.http': '版本检查地址 %(url)s 返回 HTTP %(code)d',
    'update.error.network': '连不上版本检查地址 %(url)s: %(error)s',
    'update.error.empty': '版本检查地址 %(url)s 返回了空内容',
    'update.error.no_version': '版本检查地址 %(url)s 的应答里没有版本字段',
    'update.error.no_url': '没有配置版本检查地址',
    'update.error.all_failed': '%(count)d 个版本检查地址都没能应答(最后一个错误: %(error)s)',
}
