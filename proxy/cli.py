"""Command line mode (no GUI).

Suited to servers and scheduled tasks, and also used to smoke-test the GUI
build without a display:

    python main.py --no-gui
    python main.py --no-gui --target play.example.net --port 8443
    python main.py --check
"""

from __future__ import annotations

import argparse
import sys
import threading

from . import accounts, certs, resolver, update
from .config import Config, SPOOF_CLIENTS, parse_address
from .i18n import LANGUAGES, set_language, tr, tr_in
from .logger import Logger
from .proxy import ProxyServer
from .utils import config_dir, human_bytes
from .version import VERSION, app_name


def build_parser() -> argparse.ArgumentParser:
    # argparse resolves the text below while the parser is built, which happens
    # before the configured language is known, so --help and --version always
    # render in the default language.
    parser = argparse.ArgumentParser(
        prog='server-protocol-bridge',
        description=tr('core.cli.description', app=app_name(), version=VERSION))
    parser.add_argument('-c', '--config', help=tr('core.cli.config_help'))
    parser.add_argument('--no-gui', action='store_true', help=tr('core.cli.no_gui_help'))
    parser.add_argument('-t', '--target', help=tr('core.cli.target_help'))
    parser.add_argument('-l', '--listen', help=tr('core.cli.listen_help'))
    parser.add_argument('-p', '--port', type=int, help=tr('core.cli.port_help'))
    parser.add_argument('--ws-port', type=int, help=tr('core.cli.ws_port_help'))
    parser.add_argument('--no-srv', action='store_true', help=tr('core.cli.no_srv_help'))
    parser.add_argument('--rewrite-handshake-host', action='store_true',
                        help=tr('core.cli.rewrite_host_help'))
    parser.add_argument('--no-eagler-translate', action='store_true',
                        help=tr('core.cli.no_eagler_help'))
    parser.add_argument('--no-login-ack', action='store_true',
                        help=tr('core.cli.no_login_ack_help'))
    parser.add_argument('--account', help=tr('core.cli.account_help'))
    parser.add_argument('--server-brand', help=tr('core.cli.server_brand_help'))
    parser.add_argument('--server-version', help=tr('core.cli.server_version_help'))
    parser.add_argument('--spoof-client', choices=SPOOF_CLIENTS,
                        help=tr('core.cli.spoof_client_help'))
    parser.add_argument('--spoof-brand', help=tr('core.cli.spoof_brand_help'))
    parser.add_argument('--no-spoof-brand', action='store_true',
                        help=tr('core.cli.no_spoof_brand_help'))
    parser.add_argument('--cert-dir', help=tr('core.cli.cert_dir_help'))
    parser.add_argument('--regen-cert', action='store_true', help=tr('core.cli.regen_cert_help'))
    parser.add_argument('--install-cert', action='store_true', help=tr('core.cli.install_cert_help'))
    parser.add_argument('--check', action='store_true', help=tr('core.cli.check_help'))
    parser.add_argument('--selftest', action='store_true', help=tr('core.cli.selftest_help'))
    parser.add_argument('--check-update', action='store_true', help=tr('core.cli.check_update_help'))
    parser.add_argument('--no-update-check', action='store_true',
                        help=tr('core.cli.no_update_check_help'))
    parser.add_argument('--log-level', choices=('debug', 'info', 'warn', 'error'),
                        help=tr('core.cli.log_level_help'))
    parser.add_argument('--heartbeat', type=int, help=tr('core.cli.heartbeat_help'))
    parser.add_argument('--max-payload', type=int, help=tr('core.cli.max_payload_help'))
    parser.add_argument('--language', choices=LANGUAGES, help=tr('core.cli.language_help'))
    parser.add_argument('--version', action='version',
                        version=tr('core.cli.version_line', app=app_name(), version=VERSION))
    return parser


def apply_arguments(config: Config, args: argparse.Namespace) -> Config:
    if args.target:
        config.target = args.target
    if args.listen:
        config.listen_host = args.listen
    if args.port is not None:
        config.wss_port = args.port
    if args.ws_port is not None:
        config.ws_port = args.ws_port
    if args.no_srv:
        config.use_srv = False
    if args.rewrite_handshake_host:
        config.rewrite_handshake_host = True
    if args.no_eagler_translate:
        config.eagler_translate = False
    if args.no_login_ack:
        config.login_ack = False
    if args.account:
        # A per-run override only: the selection made in the account manager is
        # not touched (the attribute is deliberately not a config field, so it
        # never lands in config.json).
        config.account_override = args.account
    if args.server_brand:
        config.server_brand = args.server_brand
    if args.server_version is not None:
        config.server_brand_version = args.server_version
    if args.no_spoof_brand:
        config.spoof_client = 'off'
    elif args.spoof_client:
        config.spoof_client = args.spoof_client
    if args.spoof_brand is not None:
        config.spoof_brand = args.spoof_brand
    if args.cert_dir:
        config.cert_dir = args.cert_dir
    if args.log_level:
        config.log_level = args.log_level
    if args.heartbeat is not None:
        config.heartbeat_sec = args.heartbeat
    if args.max_payload is not None:
        config.max_payload_mb = args.max_payload
    if args.language:
        config.language = args.language
    if args.no_update_check:
        config.update_check = False
    return config


def run_check(config: Config, logger: Logger) -> int:
    """Check the configuration, the certificate and the target connectivity."""
    problems = config.validate()
    for problem in problems:
        logger.error(tr_in('en', 'core.cli.config_problem', problem=problem))
    logger.info(tr('core.cli.config_dir', path=config_dir()))
    logger.info(tr('core.cli.target_line', target=config.describe_target()))

    if config.tls_enabled:
        logger.info(tr('core.cli.checking_cert'))
        try:
            info = certs.ensure_certificate(
                config.resolved_cert_dir, common_name=config.cert_common_name,
                extra_names=config.cert_extra_names, days=int(config.cert_days),
                generator=config.cert_generator, regenerate=False, logger=logger)
            logger.info(tr('core.cli.cert_ok', path=info['cert_path']))
            logger.info(tr('core.cli.cert_thumbprint', thumbprint=info['thumbprint']))
            if info.get('alt_names'):
                logger.info(tr('core.cli.cert_alt_names', names=', '.join(info['alt_names'])))
            logger.warn(tr('core.cli.cert_trust_hint'))
        except Exception as exc:
            logger.error(tr('core.cli.cert_check_failed', error=exc))
            return 2

    try:
        host, port = parse_address(config.target)
        if not port:
            host, port = resolver.resolve_target(host, None, logger=logger, use_srv=config.use_srv)
    except ValueError as exc:
        logger.error(tr_in('en', 'core.config.target_invalid', error=exc))
        return 2
    logger.info(tr('core.cli.probing', host=host, port=port))
    ok, elapsed, message = resolver.probe(host, port)
    if ok:
        logger.info(tr('core.cli.probe_ok', ms='%.0f' % elapsed))
    else:
        logger.error(tr('core.cli.probe_failed', error=message))
    return 0 if (ok and not problems) else 1


def run_selftest(config: Config, logger: Logger) -> int:
    """Print an environment self-test.  The crypto handshake is the step to
    watch: it needs ``cryptography``, the dependency most easily missed when
    packaging."""
    import platform

    from . import crypto

    frozen = getattr(sys, 'frozen', False)
    logger.info(tr('core.cli.version_line', app=app_name(), version=VERSION))
    logger.info('Python: %s (%s)' % (platform.python_version(), platform.machine()))
    mode = tr('core.cli.run_mode_frozen') if frozen else tr('core.cli.run_mode_source')
    logger.info(tr('core.cli.run_mode', mode=mode))
    logger.info(tr('core.cli.config_dir', path=config_dir()))
    if crypto.available():
        logger.info(tr('core.cli.crypto_ok', backend=crypto.backend_name()))
    else:
        logger.error(tr('core.cli.crypto_missing'))
    try:
        import webview  # noqa: F401

        logger.info(tr('core.cli.gui_ok'))
    except Exception as exc:                       # the symptom seen when pywebview / the webview runtime is missing
        logger.error(tr('core.cli.gui_missing', error=exc))
    try:
        import difflib  # noqa: F401  # flask's click imports it lazily when formatting errors
        logger.info(tr('core.cli.difflib_ok'))
    except ImportError as exc:           # the symptom seen when difflib was dropped from the build
        logger.error(tr('core.cli.difflib_missing', error=exc))
    for problem in config.validate():
        logger.warn(tr_in('en', 'core.cli.config_problem', problem=problem))
    return 0 if crypto.available() else 1


def run_install_certificate(config: Config, logger: Logger, regenerate: bool) -> int:
    if regenerate:
        logger.info(tr('core.cli.regen_notice'))
    try:
        info = certs.ensure_certificate(
            config.resolved_cert_dir, common_name=config.cert_common_name,
            extra_names=config.cert_extra_names, days=int(config.cert_days),
            generator=config.cert_generator, regenerate=regenerate, logger=logger)
    except Exception as exc:
        logger.error(tr('core.cli.cert_generate_failed', error=exc))
        return 2
    ok, message = certs.install_to_trust_store(info['cert_path'], logger=logger)
    if not ok:
        logger.error(tr('core.cli.install_failed', error=message))
        return 1
    logger.info(tr('core.cli.install_done', url=config.wss_url()))
    return 0


def run_update_check(config: Config, logger: Logger) -> int:
    """Ask the update endpoint for the newest release and print the outcome.

    The endpoint is compiled into the program (proxy/update.py) and never read
    from the configuration: there is no option that points the check elsewhere.
    Exit codes: 0 = the running version is the newest one, 1 = a newer release
    exists, 2 = the check itself failed (offline, bad answer, ...).
    """
    try:
        result = update.check(update.DEFAULT_UPDATE_URL, VERSION)
    except update.UpdateError as exc:
        logger.error(tr('core.cli.update_failed', error=exc))
        return 2
    log_update_outcome(logger, result, announce_current=True)
    return 1 if result['newer'] else 0


def log_update_outcome(logger: Logger, outcome, announce_current: bool = False) -> None:
    """Log a finished version check.

    A newer release is worth a warning; being up to date, or a check that never
    reached the endpoint, is ordinary background noise.
    """
    if isinstance(outcome, update.UpdateError):
        logger.debug(tr('core.cli.update_failed', error=outcome))
    elif outcome['newer']:
        logger.warn(tr('core.cli.update_available', version=outcome['version'],
                       current=outcome['current']))
        if outcome.get('must_update'):
            logger.warn(tr('core.cli.update_required'))
            minimum = outcome.get('min_version') or ''
            if minimum:
                logger.warn(tr('core.cli.update_min_version', version=minimum))
        date = outcome.get('release_date') or ''
        if date:
            logger.info(tr('core.cli.update_release_date', date=date))
        size = outcome.get('file_size') or 0
        if size:
            logger.info(tr('core.cli.update_file_size', size=human_bytes(size)))
        notes = (outcome.get('notes') or '').strip()
        if notes:
            logger.info(tr('core.cli.update_notes_header'))
            for line in notes.splitlines():
                logger.info(line)
        page = (outcome.get('page') or '').strip()
        if page:
            logger.info(tr('core.cli.update_page', url=page))
        source = (outcome.get('source') or '').strip()
        if source:
            logger.info(tr('core.cli.update_source', url=source))
    elif announce_current:
        logger.info(tr('core.cli.update_latest', version=outcome['current']))
        source = (outcome.get('source') or '').strip()
        if source:
            logger.info(tr('core.cli.update_source', url=source))


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    config = apply_arguments(Config.load(args.config), args)
    # Everything below -- log lines, errors, --check output -- uses this language.
    set_language(config.language)
    logger = Logger(config.log_level)

    if args.check:
        return run_check(config, logger)
    if args.selftest:
        return run_selftest(config, logger)
    if args.install_cert:
        return run_install_certificate(config, logger, args.regen_cert)
    if args.check_update:
        return run_update_check(config, logger)

    if config.update_check:
        # Fire and forget: the answer only ever produces a log line, so it must
        # not delay the listeners coming up.
        update.check_async(update.DEFAULT_UPDATE_URL, VERSION,
                           callback=lambda outcome: log_update_outcome(logger, outcome))

    try:
        server = ProxyServer(config, logger)
        info = server.start()
    except Exception as exc:
        logger.error(tr('core.cli.start_failed', error=exc))
        return 1

    logger.info(tr('core.cli.wss_line', url=info.get('wss_url') or tr('core.cli.disabled')))
    for listener in info.get('listeners', []):
        if listener.startswith('ws://'):
            logger.info(tr('core.cli.fallback_ws_line', url=listener))
    logger.info(tr('core.cli.stop_hint'))

    stop_event = threading.Event()
    try:
        while not stop_event.wait(0.5):
            pass
    except KeyboardInterrupt:
        logger.info(tr('core.cli.ctrl_c'))
    finally:
        server.stop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
