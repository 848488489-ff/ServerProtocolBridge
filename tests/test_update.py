"""Tests for the cloud version check (mcjs_proxy/update.py).

    python -m unittest tests.test_update -v

Every test talks to a throwaway HTTP server on 127.0.0.1, so the suite needs no
internet access and never touches the real endpoint.
"""

from __future__ import annotations

import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcjs_proxy import update  # noqa: E402
from mcjs_proxy.config import Config  # noqa: E402
from mcjs_proxy.i18n import tr  # noqa: E402
from mcjs_proxy.logger import NullLogger  # noqa: E402

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


class CliTests(_ServerTest):
    def test_parser_and_config_wiring(self):
        from mcjs_proxy.cli import apply_arguments, build_parser

        args = build_parser().parse_args(
            ['--check-update', '--update-url', 'https://example.invalid/', '--no-update-check'])
        self.assertTrue(args.check_update)
        config = apply_arguments(Config(), args)
        self.assertEqual(config.update_url, 'https://example.invalid/')
        self.assertFalse(config.update_check)

    def test_check_update_exit_codes(self):
        from mcjs_proxy.cli import run_update_check

        REPLIES['/new.json'] = (200, '{"version": "1.1"}')
        REPLIES['/same.json'] = (200, '{"version": "1.0.0"}')
        logger = NullLogger()
        with _Server() as base:
            config = Config()
            config.update_url = base + '/new.json'
            self.assertEqual(run_update_check(config, logger), 1)   # newer release exists
            config.update_url = base + '/same.json'
            self.assertEqual(run_update_check(config, logger), 0)   # up to date
            config.update_url = base + '/missing.json'
            self.assertEqual(run_update_check(config, logger), 2)   # check failed


class ConfigTests(unittest.TestCase):
    def test_update_url_validation(self):
        config = Config()
        self.assertNotIn(tr('core.config.update_url_invalid'), config.validate())
        config.update_url = 'ftp://example.invalid/'
        self.assertIn(tr('core.config.update_url_invalid'), config.validate())
        # With the check switched off the URL is never used, so it may be anything.
        config.update_check = False
        self.assertNotIn(tr('core.config.update_url_invalid'), config.validate())

    def test_update_url_list_validation(self):
        config = Config()
        config.update_url = 'https://one.invalid/ , https://two.invalid/version.json'
        self.assertNotIn(tr('core.config.update_url_invalid'), config.validate())
        # One bad entry in the list is enough to report the list as bad.
        config.update_url = 'https://one.invalid/, ftp://two.invalid/'
        self.assertIn(tr('core.config.update_url_invalid'), config.validate())


if __name__ == '__main__':
    unittest.main(verbosity=2)
