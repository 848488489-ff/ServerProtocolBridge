"""Module-level helpers for the Web UI, split from web.py for size.

Pure request helpers, the Microsoft device-code job table and the
dropdown code tables.  Function bodies are unchanged; web.py and
web_routes.py both import them.
"""

import socket
import threading
import time
from . import (accounts, certs, config as config_module)
from .i18n import (LANGUAGES, language_label, tr)
from .locales import EN as EN_TABLE
from .runtime import get_manager
# Dropdown value sets.  Labels are looked up as ``gui.log_level.<code>`` and
# ``gui.cert_generator.<code>`` so they follow the interface language instead of
# being hard-coded English words.
LOG_LEVEL_CODES = ('debug', 'info', 'warn', 'error')
LOG_LINE_LIMIT_CODES = ('1000', '4000', '10000', '20000', '50000')
CERT_GENERATOR_CODES = ('auto', 'python', 'openssl')
_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()
JOB_TTL = 1800.0
def _prune_jobs() -> None:
    now = time.time()
    with _jobs_lock:
        for key in [key for key, job in _jobs.items()
                    if now - job.get('created', now) > JOB_TTL]:
            _jobs.pop(key, None)
def _ms_worker(job_id: str, info: dict, verify: bool) -> None:
    try:
        account = accounts.microsoft_device_poll(info, verify)
    except accounts.AccountError as exc:
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is not None:
                job.update(state='error', error=str(exc), code=exc.code)
    except Exception as exc:
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is not None:
                job.update(state='error', error=str(exc), code='')
    else:
        try:
            accounts.add_account(account)
        except Exception as exc:
            # A store write failure must surface in the job, not kill the
            # worker thread silently and leave the UI polling a dead job.
            with _jobs_lock:
                job = _jobs.get(job_id)
                if job is not None:
                    job.update(state='error', error=str(exc), code='')
        else:
            with _jobs_lock:
                job = _jobs.get(job_id)
                if job is not None:
                    job.update(state='done', account=_account_payload(account, ''))
def _account_payload(account, active_id: str) -> dict:
    return {
        'id': account.id,
        'kind': account.kind,
        'username': account.username,
        'uuid': account.uuid,
        'active': bool(active_id and account.id == active_id),
        'kind_label': tr('accounts.kind.' + account.kind),
    }
def _web_info() -> dict:
    from .webserver import current_address, current_url

    host, port = current_address()
    config = get_manager().config
    host = host or config.web_host
    port = port or config.web_port
    url = current_url() or config.web_url()
    lan = ''
    if (host or '').strip() in ('0.0.0.0', '::', '[::]'):
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                probe.connect(('8.8.8.8', 80))
                lan = 'http://%s:%d/' % (probe.getsockname()[0], int(port))
            finally:
                probe.close()
        except Exception:
            lan = ''
    return {'host': host, 'port': int(port), 'url': url, 'lan_url': lan}
def _config_options() -> dict:
    return {
        'themes': [{'code': code, 'label': tr('gui.theme.' + code)}
                   for code in config_module.THEME_MODES],
        'languages': [{'code': code, 'label': language_label(code)}
                      for code in LANGUAGES],
        'spoof_clients': [{'code': code, 'label': tr('gui.spoof.' + code)}
                          for code in config_module.SPOOF_CLIENTS],
        'resource_pack_modes': [
            {'code': code, 'label': tr('gui.resource_pack_mode.' + code)}
            for code in config_module.RESOURCE_PACK_MODES],
        'log_levels': [{'code': code, 'label': tr('gui.log_level.' + code)}
                       for code in LOG_LEVEL_CODES],
        'log_limits': [{'code': code, 'label': tr('gui.log_limit.' + code)}
                       for code in LOG_LINE_LIMIT_CODES],
        'cert_generators': [
            {'code': code, 'label': tr('gui.cert_generator.' + code)}
            for code in CERT_GENERATOR_CODES],
        'appearance_presets': [
            {'code': code, 'label': tr('gui.label.appearance_preset_' + code)}
            for code in config_module.APPEARANCE_PRESETS],
        'appearance_densities': [
            {'code': code, 'label': tr('gui.label.appearance_density_' + code)}
            for code in config_module.APPEARANCE_DENSITIES],
    }
def _int_field(body: dict, key: str, label: str) -> int | None:
    if key not in body:
        return None
    raw = body.get(key)
    if isinstance(raw, bool):
        raise ValueError(tr('web.invalid_number', field=label))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValueError(tr('web.invalid_number', field=label)) from None
    return value
def _config_from_body(body: dict) -> config_module.Config:
    current = get_manager().config
    data = current.to_dict()
    for key, value in body.items():
        if key in data:
            data[key] = value

    for key, label in (
            ('wss_port', tr('gui.label.wss_port')),
            ('ws_port', tr('gui.label.ws_port')),
            ('web_port', tr('gui.label.web_port')),
            ('heartbeat_sec', tr('gui.label.heartbeat')),
            ('log_max_lines', tr('gui.label.log_max_lines')),
            ('status_cache_ttl', tr('gui.label.status_cache_ttl')),
            ('max_payload_mb', tr('gui.label.max_payload')),
            ('cert_days', tr('gui.label.cert_days'))):
        value = _int_field(body, key, label)
        if value is not None:
            data[key] = value
    if 'connect_timeout' in body:
        try:
            data['connect_timeout'] = float(body['connect_timeout'])
        except (TypeError, ValueError):
            raise ValueError(tr('web.invalid_number',
                                field=tr('gui.label.connect_timeout'))) from None

    if 'routes_text' in body:
        data['routes'] = config_module.parse_routes_text(str(body['routes_text']))
    if 'cert_extra_names' in body:
        value = body['cert_extra_names']
        if isinstance(value, str):
            value = [item.strip() for item in value.replace(',', ' ').split()
                     if item.strip()]
        data['cert_extra_names'] = list(value or [])

    # The buffer size is a runtime field, so validate_web() never reaches it and
    # a hand-written request could otherwise install an unbounded buffer.
    if 'log_max_lines' in body:
        if not 50 <= int(data['log_max_lines']) <= 100000:
            raise ValueError(tr('core.config.log_max_lines_invalid'))

    # Suffix routing and the path-route table cannot be enabled together: the
    # same request path cannot be read as both a route key and a server
    # address, so the merged configuration must never carry both
    if bool(data.get('suffix_route')) and (data.get('routes') or {}):
        raise ValueError(tr('core.config.suffix_route_conflict'))

    config = config_module.Config.from_dict(data)
    if config.theme not in config_module.THEME_MODES:
        config.theme = current.theme
    if (config.language or '').lower() not in LANGUAGES:
        config.language = current.language
    problems = config.validate_web()
    if problems:
        raise ValueError('\n'.join(problems))
    return config
def _save_body(body: dict) -> tuple[config_module.Config, bool, bool, bool]:
    manager = get_manager()
    old = manager.config
    config = _config_from_body(body)
    web_changed = ((old.web_host or '').strip() != (config.web_host or '').strip()
                   or int(old.web_port) != int(config.web_port))
    language_changed = (old.language or '').lower() != (config.language or '').lower()
    # Whether the running proxy must be restarted for the new configuration to
    # take effect: the service reads these fields when it starts, so changing
    # any of them while it is up needs a restart.  UI/theme/language/log fields
    # apply live and are deliberately excluded.
    service_restart = (bool(manager.running)
                       and _needs_service_restart(old, config))
    manager.save_config(config)
    if web_changed:
        _schedule_web_restart(config.web_host, config.web_port)
    return manager.config, language_changed, web_changed, service_restart


# Fields the proxy reads at startup (or only applies at startup).  Changing any
# of these while the service is running requires a restart; the rest of the
# configuration applies live (language, log level/buffer, theme/appearance,
# Web UI bind handled separately, and GUI-only switches).
_RESTART_FIELDS = frozenset({
    'listen_host', 'wss_port', 'ws_port',
    'target', 'routes', 'suffix_route', 'use_srv',
    'rewrite_handshake_host', 'eagler_translate', 'login_ack',
    'resource_pack_mode',
    'server_brand', 'server_brand_version', 'spoof_client', 'spoof_brand',
    'tls_enabled',
    'cert_dir', 'cert_common_name', 'cert_extra_names', 'cert_days',
    'cert_generator',
    'connect_timeout', 'heartbeat_sec', 'max_payload_mb',
    'status_cache', 'status_cache_ttl',
})


def _needs_service_restart(old: config_module.Config,
                           new: config_module.Config) -> bool:
    """True when a running proxy would need a restart to pick up *new*."""
    for name in _RESTART_FIELDS:
        if getattr(old, name) != getattr(new, name):
            return True
    return False
def _schedule_web_restart(host: str, port: int) -> None:
    def run() -> None:
        time.sleep(1.0)
        manager = get_manager()
        try:
            from .webserver import restart_web_ui

            url, error = restart_web_ui(host, port)
        except Exception as exc:
            manager.hub.add('error', tr('web.webui_restart_failed', error=exc))
            return
        if url:
            manager.hub.add('info', tr('web.webui_listening', host=host, port=port))
        else:
            manager.hub.add('error', tr('web.webui_restart_failed', error=error))

    threading.Thread(target=run, name='web-ui-restart', daemon=True).start()
def _i18n_payload() -> dict:
    # Every namespace the front end can render.  A key that is used by the page
    # but absent here shows up as its own raw identifier on screen, which reads
    # as an un-localised bug ("core.config.route_missing_path").
    prefixes = ('web.', 'gui.', 'accounts.', 'core.')
    return {key: tr(key) for key in EN_TABLE if key.startswith(prefixes)}
def _cert_payload() -> dict:
    config = get_manager().config
    cert_path, key_path = certs.certificate_paths(config.resolved_cert_dir)
    info = certs.inspect_certificate(cert_path, key_path) if cert_path.exists() else None
    return {
        'exists': info is not None,
        'cert_path': str(cert_path),
        'key_path': str(key_path),
        'info': info,
    }


def _mcp_info() -> dict:
    """MCP endpoint and key state, shared by the status/auth/config routes."""
    from . import webauth

    config = get_manager().config
    info = webauth.mcp_state()
    base = _web_info().get('url') or config.web_url()
    info['endpoint'] = (base.rstrip('/') + '/mcp') if base else ''
    info['loopback_bind'] = webauth.is_loopback_host(config.web_host)
    return info


def _api_info() -> dict:
    """REST API base URL and the in-program documentation page."""
    config = get_manager().config
    base = _web_info().get('url') or config.web_url()
    root = (base.rstrip('/') + '/api/v1/') if base else ''
    return {'endpoint': root, 'docs': (root.rstrip('/') + '/docs') if root else ''}
