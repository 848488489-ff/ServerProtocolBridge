"""Structural tests for the embedded Web UI template.

The UI is a single HTML/JS string inside web_html.py.  These tests pin the
behaviour that would be easy to break silently and that the user relies on:
the persistent top-right "needs a restart" notice, the debounced auto-save
wiring on *both* the settings page and the dashboard (the connection fields
live on the dashboard), and the auto-save indicator.
"""

from __future__ import annotations

import unittest

from proxy.web_html import INDEX_HTML


class WebUiStructureTests(unittest.TestCase):
    """Key structural contracts of the embedded Web UI."""

    def test_auto_save_wired_on_both_pages(self):
        # The connection fields (target, listen host, ports, use_srv) live on
        # the dashboard, so auto-save must listen there as well as on the
        # settings page -- otherwise editing them never saves and the
        # "needs a restart" notice never appears.
        self.assertIn("addEventListener('input', onConfigEdit)", INDEX_HTML)
        self.assertIn("addEventListener('change', onConfigEdit)", INDEX_HTML)
        self.assertIn("'#page-settings'", INDEX_HTML)
        self.assertIn("'#page-dashboard'", INDEX_HTML)
        self.assertIn('const onConfigEdit =', INDEX_HTML)
        self.assertIn('scheduleAutoSave', INDEX_HTML)
        self.assertIn('renderServiceRestart(data.service_restart)', INDEX_HTML)

    def test_auto_save_excludes_independent_panes(self):
        # Panes with their own save buttons (appearance, Web UI/auth, MCP key,
        # API info) and the settings search box must not trigger auto-save.
        self.assertGreaterEqual(INDEX_HTML.count('data-no-autosave'), 5)

    def test_restart_toast_persistent_and_dismissable(self):
        # The notice is a fixed top-right toast with a close button; the old
        # savebar hint is gone.
        self.assertIn('id="service-restart-toast"', INDEX_HTML)
        self.assertIn('id="btn-service-restart-close"', INDEX_HTML)
        self.assertIn('.toast-persist', INDEX_HTML)
        self.assertNotIn('service-restart-note', INDEX_HTML)

    def test_auto_save_indicator_and_i18n(self):
        self.assertIn('id="auto-save-indicator"', INDEX_HTML)
        self.assertIn("t('web.auto_saved')", INDEX_HTML)
        self.assertIn("t('web.auto_save_error')", INDEX_HTML)


if __name__ == '__main__':
    unittest.main()
