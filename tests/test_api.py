"""Tests for the automation REST API (/api/v1).

The API reuses the MCP tools, so these tests focus on the transport: routing,
status codes, authentication, and that the JSON surface matches the tools.
Config and auth state are isolated to a temporary directory so the tests never
touch the operator's real config.json or web_auth.json.
"""

from __future__ import annotations

import json
import shutil
import socket
import tempfile
import unittest
from pathlib import Path

from proxy import config as config_module, webauth
from proxy.version import VERSION


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


class ApiTests(unittest.TestCase):
    """The REST JSON API under /api/v1."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='spb-api-'))
        self._original_auth_path = webauth.auth_path
        webauth.auth_path = lambda: self.tmp / 'web_auth.json'
        webauth.clear_failures('')
        from proxy.runtime import get_manager

        self.manager = get_manager()
        # Point config at the scratch directory, like McpTests.
        self._original_resolve = config_module.resolve_path
        config_module.resolve_path = lambda name: self.tmp / name
        self._original_config = config_module.Config.from_dict(
            self.manager.config.to_dict())
        # A password/key may only be set on a non-loopback bind, which is what
        # the authentication cases exercise.
        self.manager.config.web_host = '0.0.0.0'
        from proxy.web import create_app

        app = create_app()
        app.testing = True
        self.client = app.test_client()
        # Non-loopback client for the auth gate tests.
        self._remote = {'environ_overrides': {'REMOTE_ADDR': '198.51.100.7'}}

    def tearDown(self):
        config_module.resolve_path = self._original_resolve
        self.manager.save_config(self._original_config)
        webauth.auth_path = self._original_auth_path
        webauth.clear_failures('')
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _get(self, path, **kw):
        return self.client.get('/api/v1' + path, **kw)

    def _post(self, path, body=None, **kw):
        return self.client.post('/api/v1' + path, json=body or {},
                                content_type='application/json', **kw)

    # ------------------------------------------------------------------ basics

    def test_index_lists_tools_and_version(self):
        response = self._get('/')
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertTrue(body['ok'])
        self.assertEqual(body['version'], VERSION)
        self.assertEqual(body['name'], 'server-protocol-bridge')
        self.assertEqual(body['docs'], '/api/v1/docs')
        names = {tool['name'] for tool in body['tools']}
        self.assertIn('status', names)
        self.assertIn('get_config', names)
        # The tutorial module was removed; its tools must not be exposed.
        self.assertNotIn('get_tutorial', names)
        self.assertNotIn('open_tutorial', names)
        self.assertGreaterEqual(len(body['tools']), 30)

    def test_docs_page_bilingual_default_english(self):
        response = self._get('/docs')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/html', response.content_type)
        html = response.get_data(as_text=True)
        # English is the default, Chinese block starts hidden.
        self.assertIn('<html lang="en" data-lang="en">', html)
        self.assertIn('<div class="lang-zh" hidden>', html)
        self.assertIn('<div class="lang-en">', html)
        # The switch uses each language's native name, never "英文"/"EN".
        self.assertIn('>中文<', html)
        self.assertIn('>English<', html)
        self.assertNotIn('英文', html)
        self.assertNotIn("'EN'", html)
        # Both languages carry the endpoint surface.
        self.assertIn('/api/v1/status', html)
        self.assertIn('/api/v1/service/start', html)
        self.assertIn('/api/v1/tools/&lt;name&gt;', html)

    def test_docs_page_needs_no_auth(self):
        # A remote caller without a key can still read the documentation page.
        response = self.client.get('/api/v1/docs', **self._remote)
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/html', response.content_type)

    def test_status_and_config(self):
        response = self._get('/status')
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body['version'], VERSION)
        self.assertIn('state', body)

        response = self._get('/config')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['ok'])
        self.assertIn('revision', response.get_json())

    def test_update_config_accepts_fields_directly(self):
        response = self._post('/config', {'target': 'api-test.example:25565'})
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertTrue(body['ok'])
        self.assertEqual(self.manager.config.target, 'api-test.example:25565')

        # The MCP arguments shape ({config: {...}}) works too.
        response = self._post('/config',
                              {'config': {'log_max_lines': 4321}})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()['ok'])
        self.assertEqual(self.manager.config.log_max_lines, 4321)

    def test_service_start_stop(self):
        config = self.manager.config
        snapshot = config.to_dict()
        config.target = '127.0.0.1:25565'
        config.listen_host = '127.0.0.1'
        config.tls_enabled = False
        config.wss_port = 0
        config.ws_port = free_port()
        config.heartbeat_sec = 0
        try:
            started = self._post('/service/start')
            self.assertEqual(started.status_code, 200)
            self.assertTrue(started.get_json()['ok'])

            stopped = self._post('/service/stop')
            self.assertEqual(stopped.status_code, 200)
            self.assertTrue(stopped.get_json()['ok'])
        finally:
            self.manager.save_config(config_module.Config.from_dict(snapshot))

    def test_logs_and_clear(self):
        logs = self._get('/logs')
        self.assertEqual(logs.status_code, 200)
        body = logs.get_json()
        self.assertIn('seq', body)
        self.assertIn('lines', body)

        cleared = self._post('/logs/clear')
        self.assertEqual(cleared.status_code, 200)
        self.assertTrue(cleared.get_json()['ok'])

    # ----------------------------------------------------------- generic tool

    def test_generic_tool_call(self):
        # Arguments object directly.
        called = self._post('/tools/get_config', {})
        self.assertEqual(called.status_code, 200)
        self.assertTrue(called.get_json()['ok'])

        # {arguments: {...}} wrapper.
        resized = self._post('/tools/set_log_limit',
                             {'arguments': {'limit': 234}})
        self.assertEqual(resized.status_code, 200)
        self.assertEqual(resized.get_json()['limit'], 234)

    def test_unknown_tool_404(self):
        response = self._post('/tools/no_such_tool', {})
        self.assertEqual(response.status_code, 404)
        body = response.get_json()
        self.assertFalse(body['ok'])
        self.assertIn('unknown tool', body['error'])

    def test_tool_failure_is_400(self):
        # update_config with a non-object config is a tool error.
        response = self._post('/tools/update_config', {'config': 'nope'})
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()['ok'])

    # ------------------------------------------------------ restart required

    def test_needs_service_restart(self):
        from proxy.web_helpers import _needs_service_restart
        from proxy.config import Config

        old = Config()
        new = Config()
        # A proxy-runtime field change requires a restart.
        new.target = 'other.example:25565'
        self.assertTrue(_needs_service_restart(old, new))
        # A live-applied field does not.
        new = Config()
        new.log_max_lines = 999
        self.assertFalse(_needs_service_restart(old, new))
        new = Config()
        new.theme = 'dark'
        self.assertFalse(_needs_service_restart(old, new))
        # Routes are restart-required too.
        new = Config()
        new.routes = {'/x': 'a:1'}
        self.assertTrue(_needs_service_restart(old, new))

    def test_config_save_reports_service_restart(self):
        # Changing a restart field is reported whether or not the service is
        # running: the notice tells the user to start/restart the service, and
        # the fields are read at startup either way.
        snapshot = self.manager.config.to_dict()
        try:
            response = self._post('/config', {'target': 'restart-test.example:25565'})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.get_json()['service_restart'])

            # Changing only a live field does not need a restart.
            response = self._post('/config', {'log_max_lines': 999})
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.get_json()['service_restart'])
        finally:
            self.manager.save_config(
                config_module.Config.from_dict(snapshot))

    def test_config_reset_reports_service_restart(self):
        # Resetting to defaults also reports whether a restart is needed.  The
        # reset branch lives on the Web UI /api/config route (the REST /api/v1
        # surface reuses MCP update_config, which has no reset concept).
        snapshot = self.manager.config.to_dict()
        try:
            response = self.client.post('/api/config',
                                        json={'target': 'reset-test.example:25565'})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.get_json()['service_restart'])
            response = self.client.post('/api/config', json={'reset': True})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.get_json()['service_restart'])
            # The reset restored the default target, so a further reset (no
            # change) no longer needs one.
            response = self.client.post('/api/config', json={'reset': True})
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.get_json()['service_restart'])
        finally:
            self.manager.save_config(
                config_module.Config.from_dict(snapshot))

    # -------------------------------------------------------------- auth gate

    def test_loopback_needs_no_auth(self):
        response = self._get('/status')
        self.assertEqual(response.status_code, 200)

    def test_remote_requires_mcp_key(self):
        self.manager.config.web_host = '0.0.0.0'
        webauth.set_password('secret123')
        webauth.set_mcp_key('sk-abc-123456')
        try:
            denied = self.client.get('/api/v1/status', **self._remote)
            self.assertEqual(denied.status_code, 401)
            self.assertFalse(denied.get_json()['ok'])

            wrong = self.client.get(
                '/api/v1/status',
                headers={'Authorization': 'Bearer wrong-key'}, **self._remote)
            self.assertEqual(wrong.status_code, 401)

            bearer = self.client.get(
                '/api/v1/status',
                headers={'Authorization': 'Bearer sk-abc-123456'},
                **self._remote)
            self.assertEqual(bearer.status_code, 200)

            api_key = self.client.get(
                '/api/v1/status', headers={'X-API-Key': 'sk-abc-123456'},
                **self._remote)
            self.assertEqual(api_key.status_code, 200)
        finally:
            webauth.disable()
            webauth.clear_mcp_key()

    def test_remote_password_without_key_is_closed(self):
        # Password on but no MCP key: the API must be closed, matching /mcp.
        webauth.set_password('secret123')
        try:
            response = self.client.get('/api/v1/status', **self._remote)
            self.assertEqual(response.status_code, 401)
        finally:
            webauth.disable()


if __name__ == '__main__':
    unittest.main()
