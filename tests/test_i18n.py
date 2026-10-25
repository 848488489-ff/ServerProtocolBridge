"""Tests for the language layer: defaults, switching, and table sanity.

    python -m unittest tests.test_i18n -v

The suite runs in the program's default language (English); the Chinese
tables are exercised by switching explicitly.
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

    def test_switch_to_chinese_and_back(self):
        self.assertEqual(i18n.set_language('zh'), 'zh')
        self.assertEqual(i18n.get_language(), 'zh')
        self.assertEqual(i18n.tr('proxy.query.no_motd'), '服务器未返回MOTD信息')
        self.assertEqual(i18n.tr('translator.prefix'), '[协议转换器] ')

        i18n.set_language('en')
        self.assertEqual(i18n.tr('proxy.query.no_motd'),
                         'The server did not return any MOTD information')
        self.assertEqual(i18n.tr('translator.prefix'), '[Protocol Adapter] ')

    def test_unknown_language_falls_back_to_default(self):
        self.assertEqual(i18n.set_language('klingon'), 'en')
        self.assertEqual(i18n.get_language(), 'en')

    def test_unknown_key_returns_the_key(self):
        self.assertEqual(i18n.tr('nope.nothing.here'), 'nope.nothing.here')

    def test_broken_template_does_not_crash(self):
        # Call sites must be able to format safely even if a value is missing.
        i18n.set_language('zh')
        self.assertIn('%', i18n.tr('translator.log.protocols_selected'))

    def test_language_label_round_trip(self):
        for code in i18n.LANGUAGES:
            self.assertEqual(i18n.language_code(i18n.language_label(code)), code)
        self.assertEqual(i18n.language_code('zh'), 'zh')

    def test_every_english_key_has_a_translation(self):
        self.assertEqual(i18n.missing_keys('zh'), [])

    def test_placeholder_names_match_between_languages(self):
        for key, text in i18n.EN.items():
            self.assertEqual(sorted(PLACEHOLDER.findall(text)),
                             sorted(PLACEHOLDER.findall(i18n.ZH.get(key, ''))), key)

    def test_config_carries_the_language(self):
        config = Config()
        config.target = 'play.example.net'
        self.assertEqual(config.language, 'en')
        self.assertEqual(config.validate(), [])
        self.assertEqual(Config.from_dict({'language': 'zh'}).language, 'zh')
        config.language = 'ZH'                       # case is normalised
        self.assertEqual(config.validate(), [])
        config.language = 'fr'
        self.assertTrue(any(i18n.tr('core.config.language_invalid') in item
                            for item in config.validate()))

    def test_cli_language_argument(self):
        from proxy.cli import apply_arguments, build_parser

        args = build_parser().parse_args(['--language', 'zh'])
        config = apply_arguments(Config(), args)
        self.assertEqual(config.language, 'zh')

    def test_code_retry_copy_does_not_claim_a_previous_attempt(self):
        # The retry may happen on the very first code (for example after an SSL
        # retry), so the text must describe Microsoft rejecting *this* code,
        # not a previous one.
        for code in ('en', 'zh'):
            i18n.set_language(code)
            text = i18n.tr('gui.accounts.ms.renewing').lower()
            self.assertNotIn('previous', text)
            self.assertNotIn('上一个', text)
            self.assertTrue(i18n.tr('gui.accounts.ms.retrying_ssl'))

    def test_player_facing_messages_follow_the_language(self):
        """Protocol-layer text (here: a proxy error sent as 0xFF) is localised too."""
        i18n.set_language('zh')
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
        self.assertTrue(text.startswith('[协议转换器] '), text)


if __name__ == '__main__':
    unittest.main(verbosity=2)
