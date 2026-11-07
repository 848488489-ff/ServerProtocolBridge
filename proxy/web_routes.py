"""HTTP handlers for the Web UI, split from web.py for size.

``register`` receives the Flask application and the ``fail`` error
helper and installs the routes on it.  The handler bodies are
copied verbatim out of create_app: they still close over ``app`` and
``fail`` exactly as before, and their ``@app.route`` decorators are
unchanged, so every endpoint keeps the same rule, methods and name.
"""

import json
import re
import threading
import time
import uuid
from . import (accounts, certs, config as config_module, eagler, mcp, third_party, update, webauth)
from .i18n import (LANGUAGES, get_language, tr)
from .gui_shell import update_window_title as _update_native_title
from .runtime import get_manager
from .utils import config_dir
from .version import VERSION
from .web_helpers import (_account_payload, _api_info, _cert_payload, _config_options, _i18n_payload, _jobs, _jobs_lock, _mcp_info, _ms_worker, _prune_jobs, _save_body, _schedule_web_restart, _web_info)
from .web_html import INDEX_HTML
from flask import (Response, jsonify, request, session)
def register(app, fail):
    """Install the Web UI routes on *app*."""
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
        data['mcp'] = _mcp_info()
        data['api'] = _api_info()
        data['loopback_bind'] = data['mcp']['loopback_bind']
        return jsonify(data)
    @app.route('/api/config', methods=['GET', 'POST'])
    def api_config():
        manager = get_manager()
        if request.method == 'GET':
            return jsonify({
                'ok': True,
                'revision': manager.revision,
                'config': manager.config.to_dict(),
                'options': _config_options(),
                'problems': manager.config.validate(),
                'web_problems': manager.config.validate_web(),
                'web': _web_info(),
                'auth': webauth.state(),
                'mcp': _mcp_info(),
                'api': _api_info(),
                'loopback_bind': webauth.is_loopback_host(manager.config.web_host),
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
            'revision': manager.revision,
            'config': config.to_dict(),
            'problems': config.validate(),
            'web': _web_info(),
            'web_restart': web_changed,
            'web_url': config.web_url(),
            'language_changed': language_changed,
            'auth': webauth.state(),
            'mcp': _mcp_info(),
            'api': _api_info(),
            'loopback_bind': webauth.is_loopback_host(config.web_host),
        })
    @app.route('/api/auth', methods=['GET', 'POST'])
    def api_auth():
        manager = get_manager()
        loopback_bind = webauth.is_loopback_host(manager.config.web_host)
        if request.method == 'GET':
            return jsonify({'ok': True, 'auth': webauth.state(),
                            'loopback_bind': loopback_bind,
                            'mcp': _mcp_info()})
        body = request.get_json(silent=True) or {}
        enabled = bool(body.get('enabled'))
        password = str(body.get('password') or '')
        # A password only constrains clients that can reach the listener over
        # the network.  With a loopback bind there are none, and pretending
        # otherwise adds a setting that can never do anything.
        if enabled and loopback_bind:
            return fail(tr('web.password_loopback_no_set'))
        was_enabled = webauth.is_enabled()
        password_changed = False
        try:
            if enabled:
                if password:
                    if len(password) < 4:
                        return fail(tr('web.password_short'))
                    webauth.set_password(password)
                    password_changed = True
                elif not webauth.has_password():
                    return fail(tr('web.password_required'))
                else:
                    # The field was left blank, which the form documents as "keep the
                    # current password".  Nothing was written before, so the switch
                    # could read "on" in the browser while the file still said
                    # otherwise; persist the switch either way.
                    webauth.enable()
            else:
                webauth.disable()
        except OSError:
            # The file exists but cannot be read or written.  Fail the request
            # instead of proceeding: the switch is already on in the browser and
            # would silently claim a password was set when the file still says
            # otherwise (this is what wiped a stored password before).
            return fail(tr('web.auth_unreadable'), status=503)
        # Enabling access control or changing the password must invalidate the
        # current browser session: otherwise the page that just set the
        # password keeps working and the password looks like it had no effect.
        reauth = enabled and (password_changed or not was_enabled)
        if reauth:
            session.clear()
        else:
            session['authenticated'] = True
        return jsonify({'ok': True, 'auth': webauth.state(), 'reauth': reauth,
                        'loopback': webauth.is_loopback(request.remote_addr or ''),
                        'loopback_bind': loopback_bind,
                        'mcp': _mcp_info(),
                        'password_changed': password_changed})
    @app.route('/api/mcp', methods=['GET', 'POST'])
    def api_mcp():
        manager = get_manager()
        loopback_bind = webauth.is_loopback_host(manager.config.web_host)
        if request.method == 'GET':
            return jsonify({'ok': True, 'mcp': _mcp_info()})
        body = request.get_json(silent=True) or {}
        if body.get('clear'):
            # Removing a key is always allowed, including on loopback: a key
            # left over from a previous LAN bind should not be stuck forever.
            try:
                webauth.clear_mcp_key()
            except OSError:
                return fail(tr('web.auth_unreadable'), status=503)
            return jsonify({'ok': True, 'mcp': _mcp_info()})
        key = str(body.get('key') or '')
        if not key:
            return fail(tr('web.mcp_key_required'))
        if len(key) < 8:
            return fail(tr('web.mcp_key_short'))
        if loopback_bind:
            return fail(tr('web.mcp_loopback_no_key'))
        try:
            webauth.set_mcp_key(key)
        except OSError:
            return fail(tr('web.auth_unreadable'), status=503)
        return jsonify({'ok': True, 'mcp': _mcp_info()})
    # ------------------------------------------------------------------
    # MCP (Model Context Protocol)
    # ------------------------------------------------------------------
    @app.route('/mcp', methods=['GET', 'POST', 'DELETE', 'OPTIONS'])
    def mcp_endpoint():
        if request.method == 'OPTIONS':
            return ('', 204, {'Allow': 'POST'})
        if request.method != 'POST':
            return ('', 405, {'Allow': 'POST'})
        if not mcp.authorized(request.remote_addr or '', request.headers):
            return jsonify(mcp.unauthorized_response()), 401
        payload = request.get_json(silent=True)
        if payload is None:
            return jsonify(mcp.handle_payload(None)), 200
        result = mcp.handle_payload(payload)
        if result is None:
            return ('', 202)
        return jsonify(result)
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
        # Appearance personalization: accept a partial dict and merge, so a
        # single control can update one field without wiping the others.
        appearance = body.get('appearance')
        if isinstance(appearance, dict):
            merged = dict(getattr(config, 'appearance', {}) or {})
            # Background image / blur / opacity were removed on request; drop any
            # stale values a previous config might still carry.
            for key in ('bgImage', 'bgBlur', 'bgOpacity'):
                merged.pop(key, None)
            for key, value in appearance.items():
                if key not in ('accent', 'bgColor', 'radius', 'density', 'preset', 'fontScale'):
                    continue
                if key in ('accent', 'bgColor'):
                    # accept #rgb / #rrggbb only, else drop the value
                    if not (isinstance(value, str) and re.fullmatch(r'#[0-9a-fA-F]{3}([0-9a-fA-F]{3})?', value)):
                        continue
                elif key in ('radius', 'fontScale'):
                    try:
                        value = max(0, min(100000, int(value)))
                    except (TypeError, ValueError):
                        continue
                elif key == 'density':
                    if value not in ('compact', 'comfortable', 'spacious'):
                        continue
                merged[key] = value
            config.appearance = merged
        manager.save_config(config)
        # The embedded pywebview window title is set once at startup from the
        # language at that time; a language change here must refresh it.
        if old_language != config.language:
            _update_native_title()
        return jsonify({'ok': True, 'theme': config.theme,
                        'language': config.language,
                        'appearance': config.appearance,
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
    @app.route('/api/logs/export')
    def api_logs_export():
        """Download the whole in-memory log as a plain-text attachment.

        The page only renders the newest 2500 lines, so exporting from the DOM
        would quietly truncate the buffer.  This route reads the full hub
        snapshot and honours the same level filter as the live view.
        """
        manager = get_manager()
        level = (request.args.get('level') or 'all').strip().lower()
        items = manager.hub.snapshot(0)
        if level != 'all':
            items = [item for item in items if item['level'] == level]
        text = '\n'.join(item['text'] for item in items)
        if text:
            text += '\n'
        stamp = time.strftime('%Y%m%d-%H%M%S')
        filename = 'server-protocol-bridge-%s.log' % stamp
        return Response(
            text, mimetype='text/plain',
            headers={'Content-Disposition': 'attachment; filename="%s"' % filename,
                     'Cache-Control': 'no-store'})
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
        name = eagler.usable_name(body.get('username'))
        if not name:
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
    @app.route('/api/accounts/none', methods=['POST'])
    def api_account_none():
        # "Use no account": keep every stored account but stop using one, so
        # clients send the names they request themselves again (the old
        # behaviour).  set_active('') clears the selection; the store already
        # accepts an empty active id.
        accounts.set_active('')
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
            'blurb': tr('gui.about.blurb', workdir=config_dir()),
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
