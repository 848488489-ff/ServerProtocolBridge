"""Tests for the language layer (English-only).

    python -m unittest tests.test_i18n -v

The project has no second language: every language code resolves to English,
and the Chinese table has been removed entirely.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from proxy import i18n  # noqa: E402
from proxy.config import Config  # noqa: E402
from proxy.logger import NullLogger  # noqa: E402
from proxy.translator import EaglerTranslator  # noqa: E402
from test_translate import REAL_FIRST_PACKET, build_request_login  # noqa: E402

PLACEHOLDER = re.compile(r'%\((\w+)\)')


class LanguageTests(unittest.TestCase):
    def tearDown(self):
        # Never leak the selected language into the other test modules.
        i18n.set_language(i18n.DEFAULT_LANGUAGE)

    def test_default_language_is_english(self):
        i18n.set_language('')
        self.assertEqual(i18n.get_language(), 'en')
        self.assertEqual(i18n.tr('proxy.query.no_motd'),
                         'The server did not return any MOTD information')

    def test_every_code_resolves_to_english(self):
        # There is no second language: even a legacy 'zh' resolves to English.
        self.assertEqual(i18n.set_language('zh'), 'en')
        self.assertEqual(i18n.get_language(), 'en')
        self.assertEqual(i18n.tr('proxy.query.no_motd'),
                         'The server did not return any MOTD information')
        self.assertEqual(i18n.tr('translator.prefix'), '[Protocol Adapter] ')
        self.assertEqual(i18n.set_language('auto'), 'en')
        self.assertEqual(i18n.get_language(), 'en')

    def test_unknown_language_falls_back_to_default(self):
        self.assertEqual(i18n.set_language('klingon'), 'en')
        self.assertEqual(i18n.get_language(), 'en')

    def test_unknown_key_returns_the_key(self):
        self.assertEqual(i18n.tr('nope.nothing.here'), 'nope.nothing.here')

    def test_broken_template_does_not_crash(self):
        # Call sites must be able to format safely even if a value is missing.
        self.assertIn('%', i18n.tr('translator.log.protocols_selected'))

    def test_language_label_round_trip(self):
        for code in i18n.LANGUAGES:
            self.assertEqual(i18n.language_code(i18n.language_label(code)), code)
        # An unknown label maps back to the default language (English).
        self.assertEqual(i18n.language_code('Chinese (simplified)'), 'en')

    def test_no_missing_keys_reported(self):
        self.assertEqual(i18n.missing_keys('zh'), [])

    def test_english_templates_use_named_placeholders(self):
        # Every English template must use named placeholders; a bare %s / %d
        # would be a formatting bug at a call site.
        for key, text in i18n.EN.items():
            self.assertNotIn('%s', text, key)
            self.assertNotIn('%d', text, key)
            self.assertNotIn('%r', text, key)

    def test_config_carries_the_language(self):
        config = Config()
        config.target = 'play.example.net'
        self.assertEqual(config.language, 'en')
        self.assertEqual(config.validate(), [])
        # A legacy 'zh' value is coerced to English on load.
        self.assertEqual(Config.from_dict({'language': 'zh'}).language, 'en')
        config.language = 'auto'
        self.assertEqual(config.validate(), [])
        config.language = 'fr'
        self.assertTrue(any(i18n.tr('core.config.language_invalid') in item
                            for item in config.validate()))

    def test_config_problems_stay_english(self):
        """Validation diagnostics are always English, whatever the UI language."""
        i18n.set_language('en')
        config = Config()
        config.language = 'fr'
        problems = config.validate()
        self.assertIn(i18n.tr_in('en', 'core.config.language_invalid'), problems)

    def test_cli_language_argument(self):
        from proxy.cli import apply_arguments, build_parser

        args = build_parser().parse_args(['--language', 'auto'])
        config = apply_arguments(Config(), args)
        self.assertEqual(config.language, 'auto')

    def test_code_retry_copy_does_not_claim_a_previous_attempt(self):
        # The retry may happen on the very first code (for example after an SSL
        # retry), so the text must describe Microsoft rejecting *this* code,
        # not a previous one.
        text = i18n.tr('gui.accounts.ms.renewing').lower()
        self.assertNotIn('previous', text)
        self.assertTrue(i18n.tr('gui.accounts.ms.retrying_ssl'))

    def test_player_facing_messages_follow_the_language(self):
        """Protocol-layer text (here: a proxy error sent as 0xFF) is English."""
        i18n.set_language('en')
        sent: list = []
        translator = EaglerTranslator(
            target_host='play.example.net', target_port=25565, log=NullLogger(), tag='#1',
            send_client=sent.append, send_backend=[].append, request_close=[].append)
        translator.feed_client(REAL_FIRST_PACKET)
        translator.feed_client(build_request_login(username='Tester'))
        translator.feed_server(b'\x00')              # truncated frame -> proxy side error
        self.assertEqual(sent[-1][0], 0xFF)
        length = int.from_bytes(sent[-1][2:4], 'big')
        text = json.loads(sent[-1][4:4 + length].decode('utf-8'))['text']
        self.assertTrue(text.startswith('[Protocol Adapter] '), text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
