"""Tests for the usage tutorials (MCP / CLI) and the cross-platform opener.

    python -m unittest tests.test_tutorial -v

The opener is exercised with mocks so no editor/browser actually opens.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from proxy import i18n, tutorial  # noqa: E402
from proxy.tutorial import CLI_TUTORIAL, MCP_TUTORIAL  # noqa: E402


class TutorialTextTests(unittest.TestCase):
    def tearDown(self):
        i18n.set_language(i18n.DEFAULT_LANGUAGE)

    def test_every_kind_has_both_languages(self):
        for table in (MCP_TUTORIAL, CLI_TUTORIAL):
            self.assertIn('en', table)
            self.assertIn('zh', table)
            for entry in table.values():
                self.assertTrue(entry['title'].strip())
                self.assertTrue(entry['body'].strip())

    def test_tutorial_follows_active_language(self):
        i18n.set_language('zh')
        self.assertEqual(tutorial.tutorial('mcp')['language'], 'zh')
        self.assertIn('使用教程', tutorial.tutorial('mcp')['title'])
        self.assertIn('使用教程', tutorial.tutorial('cli')['title'])
        i18n.set_language('en')
        self.assertEqual(tutorial.tutorial('mcp')['language'], 'en')
        self.assertIn('Usage', tutorial.tutorial('mcp')['title'])
        self.assertIn('Usage', tutorial.tutorial('cli')['title'])

    def test_tutorial_explicit_language_overrides(self):
        self.assertEqual(tutorial.tutorial('mcp', 'zh')['language'], 'zh')
        self.assertEqual(tutorial.tutorial('cli', 'en')['language'], 'en')

    def test_tutorial_unknown_kind_falls_back_to_mcp(self):
        self.assertIn('body', tutorial.tutorial('bogus', 'en'))

    def test_mcp_tutorial_covers_endpoint_and_key(self):
        en = MCP_TUTORIAL['en']['body']
        zh = MCP_TUTORIAL['zh']['body']
        self.assertIn('/mcp', en)
        self.assertIn('Bearer', en)
        self.assertIn('/mcp', zh)
        self.assertIn('Bearer', zh)


class TutorialOpenTests(unittest.TestCase):
    @mock.patch('proxy.tutorial._open_with_default_app')
    def test_open_tutorial_writes_file_and_opens(self, open_mock):
        path = tutorial.open_tutorial('mcp', 'zh')
        self.assertTrue(Path(path).exists())
        content = Path(path).read_text(encoding='utf-8')
        self.assertIn('/mcp', content)
        open_mock.assert_called_once_with(path)
        Path(path).unlink(missing_ok=True)

    @mock.patch('proxy.tutorial.subprocess.Popen')
    @mock.patch('proxy.tutorial.sys.platform', 'linux')
    def test_linux_uses_xdg_open(self, popen_mock):
        tutorial._open_with_default_app('/tmp/x.md')
        popen_mock.assert_called_once_with(['xdg-open', '/tmp/x.md'])

    @mock.patch('proxy.tutorial.subprocess.Popen')
    @mock.patch('proxy.tutorial.sys.platform', 'darwin')
    def test_macos_uses_open(self, popen_mock):
        tutorial._open_with_default_app('/tmp/x.md')
        popen_mock.assert_called_once_with(['open', '/tmp/x.md'])

    @mock.patch('proxy.tutorial.os.startfile')
    @mock.patch('proxy.tutorial.sys.platform', 'win32')
    def test_windows_uses_startfile(self, startfile_mock):
        tutorial._open_with_default_app('C:\\x.md')
        startfile_mock.assert_called_once_with('C:\\x.md')

    @mock.patch('proxy.tutorial.sys.platform', 'plan9')
    def test_unknown_platform_raises(self):
        with self.assertRaises(RuntimeError):
            tutorial._open_with_default_app('/tmp/x.md')


if __name__ == '__main__':
    unittest.main()