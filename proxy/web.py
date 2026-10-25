"""Browser interface for Server Protocol Bridge.

The Web UI is a small single-page application served by Flask.  It talks to
the same :class:`proxy.runtime.ServiceManager` as the desktop window, so both
interfaces start, stop, configure and monitor one proxy and read one log.

Everything the window can do is exposed here: service control, the complete
configuration, account management (offline / third-party / Microsoft device
sign-in), certificate generation and installation, live logs, theme and
language switching, and the Web UI's own bind address and port.  The bind
settings are stored in ``config.json`` next to the other options; changing
them schedules a restart of this listener and reports the new URL.
"""

from __future__ import annotations

from . import (web_routes, webauth)
from .i18n import (get_language, tr)
from .runtime import get_manager
from .web_html import LOGIN_HTML
from flask import (Flask, jsonify, redirect, request, session, url_for)
from html import escape as html_escape
def create_app(config_path: str | None = None) -> Flask:
    """Build the Flask application."""
    app = Flask(__name__)
    app.config['CONFIG_PATH'] = config_path
    app.json.ensure_ascii = False

    def fail(message, status: int = 400):
        return jsonify({'ok': False, 'error': str(message)}), status

    # ------------------------------------------------------------------
    # Access password
    # ------------------------------------------------------------------
    # The session cookie is deliberately not permanent: with no expiry it is a
    # browser-session cookie, so closing the tab ends the signed-in state and
    # the next visit asks for the password again.  A 30-day cookie made the
    # password effectively a one-time entry.
    #
    # Browsers also store cookies in plaintext in the profile, so a cookie is
    # a bearer token: whoever copies it can act as the signed-in user.  There is
    # no HTTPS here, so the cookie also travels in plaintext on the wire and
    # SESSION_COOKIE_SECURE cannot be used.  What can be done is bind a session
    # to the client that produced it -- ip, user agent, and a per-browser device
    # id kept in localStorage -- so a copied cookie is rejected when replayed
    # from another machine, another browser, or another profile, and that client
    # has to type the password itself.
    app.secret_key = webauth.secret_key()
    app.config.update(SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE='Lax')

    def _client_fingerprint() -> list[str]:
        """Identify the client owning this request: ip, user agent, device id.

        The device id arrives as the X-Device-Id header for XHR traffic, or as
        the ``device`` form field when the login form posts (the form is plain
        HTML and cannot set headers).
        """
        agent = (request.user_agent.string or '').strip()
        agent = ' '.join(agent.split())[:160]
        device = (request.headers.get('X-Device-Id') or '').strip()
        if not device:
            device = str(request.form.get('device') or '').strip()
        return [request.remote_addr or '', agent, device[:64]]

    def _signed_in() -> bool:
        return bool(session.get('authenticated')) and \
            session.get('client') == _client_fingerprint()

    def _safe_next(value: str) -> str:
        value = (value or '').strip()
        if value.startswith('/') and not value.startswith('//') and '\\' not in value:
            return value
        return '/'

    @app.before_request
    def _require_login():
        if not webauth.is_enabled():
            return None
        if request.path in ('/login', '/favicon.ico'):
            return None
        if _signed_in():
            return None
        if session.get('authenticated'):
            # This cookie belongs to a different client than the one that signed
            # in: it was copied.  Drop it; do not let it through.
            session.clear()
        if request.path.startswith('/api/'):
            return jsonify({'ok': False, 'error': tr('web.login_required'),
                            'login': True}), 401
        return redirect(url_for('login', next=request.path))

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if not webauth.is_enabled():
            return redirect('/')
        target = _safe_next(request.values.get('next', '/'))
        error = ''
        if _signed_in():
            return redirect(target)
        if request.method == 'POST':
            key = request.remote_addr or ''
            remaining = webauth.throttle_remaining(key)
            if remaining:
                error = tr('web.login_locked', seconds=remaining)
            elif webauth.verify(request.form.get('password', '')):
                webauth.clear_failures(key)
                session.clear()
                session['authenticated'] = True
                session['client'] = _client_fingerprint()
                return redirect(target)
            else:
                webauth.record_failure(key)
                error = tr('web.login_failed')
        html = (LOGIN_HTML
                .replace('__LANG__', get_language())
                .replace('__THEME__', get_manager().config.theme)
                .replace('__APP__', tr('core.app_name'))
                .replace('__TITLE__', tr('web.login_title'))
                .replace('__INTRO__', tr('web.login_intro'))
                .replace('__PASSWORD__', tr('web.password'))
                .replace('__SUBMIT__', tr('web.sign_in'))
                .replace('__NEXT__', html_escape(target, quote=True))
                .replace('__ERROR__', html_escape(error)))
        return html, 200, {'Content-Type': 'text/html; charset=utf-8',
                           'Cache-Control': 'no-store'}

    @app.route('/logout', methods=['GET', 'POST'])
    def logout():
        session.clear()
        if webauth.is_enabled():
            return redirect(url_for('login'))
        return redirect('/')

    @app.route('/api/logout', methods=['POST'])
    def api_logout():
        session.clear()
        return jsonify({'ok': True})
























    web_routes.register(app, fail)
    return app
