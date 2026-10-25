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

import json
import socket
import threading
import time
import uuid
from html import escape as html_escape

from flask import (Flask, jsonify, redirect, request, session, url_for)

from . import (accounts, certs, config as config_module, eagler, third_party,
               update, webauth)
from .i18n import LANGUAGES, get_language, language_label, set_language, tr
from .locales import EN as EN_TABLE
from .runtime import get_manager
from .utils import human_bytes, human_duration
from .version import VERSION

# ---------------------------------------------------------------------------
# Microsoft device-code jobs
# ---------------------------------------------------------------------------

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()
JOB_TTL = 1800.0


def _prune_jobs() -> None:
    now = time.time()
    with _jobs_lock:
        for key in [key for key, job in _jobs.items()
                    if now - job.get('created', now) > JOB_TTL]:
            _jobs.pop(key, None)


def _ms_worker(job_id: str, info: dict, verify: bool) -> None:
    try:
        account = accounts.microsoft_device_poll(info, verify)
    except accounts.AccountError as exc:
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is not None:
                job.update(state='error', error=str(exc), code=exc.code)
    except Exception as exc:
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is not None:
                job.update(state='error', error=str(exc), code='')
    else:
        accounts.add_account(account)
        with _jobs_lock:
            job = _jobs.get(job_id)
            if job is not None:
                job.update(state='done', account=_account_payload(account, ''))


def _account_payload(account, active_id: str) -> dict:
    return {
        'id': account.id,
        'kind': account.kind,
        'username': account.username,
        'uuid': account.uuid,
        'active': bool(active_id and account.id == active_id),
        'kind_label': tr('accounts.kind.' + account.kind),
    }


def _web_info() -> dict:
    from .webserver import current_address, current_url

    host, port = current_address()
    config = get_manager().config
    host = host or config.web_host
    port = port or config.web_port
    url = current_url() or config.web_url()
    lan = ''
    if (host or '').strip() in ('0.0.0.0', '::', '[::]'):
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                probe.connect(('8.8.8.8', 80))
                lan = 'http://%s:%d/' % (probe.getsockname()[0], int(port))
            finally:
                probe.close()
        except Exception:
            lan = ''
    return {'host': host, 'port': int(port), 'url': url, 'lan_url': lan}


def _config_options() -> dict:
    return {
        'themes': [{'code': code, 'label': tr('gui.theme.' + code)}
                   for code in config_module.THEME_MODES],
        'languages': [{'code': code, 'label': language_label(code)}
                      for code in LANGUAGES],
        'spoof_clients': [{'code': code, 'label': tr('gui.spoof.' + code)}
                          for code in config_module.SPOOF_CLIENTS],
        'resource_pack_modes': [
            {'code': code, 'label': tr('gui.resource_pack_mode.' + code)}
            for code in config_module.RESOURCE_PACK_MODES],
        'log_levels': ['debug', 'info', 'warn', 'error'],
        'cert_generators': [
            {'code': code, 'label': code.capitalize()}
            for code in ('auto', 'python', 'openssl')],
    }


def _int_field(body: dict, key: str, label: str) -> int | None:
    if key not in body:
        return None
    raw = body.get(key)
    if isinstance(raw, bool):
        raise ValueError(tr('web.invalid_number', field=label))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValueError(tr('web.invalid_number', field=label)) from None
    return value


def _config_from_body(body: dict) -> config_module.Config:
    current = get_manager().config
    data = current.to_dict()
    for key, value in body.items():
        if key in data:
            data[key] = value

    for key, label in (
            ('wss_port', tr('gui.label.wss_port')),
            ('ws_port', tr('gui.label.ws_port')),
            ('web_port', tr('gui.label.web_port')),
            ('heartbeat_sec', tr('gui.label.heartbeat')),
            ('status_cache_ttl', tr('gui.label.status_cache_ttl')),
            ('max_payload_mb', tr('gui.label.max_payload')),
            ('cert_days', tr('gui.label.cert_days'))):
        value = _int_field(body, key, label)
        if value is not None:
            data[key] = value
    if 'connect_timeout' in body:
        try:
            data['connect_timeout'] = float(body['connect_timeout'])
        except (TypeError, ValueError):
            raise ValueError(tr('web.invalid_number',
                                field=tr('gui.label.connect_timeout'))) from None

    if 'routes_text' in body:
        data['routes'] = config_module.parse_routes_text(str(body['routes_text']))
    if 'cert_extra_names' in body:
        value = body['cert_extra_names']
        if isinstance(value, str):
            value = [item.strip() for item in value.replace(',', ' ').split()
                     if item.strip()]
        data['cert_extra_names'] = list(value or [])

    config = config_module.Config.from_dict(data)
    if config.theme not in config_module.THEME_MODES:
        config.theme = current.theme
    if (config.language or '').lower() not in LANGUAGES:
        config.language = current.language
    problems = config.validate_web()
    if problems:
        raise ValueError('\n'.join(problems))
    return config


def _save_body(body: dict) -> tuple[config_module.Config, bool, bool]:
    manager = get_manager()
    old = manager.config
    config = _config_from_body(body)
    web_changed = ((old.web_host or '').strip() != (config.web_host or '').strip()
                   or int(old.web_port) != int(config.web_port))
    language_changed = (old.language or '').lower() != (config.language or '').lower()
    manager.save_config(config)
    if web_changed:
        _schedule_web_restart(config.web_host, config.web_port)
    return manager.config, language_changed, web_changed


def _schedule_web_restart(host: str, port: int) -> None:
    def run() -> None:
        time.sleep(1.0)
        manager = get_manager()
        try:
            from .webserver import restart_web_ui

            url, error = restart_web_ui(host, port)
        except Exception as exc:
            manager.hub.add('error', tr('web.webui_restart_failed', error=exc))
            return
        if url:
            manager.hub.add('info', tr('web.webui_listening', host=host, port=port))
        else:
            manager.hub.add('error', tr('web.webui_restart_failed', error=error))

    threading.Thread(target=run, name='web-ui-restart', daemon=True).start()


def _i18n_payload() -> dict:
    prefixes = ('web.', 'gui.', 'accounts.kind.', 'core.app_name')
    return {key: tr(key) for key in EN_TABLE if key.startswith(prefixes)}


def _cert_payload() -> dict:
    config = get_manager().config
    cert_path, key_path = certs.certificate_paths(config.resolved_cert_dir)
    info = certs.inspect_certificate(cert_path, key_path) if cert_path.exists() else None
    return {
        'exists': info is not None,
        'cert_path': str(cert_path),
        'key_path': str(key_path),
        'info': info,
    }


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
    app.secret_key = webauth.secret_key()
    app.config.update(SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE='Lax',
                      PERMANENT_SESSION_LIFETIME=60 * 60 * 24 * 30)

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
        if session.get('authenticated'):
            return None
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
        if session.get('authenticated'):
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
                session.permanent = True
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

    # ------------------------------------------------------------------
    # Pages
    # ------------------------------------------------------------------
    @app.route('/')
    def index():
        i18n = json.dumps(_i18n_payload(), ensure_ascii=False).replace('<', '\\u003c')
        manager = get_manager()
        html = (INDEX_HTML
                .replace('__LANG__', get_language())
                .replace('__THEME__', manager.config.theme)
                .replace('__APP__', tr('core.app_name'))
                .replace('__VERSION__', VERSION)
                .replace('__I18N__', i18n))
        return html, 200, {'Content-Type': 'text/html; charset=utf-8',
                           'Cache-Control': 'no-store'}

    @app.route('/favicon.ico')
    def favicon():
        return ('', 204)

    # ------------------------------------------------------------------
    # Status / configuration
    # ------------------------------------------------------------------
    @app.route('/api/status')
    def api_status():
        manager = get_manager()
        data = manager.status()
        data['web'] = _web_info()
        data['language'] = get_language()
        data['theme'] = manager.config.theme
        data['config_problems'] = manager.config.validate()
        data['log_seq'] = manager.hub.seq
        data['auth'] = webauth.state()
        return jsonify(data)

    @app.route('/api/config', methods=['GET', 'POST'])
    def api_config():
        manager = get_manager()
        if request.method == 'GET':
            return jsonify({
                'ok': True,
                'config': manager.config.to_dict(),
                'options': _config_options(),
                'problems': manager.config.validate(),
                'web_problems': manager.config.validate_web(),
                'web': _web_info(),
                'auth': webauth.state(),
            })
        body = request.get_json(silent=True) or {}
        if body.get('reset'):
            old = manager.config
            config = config_module.Config()
            language_changed = ((old.language or '').lower()
                                != (config.language or '').lower())
            web_changed = ((old.web_host or '').strip()
                           != (config.web_host or '').strip()
                           or int(old.web_port) != int(config.web_port))
            manager.save_config(config)
            if web_changed:
                _schedule_web_restart(config.web_host, config.web_port)
        else:
            try:
                config, language_changed, web_changed = _save_body(body)
            except ValueError as exc:
                return fail(exc)
        return jsonify({
            'ok': True,
            'config': config.to_dict(),
            'problems': config.validate(),
            'web': _web_info(),
            'web_restart': web_changed,
            'web_url': config.web_url(),
            'language_changed': language_changed,
            'auth': webauth.state(),
        })

    @app.route('/api/auth', methods=['GET', 'POST'])
    def api_auth():
        if request.method == 'GET':
            return jsonify({'ok': True, 'auth': webauth.state()})
        body = request.get_json(silent=True) or {}
        enabled = bool(body.get('enabled'))
        password = str(body.get('password') or '')
        was_enabled = webauth.is_enabled()
        if enabled:
            if password:
                if len(password) < 4:
                    return fail(tr('web.password_short'))
                webauth.set_password(password)
            elif not webauth.has_password():
                return fail(tr('web.password_required'))
        else:
            webauth.disable()
        # Enabling access control or changing the password must invalidate the
        # current browser session: otherwise the page that just set the
        # password keeps working and the password looks like it had no effect.
        reauth = enabled and (bool(password) or not was_enabled)
        if reauth:
            session.clear()
        else:
            session['authenticated'] = True
        return jsonify({'ok': True, 'auth': webauth.state(), 'reauth': reauth})

    @app.route('/api/ui/preferences', methods=['POST'])
    def api_preferences():
        manager = get_manager()
        body = request.get_json(silent=True) or {}
        config = manager.config
        old_language = (config.language or '').lower()
        theme = str(body.get('theme') or '').strip().lower()
        language = str(body.get('language') or '').strip().lower()
        if theme in config_module.THEME_MODES:
            config.theme = theme
        if language in LANGUAGES:
            config.language = language
        manager.save_config(config)
        return jsonify({'ok': True, 'theme': config.theme,
                        'language': config.language,
                        'language_changed': old_language != config.language})

    # ------------------------------------------------------------------
    # Service
    # ------------------------------------------------------------------
    @app.route('/api/service/start', methods=['POST'])
    def api_start():
        manager = get_manager()
        body = request.get_json(silent=True) or {}
        if body:
            try:
                _save_body(body)
            except ValueError as exc:
                return fail(exc)
        ok, message = manager.start(manager.config)
        if not ok:
            return fail(message)
        return jsonify({'ok': True})

    @app.route('/api/service/stop', methods=['POST'])
    def api_stop():
        manager = get_manager()
        manager.stop()
        return jsonify({'ok': True})

    # ------------------------------------------------------------------
    # Logs
    # ------------------------------------------------------------------
    @app.route('/api/logs')
    def api_logs():
        manager = get_manager()
        try:
            since = max(0, int(request.args.get('since', 0)))
        except (TypeError, ValueError):
            since = 0
        level = (request.args.get('level') or 'all').strip().lower()
        try:
            limit = min(1000, max(1, int(request.args.get('limit', 500))))
        except (TypeError, ValueError):
            limit = 500
        items = manager.hub.snapshot(since)
        if level != 'all':
            items = [item for item in items if item['level'] == level]
        return jsonify({'ok': True, 'seq': manager.hub.seq,
                        'lines': items[-limit:]})

    @app.route('/api/logs/clear', methods=['POST'])
    def api_logs_clear():
        get_manager().hub.clear()
        return jsonify({'ok': True})

    # ------------------------------------------------------------------
    # Accounts
    # ------------------------------------------------------------------
    @app.route('/api/accounts')
    def api_accounts():
        store = accounts.load_store()
        return jsonify({
            'ok': True,
            'active': store.active,
            'accounts': [_account_payload(account, store.active)
                         for account in store.accounts],
        })

    @app.route('/api/accounts/offline', methods=['POST'])
    def api_account_offline():
        body = request.get_json(silent=True) or {}
        name = str(body.get('username') or '').strip()
        if not eagler.USERNAME_PATTERN.match(name):
            return fail(tr('gui.accounts.offline.bad_name'))
        account = accounts.add_account(
            accounts.Account(kind=accounts.KIND_OFFLINE, username=name))
        return jsonify({'ok': True, 'account': _account_payload(account, '')})

    @app.route('/api/accounts/thirdparty', methods=['POST'])
    def api_account_thirdparty():
        body = request.get_json(silent=True) or {}
        server = str(body.get('server') or '').strip()
        username = str(body.get('username') or '').strip()
        password = str(body.get('password') or '')
        if not (server and username and password):
            return fail(tr('gui.accounts.thirdparty.missing'))
        try:
            account = accounts.thirdparty_authenticate(server, username, password)
        except accounts.AccountError as exc:
            return fail(exc)
        except Exception as exc:
            return fail(exc)
        accounts.add_account(account)
        return jsonify({'ok': True, 'account': _account_payload(account, '')})

    @app.route('/api/accounts/microsoft/start', methods=['POST'])
    def api_ms_start():
        _prune_jobs()
        body = request.get_json(silent=True) or {}
        verify = bool(body.get('verify', True))
        try:
            info = accounts.microsoft_device_start(verify)
        except accounts.AccountError as exc:
            return fail(exc)
        except Exception as exc:
            return fail(exc)
        job_id = uuid.uuid4().hex
        with _jobs_lock:
            _jobs[job_id] = {'state': 'pending', 'created': time.time(),
                             'info': info, 'error': '', 'code': '', 'account': None}
        threading.Thread(target=_ms_worker, args=(job_id, info, verify),
                         name='ms-signin', daemon=True).start()
        return jsonify({
            'ok': True, 'job': job_id,
            'user_code': info.get('user_code', ''),
            'verification_uri': info.get('verification_uri', ''),
            'expires_in': info.get('expires_in', 0),
            'interval': info.get('interval', 5),
        })

    @app.route('/api/accounts/microsoft/<job_id>')
    def api_ms_job(job_id: str):
        _prune_jobs()
        with _jobs_lock:
            job = dict(_jobs.get(job_id) or {})
        if not job:
            return fail(tr('gui.accounts.ms.title'), 404)
        return jsonify({
            'ok': True,
            'state': job.get('state', 'pending'),
            'error': job.get('error', ''),
            'code': job.get('code', ''),
            'account': job.get('account'),
        })

    @app.route('/api/accounts/<account_id>/active', methods=['POST'])
    def api_account_active(account_id: str):
        store = accounts.load_store()
        if store.get(account_id) is None:
            return fail(tr('web.account_select'), 404)
        accounts.set_active(account_id)
        return jsonify({'ok': True})

    @app.route('/api/accounts/<account_id>', methods=['DELETE'])
    def api_account_delete(account_id: str):
        if not accounts.remove_account(account_id):
            return fail(tr('web.account_select'), 404)
        return jsonify({'ok': True})

    # ------------------------------------------------------------------
    # Certificates
    # ------------------------------------------------------------------
    @app.route('/api/cert')
    def api_cert():
        return jsonify({'ok': True, **_cert_payload()})

    @app.route('/api/cert/generate', methods=['POST'])
    def api_cert_generate():
        manager = get_manager()
        if manager.running:
            return fail(tr('web.cert_running'))
        body = request.get_json(silent=True) or {}
        config = manager.config
        try:
            days = int(body.get('days', config.cert_days))
            common_name = str(body.get('common_name') or config.cert_common_name or 'localhost')
            generator = str(body.get('generator') or config.cert_generator or 'auto')
            extra = body.get('extra_names', config.cert_extra_names)
            if isinstance(extra, str):
                extra = [item.strip() for item in extra.replace(',', ' ').split()
                         if item.strip()]
            cert_path, key_path = certs.certificate_paths(config.resolved_cert_dir)
            for path in (cert_path, key_path):
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
            certs.generate_certificate(
                config.resolved_cert_dir, common_name=common_name,
                extra_names=list(extra or []), days=max(1, days),
                generator=generator, logger=manager.logger)
        except Exception as exc:
            return fail(tr('web.cert_failed', error=exc))
        return jsonify({'ok': True, **_cert_payload()})

    @app.route('/api/cert/install', methods=['POST'])
    def api_cert_install():
        manager = get_manager()
        payload = _cert_payload()
        if not payload['exists']:
            return fail(tr('web.no_cert'))
        try:
            ok, message = certs.install_to_trust_store(
                certs.certificate_paths(manager.config.resolved_cert_dir)[0],
                logger=manager.logger)
        except Exception as exc:
            return fail(tr('web.cert_failed', error=exc))
        if not ok:
            return fail(message or tr('web.cert_failed', error=''))
        return jsonify({'ok': True, 'message': message})

    # ------------------------------------------------------------------
    # Updates / about / Web UI control
    # ------------------------------------------------------------------
    @app.route('/api/update')
    def api_update():
        try:
            outcome = update.check(update.DEFAULT_UPDATE_URL, VERSION)
        except update.UpdateError as exc:
            return fail(tr('web.update_failed', error=exc))
        except Exception as exc:
            return fail(tr('web.update_failed', error=exc))
        return jsonify({'ok': True, 'update': outcome})

    @app.route('/api/about')
    def api_about():
        return jsonify({
            'ok': True,
            'version': VERSION,
            'blurb': tr('gui.about.blurb'),
            'license': tr('gui.about.project_license'),
            'components': [
                {'name': item['name'], 'license': item['license'],
                 'url': item['url']} for item in third_party.COMPONENTS],
            'stdlib': list(third_party.STDLIB_MODULES),
        })

    @app.route('/api/web/restart', methods=['POST'])
    def api_web_restart():
        config = get_manager().config
        _schedule_web_restart(config.web_host, config.web_port)
        return jsonify({'ok': True, 'url': config.web_url()})

    return app


# ---------------------------------------------------------------------------
# Single-page front end
# ---------------------------------------------------------------------------

INDEX_HTML = r"""<!doctype html>
<html lang="__LANG__" data-theme="__THEME__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__APP__ · __VERSION__</title>
<style>
:root {
  --bg: #eef1f6; --sidebar: #e3e8f0; --card: #ffffff; --field: #f4f6fa;
  --border: #d8dfe9; --text: #151c26; --muted: #5d6878; --hover: #d7deea;
  --accent: #2f6fed; --accent-hover: #2559c9; --success: #159a63;
  --danger: #d64545; --warn: #c27508; --shadow: 0 8px 24px rgba(20, 30, 50, .08);
}
html[data-theme="dark"] {
  --bg: #0d1014; --sidebar: #141920; --card: #1a1f27; --field: #11151b;
  --border: #262d38; --text: #e9eef6; --muted: #8b95a7; --hover: #1e242e;
  --accent: #3b82f6; --accent-hover: #2f6fed; --success: #22b378;
  --danger: #ef5b5b; --warn: #e0a12a; --shadow: 0 8px 24px rgba(0, 0, 0, .35);
}
@media (prefers-color-scheme: dark) {
  html[data-theme="system"] {
    --bg: #0d1014; --sidebar: #141920; --card: #1a1f27; --field: #11151b;
    --border: #262d38; --text: #e9eef6; --muted: #8b95a7; --hover: #1e242e;
    --accent: #3b82f6; --accent-hover: #2f6fed; --success: #22b378;
    --danger: #ef5b5b; --warn: #e0a12a; --shadow: 0 8px 24px rgba(0, 0, 0, .35);
  }
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0; background: var(--bg); color: var(--text);
  font: 15px/1.55 "Microsoft YaHei UI", "PingFang SC", "Noto Sans CJK SC", system-ui, sans-serif;
}
button, input, select, textarea { font: inherit; color: inherit; }
a { color: var(--accent); }
.app { display: flex; min-height: 100vh; }
.sidebar {
  width: 236px; flex: 0 0 236px; background: var(--sidebar);
  padding: 22px 14px 18px; position: sticky; top: 0; height: 100vh;
  display: flex; flex-direction: column; gap: 8px; overflow-y: auto;
}
.brand { padding: 0 10px 18px; }
.brand strong { display: block; font-size: 17px; line-height: 1.35; }
.brand span { color: var(--muted); font-size: 12px; }
.nav { display: flex; flex-direction: column; gap: 3px; }
.nav button {
  border: 0; background: transparent; color: var(--text); text-align: left;
  padding: 10px 12px; border-radius: 9px; cursor: pointer; font-size: 14px;
}
.nav button:hover { background: var(--hover); }
.nav button.active { background: var(--accent); color: #fff; }
.side-foot { margin-top: auto; padding: 14px 10px 0; display: grid; gap: 10px; }
.side-foot label { display: block; color: var(--muted); font-size: 12px; margin-bottom: 4px; }
.side-foot select {
  width: 100%; background: var(--field); border: 1px solid var(--border);
  border-radius: 8px; padding: 7px 9px;
}
.main { flex: 1; min-width: 0; padding: 22px 26px 40px; }
.header { display: flex; align-items: flex-start; gap: 16px; margin-bottom: 18px; }
.header h1 { margin: 0; font-size: 25px; }
.header p { margin: 3px 0 0; color: var(--muted); font-size: 13px; }
.header-actions { margin-left: auto; display: flex; align-items: center; gap: 10px; }
.pill {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 92px; padding: 6px 12px; border-radius: 999px;
  color: #fff; background: var(--muted); font-size: 13px; font-weight: 600;
}
.pill.running { background: var(--success); }
.pill.starting, .pill.stopping { background: var(--warn); }
.pill.error { background: var(--danger); }
.page { display: none; }
.page.active { display: block; }
.card {
  background: var(--card); border: 1px solid var(--border); border-radius: 14px;
  padding: 18px; margin-bottom: 16px; box-shadow: var(--shadow);
}
.card h2 { margin: 0 0 12px; font-size: 15px; }
.card h3 { margin: 0 0 8px; font-size: 14px; }
.grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); }
.grid2 { display: grid; gap: 12px 18px; grid-template-columns: 180px minmax(0, 1fr); align-items: center; }
.grid2 .hint { grid-column: 1 / -1; color: var(--muted); font-size: 12px; margin: -4px 0 4px; }
.grid2 label[for] { cursor: pointer; }
.switch {
  position: relative; display: inline-block; width: 46px; height: 26px;
  justify-self: start; flex: 0 0 auto; cursor: pointer;
}
.switch input {
  position: absolute; inset: 0; width: 100%; height: 100%;
  margin: 0; opacity: 0; cursor: pointer; z-index: 1;
}
.switch .knob {
  position: absolute; inset: 0; border-radius: 999px;
  background: var(--border); transition: background .18s ease;
  pointer-events: none;
}
.switch .knob::after {
  content: ""; position: absolute; top: 3px; left: 3px;
  width: 20px; height: 20px; border-radius: 50%; background: #fff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, .28);
  transition: transform .18s ease;
}
.switch input:checked + .knob { background: var(--accent); }
.switch input:checked + .knob::after { transform: translateX(20px); }
.switch input:focus-visible + .knob { outline: 2px solid var(--accent); outline-offset: 2px; }
.field, .grid2 input, .grid2 select, .grid2 textarea {
  width: 100%; background: var(--field); border: 1px solid var(--border);
  border-radius: 8px; padding: 8px 10px; outline: none;
}
.field:focus, .grid2 input:focus, .grid2 select:focus, .grid2 textarea:focus {
  border-color: var(--accent);
}
textarea { resize: vertical; min-height: 82px; font-family: Consolas, monospace; font-size: 13px; }
.btn {
  border: 1px solid transparent; border-radius: 9px; padding: 9px 16px;
  background: var(--field); color: var(--text); cursor: pointer; font-size: 13px;
}
.btn:hover { filter: brightness(.97); }
.btn.primary { background: var(--accent); color: #fff; }
.btn.primary:hover { background: var(--accent-hover); }
.btn.success { background: var(--success); color: #fff; }
.btn.danger { background: var(--danger); color: #fff; }
.btn.ghost { border-color: var(--border); background: transparent; }
.btn:disabled { opacity: .45; cursor: not-allowed; }
.actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.actions .spacer { flex: 1; }
.stats { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); }
.stat { background: var(--field); border-radius: 10px; padding: 12px 14px; }
.stat b { display: block; font-size: 20px; line-height: 1.2; }
.stat span { color: var(--muted); font-size: 12px; }
.endpoint {
  display: flex; align-items: center; gap: 10px; background: var(--field);
  border-radius: 10px; padding: 10px 12px; margin: 10px 0;
}
.endpoint code { flex: 1; font-family: Consolas, monospace; font-size: 15px; color: var(--success); word-break: break-all; }
.kv { display: grid; gap: 8px; }
.kv div { display: flex; gap: 12px; font-size: 13px; }
.kv span { color: var(--muted); min-width: 90px; }
.kv b { font-weight: 500; word-break: break-all; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { text-align: left; padding: 9px 10px; border-bottom: 1px solid var(--border); }
th { color: var(--muted); font-weight: 500; }
tr:last-child td { border-bottom: 0; }
.tag { display: inline-block; padding: 2px 8px; border-radius: 999px; background: var(--field); color: var(--muted); font-size: 11px; }
.tag.active { background: color-mix(in srgb, var(--success) 18%, transparent); color: var(--success); }
.log-toolbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 10px; }
.log-toolbar label { color: var(--muted); font-size: 12px; }
.log-box {
  height: calc(100vh - 250px); min-height: 320px; overflow: auto; background: #0f1319;
  border: 1px solid var(--border); border-radius: 12px; padding: 12px;
  font: 12.5px/1.55 Consolas, "Courier New", monospace; color: #cbd5e1;
  scroll-behavior: smooth;
}
.log-line { white-space: pre-wrap; word-break: break-word; }
.log-debug { color: #7c8798; }
.log-info { color: #7fb0ff; }
.log-warn { color: #f0b45a; }
.log-error { color: #ff7b7b; }
.hint { color: var(--muted); font-size: 12px; }
.problems { color: var(--warn); font-size: 12px; white-space: pre-line; margin-top: 8px; }
.banner {
  display: none; border: 1px solid var(--warn); background: color-mix(in srgb, var(--warn) 12%, var(--card));
  border-radius: 12px; padding: 12px 14px; margin-bottom: 16px; font-size: 13px;
}
.banner.show { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.banner .spacer { flex: 1; }
.toast {
  position: fixed; top: 18px; right: 18px; z-index: 60; display: grid; gap: 8px;
  max-width: min(420px, calc(100vw - 36px));
}
.toast div {
  background: var(--card); border: 1px solid var(--border); border-left: 4px solid var(--accent);
  border-radius: 10px; padding: 10px 14px; box-shadow: var(--shadow); font-size: 13px;
  animation: slide .18s ease-out;
}
.toast div.ok { border-left-color: var(--success); }
.toast div.warn { border-left-color: var(--warn); }
.toast div.error { border-left-color: var(--danger); }
@keyframes slide { from { transform: translateY(-6px); opacity: 0; } }
dialog {
  border: 1px solid var(--border); border-radius: 14px; background: var(--card);
  color: var(--text); padding: 0; width: min(520px, calc(100vw - 32px)); box-shadow: var(--shadow);
}
dialog::backdrop { background: rgba(0, 0, 0, .42); }
.modal-head { display: flex; align-items: center; gap: 10px; padding: 16px 18px 0; }
.modal-head h3 { margin: 0; font-size: 16px; }
.modal-head .icon-btn { margin-left: auto; }
.modal-body { padding: 14px 18px; display: grid; gap: 10px; }
.modal-body label { color: var(--muted); font-size: 12px; }
.modal-body input, .modal-body select {
  width: 100%; background: var(--field); border: 1px solid var(--border);
  border-radius: 8px; padding: 9px 10px;
}
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; padding: 0 18px 16px; flex-wrap: wrap; }
.icon-btn { border: 0; background: transparent; color: var(--muted); cursor: pointer; font-size: 22px; line-height: 1; padding: 4px 8px; }
.ms-code { font: 700 28px/1.2 Consolas, monospace; letter-spacing: 4px; text-align: center; color: var(--accent); padding: 8px 0; }
.ms-link { font-family: Consolas, monospace; font-size: 12px; }
.list { display: grid; gap: 6px; }
.component { display: flex; gap: 8px; justify-content: space-between; font-size: 13px; padding: 7px 0; border-bottom: 1px solid var(--border); }
.component:last-child { border-bottom: 0; }
.component a { text-decoration: none; }
@media (max-width: 860px) {
  .app { display: block; }
  .sidebar { position: static; width: auto; height: auto; flex-direction: row; flex-wrap: wrap; align-items: center; }
  .brand { padding: 0 10px 0 4px; }
  .nav { flex-direction: row; flex-wrap: wrap; }
  .side-foot { margin: 0 0 0 auto; padding: 0; display: flex; gap: 8px; }
  .side-foot label { display: none; }
  .side-foot select { width: auto; }
  .main { padding: 16px; }
  .grid2 { grid-template-columns: 1fr; }
  .log-box { height: 55vh; }
}
</style>
</head>
<body>
<div class="app">
  <aside class="sidebar">
    <div class="brand">
      <strong>__APP__</strong>
      <span>v__VERSION__</span>
    </div>
    <nav class="nav" id="nav">
      <button data-page="dashboard" data-i18n="web.dashboard"></button>
      <button data-page="settings" data-i18n="web.settings"></button>
      <button data-page="accounts" data-i18n="web.accounts"></button>
      <button data-page="certificate" data-i18n="web.certificate"></button>
      <button data-page="logs" data-i18n="web.logs"></button>
      <button data-page="about" data-i18n="web.about"></button>
    </nav>
    <div class="side-foot">
      <div><label data-i18n="gui.label.theme"></label><select id="theme-select"></select></div>
      <div><label data-i18n="gui.language"></label><select id="language-select"></select></div>
      <button class="btn ghost" id="btn-logout" style="display:none" data-i18n="web.sign_out"></button>
    </div>
  </aside>

  <main class="main">
    <header class="header">
      <div>
        <h1 id="page-title"></h1>
        <p id="page-subtitle"></p>
      </div>
      <div class="header-actions">
        <span class="pill" id="status-pill"></span>
        <button class="btn ghost" id="btn-update" data-i18n="gui.update.button_check"></button>
      </div>
    </header>

    <div class="banner" id="update-banner">
      <span id="update-text"></span>
      <span class="spacer"></span>
      <a class="btn primary" id="update-link" target="_blank" rel="noreferrer" data-i18n="web.open_release"></a>
    </div>

    <section class="page" id="page-dashboard">
      <div class="card">
        <h2 data-i18n="web.service"></h2>
        <div class="endpoint">
          <code id="endpoint">—</code>
          <button class="btn primary" id="btn-copy-endpoint" data-i18n="gui.button.copy"></button>
        </div>
        <div class="actions">
          <button class="btn success" id="btn-start" data-i18n="gui.button.start"></button>
          <button class="btn danger" id="btn-stop" data-i18n="gui.button.stop"></button>
          <span class="spacer"></span>
          <span class="hint" id="service-hint"></span>
        </div>
      </div>

      <div class="card">
        <h2 data-i18n="web.session"></h2>
        <div class="stats">
          <div class="stat"><b id="stat-active">0</b><span data-i18n="gui.stat.active"></span></div>
          <div class="stat"><b id="stat-total">0</b><span data-i18n="gui.stat.total"></span></div>
          <div class="stat"><b id="stat-up">0 B</b><span data-i18n="gui.stat.up"></span></div>
          <div class="stat"><b id="stat-down">0 B</b><span data-i18n="gui.stat.down"></span></div>
          <div class="stat"><b id="stat-uptime">0:00</b><span data-i18n="gui.stat.uptime"></span></div>
        </div>
      </div>

      <div class="card">
        <h2 data-i18n="gui.section.connection"></h2>
        <div class="kv">
          <div><span data-i18n="web.target"></span><b id="status-target">—</b></div>
          <div><span data-i18n="web.listeners"></span><b id="listeners">—</b></div>
          <div><span data-i18n="web.webui_url"></span><b><a id="web-url" href="#" target="_blank" rel="noreferrer">—</a></b></div>
          <div><span data-i18n="web.webui"></span><b id="web-bind">—</b></div>
        </div>
      </div>
    </section>

    <section class="page" id="page-settings">
      <div class="card">
        <h2 data-i18n="gui.section.connection"></h2>
        <div class="grid2">
          <label data-i18n="gui.label.target"></label>
          <input id="target" autocomplete="off">
          <label data-i18n="gui.label.listen_host"></label>
          <input id="listen_host" autocomplete="off">
          <label data-i18n="gui.label.wss_port"></label>
          <input id="wss_port" inputmode="numeric">
          <label data-i18n="gui.label.ws_port"></label>
          <input id="ws_port" inputmode="numeric">
          <label for="use_srv" data-i18n="gui.label.use_srv"></label>
          <label class="switch"><input type="checkbox" id="use_srv"><span class="knob"></span></label>
          <div class="hint" data-i18n="gui.hint.endpoint"></div>
        </div>
      </div>

      <div class="card">
        <h2 data-i18n="gui.section.forwarding"></h2>
        <div class="grid2">
          <label data-i18n="gui.label.server_brand"></label>
          <input id="server_brand" autocomplete="off">
          <label data-i18n="gui.label.server_brand_version"></label>
          <input id="server_brand_version" autocomplete="off">
          <label data-i18n="gui.label.spoof_client"></label>
          <select id="spoof_client"></select>
          <label data-i18n="gui.label.spoof_brand"></label>
          <input id="spoof_brand" autocomplete="off">
          <div class="hint" data-i18n="gui.hint.spoof_brand"></div>
          <label data-i18n="gui.label.routes"></label>
          <textarea id="routes_text" spellcheck="false"></textarea>
          <div class="hint" data-i18n="gui.hint.routes"></div>
        </div>
      </div>

      <div class="card">
        <h2 data-i18n="gui.section.protocol"></h2>
        <div class="grid2">
          <label for="rewrite_handshake_host" data-i18n="gui.label.rewrite_host"></label>
          <label class="switch"><input type="checkbox" id="rewrite_handshake_host"><span class="knob"></span></label>
          <label for="eagler_translate" data-i18n="gui.label.eagler_translate"></label>
          <label class="switch"><input type="checkbox" id="eagler_translate"><span class="knob"></span></label>
          <label for="login_ack" data-i18n="gui.label.login_ack"></label>
          <label class="switch"><input type="checkbox" id="login_ack"><span class="knob"></span></label>
          <label data-i18n="gui.label.resource_pack_mode"></label>
          <select id="resource_pack_mode"></select>
          <label for="auto_exit" data-i18n="gui.label.auto_exit"></label>
          <label class="switch"><input type="checkbox" id="auto_exit"><span class="knob"></span></label>
        </div>
      </div>

      <div class="card">
        <h2 data-i18n="gui.section.runtime"></h2>
        <div class="grid2">
          <label data-i18n="gui.label.log_level"></label>
          <select id="log_level"></select>
          <label data-i18n="gui.label.heartbeat"></label>
          <input id="heartbeat_sec" inputmode="numeric">
          <label data-i18n="gui.label.connect_timeout"></label>
          <input id="connect_timeout" inputmode="decimal">
          <label data-i18n="gui.label.max_payload"></label>
          <input id="max_payload_mb" inputmode="numeric">
          <label for="status_cache" data-i18n="gui.label.status_cache"></label>
          <label class="switch"><input type="checkbox" id="status_cache"><span class="knob"></span></label>
          <label data-i18n="gui.label.status_cache_ttl"></label>
          <input id="status_cache_ttl" inputmode="numeric">
          <label for="update_check" data-i18n="gui.label.update_check"></label>
          <label class="switch"><input type="checkbox" id="update_check"><span class="knob"></span></label>
        </div>
      </div>

      <div class="card">
        <h2 data-i18n="gui.section.certificate"></h2>
        <div class="grid2">
          <label data-i18n="gui.label.cert_dir"></label>
          <input id="cert_dir" autocomplete="off">
          <label data-i18n="gui.label.cert_cn"></label>
          <input id="cert_common_name" autocomplete="off">
          <label data-i18n="gui.label.cert_extra"></label>
          <input id="cert_extra_names" autocomplete="off">
          <label data-i18n="gui.label.cert_days"></label>
          <input id="cert_days" inputmode="numeric">
          <label data-i18n="gui.label.cert_generator"></label>
          <select id="cert_generator"></select>
        </div>
      </div>

      <div class="card">
        <h2 data-i18n="gui.section.web"></h2>
        <div class="grid2">
          <label data-i18n="gui.label.web_host"></label>
          <input id="web_host" autocomplete="off">
          <label data-i18n="gui.label.web_port"></label>
          <input id="web_port" inputmode="numeric">
          <div class="hint" data-i18n="gui.hint.web_bind"></div>
        </div>
        <div class="actions" style="margin-top:12px">
          <button class="btn ghost" id="btn-web-restart" data-i18n="gui.button.web_restart"></button>
          <span class="hint" data-i18n="web.bind_hint"></span>
        </div>
      </div>

      <div class="card">
        <h2 data-i18n="web.access"></h2>
        <div class="grid2">
          <label for="auth-enabled" data-i18n="web.require_password"></label>
          <label class="switch"><input type="checkbox" id="auth-enabled"><span class="knob"></span></label>
          <label data-i18n="web.new_password"></label>
          <input id="auth-password" type="password" autocomplete="new-password">
          <label data-i18n="web.confirm_password"></label>
          <input id="auth-confirm" type="password" autocomplete="new-password">
          <div class="hint" data-i18n="web.password_hint"></div>
        </div>
        <div class="actions" style="margin-top:12px">
          <button class="btn primary" id="btn-save-auth" data-i18n="gui.button.save_config"></button>
          <span class="hint" id="auth-status"></span>
        </div>
      </div>

      <div class="card">
        <div class="actions">
          <button class="btn primary" id="btn-save" data-i18n="gui.button.save_config"></button>
          <button class="btn ghost" id="btn-reset" data-i18n="gui.button.reset_defaults"></button>
          <span class="spacer"></span>
          <span class="hint" id="config-status"></span>
        </div>
        <div class="problems" id="config-problems"></div>
      </div>
    </section>

    <section class="page" id="page-accounts">
      <div class="card">
        <h2 data-i18n="web.accounts"></h2>
        <div class="actions">
          <button class="btn primary" id="btn-add-offline" data-i18n="gui.accounts.add.offline"></button>
          <button class="btn ghost" id="btn-add-thirdparty" data-i18n="gui.accounts.add.thirdparty"></button>
          <button class="btn ghost" id="btn-add-microsoft" data-i18n="gui.accounts.add.microsoft"></button>
        </div>
        <div style="overflow:auto;margin-top:12px">
          <table>
            <thead><tr>
              <th></th>
              <th data-i18n="gui.accounts.col.name"></th>
              <th data-i18n="gui.accounts.col.kind"></th>
              <th data-i18n="gui.accounts.col.uuid"></th>
              <th></th>
            </tr></thead>
            <tbody id="accounts-body"></tbody>
          </table>
        </div>
        <p class="hint" data-i18n="gui.accounts.hint"></p>
      </div>
    </section>

    <section class="page" id="page-certificate">
      <div class="card">
        <h2 data-i18n="gui.section.certificate"></h2>
        <div class="kv" id="cert-info"></div>
        <div class="actions" style="margin-top:14px">
          <button class="btn primary" id="btn-generate-cert" data-i18n="gui.button.regen_cert"></button>
          <button class="btn ghost" id="btn-install-cert" data-i18n="gui.button.install_cert"></button>
        </div>
        <p class="hint" data-i18n="gui.cert.hint"></p>
      </div>
      <div class="card">
        <h2 data-i18n="gui.label.cert_generator"></h2>
        <div class="grid2">
          <label data-i18n="gui.label.cert_cn"></label>
          <input id="cert_cn_page" autocomplete="off">
          <label data-i18n="gui.label.cert_extra"></label>
          <input id="cert_extra_page" autocomplete="off">
          <label data-i18n="gui.label.cert_days"></label>
          <input id="cert_days_page" inputmode="numeric">
          <label data-i18n="gui.label.cert_generator"></label>
          <select id="cert_generator_page"></select>
        </div>
      </div>
    </section>

    <section class="page" id="page-logs">
      <div class="card">
        <div class="log-toolbar">
          <button class="btn ghost" id="btn-clear-log" data-i18n="gui.log.clear"></button>
          <label><input type="checkbox" id="log-autoscroll" checked> <span data-i18n="gui.log.auto_scroll"></span></label>
          <label for="log-level" data-i18n="gui.label.log_level"></label>
          <select id="log-level" class="field" style="width:auto"></select>
          <span class="hint" data-i18n="gui.log.hint"></span>
        </div>
        <div class="log-box" id="log-box"></div>
      </div>
    </section>

    <section class="page" id="page-about">
      <div class="card">
        <h2 id="about-title"></h2>
        <p id="about-blurb"></p>
        <p class="hint" id="about-license"></p>
      </div>
      <div class="card">
        <h2 data-i18n="gui.about.components"></h2>
        <div class="list" id="about-components"></div>
        <p class="hint" data-i18n="gui.about.hint"></p>
      </div>
    </section>
  </main>
</div>

<div class="toast" id="toast"></div>
<dialog id="modal"></dialog>

<script>
const I18N = __I18N__;
const state = {
  config: null, status: null, accounts: [], logSeq: 0, language: '__LANG__',
  theme: '__THEME__', update: null, page: 'dashboard',
  auth: { enabled: false, has_password: false }
};

function t(key, vars) {
  let text = I18N[key] || key;
  if (vars) {
    text = text.replace(/%\((\w+)\)s/g, (m, k) => (k in vars ? vars[k] : m))
               .replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m));
  }
  return text;
}
function $(sel) { return document.querySelector(sel); }
function $$(sel) { return Array.from(document.querySelectorAll(sel)); }
function esc(value) {
  return String(value == null ? '' : value).replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  })[ch]);
}
function fmt(value, fallback) { return value == null || value === '' ? (fallback || '—') : value; }

async function api(path, options) {
  options = options || {};
  const init = { method: options.method || 'GET', headers: {} };
  if (options.body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = typeof options.body === 'string' ? options.body : JSON.stringify(options.body);
  }
  const response = await fetch(path, init);
  let data = null;
  try { data = await response.json(); } catch (err) { data = null; }
  if (response.status === 401 && data && data.login) {
    location.href = '/login';
    throw new Error(data.error || 'HTTP 401');
  }
  if (!response.ok || (data && data.ok === false)) {
    throw new Error((data && data.error) || response.statusText || ('HTTP ' + response.status));
  }
  return data || {};
}

function toast(message, kind, timeout) {
  const box = $('#toast');
  const item = document.createElement('div');
  item.className = kind || '';
  item.textContent = message;
  box.appendChild(item);
  setTimeout(() => item.remove(), timeout || 4200);
}

function applyI18n() {
  $$('[data-i18n]').forEach(el => { el.textContent = t(el.dataset.i18n); });
  $$('[data-i18n-placeholder]').forEach(el => { el.placeholder = t(el.dataset.i18nPlaceholder); });
  document.title = t('core.app_name') + ' · ' + t('web.subtitle');
}

function fillSelect(selector, options, selected) {
  const select = $(selector);
  if (!select) return;
  select.innerHTML = '';
  (options || []).forEach(option => {
    const item = document.createElement('option');
    item.value = option.code !== undefined ? option.code : option;
    item.textContent = option.label !== undefined ? option.label : option;
    select.appendChild(item);
  });
  if (selected !== undefined && selected !== null) select.value = String(selected);
}

function setPage(name) {
  const pages = ['dashboard', 'settings', 'accounts', 'certificate', 'logs', 'about'];
  if (!pages.includes(name)) name = 'dashboard';
  state.page = name;
  $$('.nav button').forEach(btn => btn.classList.toggle('active', btn.dataset.page === name));
  pages.forEach(page => $('#page-' + page).classList.toggle('active', page === name));
  const titles = {
    dashboard: ['web.dashboard', 'gui.page.control.subtitle'],
    settings: ['web.settings', 'gui.page.settings.subtitle'],
    accounts: ['web.accounts', 'gui.page.accounts.subtitle'],
    certificate: ['web.certificate', 'gui.page.cert.subtitle'],
    logs: ['web.logs', 'gui.page.log.subtitle'],
    about: ['web.about', 'gui.page.about.subtitle']
  };
  $('#page-title').textContent = t(titles[name][0]);
  $('#page-subtitle').textContent = t(titles[name][1]);
  if (history.replaceState) history.replaceState(null, '', '#' + name);
  if (name === 'accounts') loadAccounts();
  if (name === 'certificate') loadCert();
  if (name === 'about') loadAbout();
}

/* ---------- status ---------- */
function renderStatus(data) {
  state.status = data;
  const pill = $('#status-pill');
  const map = {
    stopped: ['gui.status.stopped', ''], starting: ['gui.status.starting', 'starting'],
    running: ['gui.status.running', 'running'], stopping: ['gui.status.stopping', 'stopping'],
    error: ['gui.status.start_failed', 'error']
  };
  const entry = map[data.state] || map.stopped;
  pill.textContent = t(entry[0]);
  pill.className = 'pill ' + entry[1];
  const busy = ['starting', 'running', 'stopping'].includes(data.state);
  $('#btn-start').disabled = busy;
  $('#btn-stop').disabled = !['starting', 'running'].includes(data.state);
  $('#service-hint').textContent = data.error || '';
  const stats = data.stats || {};
  $('#stat-active').textContent = fmt(stats.active, '0');
  $('#stat-total').textContent = fmt(stats.total, '0');
  $('#stat-up').textContent = fmt(stats.bytes_to_server_human, '0 B');
  $('#stat-down').textContent = fmt(stats.bytes_to_client_human, '0 B');
  $('#stat-uptime').textContent = fmt(stats.uptime_human, '0:00');
  $('#endpoint').textContent = data.endpoint || '—';
  $('#status-target').textContent = data.target || '—';
  $('#listeners').textContent = (data.listeners || []).join('  ·  ') || '—';
  const web = data.web || {};
  if (web.url) {
    $('#web-url').textContent = web.url;
    $('#web-url').href = web.url;
  }
  $('#web-bind').textContent = (web.host || '') + ':' + (web.port || '');
  if (data.auth) {
    state.auth = data.auth;
    updateAuthVisibility();
  }
}

async function loadStatus() {
  try {
    renderStatus(await api('/api/status'));
  } catch (err) {
    $('#status-pill').textContent = t('gui.status.start_failed');
    $('#status-pill').className = 'pill error';
    $('#service-hint').textContent = t('web.connection_failed', { error: err.message });
  }
}

/* ---------- configuration ---------- */
function routesToText(routes) {
  return Object.entries(routes || {}).map(([path, target]) => path + '=' + target).join('\n');
}

function renderConfig(data) {
  state.config = data.config;
  const config = data.config;
  const options = data.options || {};
  fillSelect('#spoof_client', options.spoof_clients, config.spoof_client);
  fillSelect('#resource_pack_mode', options.resource_pack_modes, config.resource_pack_mode);
  fillSelect('#log_level', options.log_levels, config.log_level);
  const logFilter = $('#log-level');
  fillSelect('#log-level', [{ code: 'all', label: t('web.all_levels') }]
    .concat(options.log_levels || []), logFilter.value || 'all');
  fillSelect('#cert_generator', options.cert_generators, config.cert_generator);
  fillSelect('#cert_generator_page', options.cert_generators, config.cert_generator);
  fillSelect('#theme-select', options.themes, config.theme);
  fillSelect('#language-select', options.languages, config.language);
  state.theme = config.theme;
  state.language = config.language;
  document.documentElement.dataset.theme = config.theme;
  const fields = ['target', 'listen_host', 'wss_port', 'ws_port', 'server_brand',
    'server_brand_version', 'spoof_brand', 'log_level', 'heartbeat_sec',
    'connect_timeout', 'max_payload_mb', 'status_cache_ttl', 'cert_dir',
    'cert_common_name', 'cert_extra_names', 'cert_days', 'cert_generator',
    'web_host', 'web_port'];
  fields.forEach(id => { const el = $('#' + id); if (el) el.value = config[id] ?? ''; });
  $('#routes_text').value = routesToText(config.routes);
  ['use_srv', 'rewrite_handshake_host', 'eagler_translate', 'login_ack',
   'auto_exit', 'status_cache', 'update_check'].forEach(id => {
    const el = $('#' + id); if (el) el.checked = !!config[id];
  });
  $('#cert_cn_page').value = config.cert_common_name || '';
  $('#cert_extra_page').value = (config.cert_extra_names || []).join(', ');
  $('#cert_days_page').value = config.cert_days || 3650;
  renderProblems(data.problems || []);
  if (data.auth) renderAuth(data.auth);
}

function renderAuth(auth) {
  state.auth = auth || { enabled: false, has_password: false };
  $('#auth-enabled').checked = !!state.auth.enabled;
  $('#auth-password').value = '';
  $('#auth-confirm').value = '';
  updateAuthVisibility();
}

function updateAuthVisibility() {
  const enabled = !!(state.auth && state.auth.enabled);
  $('#btn-logout').style.display = enabled ? '' : 'none';
  const status = $('#auth-status');
  if (status) {
    status.textContent = state.auth && state.auth.has_password
      ? t('web.password_set') : t('web.password_unset');
  }
}

async function saveAuth() {
  const enabled = $('#auth-enabled').checked;
  const password = $('#auth-password').value;
  const confirm = $('#auth-confirm').value;
  if (enabled && password !== confirm) {
    toast(t('web.password_mismatch'), 'error');
    return;
  }
  if (enabled && !password && !(state.auth && state.auth.has_password)) {
    toast(t('web.password_required'), 'error');
    return;
  }
  if (enabled && password && password.length < 4) {
    toast(t('web.password_short'), 'error');
    return;
  }
  try {
    const data = await api('/api/auth', { method: 'POST', body: { enabled, password } });
    renderAuth(data.auth);
    if (data.reauth) {
      toast(t('web.password_saved'), 'ok');
      setTimeout(() => {
        const next = location.pathname + location.hash;
        location.href = '/login?next=' + encodeURIComponent(next);
      }, 700);
      return;
    }
    toast(enabled ? t('web.password_saved') : t('web.saved'), 'ok');
  } catch (err) {
    toast(err.message, 'error', 6000);
  }
}

async function signOut() {
  try {
    await api('/api/logout', { method: 'POST', body: {} });
  } catch (err) { /* the session may already be gone */ }
  location.href = '/login';
}

function renderProblems(problems) {
  const box = $('#config-problems');
  box.textContent = (problems || []).join('\n');
}

function numberValue(id, label, integer) {
  const raw = ($('#' + id).value || '').trim();
  const value = Number(raw);
  if (raw === '' || !Number.isFinite(value) || (integer && !Number.isInteger(value))) {
    throw new Error(t('web.invalid_number', { field: label }));
  }
  return value;
}

function collectConfig() {
  const config = {};
  ['target', 'listen_host', 'server_brand', 'server_brand_version', 'spoof_brand',
   'cert_dir', 'cert_common_name', 'web_host'].forEach(id => {
    config[id] = ($('#' + id).value || '').trim();
  });
  config.wss_port = numberValue('wss_port', t('gui.label.wss_port'), true);
  config.ws_port = numberValue('ws_port', t('gui.label.ws_port'), true);
  config.web_port = numberValue('web_port', t('gui.label.web_port'), true);
  config.heartbeat_sec = numberValue('heartbeat_sec', t('gui.label.heartbeat'), true);
  config.connect_timeout = numberValue('connect_timeout', t('gui.label.connect_timeout'), false);
  config.max_payload_mb = numberValue('max_payload_mb', t('gui.label.max_payload'), true);
  config.status_cache_ttl = numberValue('status_cache_ttl', t('gui.label.status_cache_ttl'), true);
  config.cert_days = numberValue('cert_days', t('gui.label.cert_days'), true);
  config.routes_text = $('#routes_text').value;
  config.cert_extra_names = $('#cert_extra_names').value;
  config.spoof_client = $('#spoof_client').value;
  config.resource_pack_mode = $('#resource_pack_mode').value;
  config.log_level = $('#log_level').value;
  config.cert_generator = $('#cert_generator').value;
  config.theme = $('#theme-select').value;
  config.language = $('#language-select').value;
  ['use_srv', 'rewrite_handshake_host', 'eagler_translate', 'login_ack',
   'auto_exit', 'status_cache', 'update_check'].forEach(id => {
    config[id] = $('#' + id).checked;
  });
  return config;
}

async function loadConfig() {
  try {
    renderConfig(await api('/api/config'));
  } catch (err) {
    toast(err.message, 'error');
  }
}

async function saveConfig(silent) {
  const config = collectConfig();
  const data = await api('/api/config', { method: 'POST', body: config });
  state.config = data.config;
  renderProblems(data.problems || []);
  if (!silent) toast(t('web.saved'), 'ok');
  if (data.language_changed) {
    toast(t('web.language_reload'), 'warn');
    setTimeout(() => location.reload(), 600);
    return data;
  }
  if (data.web_restart) {
    toast(t('web.webui_restarting', { url: data.web_url }), 'warn', 9000);
  }
  return data;
}

/* ---------- service ---------- */
async function startService() {
  try {
    await saveConfig(true);
    await api('/api/service/start', { method: 'POST', body: {} });
    toast(t('web.started'), 'ok');
    loadStatus();
  } catch (err) {
    toast(t('web.start_failed', { error: err.message }), 'error', 7000);
  }
}
async function stopService() {
  try {
    await api('/api/service/stop', { method: 'POST', body: {} });
    toast(t('web.stopped'), 'ok');
    loadStatus();
  } catch (err) {
    toast(t('web.stop_failed', { error: err.message }), 'error');
  }
}

/* ---------- logs ---------- */
async function loadLogs() {
  if (state.page !== 'logs') return;
  try {
    const level = $('#log-level').value || 'all';
    const data = await api('/api/logs?since=' + state.logSeq + '&level=' + encodeURIComponent(level));
    state.logSeq = data.seq;
    appendLogs(data.lines || []);
  } catch (err) { /* polling errors are transient */ }
}
function appendLogs(lines) {
  if (!lines.length) return;
  const box = $('#log-box');
  const frag = document.createDocumentFragment();
  lines.forEach(line => {
    const item = document.createElement('div');
    item.className = 'log-line log-' + (line.level || 'info');
    item.textContent = line.text || '';
    frag.appendChild(item);
  });
  box.appendChild(frag);
  while (box.childElementCount > 2500) box.firstElementChild.remove();
  if ($('#log-autoscroll').checked) box.scrollTop = box.scrollHeight;
}
async function clearLogs() {
  try {
    await api('/api/logs/clear', { method: 'POST', body: {} });
    $('#log-box').innerHTML = '';
    state.logSeq = 0;
    toast(t('web.log_cleared'), 'ok');
  } catch (err) { toast(err.message, 'error'); }
}

/* ---------- accounts ---------- */
async function loadAccounts() {
  try {
    const data = await api('/api/accounts');
    state.accounts = data.accounts || [];
    renderAccounts();
  } catch (err) { toast(err.message, 'error'); }
}
function renderAccounts() {
  const body = $('#accounts-body');
  body.innerHTML = '';
  if (!state.accounts.length) {
    const row = document.createElement('tr');
    const cell = document.createElement('td');
    cell.colSpan = 5;
    cell.className = 'hint';
    cell.textContent = t('web.accounts_empty');
    row.appendChild(cell);
    body.appendChild(row);
    return;
  }
  state.accounts.forEach(account => {
    const row = document.createElement('tr');
    const mark = document.createElement('td');
    mark.textContent = account.active ? '●' : '○';
    mark.style.color = account.active ? 'var(--success)' : 'var(--muted)';
    row.appendChild(mark);
    const name = document.createElement('td');
    name.textContent = account.username || '?';
    row.appendChild(name);
    const kind = document.createElement('td');
    const tag = document.createElement('span');
    tag.className = 'tag' + (account.active ? ' active' : '');
    tag.textContent = t('accounts.kind.' + account.kind);
    kind.appendChild(tag);
    row.appendChild(kind);
    const uuid = document.createElement('td');
    uuid.textContent = account.uuid ? account.uuid.slice(0, 8) + '…' : '—';
    uuid.style.fontFamily = 'Consolas, monospace';
    row.appendChild(uuid);
    const actions = document.createElement('td');
    actions.style.whiteSpace = 'nowrap';
    if (!account.active) {
      const activeBtn = document.createElement('button');
      activeBtn.className = 'btn ghost';
      activeBtn.textContent = t('gui.accounts.button.active');
      activeBtn.addEventListener('click', () => setActive(account.id));
      actions.appendChild(activeBtn);
    }
    const removeBtn = document.createElement('button');
    removeBtn.className = 'btn ghost';
    removeBtn.style.color = 'var(--danger)';
    removeBtn.textContent = t('gui.accounts.button.remove');
    removeBtn.addEventListener('click', () => removeAccount(account));
    actions.appendChild(removeBtn);
    row.appendChild(actions);
    body.appendChild(row);
  });
}
async function setActive(id) {
  try {
    await api('/api/accounts/' + encodeURIComponent(id) + '/active', { method: 'POST', body: {} });
    toast(t('web.account_active'), 'ok');
    loadAccounts();
  } catch (err) { toast(err.message, 'error'); }
}
async function removeAccount(account) {
  if (!confirm(t('web.confirm_remove', { name: account.username }))) return;
  try {
    await api('/api/accounts/' + encodeURIComponent(account.id), { method: 'DELETE' });
    toast(t('web.account_removed'), 'ok');
    loadAccounts();
  } catch (err) { toast(err.message, 'error'); }
}

function modal(title, bodyHtml, buttons) {
  const dialog = $('#modal');
  dialog.innerHTML = '<div class="modal-head"><h3></h3><button type="button" class="icon-btn" data-close>×</button></div>'
    + '<div class="modal-body"></div><div class="modal-actions"></div>';
  dialog.querySelector('h3').textContent = title;
  dialog.querySelector('.modal-body').innerHTML = bodyHtml;
  const actions = dialog.querySelector('.modal-actions');
  (buttons || []).forEach(button => {
    const element = document.createElement('button');
    element.type = 'button';
    element.className = 'btn ' + (button.kind || 'ghost');
    element.textContent = button.label;
    element.addEventListener('click', () => button.onClick(dialog));
    actions.appendChild(element);
  });
  dialog.querySelector('[data-close]').addEventListener('click', () => dialog.close());
  dialog.showModal();
  return dialog;
}

function addOffline() {
  const dialog = modal(t('gui.accounts.add.offline'),
    '<label>' + esc(t('web.offline_prompt')) + '</label><input id="offline-name" autocomplete="off">',
    [
      { label: t('gui.accounts.add.offline'), kind: 'primary', onClick: async (dlg) => {
          const name = dlg.querySelector('#offline-name').value.trim();
          try {
            await api('/api/accounts/offline', { method: 'POST', body: { username: name } });
            dlg.close(); toast(t('web.account_added'), 'ok'); loadAccounts();
          } catch (err) { toast(err.message, 'error'); }
        } },
      { label: t('gui.settings.close'), onClick: dlg => dlg.close() }
    ]);
  setTimeout(() => dialog.querySelector('#offline-name').focus(), 50);
}

function addThirdParty() {
  modal(t('gui.accounts.thirdparty.title'),
    '<label>' + esc(t('gui.accounts.thirdparty.server')) + '</label><input id="tp-server" placeholder="https://example.com" autocomplete="off">'
    + '<label>' + esc(t('gui.accounts.thirdparty.username')) + '</label><input id="tp-user" autocomplete="off">'
    + '<label>' + esc(t('gui.accounts.thirdparty.password')) + '</label><input id="tp-pass" type="password">'
    + '<p class="hint">' + esc(t('gui.accounts.thirdparty.note')) + '</p>',
    [
      { label: t('gui.accounts.thirdparty.submit'), kind: 'primary', onClick: async (dlg) => {
          const body = {
            server: dlg.querySelector('#tp-server').value.trim(),
            username: dlg.querySelector('#tp-user').value.trim(),
            password: dlg.querySelector('#tp-pass').value
          };
          if (!body.server || !body.username || !body.password) {
            toast(t('gui.accounts.thirdparty.missing'), 'error'); return;
          }
          const status = document.createElement('p');
          status.className = 'hint';
          status.textContent = t('gui.accounts.thirdparty.busy');
          dlg.querySelector('.modal-body').appendChild(status);
          try {
            await api('/api/accounts/thirdparty', { method: 'POST', body });
            dlg.close(); toast(t('web.account_added'), 'ok'); loadAccounts();
          } catch (err) { status.textContent = err.message; status.style.color = 'var(--danger)'; }
        } },
      { label: t('gui.settings.close'), onClick: dlg => dlg.close() }
    ]);
}

async function addMicrosoft(verify) {
  if (verify === undefined) verify = true;
  const dialog = modal(t('gui.accounts.ms.title'),
    '<p>' + esc(t('gui.accounts.ms.intro')) + '</p>'
    + '<div class="ms-code" id="ms-code">--------</div>'
    + '<input id="ms-link" class="ms-link" readonly>'
    + '<p class="hint" id="ms-status">' + esc(t('gui.accounts.ms.starting')) + '</p>',
    [
      { label: t('gui.accounts.ms.copy'), onClick: () => copyText($('#ms-code').textContent) },
      { label: t('gui.accounts.ms.open'), onClick: () => { const url = $('#ms-link').value; if (url) window.open(url, '_blank'); } },
      { label: t('gui.settings.close'), onClick: dlg => dlg.close() }
    ]);
  try {
    const start = await api('/api/accounts/microsoft/start', { method: 'POST', body: { verify } });
    $('#ms-code').textContent = start.user_code || '--------';
    $('#ms-link').value = start.verification_uri || '';
    $('#ms-status').textContent = t('web.ms_waiting') + ' ' + t('web.ms_verify_note');
    if (start.verification_uri) window.open(start.verification_uri, '_blank');
    pollMicrosoft(start.job, dialog, verify);
  } catch (err) {
    $('#ms-status').textContent = t('web.ms_failed', { error: err.message });
    $('#ms-status').style.color = 'var(--danger)';
  }
}

function pollMicrosoft(job, dialog, verify) {
  const timer = setInterval(async () => {
    if (!dialog.open) { clearInterval(timer); return; }
    try {
      const data = await api('/api/accounts/microsoft/' + encodeURIComponent(job));
      if (data.state === 'done') {
        clearInterval(timer);
        dialog.close();
        toast(t('web.ms_done', { name: data.account.username }), 'ok');
        loadAccounts();
      } else if (data.state === 'error') {
        clearInterval(timer);
        const status = dialog.querySelector('#ms-status');
        status.textContent = t('web.ms_failed', { error: data.error });
        status.style.color = 'var(--danger)';
        if (data.code === 'ssl' && verify) {
          const retry = document.createElement('button');
          retry.className = 'btn primary';
          retry.textContent = t('web.ms_retry_ssl');
          retry.addEventListener('click', () => { dialog.close(); addMicrosoft(false); });
          dialog.querySelector('.modal-actions').prepend(retry);
        }
      }
    } catch (err) {
      clearInterval(timer);
    }
  }, 2000);
}

/* ---------- certificate ---------- */
async function loadCert() {
  try {
    const data = await api('/api/cert');
    const info = data.info;
    const box = $('#cert-info');
    box.innerHTML = '';
    if (!data.exists || !info) {
      box.innerHTML = '<div class="hint">' + esc(t('web.no_cert')) + '</div>';
      return;
    }
    const rows = [
      [t('web.cert_file'), data.cert_path],
      [t('web.valid_until'), info.not_after || '—'],
      [t('web.fingerprint'), info.thumbprint || '—'],
      [t('web.covers'), (info.alt_names || []).join(', ') || '—']
    ];
    rows.forEach(([key, value]) => {
      const row = document.createElement('div');
      const label = document.createElement('span');
      label.textContent = key;
      const text = document.createElement('b');
      text.textContent = value;
      row.append(label, text);
      box.appendChild(row);
    });
  } catch (err) { toast(err.message, 'error'); }
}
async function generateCert() {
  const body = {
    common_name: $('#cert_cn_page').value.trim(),
    extra_names: $('#cert_extra_page').value,
    days: Number($('#cert_days_page').value || 3650),
    generator: $('#cert_generator_page').value
  };
  try {
    await api('/api/cert/generate', { method: 'POST', body });
    toast(t('web.cert_generated'), 'ok');
    loadCert(); loadConfig();
  } catch (err) { toast(err.message, 'error', 7000); }
}
async function installCert() {
  try {
    await api('/api/cert/install', { method: 'POST', body: {} });
    toast(t('web.cert_installed'), 'ok');
  } catch (err) { toast(err.message, 'error', 7000); }
}

/* ---------- update / about ---------- */
async function checkUpdate() {
  const button = $('#btn-update');
  button.disabled = true;
  button.textContent = t('web.update_checking');
  try {
    const data = await api('/api/update');
    state.update = data.update;
    if (data.update.newer) {
      $('#update-text').textContent = t('web.update_available', {
        version: data.update.version, current: data.update.current
      });
      const link = $('#update-link');
      link.href = data.update.page || '#';
      link.style.display = data.update.page ? '' : 'none';
      $('#update-banner').classList.add('show');
    } else {
      toast(t('web.update_current', { version: data.update.current || '__VERSION__' }), 'ok');
    }
  } catch (err) {
    toast(t('web.update_failed', { error: err.message }), 'error', 7000);
  } finally {
    button.disabled = false;
    button.textContent = t('gui.update.button_check');
  }
}

async function loadAbout() {
  try {
    const data = await api('/api/about');
    $('#about-title').textContent = t('core.app_name') + '  v' + data.version;
    $('#about-blurb').textContent = data.blurb;
    $('#about-license').textContent = data.license;
    const list = $('#about-components');
    list.innerHTML = '';
    (data.components || []).forEach(component => {
      const row = document.createElement('div');
      row.className = 'component';
      const name = document.createElement('span');
      name.textContent = component.name + '  ·  ' + component.license;
      const link = document.createElement('a');
      link.href = component.url;
      link.target = '_blank';
      link.rel = 'noreferrer';
      link.textContent = '↗';
      row.append(name, link);
      list.appendChild(row);
    });
  } catch (err) { toast(err.message, 'error'); }
}

/* ---------- clipboard / theme / language ---------- */
async function copyText(text) {
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    toast(t('web.copy_done'), 'ok');
  } catch (err) {
    const area = document.createElement('textarea');
    area.value = text;
    document.body.appendChild(area);
    area.select();
    document.execCommand('copy');
    area.remove();
    toast(t('web.copy_done'), 'ok');
  }
}

async function savePreference(payload) {
  try {
    return await api('/api/ui/preferences', { method: 'POST', body: payload });
  } catch (err) {
    toast(err.message, 'error');
    return null;
  }
}

/* ---------- wiring ---------- */
function bindEvents() {
  $$('.nav button').forEach(button => {
    button.addEventListener('click', () => setPage(button.dataset.page));
  });
  $('#btn-start').addEventListener('click', startService);
  $('#btn-stop').addEventListener('click', stopService);
  $('#btn-save').addEventListener('click', async () => {
    try { await saveConfig(false); loadStatus(); }
    catch (err) { toast(t('web.save_failed', { error: err.message }), 'error', 7000); }
  });
  $('#btn-reset').addEventListener('click', async () => {
    if (!confirm(t('gui.dialog.reset.ask'))) return;
    try {
      const data = await api('/api/config', { method: 'POST', body: { reset: true } });
      const options = (await api('/api/config')).options;
      renderConfig({ config: data.config, options, problems: data.problems,
                     auth: data.auth });
      if (data.language_changed) {
        toast(t('web.language_reload'), 'warn');
        setTimeout(() => location.reload(), 600);
        return;
      }
      if (data.web_restart) {
        toast(t('web.webui_restarting', { url: data.web_url }), 'warn', 9000);
      }
      toast(t('web.saved'), 'ok');
    } catch (err) { toast(err.message, 'error'); }
  });
  $('#btn-save-auth').addEventListener('click', saveAuth);
  $('#btn-logout').addEventListener('click', signOut);
  $('#btn-web-restart').addEventListener('click', async () => {
    try {
      const data = await api('/api/web/restart', { method: 'POST', body: {} });
      toast(t('web.webui_restarting', { url: data.url }), 'warn', 9000);
    } catch (err) { toast(err.message, 'error'); }
  });
  $('#btn-copy-endpoint').addEventListener('click', () => copyText($('#endpoint').textContent));
  $('#btn-update').addEventListener('click', checkUpdate);
  $('#btn-clear-log').addEventListener('click', clearLogs);
  $('#log-level').addEventListener('change', () => {
    $('#log-box').innerHTML = '';
    state.logSeq = 0;
    loadLogs();
  });
  $('#btn-add-offline').addEventListener('click', addOffline);
  $('#btn-add-thirdparty').addEventListener('click', addThirdParty);
  $('#btn-add-microsoft').addEventListener('click', () => addMicrosoft(true));
  $('#btn-generate-cert').addEventListener('click', generateCert);
  $('#btn-install-cert').addEventListener('click', installCert);
  $('#theme-select').addEventListener('change', async event => {
    const theme = event.target.value;
    document.documentElement.dataset.theme = theme;
    state.theme = theme;
    const result = await savePreference({ theme });
    if (result) toast(t('web.theme_saved'), 'ok');
  });
  $('#language-select').addEventListener('change', async event => {
    const language = event.target.value;
    const result = await savePreference({ language });
    if (result && result.language_changed) {
      toast(t('web.language_reload'), 'warn');
      setTimeout(() => location.reload(), 500);
    }
  });
  window.addEventListener('hashchange', () => setPage(location.hash.slice(1) || 'dashboard'));
}

async function init() {
  applyI18n();
  bindEvents();
  setPage(location.hash.slice(1) || 'dashboard');
  await Promise.allSettled([loadConfig(), loadStatus(), loadAccounts(), loadCert()]);
  if (state.page === 'logs') loadLogs();
  setInterval(loadStatus, 1200);
  setInterval(loadLogs, 1000);
}

document.addEventListener('DOMContentLoaded', init);
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Login page (only shown when the access password is enabled)
# ---------------------------------------------------------------------------

LOGIN_HTML = r"""<!doctype html>
<html lang="__LANG__" data-theme="__THEME__">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ · __APP__</title>
<style>
:root {
  --bg: #eef1f6; --card: #ffffff; --field: #f4f6fa; --border: #d8dfe9;
  --text: #151c26; --muted: #5d6878; --accent: #2f6fed; --accent-hover: #2559c9;
  --danger: #d64545; --shadow: 0 10px 30px rgba(20, 30, 50, .10);
}
html[data-theme="dark"] {
  --bg: #0d1014; --card: #1a1f27; --field: #11151b; --border: #262d38;
  --text: #e9eef6; --muted: #8b95a7; --accent: #3b82f6; --accent-hover: #2f6fed;
  --danger: #ef5b5b; --shadow: 0 10px 30px rgba(0, 0, 0, .40);
}
@media (prefers-color-scheme: dark) {
  html[data-theme="system"] {
    --bg: #0d1014; --card: #1a1f27; --field: #11151b; --border: #262d38;
    --text: #e9eef6; --muted: #8b95a7; --accent: #3b82f6; --accent-hover: #2f6fed;
    --danger: #ef5b5b; --shadow: 0 10px 30px rgba(0, 0, 0, .40);
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 24px;
  background: var(--bg); color: var(--text);
  font: 15px/1.55 "Microsoft YaHei UI", "PingFang SC", "Noto Sans CJK SC", system-ui, sans-serif;
}
.card {
  width: min(400px, 100%); background: var(--card); border: 1px solid var(--border);
  border-radius: 16px; padding: 28px; box-shadow: var(--shadow);
}
h1 { margin: 0 0 4px; font-size: 22px; }
p.intro { margin: 0 0 20px; color: var(--muted); font-size: 13px; }
label { display: block; color: var(--muted); font-size: 12px; margin-bottom: 6px; }
input[type="password"] {
  width: 100%; background: var(--field); border: 1px solid var(--border);
  border-radius: 9px; padding: 11px 12px; font: inherit; color: inherit; outline: none;
}
input[type="password"]:focus { border-color: var(--accent); }
button {
  width: 100%; margin-top: 16px; border: 0; border-radius: 9px; padding: 11px 16px;
  background: var(--accent); color: #fff; font: inherit; font-weight: 600; cursor: pointer;
}
button:hover { background: var(--accent-hover); }
.error { color: var(--danger); font-size: 13px; margin-top: 12px; }
.error:empty { display: none; }
.brand { color: var(--muted); font-size: 12px; margin-top: 18px; text-align: center; }
</style>
</head>
<body>
<form class="card" method="post" action="/login">
  <h1>__TITLE__</h1>
  <p class="intro">__INTRO__</p>
  <label for="password">__PASSWORD__</label>
  <input id="password" name="password" type="password" autocomplete="current-password" autofocus required>
  <input type="hidden" name="next" value="__NEXT__">
  <button type="submit">__SUBMIT__</button>
  <div class="error">__ERROR__</div>
  <div class="brand">__APP__</div>
</form>
</body>
</html>
"""

