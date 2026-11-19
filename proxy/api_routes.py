"""Automation-oriented REST JSON API for Server Protocol Bridge.

Mounted under ``/api/v1/``.  Authentication is exactly the MCP endpoint's
(see :func:`proxy.mcp.authorized`): loopback callers are always allowed; a
non-loopback caller must present the MCP key as ``Authorization: Bearer
<key>``, ``X-MCP-Key: <key>`` or ``X-API-Key: <key>``.  When no MCP key is
configured the API is open only if the Web UI password is also off, so this
machine-friendly endpoint cannot bypass a password protecting the same
controls.

Every operation delegates to the matching MCP tool through
:func:`proxy.mcp.call_tool`, so this surface cannot drift from what an MCP
client can do.  Responses are JSON: the tool's own payload plus an ``ok``
flag, and ``error`` when the call failed.  Tool-level failures return HTTP
400 (the body still explains the problem), unknown tools 404, and missing
authentication 401.
"""

from __future__ import annotations

import json

from . import mcp
from .api_docs import API_DOCS_HTML
from .i18n import get_language, tr
from .version import VERSION
from flask import Blueprint, Response, jsonify, request

api = Blueprint('api_v1', __name__, url_prefix='/api/v1')


@api.before_request
def _authorize():
    """Same gate as ``/mcp``: loopback free, otherwise the MCP key.

    The documentation page (``/api/v1/docs``) is a static description of the
    endpoint surface -- no live data, no secrets -- so it is served without a
    key to stay browsable.
    """
    if request.path == '/api/v1/docs':
        return None
    if mcp.authorized(request.remote_addr or '', request.headers):
        return None
    return jsonify({'ok': False, 'error': 'authentication required',
                    'auth': 'bearer'}), 401


def _unwrap(result: dict):
    """Extract the structured payload from a tool's raw MCP result.

    Most tools serialize a JSON object into ``content[0].text``; a few
    (``export_logs``) return plain text.  Non-JSON text is wrapped so the
    response stays a JSON object.
    """
    text = result['content'][0]['text']
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return {'text': text}


def _call(name: str, arguments: dict | None = None):
    """Run one MCP tool and render its payload as JSON with a status code.

    Every response is normalized to carry ``ok``: True on success, False on
    failure, plus the tool's own payload fields verbatim (so an existing
    ``ok`` or ``error`` in the payload is preserved).
    """
    try:
        result, is_error = mcp.call_tool(name, arguments)
    except KeyError:
        return jsonify({'ok': False, 'error': 'unknown tool: %s' % name}), 404
    except TypeError as exc:
        return jsonify({'ok': False, 'error': str(exc)}), 400
    payload = _unwrap(result)
    if not isinstance(payload, dict):
        payload = {'data': payload}
    if 'ok' not in payload:
        payload['ok'] = not is_error
    return jsonify(payload), (400 if is_error else 200)


@api.get('/')
def index():
    """API discovery: name, version and the full tool catalogue."""
    tools = [{'name': tool['name'], 'description': tool['description'],
              'inputSchema': tool.get('inputSchema', {})}
             for tool in mcp.TOOLS]
    return jsonify({'ok': True, 'name': 'server-protocol-bridge',
                    'version': VERSION, 'docs': '/api/v1/docs',
                    'tools': tools})


@api.get('/docs')
def docs():
    """In-program bilingual docs page: follows the interface language by default,
    and the switch labels follow it as well."""
    html = (API_DOCS_HTML
            .replace('__VERSION__', VERSION)
            .replace('__DEFAULT_LANG__', get_language())
            .replace('__LABEL_AUTO__', tr('gui.language.auto'))
            .replace('__LABEL_ZH__', tr('gui.language.zh'))
            .replace('__LABEL_EN__', tr('gui.language.en')))
    return Response(html, mimetype='text/html')


@api.get('/status')
def status():
    return _call('status')


@api.get('/config')
def get_config():
    return _call('get_config')


@api.post('/config')
def update_config():
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        return jsonify({'ok': False,
                        'error': 'request body must be a JSON object'}), 400
    # Accept either the MCP arguments shape ({config: {...}}) or the config
    # fields directly ({target: ..., routes: ...}).
    if isinstance(body.get('config'), dict):
        arguments = body
    else:
        arguments = {'config': body}
    return _call('update_config', arguments)


@api.post('/service/start')
def service_start():
    return _call('start_service')


@api.post('/service/stop')
def service_stop():
    return _call('stop_service')


@api.post('/service/restart')
def service_restart():
    return _call('restart_service')


@api.get('/logs')
def get_logs():
    arguments = {}
    for key in ('since', 'level', 'limit'):
        if request.args.get(key) is not None:
            arguments[key] = request.args.get(key)
    return _call('get_logs', arguments)


@api.post('/logs/clear')
def clear_logs():
    return _call('clear_logs')


@api.get('/tools')
def list_tools():
    tools = [{'name': tool['name'], 'description': tool['description'],
              'inputSchema': tool.get('inputSchema', {})}
             for tool in mcp.TOOLS]
    return jsonify({'ok': True, 'tools': tools})


@api.post('/tools/<name>')
def call_tool(name: str):
    """Call any MCP tool by name.

    The body is either the MCP arguments object directly or ``{"arguments":
    {...}}``; an empty body calls the tool with no arguments.
    """
    body = request.get_json(silent=True) or {}
    if isinstance(body, dict) and isinstance(body.get('arguments'), dict):
        arguments = body['arguments']
    elif isinstance(body, dict):
        arguments = body
    else:
        arguments = {}
    return _call(name, arguments)


def register(app) -> None:
    """Attach the ``/api/v1`` blueprint to a Flask application."""
    app.register_blueprint(api)
