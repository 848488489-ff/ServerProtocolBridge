"""Tests for the cloud version check (proxy/update.py).

    python -m unittest tests.test_update -v

Every test talks to a throwaway HTTP server on 127.0.0.1, so the suite needs no
internet access and never touches the real endpoint.
"""

from __future__ import annotations

import json
import sys
import threading
import unittest
from unittest import mock
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from proxy import update  # noqa: E402
from proxy.config import Config  # noqa: E402
from proxy.i18n import set_language, tr  # noqa: E402
from proxy.logger import NullLogger  # noqa: E402

# path -> (status, body); the handler answers 404 for anything not listed
REPLIES: dict[str, tuple[int, str]] = {}
# headers of the most recent request, lower-cased, for assertions
LAST_HEADERS: dict[str, str] = {}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 -- the name is fixed by http.server
        LAST_HEADERS.clear()
        LAST_HEADERS.update({key.lower(): value for key, value in self.headers.items()})
        status, body = REPLIES.get(self.path, (404, '{"error": "not found"}'))
        payload = body.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):  # keep the unittest output clean
        pass


class _Server:
    """Context manager giving a local HTTP server; yields its base URL."""

    def __enter__(self):
        self.httpd = ThreadingHTTPServer(('127.0.0.1', 0), _Handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return 'http://127.0.0.1:%d' % self.httpd.server_address[1]

    def __exit__(self, *_exc):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        return False


class _ServerTest(unittest.TestCase):
    def setUp(self):
        REPLIES.clear()
        LAST_HEADERS.clear()
        self.addCleanup(REPLIES.clear)


class VersionCompareTests(unittest.TestCase):
    def test_parse_version(self):
        self.assertEqual(update.parse_version('1.1'), (1, 1))
        self.assertEqual(update.parse_version('1.0.0'), (1, 0, 0))
        self.assertEqual(update.parse_version('v1.2.3'), (1, 2, 3))
        self.assertEqual(update.parse_version('  2.0 '), (2, 0))
        # A suffix ("-beta", " (build 5)") belongs to the same release.
        self.assertEqual(update.parse_version('1.1.0-beta'), (1, 1, 0))
        self.assertEqual(update.parse_version('1.1 release'), (1, 1))

    def test_parse_version_rejects_junk(self):
        for text in ('', 'latest', 'v', None):
            with self.assertRaises(update.UpdateError):
                update.parse_version(text)

    def test_is_newer(self):
        self.assertTrue(update.is_newer('1.1', '1.0.0'))
        self.assertTrue(update.is_newer('1.0.1', '1.0.0'))
        self.assertTrue(update.is_newer('2.0', '1.9.9'))
        self.assertTrue(update.is_newer('v1.1', '1.0.0'))
        # Trailing zeros do not make a release newer.
        self.assertFalse(update.is_newer('1.0.0', '1.0.0'))
        self.assertFalse(update.is_newer('1.0', '1.0.0'))
        self.assertFalse(update.is_newer('0.9.9', '1.0.0'))


class FetchTests(_ServerTest):
    def test_json_answer(self):
        # The endpoint publishes a download *page*; the field name is not carved
        # in stone, so the usual spellings are accepted.
        REPLIES['/v.json'] = (200, '{"version": "1.1", '
                                    '"download_page": "https://example.invalid/download"}')
        with _Server() as base:
            result = update.check(base + '/v.json', '1.0.0')
        self.assertEqual(result['version'], '1.1')
        self.assertEqual(result['page'], 'https://example.invalid/download')
        self.assertEqual(result['current'], '1.0.0')
        self.assertTrue(result['newer'])

    def test_same_version_is_not_newer(self):
        REPLIES['/v.json'] = (200, '{"version": "1.1"}')
        with _Server() as base:
            result = update.check(base + '/v.json', '1.1')
        self.assertFalse(result['newer'])

    def test_unknown_fields_are_ignored(self):
        # The endpoint may grow fields; an older build must keep working, and a
        # known field that is missing may not break the answer either.
        # "download_url" is the older spelling of the page field and still works.
        REPLIES['/v.json'] = (200, '{"version": "1.1", "download_url": "https://x/download", '
                                   '"sha256": "deadbeef", "size": 123, "notes": "hello"}')
        with _Server() as base:
            result = update.check(base + '/v.json', '1.0.0')
        self.assertEqual(result['version'], '1.1')
        self.assertEqual(result['page'], 'https://x/download')
        self.assertEqual(result['notes'], 'hello')

    def test_tokenized_page_link_is_kept_verbatim(self):
        # Real pages carry tokens with "&", "%" and friends; they must survive.
        link = ('https://files.example.invalid/api/files/abc/content?token=eyJ%d%%2Bx'
                '&share=77f265f5204d414f19076bf3716d160b')
        REPLIES['/v.json'] = (200, json.dumps({'version': '1.1', 'download_page': link}))
        with _Server() as base:
            result = update.check(base + '/v.json', '1.0.0')
        self.assertEqual(result['page'], link)

    def test_download_page_is_optional(self):
        REPLIES['/v.json'] = (200, '{"version": "1.1"}')
        with _Server() as base:
            result = update.check(base + '/v.json', '1.0.0')
        self.assertEqual(result['page'], '')
        self.assertEqual(result['notes'], '')

    def test_plain_text_answer(self):
        REPLIES['/latest.txt'] = (200, '1.1\n')
        with _Server() as base:
            self.assertTrue(update.check(base + '/latest.txt', '1.0.0')['newer'])

    def test_request_identifies_itself(self):
        # The public endpoint only answers requests whose user agent mentions
        # "wss-proxy", so the check has to send it.
        REPLIES['/v.json'] = (200, '{"version": "1.1"}')
        with _Server() as base:
            update.check(base + '/v.json', '1.0.0')
        user_agent = LAST_HEADERS.get('user-agent', '')
        self.assertIn('wss-proxy', user_agent)
        self.assertIn('ServerProtocolBridge', user_agent)

    def test_http_error_is_reported(self):
        with _Server() as base:
            with self.assertRaises(update.UpdateError):
                update.check(base + '/missing.json', '1.0.0')

    def test_answer_without_version_is_reported(self):
        REPLIES['/v.json'] = (200, '{"whatever": true}')
        with _Server() as base:
            with self.assertRaises(update.UpdateError):
                update.check(base + '/v.json', '1.0.0')

    def test_empty_answer_is_reported(self):
        REPLIES['/empty'] = (200, '   ')
        with _Server() as base:
            with self.assertRaises(update.UpdateError):
                update.check(base + '/empty', '1.0.0')

    def test_empty_url_is_reported(self):
        with self.assertRaises(update.UpdateError):
            update.check('   ', '1.0.0')

    def test_unreachable_endpoint_is_reported(self):
        with self.assertRaises(update.UpdateError):
            update.check('http://127.0.0.1:9/', '1.0.0', timeout=0.5)


class MultipleEndpointTests(_ServerTest):
    def test_url_list_splitter(self):
        self.assertEqual(update.split_urls(' a , b\nc '), ['a', 'b', 'c'])
        self.assertEqual(update.split_urls(['a', 'b']), ['a', 'b'])
        self.assertEqual(update.split_urls(''), [])
        self.assertEqual(update.split_urls(None), [])

    def test_falls_back_to_the_next_endpoint(self):
        # The first host is unreachable -- that is what a blocked domain looks
        # like; the mirror answers, and the mirror's link is the one used.
        REPLIES['/v.json'] = (200, '{"version": "1.1", "download_page": "https://x/download"}')
        with _Server() as base:
            result = update.check('http://127.0.0.1:9/ , ' + base + '/v.json', '1.0.0',
                                  timeout=0.5)
        self.assertTrue(result['newer'])
        self.assertEqual(result['url'], base + '/v.json')
        self.assertEqual(result['page'], 'https://x/download')

    def test_first_endpoint_wins(self):
        REPLIES['/first.json'] = (200, '{"version": "1.1"}')
        with _Server() as base:
            result = update.check(base + '/first.json ' + base + '/second.json', '1.0.0')
        self.assertEqual(result['url'], base + '/first.json')

    def test_all_endpoints_failing_is_reported(self):
        with _Server() as base:
            with self.assertRaises(update.UpdateError) as caught:
                update.check(base + '/missing.json, http://127.0.0.1:9/', '1.0.0', timeout=0.5)
        self.assertIn('2', str(caught.exception))


class AsyncTests(_ServerTest):
    @staticmethod
    def _collector():
        """Callback collecting the outcome and flagging it with an Event."""
        done = threading.Event()
        collected: list = []

        def callback(outcome):
            collected.append(outcome)
            done.set()

        return done, collected, callback

    def test_result_reaches_the_callback(self):
        REPLIES['/v.json'] = (200, '{"version": "9.9"}')
        done, collected, callback = self._collector()
        with _Server() as base:
            update.check_async(base + '/v.json', '1.0.0', callback=callback)
            self.assertTrue(done.wait(5), 'the check never called back')
        self.assertTrue(collected[0]['newer'])

    def test_failure_comes_back_as_an_error_object(self):
        done, collected, callback = self._collector()
        update.check_async('http://127.0.0.1:9/', '1.0.0', timeout=0.5, callback=callback)
        self.assertTrue(done.wait(5), 'the check never called back')
        self.assertIsInstance(collected[0], update.UpdateError)

    def test_call_sites_name_the_callback(self):
        """The GUI and the CLI must hand the callback over as ``callback=``.

        Passed as the third positional argument it landed in *timeout*: the
        request went out, the answer was thrown away, and the window that had
        logged "checking for the newest release ..." stayed silent forever.
        """
        import inspect

        from proxy import cli

        source = inspect.getsource(cli)
        self.assertIn('callback=lambda outcome', source,
                      '%s does not name the check callback' % cli.__name__)


class CliTests(_ServerTest):
    def test_parser_and_config_wiring(self):
        from proxy.cli import apply_arguments, build_parser

        args = build_parser().parse_args(['--check-update', '--no-update-check'])
        self.assertTrue(args.check_update)
        config = apply_arguments(Config(), args)
        self.assertFalse(config.update_check)

    def test_check_update_exit_codes(self):
        from proxy.cli import run_update_check
        from proxy.version import VERSION

        # The announced release is derived from the running version, so the
        # test keeps working when the program version is bumped.
        major = int(VERSION.split('.')[0])
        REPLIES['/new.json'] = (200, json.dumps({'version': '%d.0' % (major + 1)}))
        REPLIES['/same.json'] = (200, json.dumps({'version': VERSION}))
        logger = NullLogger()
        with _Server() as base:
            # The endpoint is compiled in, so the test points the constant at
            # the throwaway server instead of at a configuration field.
            for path, expected in (('/new.json', 1), ('/same.json', 0), ('/missing.json', 2)):
                with mock.patch.object(update, 'DEFAULT_UPDATE_URL', base + path):
                    self.assertEqual(run_update_check(Config(), logger), expected)


class ReleaseFieldsTests(_ServerTest):
    """The richer document the site publishes: policy, notes and download data."""

    def test_full_document(self):
        REPLIES['/v.json'] = (200, json.dumps({
            'version': '1.2.0',
            'download_url': 'https://example.invalid/setup.exe',
            'source_url': 'https://example.invalid/source.zip',
            'min_version': '1.1.0',
            'force_update': False,
            'release_date': '2026-10-18T09:00:00Z',
            'changelog': 'New settings window\nFixed the checkbox mark',
            'sha256': 'CDCDDD109CC921037229DE2B580F6FDAE4F45FF1699FC921316E39D2CA2EC798',
            'file_size': 28665610,
        }))
        with _Server() as base:
            result = update.check(base + '/v.json', '1.1.1')
        self.assertEqual(result['version'], '1.2.0')
        self.assertEqual(result['page'], 'https://example.invalid/setup.exe')
        self.assertEqual(result['source'], 'https://example.invalid/source.zip')
        self.assertEqual(result['min_version'], '1.1.0')
        self.assertEqual(result['release_date'], '2026-10-18T09:00:00Z')
        self.assertEqual(result['notes'], 'New settings window\nFixed the checkbox mark')
        # SHA-256 was removed from the release document (commit fb1cf85): the
        # program no longer parses it, and a server that still sends it must not
        # leak it into the result.  Assert that explicitly instead of ignoring it.
        self.assertNotIn('sha256', result)
        self.assertEqual(result['file_size'], 28665610)
        self.assertTrue(result['newer'])
        self.assertFalse(result['must_update'])

    def test_force_update_flag(self):
        REPLIES['/v.json'] = (200, json.dumps({'version': '1.2.0', 'force_update': True}))
        with _Server() as base:
            result = update.check(base + '/v.json', '1.1.1')
        self.assertTrue(result['force_update'])
        self.assertTrue(result['must_update'])

    def test_old_build_below_min_version_must_update(self):
        REPLIES['/v.json'] = (200, json.dumps({'version': '1.2.0', 'min_version': '1.1.0'}))
        with _Server() as base:
            result = update.check(base + '/v.json', '1.0.9')
        self.assertTrue(result['must_update'])

    def test_supported_build_is_not_forced(self):
        REPLIES['/v.json'] = (200, json.dumps({'version': '1.2.0', 'min_version': '1.1.0'}))
        with _Server() as base:
            result = update.check(base + '/v.json', '1.1.1')
        self.assertFalse(result['must_update'])

    def test_up_to_date_build_never_must_update(self):
        REPLIES['/v.json'] = (200, json.dumps({'version': '1.1.1', 'force_update': True,
                                               'min_version': '9.0'}))
        with _Server() as base:
            result = update.check(base + '/v.json', '1.1.1')
        self.assertFalse(result['newer'])
        self.assertFalse(result['must_update'])

    def test_optional_fields_may_be_missing(self):
        REPLIES['/v.json'] = (200, '{"version": "1.2.0"}')
        with _Server() as base:
            result = update.check(base + '/v.json', '1.1.1')
        self.assertEqual(result['min_version'], '')
        self.assertEqual(result['source'], '')
        self.assertEqual(result['release_date'], '')
        self.assertNotIn('sha256', result)
        self.assertEqual(result['file_size'], 0)
        self.assertFalse(result['force_update'])
        self.assertFalse(result['must_update'])

    def test_junk_optional_fields_do_not_force_an_update(self):
        REPLIES['/v.json'] = (200, json.dumps({
            'version': '1.2.0', 'force_update': 'maybe', 'min_version': 'soon',
            'sha256': 'not-a-digest', 'file_size': 'big'}))
        with _Server() as base:
            result = update.check(base + '/v.json', '1.0.0')
        self.assertFalse(result['force_update'])
        self.assertFalse(result['must_update'])
        self.assertEqual(result['min_version'], '')
        self.assertNotIn('sha256', result)
        self.assertEqual(result['file_size'], 0)

    def test_words_and_digit_strings_are_understood(self):
        REPLIES['/v.json'] = (200, json.dumps({
            'version': '1.2.0', 'force_update': 'true', 'file_size': '28,665,610'}))
        with _Server() as base:
            result = update.check(base + '/v.json', '1.0.0')
        self.assertTrue(result['must_update'])
        self.assertEqual(result['file_size'], 28665610)

    def test_source_link_rejects_non_http_schemes(self):
        for bad in ('javascript:alert(1)', 'file:///C:/secret.txt', 'not a link',
                    '//cdn.example.invalid/source.zip'):
            REPLIES['/v.json'] = (200, json.dumps({'version': '1.2.0', 'source_url': bad}))
            with _Server() as base:
                result = update.check(base + '/v.json', '1.0.0')
            self.assertEqual(result['source'], '', bad)

    def test_source_link_resolves_a_same_site_path_against_the_endpoint(self):
        REPLIES['/v.json'] = (200, json.dumps({
            'version': '1.2.0',
            'source_url': '/downloads/ServerProtocolBridge-1.1.5.1-source.zip?token=a%2Bb',
        }))
        with _Server() as base:
            result = update.check(base + '/v.json', '1.0.0')
        self.assertEqual(result['source'],
                         base + '/downloads/ServerProtocolBridge-1.1.5.1-source.zip?token=a%2Bb')

    def test_source_link_keeps_query_tokens(self):
        link = 'https://files.example.invalid/source.zip?token=a%2Bb&share=123'
        REPLIES['/v.json'] = (200, json.dumps({'version': '1.2.0', 'source_url': link}))
        with _Server() as base:
            result = update.check(base + '/v.json', '1.0.0')
        self.assertEqual(result['source'], link)


class LocalizedNotesTests(_ServerTest):
    """The changelog follows the interface language when both are published."""

    def setUp(self):
        super().setUp()
        self.addCleanup(set_language, 'en')

    def _check(self, payload):
        REPLIES['/v.json'] = (200, json.dumps(payload))
        with _Server() as base:
            return update.check(base + '/v.json', '1.1.1')

    def test_english_interface_prefers_english_notes(self):
        set_language('en')
        result = self._check({'version': '1.2.0', 'changelog': 'Chinese notes',
                              'changelog_en': 'English notes'})
        self.assertEqual(result['notes'], 'English notes')

    def test_chinese_interface_prefers_chinese_notes(self):
        set_language('zh')
        result = self._check({'version': '1.2.0', 'changelog': 'Chinese notes',
                              'changelog_zh': 'Chinese detailed notes'})
        self.assertEqual(result['notes'], 'Chinese detailed notes')

    def test_missing_translation_falls_back_to_the_plain_field(self):
        set_language('en')
        result = self._check({'version': '1.2.0', 'changelog': 'Chinese notes'})
        self.assertEqual(result['notes'], 'Chinese notes')

    def test_blank_translation_is_treated_as_missing(self):
        set_language('en')
        result = self._check({'version': '1.2.0', 'changelog': 'Chinese notes',
                              'changelog_en': '   '})
        self.assertEqual(result['notes'], 'Chinese notes')


class ConfigTests(unittest.TestCase):
    def test_update_endpoint_is_not_a_setting(self):
        """The endpoint is compiled in: no config key, no option, no field."""
        from dataclasses import fields

        from proxy.cli import build_parser

        self.assertTrue(update.DEFAULT_UPDATE_URL.startswith('https://'))
        self.assertNotIn('update_url', {item.name for item in fields(Config)})
        with self.assertRaises(SystemExit):
            build_parser().parse_args(['--update-url', 'https://example.invalid/'])

    def test_old_update_url_key_is_ignored(self):
        """A config.json from an older build cannot redirect the check."""
        config = Config.from_dict({'update_url': 'https://evil.invalid/',
                                   'update_check': False})
        self.assertFalse(config.update_check)
        self.assertFalse(hasattr(config, 'update_url'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
