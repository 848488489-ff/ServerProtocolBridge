"""Locale table for the core namespace.

Split into themed fragments (core_cli); this module merges them so the rest of the program still does ``from proxy.locales import core``.
"""

from . import core_cli


EN = {
    'core.app_name': 'Server Protocol Bridge',
    'core.tagline': 'Turns a plain Minecraft server into a local wss:// or ws:// '
                    'endpoint for WebSocket clients.',
    'core.startup_notice_immature': 'This build is not mature yet; it is not '
                                    'recommended on servers with strict anti-cheat.',
    'core.config.address_empty': 'Address must not be empty',
    'core.config.route_format': 'A route must look like "path=target", '
                                'for example: /lobby=play.example.net',
    'core.config.route_missing_target': 'Route "%(path)s" has no target address',
    'core.config.route_missing_path': 'Route has no path; both sides of '
                                      '"path=target" must be filled in',
    'core.config.default_created': 'Created the default configuration file: %(path)s',
    'core.config.listen_host_empty': 'Listen address must not be empty',
    'core.config.port_wss': 'wss port',
    'core.config.port_ws': 'ws port',
    'core.config.port_range': '%(name)s must be between 0 and 65535',
    'core.config.tls_needs_wss_port': 'TLS is enabled, so the wss port must be set '
                                      '(or disable TLS and use ws only)',
    'core.config.tls_needs_ws_port': 'TLS is disabled, so the ws port must be set',
    'core.config.ports_conflict': 'The wss port and the ws port must not be the same',
    'core.config.target_empty': 'Forward target must not be empty',
    'core.config.target_invalid': 'Invalid forward target: %(error)s',
    'core.config.target_srv': '%(host)s (resolved via SRV, port defaults to 25565)',
    'core.config.route_target_invalid': 'Route %(path)s has an invalid target: %(target)s',
    'core.config.brand_server': 'server brand',
    'core.config.brand_server_version': 'server version',
    'core.config.brand_spoof': 'spoofed client brand',
    'core.config.spoof_client_invalid': 'spoof_client must be one of: %(choices)s',
    'core.config.spoof_custom_required': 'a custom client brand is required when spoof_client is "custom"',
    'core.config.name_required': '%(name)s must not be empty',
    'core.config.brand_ascii': '%(name)s may only contain ASCII characters '
                               '(the client reads it byte by byte)',
    'core.config.brand_too_long': '%(name)s must be at most %(limit)d characters',
    'core.config.max_payload_positive': 'Max payload must be greater than 0',
    'core.config.max_connections_range': 'Max connections must not be negative (0 = unlimited)',
    'core.config.connect_timeout_positive': 'Connect timeout must be greater than 0',
    'core.config.heartbeat_non_negative': 'Heartbeat interval must not be negative',
    'core.config.status_cache_ttl_range': 'Server-list cache lifetime must be between 1 and 86400 seconds',
    'core.config.log_level_invalid': 'Log level must be one of debug / info / warn / error',
    'core.config.log_max_lines_invalid': 'The log buffer size must be between 50 and 100000 lines',
    'core.config.suffix_route_conflict': 'Suffix routing and path routes cannot be enabled together; turn one of them off',
    'core.config.language_invalid': 'Language must be "auto" or "en"',
    'core.config.web_host_empty': 'Web UI bind address must not be empty',
    'core.config.web_port_range': 'Web UI port must be between 0 and 65535 (0 = pick a free port)',
    'core.log.debug': 'DEBUG',
    'core.log.info': 'INFO',
    'core.log.warn': 'WARN',
    'core.log.error': 'ERROR',
    'accounts.kind.offline': 'Offline account',
    'accounts.kind.thirdparty': 'Third-party account',
    'accounts.kind.microsoft': 'Microsoft account',
    'accounts.error.network': 'Network error: %(error)s',
    'accounts.error.http': 'The service answered %(code)s: %(detail)s',
    'accounts.error.unknown': 'unknown error',
    'accounts.error.bad_response': 'The service sent an unexpected answer',
    'accounts.error.need_login': 'The sign-in has expired; sign in again',
    'accounts.error.no_uuid': 'This account has no profile ID yet; sign in again',
    'accounts.thirdparty.bad_url': 'The account service address must start with '
                                   'http:// or https://; use the API root given by '
                                   'your provider',
    'accounts.thirdparty.no_profile': 'That service has no Minecraft profile for this account',
    'accounts.ms.refreshed': 'Renewed the Minecraft token of %(name)s',
    'accounts.ms.refresh_failed': 'Could not refresh the Microsoft sign-in: '
                                  '%(error)s. Open Settings > Accounts and sign '
                                  'in again.',
    'accounts.ms.no_character': 'This Microsoft account has no Minecraft profile yet: '
                               'set a player name on the official site first',
    'accounts.ms.library_missing': 'The Microsoft sign-in component (mcauth3) is not '
                                   'installed; run: pip install mcauth3',
    'accounts.ms.ssl_failed': 'The TLS certificate could not be verified: %(detail)s',
    'accounts.ms.code_used': 'Microsoft says this sign-in code has already been '
                             'used. Requesting a new code.',
}


for _sub in (core_cli,):
    EN.update(_sub.EN)
