"""Model Context Protocol (MCP) server for Server Protocol Bridge.

The server speaks JSON-RPC 2.0 over the Web UI's HTTP listener at ``/mcp``
using the Streamable HTTP transport.  It exposes the same process-wide
:class:`proxy.runtime.ServiceManager` as the desktop window and the browser
page, so an AI client can inspect and control the running program rather than
a second copy of it.

Design notes
------------
* No MCP SDK dependency: the protocol surface used here is small (initialize,
  ping, tools/list, tools/call), and a hand-written implementation keeps the
  one-file EXE free of another package tree.
* The endpoint is stateless.  A client may send ``Mcp-Session-Id``; it is
  ignored, which is allowed by the Streamable HTTP transport.
* Authentication is the same rule as the Web UI password: loopback clients
  are always local and never need a key.  A key is optional and can only be
  set while the Web UI is bound to a non-loopback address.  When the Web UI
  password is enabled but no MCP key is set, remote MCP calls are refused so
  the MCP endpoint cannot bypass the password that protects the same controls.
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid

from . import (accounts, certs, config as config_module, eagler, third_party,
               update, webauth)
from .i18n import LANGUAGES
from .runtime import get_manager
from .utils import config_dir
from .version import VERSION

LATEST_PROTOCOL = '2025-06-18'
_PROTOCOL_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
_HEX_RE = re.compile(r'#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?$')


# ---------------------------------------------------------------------------
# Tool catalogue
# ---------------------------------------------------------------------------

def _schema(properties=None, required=None) -> dict:
    return {
        'type': 'object',
        'properties': properties or {},
        'required': list(required or []),
        'additionalProperties': False,
    }


TOOLS = (
    {
        'name': 'status',
        'description': (
            'Return the current service state, version, forwarding target, '
            'listeners, traffic counters, Web UI address and MCP/auth state. '
            'Call this first to see what the program is doing.'),
        'inputSchema': _schema(),
    },
    {
        'name': 'get_config',
        'description': (
            'Return the complete live configuration and any validation '
            'problems.  Passwords and account tokens are not part of it.'),
        'inputSchema': _schema(),
    },
    {
        'name': 'export_config',
        'description': (
            'Export the complete live configuration as a JSON-ready object for '
            'backup or migration.  Include its config field when calling '
            'import_config.'),
        'inputSchema': _schema(),
    },
    {
        'name': 'import_config',
        'description': (
            'Replace the configuration with a previously exported object (the '
            'config field of export_config).  It is validated before saving; '
            'a changed Web UI bind restarts the listener and a changed '
            'language switches the interface.'),
        'inputSchema': _schema(
            {'config': {'type': 'object',
                        'description': 'Complete configuration object.',
                        'additionalProperties': True}},
            ['config']),
    },
    {
        'name': 'list_connections',
        'description': (
            'List the active client connections: id, client address, request '
            'path, target server, protocol translation phase, client protocol, '
            'username, uptime and traffic counters.  Use it to see who is '
            'connected and how far each session got.'),
        'inputSchema': _schema(),
    },
    {
        'name': 'update_config',
        'description': (
            'Merge configuration fields into the live configuration, validate '
            'and save them.  The object uses the same field names as the Web '
            'UI (target, listen_host, wss_port, ws_port, routes, '
            'eagler_translate, log_level, web_host, web_port, ...).  '
            'suffix_route and routes are mutually exclusive; changing '
            'web_host or web_port restarts the Web UI listener.'),
        'inputSchema': _schema(
            {'config': {'type': 'object', 'description': 'Fields to update.',
                        'additionalProperties': True}},
            ['config']),
    },
    {
        'name': 'start_service',
        'description': 'Start the proxy with the current configuration.',
        'inputSchema': _schema(),
    },
    {
        'name': 'stop_service',
        'description': 'Stop the proxy.  The Web UI and MCP endpoint stay up.',
        'inputSchema': _schema(),
    },
    {
        'name': 'restart_service',
        'description': 'Stop the proxy and start it again with the current configuration.',
        'inputSchema': _schema(),
    },
    {
        'name': 'get_logs',
        'description': (
            'Read the in-memory log buffer.  Use since to receive only lines '
            'newer than the last seq, level to filter, and limit to cap the '
            'number of returned lines.'),
        'inputSchema': _schema({
            'since': {'type': 'integer', 'minimum': 0,
                      'description': 'Return lines with seq greater than this.'},
            'level': {'type': 'string',
                      'enum': ['all', 'debug', 'info', 'warn', 'error']},
            'limit': {'type': 'integer', 'minimum': 1, 'maximum': 1000},
        }),
    },
    {
        'name': 'clear_logs',
        'description': 'Clear the in-memory log buffer.',
        'inputSchema': _schema(),
    },
    {
        'name': 'list_accounts',
        'description': 'List stored Minecraft accounts and the active account id.',
        'inputSchema': _schema(),
    },
    {
        'name': 'set_active_account',
        'description': (
            'Select the account used for Microsoft/third-party sign-in.  An '
            'empty account_id clears the selection so clients send their own '
            'requested names.'),
        'inputSchema': _schema({
            'account_id': {'type': 'string',
                           'description': 'Account id, or an empty string for none.'},
        }, ['account_id']),
    },
    {
        'name': 'add_offline_account',
        'description': (
            'Add an offline (name-only) account.  The response carries a '
            'warning when the name is outside the usual 3-16 letter/digit/'
            'underscore shape; the account is still added because private '
            'servers may accept such names.'),
        'inputSchema': _schema({
            'username': {'type': 'string', 'minLength': 1},
        }, ['username']),
    },
    {
        'name': 'remove_account',
        'description': 'Delete a stored account by id.',
        'inputSchema': _schema({
            'account_id': {'type': 'string', 'minLength': 1},
        }, ['account_id']),
    },
    {
        'name': 'get_certificate',
        'description': 'Return the TLS certificate paths and parsed details.',
        'inputSchema': _schema(),
    },
    {
        'name': 'generate_certificate',
        'description': (
            'Generate a new self-signed certificate.  The proxy must be '
            'stopped; this replaces the current certificate files.'),
        'inputSchema': _schema({
            'days': {'type': 'integer', 'minimum': 1, 'maximum': 36500},
            'common_name': {'type': 'string'},
            'extra_names': {'type': 'array', 'items': {'type': 'string'}},
            'generator': {'type': 'string', 'enum': ['auto', 'python', 'openssl']},
        }),
    },
    {
        'name': 'install_certificate',
        'description': 'Install the current certificate into the OS trust store.',
        'inputSchema': _schema(),
    },
    {
        'name': 'import_certificate',
        'description': (
            'Import your own TLS certificate + private key (PEM text or file '
            'paths) instead of the built-in self-signed one.  The pair is '
            'validated (key matches, valid dates, serverAuth usage, a usable '
            'name) before it replaces the current certificate files.  The '
            'proxy must be stopped.'),
        'inputSchema': _schema({
            'cert_pem': {'type': 'string'},
            'key_pem': {'type': 'string'},
            'cert_path': {'type': 'string'},
            'key_path': {'type': 'string'},
        }),
    },
    {
        'name': 'check_update',
        'description': 'Ask the release endpoint whether a newer version exists.',
        'inputSchema': _schema(),
    },
    {
        'name': 'web_info',
        'description': 'Return the Web UI URL, bind address and auth/MCP state.',
        'inputSchema': _schema(),
    },
    {
        'name': 'restart_web_ui',
        'description': 'Restart the Web UI listener with the saved bind address and port.',
        'inputSchema': _schema(),
    },
    {
        'name': 'about',
        'description': (
            'Return program metadata: version, license, bundled third-party '
            'components and the stdlib modules the executable depends on.'),
        'inputSchema': _schema(),
    },
    {
        'name': 'get_config_options',
        'description': (
            'Return the dropdown option tables the Web UI renders (themes, '
            'languages, spoof client presets, resource-pack modes, log levels, '
            'certificate generators and appearance presets and densities), '
            'each as code/label pairs.'),
        'inputSchema': _schema(),
    },
    {
        'name': 'set_ui_preferences',
        'description': (
            'Change the interface theme and/or language and save them.  theme '
            'is one of light/dark/system; language is auto, en or zh (auto '
            'follows the system language).  For interface colours, radius, '
            'density and font scale use set_appearance.'),
        'inputSchema': _schema({
            'theme': {'type': 'string',
                      'description': 'light, dark or system.'},
            'language': {'type': 'string',
                         'description': 'auto, en or zh.'},
        }),
    },
    {
        'name': 'get_auth_state',
        'description': (
            'Return the Web UI password state, the MCP key state, the /mcp '
            'endpoint URL and whether the listener is bound to a loopback '
            'address (which disables password/key setup).'),
        'inputSchema': _schema(),
    },
    {
        'name': 'set_web_auth',
        'description': (
            'Enable or disable the Web UI access password.  With enabled=true '
            'and a password of at least 4 characters the hash is replaced; '
            'with enabled=true and no password the existing hash is switched '
            'on.  Only valid on a non-loopback bind.'),
        'inputSchema': _schema({
            'enabled': {'type': 'boolean'},
            'password': {'type': 'string',
                         'description': 'New password, or empty to keep the current one.'},
        }, ['enabled']),
    },
    {
        'name': 'set_mcp_key',
        'description': (
            'Set the MCP bearer key (at least 8 characters).  Only valid on a '
            'non-loopback bind; a key lets remote MCP clients through.'),
        'inputSchema': _schema({
            'key': {'type': 'string', 'minLength': 8},
        }, ['key']),
    },
    {
        'name': 'clear_mcp_key',
        'description': (
            'Remove the MCP bearer key.  Always allowed, including on a '
            'loopback bind, so a leftover key from a previous LAN bind is not '
            'stuck forever.'),
        'inputSchema': _schema(),
    },
    {
        'name': 'add_thirdparty_account',
        'description': (
            'Authenticate against a third-party (Yggdrasil-style) account '
            'server and store the resulting account.  The proxy never stores '
            'the password.'),
        'inputSchema': _schema({
            'server': {'type': 'string', 'minLength': 1,
                       'description': 'Auth server root URL.'},
            'username': {'type': 'string', 'minLength': 1},
            'password': {'type': 'string', 'minLength': 1},
        }, ['server', 'username', 'password']),
    },
    {
        'name': 'start_microsoft_login',
        'description': (
            'Start a Microsoft device-code sign-in.  The result contains a '
            'job id, the user code and the verification URI; poll with '
            'get_microsoft_job until its state is done or error.'),
        'inputSchema': _schema({
            'verify': {'type': 'boolean',
                       'description': 'Verify the session with Mojang (default true).'},
        }),
    },
    {
        'name': 'get_microsoft_job',
        'description': (
            'Poll a Microsoft sign-in job started with start_microsoft_login. '
            'state is pending or done/error; when done, account holds the '
            'stored account.'),
        'inputSchema': _schema({
            'job_id': {'type': 'string', 'minLength': 1},
        }, ['job_id']),
    },
    {
        'name': 'export_logs',
        'description': (
            'Return the complete in-memory log as plain text (the page only '
            'renders the newest 2500 lines).  level filters to debug/info/'
            'warn/error; use ''all'' for everything.'),
        'inputSchema': _schema({
            'level': {'type': 'string',
                      'enum': ['all', 'debug', 'info', 'warn', 'error']},
        }),
    },
    {
        'name': 'reset_config',
        'description': (
            'Reset the configuration to factory defaults and save it.  A '
            'changed Web UI bind restarts the listener; a changed language '
            'switches the interface.'),
        'inputSchema': _schema(),
    },
    {
        'name': 'set_appearance',
        'description': (
            'Change the interface appearance and save it.  preset is one of '
            'default/ocean/forest/sunset/mono/custom; picking a non-custom '
            'preset also applies its palette (accent and background).  '
            'Alternatively pass individual fields: accent and bgColor as '
            '#rgb or #rrggbb, radius in px, density (compact/comfortable/'
            'spacious) and fontScale (100 = default).  Omitted fields are '
            'kept; when the colours change without an explicit preset the '
            'preset is re-derived from the palette, like the Web UI.'),
        'inputSchema': _schema({
            'preset': {'type': 'string',
                       'enum': list(config_module.APPEARANCE_PRESETS),
                       'description': 'Named palette; default/custom/ocean/forest/sunset/mono.'},
            'accent': {'type': 'string',
                       'description': 'Accent colour, #rgb or #rrggbb.'},
            'bgColor': {'type': 'string',
                        'description': 'Background colour, #rgb or #rrggbb.'},
            'radius': {'type': 'integer', 'minimum': 0, 'maximum': 100000,
                       'description': 'Corner radius in px (UI range 0-24).'},
            'density': {'type': 'string',
                        'enum': list(config_module.APPEARANCE_DENSITIES),
                        'description': 'compact, comfortable or spacious.'},
            'fontScale': {'type': 'integer', 'minimum': 0, 'maximum': 100000,
                          'description': 'Font scale in percent; 100 is the default (UI range 80-130).'},
        }),
    },
    {
        'name': 'list_routes',
        'description': (
            'List the path-based routes.  A WebSocket connection whose '
            'request path matches a route is forwarded to that server '
            'instead of the default target.  Returns the map, the equivalent '
            'editable text (one path=target per line), the revision and '
            'whether suffix routing is enabled (which takes precedence and '
            'makes the table unused).'),
        'inputSchema': _schema(),
    },
    {
        'name': 'set_route',
        'description': (
            'Add or replace one path route.  Not available while suffix '
            'routing is enabled.  path is the WebSocket request path; a '
            'leading slash is added when missing and trailing slashes are '
            'dropped (/ is the catch-all).  target is host[:port] or an '
            'address like mc://host:port of the server behind that path.  '
            'Connections whose path matches no route use the default target.'),
        'inputSchema': _schema({
            'path': {'type': 'string', 'minLength': 1,
                     'description': 'Request path, e.g. /survival or /.'},
            'target': {'type': 'string', 'minLength': 1,
                       'description': 'host[:port] of the server for that path.'},
        }, ['path', 'target']),
    },
    {
        'name': 'remove_route',
        'description': (
            'Remove one path route by path.  The default target is unchanged; '
            'connections that matched the removed route use it from now on.'),
        'inputSchema': _schema({
            'path': {'type': 'string', 'minLength': 1,
                     'description': 'Request path exactly as stored, e.g. /survival.'},
        }, ['path']),
    },
    {
        'name': 'reload_config',
        'description': (
            'Re-read config.json from disk and make it the live configuration, '
            'e.g. after another editor changed the file.  Returns the '
            'revision, the configuration, validation problems and whether the '
            'Web UI bind changed (restart_web_ui applies a changed bind).  An '
            'unreadable or invalid file falls back to factory defaults.'),
        'inputSchema': _schema(),
    },
    {
        'name': 'set_log_limit',
        'description': (
            'Resize the in-memory log buffer immediately (1 to 100000 lines); '
            'lines beyond the cap are discarded, oldest first.  The persisted '
            'value is the log_max_lines setting, applied through '
            'update_config.'),
        'inputSchema': _schema({
            'limit': {'type': 'integer', 'minimum': 1, 'maximum': 100000,
                      'description': 'Number of log lines to keep.'},
        }, ['limit']),
    },
)


# ---------------------------------------------------------------------------
# JSON-RPC plumbing
# ---------------------------------------------------------------------------

def _error(message_id, code: int, message: str) -> dict:
    return {'jsonrpc': '2.0', 'id': message_id,
            'error': {'code': code, 'message': message}}


def _text_result(data, is_error: bool = False) -> dict:
    text = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    return {'content': [{'type': 'text', 'text': text}],
            'isError': bool(is_error)}


def _int_arg(arguments: dict, name: str, default: int,
             minimum: int | None = None, maximum: int | None = None) -> int:
    raw = arguments.get(name, default)
    if isinstance(raw, bool):
        raise ValueError('%s must be an integer' % name)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValueError('%s must be an integer' % name) from None
    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _account_payload(account, active_id: str) -> dict:
    from .web_helpers import _account_payload as payload

    return payload(account, active_id)


def _cert_payload() -> dict:
    from .web_helpers import _cert_payload as payload

    return payload()


def _web_info() -> dict:
    from .web_helpers import _mcp_info, _web_info as info

    data = info()
    data['auth'] = webauth.state()
    data['mcp'] = _mcp_info()
    return data


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

def _tool_status(_arguments: dict) -> dict:
    manager = get_manager()
    data = manager.status()
    data['web'] = _web_info()
    data['auth'] = webauth.state()
    data['mcp'] = _web_info()['mcp']
    return _text_result(data)


def _tool_get_config(_arguments: dict) -> dict:
    manager = get_manager()
    return _text_result({
        'revision': manager.revision,
        'config': manager.config.to_dict(),
        'problems': manager.config.validate(),
        'web_problems': manager.config.validate_web(),
    })


def _tool_export_config(_arguments: dict) -> dict:
    manager = get_manager()
    config = manager.config
    return _text_result({
        'version': VERSION,
        'revision': manager.revision,
        'config': config.to_dict(),
        'problems': config.validate(),
        'web_problems': config.validate_web(),
    })


def _tool_import_config(arguments: dict) -> dict:
    from .web_helpers import _save_body

    body = arguments.get('config')
    if not isinstance(body, dict):
        raise ValueError('config must be an object')
    candidate = config_module.Config.from_dict(body)
    problems = candidate.validate()
    if problems:
        return _text_result({'error': '\n'.join(problems),
                             'problems': problems}, True)
    try:
        config, language_changed, web_changed, service_restart = _save_body(
            candidate.to_dict())
    except ValueError as exc:
        return _text_result({'error': str(exc)}, True)
    return _text_result({
        'ok': True,
        'revision': get_manager().revision,
        'config': config.to_dict(),
        'problems': config.validate(),
        'language_changed': language_changed,
        'web_restart': web_changed,
        'service_restart': service_restart,
        'web_url': config.web_url(),
    })


def _tool_list_connections(_arguments: dict) -> dict:
    manager = get_manager()
    server = getattr(manager, 'server', None)
    connections: list[dict] = []
    if server is not None:
        try:
            connections = server.list_connections()
        except Exception as exc:
            return _text_result({'error': str(exc)}, True)
    return _text_result({
        'state': manager.state,
        'active': len(connections),
        'max_connections': int(getattr(manager.config,
                                       'max_connections', 0) or 0),
        'connections': connections,
    })


def _tool_update_config(arguments: dict) -> dict:
    from .web_helpers import _save_body

    body = arguments.get('config')
    if not isinstance(body, dict):
        raise ValueError('config must be an object')
    try:
        config, language_changed, web_changed, service_restart = _save_body(body)
    except ValueError as exc:
        return _text_result({'error': str(exc)}, True)
    return _text_result({
        'ok': True,
        'revision': get_manager().revision,
        'config': config.to_dict(),
        'problems': config.validate(),
        'language_changed': language_changed,
        'web_restart': web_changed,
        'service_restart': service_restart,
        'web_url': config.web_url(),
    })


def _tool_start_service(_arguments: dict) -> dict:
    manager = get_manager()
    ok, message = manager.start(manager.config)
    if not ok:
        return _text_result({'ok': False, 'error': message}, True)
    return _text_result({'ok': True, 'state': manager.state})


def _tool_stop_service(_arguments: dict) -> dict:
    manager = get_manager()
    stopped = manager.stop()
    return _text_result({'ok': True, 'stopped': bool(stopped)})


def _tool_restart_service(_arguments: dict) -> dict:
    manager = get_manager()
    manager.stop(wait=True)
    ok, message = manager.start(manager.config)
    if not ok:
        return _text_result({'ok': False, 'error': message}, True)
    return _text_result({'ok': True, 'state': manager.state})


def _tool_get_logs(arguments: dict) -> dict:
    manager = get_manager()
    since = _int_arg(arguments, 'since', 0, minimum=0)
    limit = _int_arg(arguments, 'limit', 200, minimum=1, maximum=1000)
    level = str(arguments.get('level') or 'all').strip().lower()
    items = manager.hub.snapshot(since)
    if level != 'all':
        items = [item for item in items if item['level'] == level]
    return _text_result({'seq': manager.hub.seq, 'lines': items[-limit:]})


def _tool_clear_logs(_arguments: dict) -> dict:
    get_manager().hub.clear()
    return _text_result({'ok': True})


def _tool_list_accounts(_arguments: dict) -> dict:
    store = accounts.load_store()
    return _text_result({
        'active': store.active,
        'accounts': [_account_payload(account, store.active)
                     for account in store.accounts],
    })


def _tool_set_active_account(arguments: dict) -> dict:
    account_id = str(arguments.get('account_id') or '').strip()
    store = accounts.load_store()
    if account_id and store.get(account_id) is None:
        return _text_result({'error': 'account not found'}, True)
    accounts.set_active(account_id)
    return _text_result({'ok': True, 'active': account_id})


def _tool_add_offline_account(arguments: dict) -> dict:
    name = eagler.usable_name(arguments.get('username'))
    if not name:
        return _text_result({'error': 'invalid username'}, True)
    account = accounts.add_account(
        accounts.Account(kind=accounts.KIND_OFFLINE, username=name))
    return _text_result({'ok': True, 'warning': eagler.name_warning(name),
                         'account': _account_payload(account, '')})


def _tool_remove_account(arguments: dict) -> dict:
    account_id = str(arguments.get('account_id') or '').strip()
    if not account_id or not accounts.remove_account(account_id):
        return _text_result({'error': 'account not found'}, True)
    return _text_result({'ok': True})


def _tool_get_certificate(_arguments: dict) -> dict:
    return _text_result(_cert_payload())


def _tool_generate_certificate(arguments: dict) -> dict:
    manager = get_manager()
    if manager.running:
        return _text_result(
            {'error': 'stop the service before changing the certificate'}, True)
    config = manager.config
    try:
        days = _int_arg(arguments, 'days', int(config.cert_days),
                        minimum=1, maximum=36500)
        common_name = str(arguments.get('common_name') or
                          config.cert_common_name or 'localhost')
        generator = str(arguments.get('generator') or
                        config.cert_generator or 'auto')
        extra = arguments.get('extra_names', config.cert_extra_names)
        if isinstance(extra, str):
            extra = [item.strip() for item in extra.replace(',', ' ').split()
                     if item.strip()]
        cert_path, key_path = certs.certificate_paths(config.resolved_cert_dir)
        for path in (cert_path, key_path):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        certs.generate_certificate(
            config.resolved_cert_dir, common_name=common_name,
            extra_names=list(extra or []), days=days,
            generator=generator, logger=manager.logger)
    except Exception as exc:
        return _text_result({'error': str(exc)}, True)
    return _text_result(_cert_payload())


def _tool_install_certificate(_arguments: dict) -> dict:
    manager = get_manager()
    payload = _cert_payload()
    if not payload['exists']:
        return _text_result({'error': 'no certificate yet'}, True)
    try:
        ok, message = certs.install_to_trust_store(
            certs.certificate_paths(manager.config.resolved_cert_dir)[0],
            logger=manager.logger)
    except Exception as exc:
        return _text_result({'error': str(exc)}, True)
    if not ok:
        return _text_result({'error': message or 'install failed'}, True)
    return _text_result({'ok': True, 'message': message})


def _tool_import_certificate(arguments: dict) -> dict:
    manager = get_manager()
    if manager.running:
        return _text_result(
            {'error': 'stop the service before changing the certificate'}, True)
    try:
        info = certs.import_certificate(
            manager.config.resolved_cert_dir,
            cert_pem=arguments.get('cert_pem'),
            key_pem=arguments.get('key_pem'),
            cert_path=arguments.get('cert_path'),
            key_path=arguments.get('key_path'),
            logger=manager.logger)
    except Exception as exc:
        return _text_result({'error': str(exc)}, True)
    return _text_result({'ok': True, 'info': info})


def _tool_check_update(_arguments: dict) -> dict:
    try:
        outcome = update.check(update.DEFAULT_UPDATE_URL, VERSION)
    except Exception as exc:
        return _text_result({'error': str(exc)}, True)
    return _text_result(outcome)


def _tool_web_info(_arguments: dict) -> dict:
    return _text_result(_web_info())


def _tool_restart_web_ui(_arguments: dict) -> dict:
    from .web_helpers import _schedule_web_restart

    config = get_manager().config
    _schedule_web_restart(config.web_host, config.web_port)
    return _text_result({'ok': True, 'url': config.web_url()})


def _raw_text_result(text: str, is_error: bool = False) -> dict:
    return {'content': [{'type': 'text', 'text': text}],
            'isError': bool(is_error)}


def _loopback_bind() -> bool:
    return webauth.is_loopback_host(get_manager().config.web_host)


def _tool_about(_arguments: dict) -> dict:
    return _text_result({
        'version': VERSION,
        'name': 'server-protocol-bridge',
        'config_dir': str(config_dir()),
        'license': 'Unlicense (public-domain dedication)',
        'components': [
            {'name': item['name'], 'license': item['license'],
             'url': item['url']} for item in third_party.COMPONENTS],
        'stdlib': list(third_party.STDLIB_MODULES),
    })


def _tool_get_config_options(_arguments: dict) -> dict:
    from .web_helpers import _config_options

    return _text_result(_config_options())


def _tool_set_ui_preferences(arguments: dict) -> dict:
    manager = get_manager()
    config = manager.config
    old_language = (config.language or '').lower()
    theme = str(arguments.get('theme') or '').strip().lower()
    language = str(arguments.get('language') or '').strip().lower()
    if theme and theme not in config_module.THEME_MODES:
        return _text_result(
            {'error': 'theme must be one of %s' % '/'.join(config_module.THEME_MODES)},
            True)
    if language and language not in LANGUAGES:
        return _text_result(
            {'error': 'language must be one of %s' % '/'.join(LANGUAGES)}, True)
    if theme:
        config.theme = theme
    if language:
        config.language = language
    manager.save_config(config)
    return _text_result({'ok': True, 'theme': config.theme,
                         'language': config.language,
                         'language_changed': old_language != config.language})


def _tool_get_auth_state(_arguments: dict) -> dict:
    from .web_helpers import _mcp_info

    return _text_result({
        'auth': webauth.state(),
        'mcp': _mcp_info(),
        'loopback_bind': _loopback_bind(),
    })


def _tool_set_web_auth(arguments: dict) -> dict:
    from .web_helpers import _mcp_info

    enabled = bool(arguments.get('enabled'))
    password = str(arguments.get('password') or '')
    if enabled and _loopback_bind():
        return _text_result(
            {'error': 'a password cannot be set on a loopback bind'}, True)
    was_enabled = webauth.is_enabled()
    password_changed = False
    try:
        if enabled:
            if password:
                if len(password) < 4:
                    return _text_result(
                        {'error': 'password must be at least 4 characters'}, True)
                webauth.set_password(password)
                password_changed = True
            elif not webauth.has_password():
                return _text_result(
                    {'error': 'password is required when enabling'}, True)
            else:
                webauth.enable()
        else:
            webauth.disable()
    except OSError as exc:
        return _text_result({'error': str(exc)}, True)
    return _text_result({'ok': True, 'auth': webauth.state(),
                         'mcp': _mcp_info(),
                         'password_changed': password_changed,
                         'reauth': enabled and (password_changed or not was_enabled)})


def _tool_set_mcp_key(arguments: dict) -> dict:
    from .web_helpers import _mcp_info

    key = str(arguments.get('key') or '')
    if len(key) < 8:
        return _text_result({'error': 'key must be at least 8 characters'}, True)
    if _loopback_bind():
        return _text_result(
            {'error': 'a key cannot be set on a loopback bind'}, True)
    try:
        webauth.set_mcp_key(key)
    except OSError as exc:
        return _text_result({'error': str(exc)}, True)
    return _text_result({'ok': True, 'mcp': _mcp_info()})


def _tool_clear_mcp_key(_arguments: dict) -> dict:
    from .web_helpers import _mcp_info

    try:
        webauth.clear_mcp_key()
    except OSError as exc:
        return _text_result({'error': str(exc)}, True)
    return _text_result({'ok': True, 'mcp': _mcp_info()})


def _tool_add_thirdparty_account(arguments: dict) -> dict:
    server = str(arguments.get('server') or '').strip()
    username = str(arguments.get('username') or '').strip()
    password = str(arguments.get('password') or '')
    if not (server and username and password):
        return _text_result({'error': 'server, username and password are required'},
                            True)
    try:
        account = accounts.thirdparty_authenticate(server, username, password)
    except accounts.AccountError as exc:
        return _text_result({'error': str(exc), 'code': getattr(exc, 'code', '')},
                            True)
    except Exception as exc:
        return _text_result({'error': str(exc)}, True)
    accounts.add_account(account)
    return _text_result({'ok': True, 'account': _account_payload(account, '')})


def _tool_start_microsoft_login(arguments: dict) -> dict:
    from .web_helpers import _jobs, _jobs_lock, _ms_worker, _prune_jobs

    verify = bool(arguments.get('verify', True))
    _prune_jobs()
    try:
        info = accounts.microsoft_device_start(verify)
    except accounts.AccountError as exc:
        return _text_result({'error': str(exc), 'code': getattr(exc, 'code', '')},
                            True)
    except Exception as exc:
        return _text_result({'error': str(exc)}, True)
    job_id = uuid.uuid4().hex
    with _jobs_lock:
        _jobs[job_id] = {'state': 'pending', 'created': time.time(),
                         'info': info, 'error': '', 'code': '', 'account': None}
    threading.Thread(target=_ms_worker, args=(job_id, info, verify),
                     name='ms-signin', daemon=True).start()
    return _text_result({
        'ok': True, 'job': job_id,
        'user_code': info.get('user_code', ''),
        'verification_uri': info.get('verification_uri', ''),
        'expires_in': info.get('expires_in', 0),
        'interval': info.get('interval', 5),
    })


def _tool_get_microsoft_job(arguments: dict) -> dict:
    from .web_helpers import _jobs, _jobs_lock, _prune_jobs

    job_id = str(arguments.get('job_id') or '').strip()
    _prune_jobs()
    with _jobs_lock:
        job = dict(_jobs.get(job_id) or {})
    if not job:
        return _text_result({'error': 'job not found'}, True)
    return _text_result({
        'ok': True,
        'state': job.get('state', 'pending'),
        'error': job.get('error', ''),
        'code': job.get('code', ''),
        'account': job.get('account'),
    })


def _tool_export_logs(arguments: dict) -> dict:
    manager = get_manager()
    level = str(arguments.get('level') or 'all').strip().lower()
    items = manager.hub.snapshot(0)
    if level != 'all':
        items = [item for item in items if item['level'] == level]
    text = '\n'.join(item['text'] for item in items)
    if text:
        text += '\n'
    return _raw_text_result(text)


def _tool_set_appearance(arguments: dict) -> dict:
    manager = get_manager()
    config = manager.config
    merged = dict(getattr(config, 'appearance', {}) or {})
    # Colour background image / blur / opacity were removed on request; drop
    # any stale values a previous config might still carry.
    for key in ('bgImage', 'bgBlur', 'bgOpacity'):
        merged.pop(key, None)
    changed: list[str] = []
    preset_given = arguments.get('preset') is not None
    if preset_given:
        preset = str(arguments.get('preset') or '').strip().lower()
        if preset not in config_module.APPEARANCE_PRESETS:
            return _text_result(
                {'error': 'preset must be one of %s'
                 % '/'.join(config_module.APPEARANCE_PRESETS)}, True)
        merged['preset'] = preset
        changed.append('preset')
        if preset != 'custom':
            accent, background = config_module.APPEARANCE_PALETTES[preset]
            merged['accent'] = accent
            merged['bgColor'] = background
            changed.extend(('accent', 'bgColor'))
    for key in ('accent', 'bgColor'):
        raw = arguments.get(key)
        if raw is None:
            continue
        if not isinstance(raw, str):
            return _text_result(
                {'error': '%s must be a string like #2f6fed' % key}, True)
        value = raw.strip()
        if not _HEX_RE.fullmatch(value):
            return _text_result(
                {'error': '%s must be #rgb or #rrggbb' % key}, True)
        merged[key] = value.lower()
        changed.append(key)
    if arguments.get('radius') is not None:
        merged['radius'] = _int_arg(arguments, 'radius', 14,
                                    minimum=0, maximum=100000)
        changed.append('radius')
    if arguments.get('fontScale') is not None:
        merged['fontScale'] = _int_arg(arguments, 'fontScale', 100,
                                       minimum=0, maximum=100000)
        changed.append('fontScale')
    if arguments.get('density') is not None:
        density = str(arguments.get('density') or '').strip().lower()
        if density not in config_module.APPEARANCE_DENSITIES:
            return _text_result(
                {'error': 'density must be one of %s'
                 % '/'.join(config_module.APPEARANCE_DENSITIES)}, True)
        merged['density'] = density
        changed.append('density')
    if not changed:
        return _text_result(
            {'error': 'nothing to change: pass preset, accent, bgColor, '
                      'radius, density and/or fontScale'}, True)
    if not preset_given and any(key in ('accent', 'bgColor') for key in changed):
        merged['preset'] = config_module.match_appearance_preset(
            merged.get('accent'), merged.get('bgColor'))
    config.appearance = merged
    manager.save_config(config)
    return _text_result({'ok': True, 'appearance': merged,
                         'changed': changed,
                         'revision': manager.revision})


def _routes_payload(config) -> dict:
    return {'routes': dict(config.routes or {}),
            'routes_text': config_module.format_routes_text(config.routes or {}),
            'suffix_route': bool(getattr(config, 'suffix_route', False)),
            'revision': get_manager().revision}


def _save_routes(routes: dict):
    manager = get_manager()
    data = manager.config.to_dict()
    data['routes'] = routes
    config = config_module.Config.from_dict(data)
    problems = config.validate_web()
    if problems:
        raise ValueError('\n'.join(problems))
    manager.save_config(config)
    return config


def _tool_list_routes(_arguments: dict) -> dict:
    return _text_result(_routes_payload(get_manager().config))


def _route_path_arg(arguments: dict):
    raw = arguments.get('path')
    if raw is None:
        raise ValueError('path is required')
    return config_module.normalize_route_path(str(raw))


def _tool_set_route(arguments: dict) -> dict:
    if getattr(get_manager().config, 'suffix_route', False):
        return _text_result(
            {'error': 'suffix routing is enabled; disable suffix_route '
                      'before adding path routes'}, True)
    try:
        path = _route_path_arg(arguments)
    except ValueError as exc:
        return _text_result({'error': str(exc)}, True)
    target = str(arguments.get('target') or '').strip()
    if not target:
        return _text_result({'error': 'target is required'}, True)
    if any(ch.isspace() for ch in target):
        return _text_result({'error': 'target must not contain whitespace'}, True)
    try:
        config_module.parse_address(target)
    except ValueError as exc:
        return _text_result({'error': 'invalid target: %s' % exc}, True)
    routes = dict(get_manager().config.routes or {})
    routes[path] = target
    try:
        config = _save_routes(routes)
    except ValueError as exc:
        return _text_result({'error': str(exc)}, True)
    return _text_result({'ok': True, 'path': path, 'target': target,
                         **_routes_payload(config),
                         'problems': config.validate()})


def _tool_remove_route(arguments: dict) -> dict:
    try:
        path = _route_path_arg(arguments)
    except ValueError as exc:
        return _text_result({'error': str(exc)}, True)
    routes = dict(get_manager().config.routes or {})
    if path not in routes:
        return _text_result({'error': 'no route for %s' % path}, True)
    del routes[path]
    try:
        config = _save_routes(routes)
    except ValueError as exc:
        return _text_result({'error': str(exc)}, True)
    return _text_result({'ok': True, 'removed': path,
                         **_routes_payload(config),
                         'problems': config.validate()})


def _tool_reload_config(_arguments: dict) -> dict:
    manager = get_manager()
    old_host = (manager.config.web_host or '').strip()
    old_port = int(manager.config.web_port)
    config = manager.reload_config()
    new_host = (config.web_host or '').strip()
    new_port = int(config.web_port)
    return _text_result({
        'ok': True,
        'revision': manager.revision,
        'config': config.to_dict(),
        'problems': config.validate(),
        'web_problems': config.validate_web(),
        'web_restart_needed': (old_host != new_host) or (old_port != new_port),
        'web_url': config.web_url(),
    })


def _tool_set_log_limit(arguments: dict) -> dict:
    if 'limit' not in arguments:
        return _text_result({'error': 'limit is required'}, True)
    try:
        limit = _int_arg(arguments, 'limit', 4000, minimum=1, maximum=100000)
    except ValueError as exc:
        return _text_result({'error': str(exc)}, True)
    applied = get_manager().set_log_limit(limit)
    return _text_result({'ok': True, 'limit': applied})


def _tool_reset_config(_arguments: dict) -> dict:
    from .web_helpers import _schedule_web_restart

    manager = get_manager()
    old = manager.config
    config = config_module.Config()
    language_changed = ((old.language or '').lower()
                        != (config.language or '').lower())
    web_changed = ((old.web_host or '').strip() != (config.web_host or '').strip()
                   or int(old.web_port) != int(config.web_port))
    manager.save_config(config)
    if web_changed:
        _schedule_web_restart(config.web_host, config.web_port)
    return _text_result({
        'ok': True,
        'revision': manager.revision,
        'config': config.to_dict(),
        'problems': config.validate(),
        'language_changed': language_changed,
        'web_restart': web_changed,
        'web_url': config.web_url(),
    })


_HANDLERS = {
    'status': _tool_status,
    'get_config': _tool_get_config,
    'export_config': _tool_export_config,
    'import_config': _tool_import_config,
    'list_connections': _tool_list_connections,
    'update_config': _tool_update_config,
    'start_service': _tool_start_service,
    'stop_service': _tool_stop_service,
    'restart_service': _tool_restart_service,
    'get_logs': _tool_get_logs,
    'clear_logs': _tool_clear_logs,
    'list_accounts': _tool_list_accounts,
    'set_active_account': _tool_set_active_account,
    'add_offline_account': _tool_add_offline_account,
    'remove_account': _tool_remove_account,
    'get_certificate': _tool_get_certificate,
    'generate_certificate': _tool_generate_certificate,
    'install_certificate': _tool_install_certificate,
    'import_certificate': _tool_import_certificate,
    'check_update': _tool_check_update,
    'web_info': _tool_web_info,
    'restart_web_ui': _tool_restart_web_ui,
    'about': _tool_about,
    'get_config_options': _tool_get_config_options,
    'set_ui_preferences': _tool_set_ui_preferences,
    'get_auth_state': _tool_get_auth_state,
    'set_web_auth': _tool_set_web_auth,
    'set_mcp_key': _tool_set_mcp_key,
    'clear_mcp_key': _tool_clear_mcp_key,
    'add_thirdparty_account': _tool_add_thirdparty_account,
    'start_microsoft_login': _tool_start_microsoft_login,
    'get_microsoft_job': _tool_get_microsoft_job,
    'export_logs': _tool_export_logs,
    'reset_config': _tool_reset_config,
    'set_appearance': _tool_set_appearance,
    'list_routes': _tool_list_routes,
    'set_route': _tool_set_route,
    'remove_route': _tool_remove_route,
    'reload_config': _tool_reload_config,
    'set_log_limit': _tool_set_log_limit,
}


# ---------------------------------------------------------------------------
# Request handling
# ---------------------------------------------------------------------------

def _initialize(params: dict) -> dict:
    requested = str(params.get('protocolVersion') or '').strip()
    # Echo a date-shaped version the client asked for.  The tool surface is
    # version-independent, so this keeps newer clients happy without claiming
    # features we do not implement.
    version = requested if _PROTOCOL_RE.match(requested) else LATEST_PROTOCOL
    return {
        'protocolVersion': version,
        'capabilities': {'tools': {'listChanged': False}},
        'serverInfo': {'name': 'server-protocol-bridge', 'version': VERSION},
        'instructions': (
            'Server Protocol Bridge control.  Start with status and get_config.  '
            'update_config merges fields and validates them; start_service, '
            'stop_service and restart_service control the proxy; get_logs '
            'reads the in-memory log; export_logs returns it as plain text; '
            'set_log_limit resizes the buffer; list_routes, set_route and '
            'remove_route manage the path routes; set_appearance '
            'personalizes the interface; reload_config re-reads config.json '
            'from disk; the account and certificate tools mirror the Web UI, '
            'and resources/list exposes logs, status, config, about and the '
            'MCP state as read-only resources.'),
    }


# ---------------------------------------------------------------------------
# Resources / prompts (MCP surface beyond tools)
# ---------------------------------------------------------------------------

def _resource_logs() -> dict:
    manager = get_manager()
    text = '\n'.join(item['text'] for item in manager.hub.snapshot(0))
    if text:
        text += '\n'
    return {'uri': 'server-protocol-bridge://logs', 'mimeType': 'text/plain',
            'text': text}


def _resource_status() -> dict:
    data = get_manager().status()
    data['web'] = _web_info()
    data['auth'] = webauth.state()
    data['mcp'] = _web_info()['mcp']
    return {'uri': 'server-protocol-bridge://status',
            'mimeType': 'application/json',
            'text': json.dumps(data, ensure_ascii=False, indent=2, default=str)}


def _resource_config() -> dict:
    manager = get_manager()
    data = {
        'revision': manager.revision,
        'config': manager.config.to_dict(),
        'problems': manager.config.validate(),
        'web_problems': manager.config.validate_web(),
    }
    return {'uri': 'server-protocol-bridge://config',
            'mimeType': 'application/json',
            'text': json.dumps(data, ensure_ascii=False, indent=2, default=str)}


def _resource_about() -> dict:
    return {'uri': 'server-protocol-bridge://about',
            'mimeType': 'application/json',
            'text': json.dumps({
                'version': VERSION,
                'name': 'server-protocol-bridge',
                'config_dir': str(config_dir()),
                'license': 'Unlicense (public-domain dedication)',
                'components': [
                    {'name': item['name'], 'license': item['license'],
                     'url': item['url']} for item in third_party.COMPONENTS],
                'stdlib': list(third_party.STDLIB_MODULES),
            }, ensure_ascii=False, indent=2)}


def _resource_mcp() -> dict:
    from .web_helpers import _mcp_info

    return {'uri': 'server-protocol-bridge://mcp',
            'mimeType': 'application/json',
            'text': json.dumps({
                'auth': webauth.state(),
                'mcp': _mcp_info(),
                'loopback_bind': _loopback_bind(),
            }, ensure_ascii=False, indent=2)}


_RESOURCES = (
    {'uri': 'server-protocol-bridge://logs', 'name': 'logs',
     'description': 'The complete in-memory log buffer as plain text.',
     'mimeType': 'text/plain'},
    {'uri': 'server-protocol-bridge://status', 'name': 'status',
     'description': 'Live service state, configuration and counters.',
     'mimeType': 'application/json'},
    {'uri': 'server-protocol-bridge://config', 'name': 'config',
     'description': 'Current configuration and validation problems.',
     'mimeType': 'application/json'},
    {'uri': 'server-protocol-bridge://about', 'name': 'about',
     'description': 'Program metadata and bundled third-party components.',
     'mimeType': 'application/json'},
    {'uri': 'server-protocol-bridge://mcp', 'name': 'mcp',
     'description': 'MCP endpoint, auth and key state.',
     'mimeType': 'application/json'},
)

_RESOURCE_READERS = {
    'server-protocol-bridge://logs': _resource_logs,
    'server-protocol-bridge://status': _resource_status,
    'server-protocol-bridge://config': _resource_config,
    'server-protocol-bridge://about': _resource_about,
    'server-protocol-bridge://mcp': _resource_mcp,
}


def _prompt_diagnose() -> dict:
    return {
        'description': 'Diagnose the service',
        'messages': [
            {'role': 'user',
             'content': {'type': 'text',
                         'text': ('Call the status tool first, then get_logs '
                                  'with level=warn and limit=100, and report '
                                  'what the service is doing.')}},
        ],
    }


def _prompt_signin() -> dict:
    return {
        'description': 'Sign in with a Microsoft account',
        'messages': [
            {'role': 'user',
             'content': {'type': 'text',
                         'text': ('Call start_microsoft_login, show the user '
                                  'code and verification URI, then poll '
                                  'get_microsoft_job until it is done or '
                                  'error, and report the result.')}},
        ],
    }


def _prompt_configure() -> dict:
    return {
        'description': 'Point the bridge at a server and start it',
        'messages': [
            {'role': 'user',
             'content': {'type': 'text',
                         'text': ('Call status and get_config first.  Pick a '
                                  'target: host, host:port, or a bare host '
                                  'when the server publishes SRV records, and '
                                  'set it with update_config.  For several '
                                  'servers behind one listener, add path '
                                  'routes with set_route (remove_route drops '
                                  'one) and check them with list_routes.  '
                                  'Then start_service and verify with get_logs '
                                  'and status.')}},
        ],
    }


def _prompt_secure() -> dict:
    return {
        'description': 'Lock down remote access to the Web UI and MCP endpoint',
        'messages': [
            {'role': 'user',
             'content': {'type': 'text',
                         'text': ('Remote access only works on a non-loopback '
                                  'bind: set web_host to 0.0.0.0 or a LAN '
                                  'address with update_config.  The Web UI '
                                  'password and the MCP key can only be '
                                  'configured on such a bind.  Then set_web_auth '
                                  'with enabled=true and a password of at '
                                  'least 4 characters, and set_mcp_key with a '
                                  'key of at least 8 characters.  Verify with '
                                  'get_auth_state.  Loopback access (127.0.0.1) '
                                  'never needs a password or a key.')}},
        ],
    }


_PROMPTS = (
    {'name': 'diagnose', 'description': 'Diagnose the running service'},
    {'name': 'microsoft-signin', 'description': 'Sign in with a Microsoft account'},
    {'name': 'configure-forwarding',
     'description': 'Point the bridge at a server and start it'},
    {'name': 'secure-remote',
     'description': 'Lock down remote access to the Web UI and MCP endpoint'},
)

_PROMPT_GETTERS = {
    'diagnose': _prompt_diagnose,
    'microsoft-signin': _prompt_signin,
    'configure-forwarding': _prompt_configure,
    'secure-remote': _prompt_secure,
}


def _handle_message(message) -> dict | None:
    if not isinstance(message, dict):
        return _error(None, -32600, 'Invalid Request')
    if message.get('jsonrpc') != '2.0':
        return _error(message.get('id'), -32600, 'Invalid Request')
    method = message.get('method')
    if not isinstance(method, str):
        return _error(message.get('id'), -32600, 'Invalid Request')
    message_id = message.get('id')
    is_notification = 'id' not in message
    params = message.get('params') or {}
    if not isinstance(params, dict):
        return _error(message_id, -32602, 'Invalid params')

    if method == 'initialize':
        return {'jsonrpc': '2.0', 'id': message_id,
                'result': _initialize(params)}
    if method == 'ping':
        return {'jsonrpc': '2.0', 'id': message_id, 'result': {}}
    if method == 'tools/list':
        return {'jsonrpc': '2.0', 'id': message_id,
                'result': {'tools': list(TOOLS)}}
    if method == 'tools/call':
        name = str(params.get('name') or '').strip()
        arguments = params.get('arguments') or {}
        if not isinstance(arguments, dict):
            return _error(message_id, -32602, 'Invalid params')
        try:
            result, _is_error = call_tool(name, arguments)
        except KeyError:
            return _error(message_id, -32602, 'Unknown tool: %s' % name)
        return {'jsonrpc': '2.0', 'id': message_id, 'result': result}
    if method == 'resources/list':
        return {'jsonrpc': '2.0', 'id': message_id,
                'result': {'resources': list(_RESOURCES)}}
    if method == 'resources/read':
        uri = str(params.get('uri') or '').strip()
        resource = _RESOURCE_READERS.get(uri)
        if resource is None:
            return _error(message_id, -32002, 'Unknown resource: %s' % uri)
        return {'jsonrpc': '2.0', 'id': message_id,
                'result': {'contents': [resource()]}}
    if method == 'prompts/list':
        return {'jsonrpc': '2.0', 'id': message_id,
                'result': {'prompts': list(_PROMPTS)}}
    if method == 'prompts/get':
        name = str(params.get('name') or '').strip()
        prompt = _PROMPT_GETTERS.get(name)
        if prompt is None:
            return _error(message_id, -32002, 'Unknown prompt: %s' % name)
        return {'jsonrpc': '2.0', 'id': message_id, 'result': prompt()}
    if method.startswith('notifications/'):
        return None
    if is_notification:
        return None
    return _error(message_id, -32601, 'Method not found: %s' % method)


def handle_payload(payload):
    """Handle one JSON-RPC message or a batch; None means "no response"."""
    if isinstance(payload, list):
        if not payload:
            return _error(None, -32600, 'Invalid Request')
        responses = []
        for item in payload:
            response = _handle_message(item)
            if response is not None:
                responses.append(response)
        return responses or None
    return _handle_message(payload)


def call_tool(name: str, arguments: dict | None = None) -> tuple[dict, bool]:
    """Invoke one MCP tool and return ``(result, is_error)``.

    This is the single implementation source for both the JSON-RPC ``/mcp``
    endpoint and the REST ``/api/v1`` surface: a tool's behaviour is defined
    once here and reused by both transports, so they cannot drift.

    ``result`` is the tool's raw MCP result (``{'content': [...],
    'isError': bool}``).  The JSON-RPC transport renders it verbatim; the
    REST transport unwraps ``content[0].text`` (a JSON object for most
    tools, plain text for ``export_logs``).  A tool-level failure is a
    result, not a transport error, exactly as MCP specifies.

    Raises :class:`KeyError` for an unknown tool name and :class:`TypeError`
    for non-dict arguments.
    """
    name = str(name or '').strip()
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise TypeError('arguments must be an object')
    handler = _HANDLERS.get(name)
    if handler is None:
        raise KeyError(name)
    try:
        result = handler(arguments)
    except Exception as exc:  # a tool failure is a result, not a transport error
        result = _text_result({'error': str(exc)}, True)
    return result, bool(result.get('isError'))


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def _presented_key(headers) -> str:
    value = (headers.get('Authorization') or '').strip()
    if value.lower().startswith('bearer '):
        return value[7:].strip()
    return (headers.get('X-MCP-Key') or headers.get('X-API-Key') or '').strip()


def authorized(remote_addr: str, headers) -> bool:
    """Whether this request may use the MCP endpoint.

    Loopback is always local, exactly like the Web UI password exemption.  A
    remote caller needs the MCP key when one is set.  With no key, MCP is open
    only when the Web UI password is also off: otherwise the machine-friendly
    endpoint would bypass the password protecting the same controls.
    """
    if webauth.is_loopback(remote_addr or ''):
        return True
    if webauth.mcp_has_key():
        return webauth.verify_mcp_key(_presented_key(headers))
    return not webauth.is_enabled()


def unauthorized_response() -> dict:
    return _error(None, -32001, 'MCP key required')
