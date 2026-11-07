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

from . import (api_routes, web_routes, webauth)
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
    #
    # The device id only exists in the browser, so the server also keeps a copy
    # in a plain cookie: that is the one channel a normal page load can use,
    # since only XHR can set a request header.  Binding it to the ip and user
    # agent is what stops a copied pair from working elsewhere.
    app.secret_key = webauth.secret_key()
    app.config.update(SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE='Lax')

    def _client_fingerprint() -> list[str]:
        """Identify the client owning this request: ip and user agent.

        Both are present on every request, including plain page navigations.
        """
        agent = (request.user_agent.string or '').strip()
        agent = ' '.join(agent.split())[:160]
        return [request.remote_addr or '', agent]

    def _client_device() -> str:
        """This browser's stable id, from whichever channel the request offers.

        The id is deliberately client supplied so a copied session cookie fails
        when replayed from another profile.  It reaches the server three ways:
        as the ``X-Device-Id`` header on XHR, as the ``device`` form field when
        the login form posts, and -- after a successful login -- as the
        ``spb-device`` cookie, which is the only channel a plain page load can
        use.  Without that last one the redirect straight after signing in
        looked like a different client and bounced the user back to the login
        page every time.
        """
        value = (request.headers.get('X-Device-Id') or '').strip()
        if not value:
            value = str(request.form.get('device') or '').strip()
        if not value:
            value = str(request.cookies.get('spb-device') or '').strip()
        return value[:64]

    def _signed_in() -> bool:
        if not session.get('authenticated'):
            return False
        if (session.get('client') or [])[:2] != _client_fingerprint():
            return False
        incoming = _client_device()
        expected = str(session.get('device') or '').strip()
        # An empty incoming id means the request could not carry one; it is not
        # evidence of a different client.
        return not (incoming and expected and incoming != expected)

    def _safe_next(value: str) -> str:
        value = (value or '').strip()
        if value.startswith('/') and not value.startswith('//') and '\\' not in value:
            return value
        return '/'

    @app.before_request
    def _require_login():
        if not webauth.is_enabled():
            return None
        if request.path in ('/login', '/favicon.ico', '/mcp'):
            return None
        if request.path.startswith('/api/v1/'):
            # The automation API authenticates itself with the MCP key (or the
            # loopback exemption); it must not sit behind the session cookie.
            return None
        if webauth.is_loopback(request.remote_addr or ''):
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
        if webauth.is_loopback(request.remote_addr or ''):
            # Local access never needs the password: the desktop shell loads
            # this page through 127.0.0.1, and showing the form would lock the
            # program out of its own window.
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
                device = _client_device()
                session['device'] = device
                response = redirect(target)
                # Give every later request a channel for the device id.  Without
                # it the redirect above would fail the fingerprint check and the
                # browser would land back on this page.  No max_age: like the
                # session cookie itself, closing the tab ends it.
                if device:
                    response.set_cookie('spb-device', device, samesite='Lax',
                                        httponly=True)
                return response
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
























    # ------------------------------------------------------------------
    # Security headers
    # ------------------------------------------------------------------
    # The Web UI is a local, single-page app that relies on inline <script>
    # and <style>, so a strict CSP would break it.  We still harden the parts
    # that do not conflict with the page: clickjacking, MIME sniffing and the
    # referrer.  CSP is deliberately omitted here (an 'unsafe-inline' policy
    # would add no protection, only a false sense of it).
    @app.after_request
    def _security_headers(response):
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'DENY')
        response.headers.setdefault('Referrer-Policy',
                                    'strict-origin-when-cross-origin')
        return response

    web_routes.register(app, fail)
    api_routes.register(app)
    return app
