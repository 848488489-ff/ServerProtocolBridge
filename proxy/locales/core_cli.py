"""Auto-split locale fragment: core_cli.  Merged by the parent module."""

EN = {
    'core.cli.description': '%(app)s v%(version)s - turns an ordinary Minecraft '
                            'server into a local wss:// or ws:// endpoint',
    'core.cli.version_line': '%(app)s v%(version)s',
    'core.cli.config_help': 'Path to the config file (default: config.json in the user '
                            'configuration folder)',
    'core.cli.no_gui_help': 'Run in command line mode (this mode already is the CLI; '
                            'the flag exists for compatibility with main.py)',
    'core.cli.target_help': 'Forward target, e.g. play.example.net (resolved '
                            'via SRV) or 127.0.0.1:25565',
    'core.cli.listen_help': 'Listen address (default 127.0.0.1)',
    'core.cli.port_help': 'wss:// listen port (default 8443)',
    'core.cli.ws_port_help': 'ws:// (plaintext, fallback) listen port; 0 disables it',
    'core.cli.no_srv_help': 'Skip SRV lookups; use port 25565 when the target has none',
    'core.cli.rewrite_host_help': 'Rewrite the server address in the handshake to the '
                                  'target domain (for servers that validate or route by address)',
    'core.cli.no_eagler_help': 'Disable WebSocket client protocol translation; '
                               'forward raw bytes only',
    'core.cli.no_login_ack_help': 'Disable the 1.20.2+ login acknowledge sent to the target '
                                  'server on the client\'s behalf',
    'core.cli.max_connections_help': 'Maximum simultaneous client connections; 0 = unlimited',
    'core.cli.account_help': 'Use this account (name or id from the account list) for this '
                             'run instead of the selected one',
    'core.cli.server_brand_help': 'Server brand shown to WebSocket clients '
                                  '(default ServerProtocolBridge)',
    'core.cli.server_version_help': 'Server version shown to WebSocket clients '
                                    '(empty = program version)',
    'core.cli.spoof_client_help': 'Client identity to imitate at the target server (pick the '
                                  'target server\'s Minecraft era): off / vanilla / forge-1.8 / '
                                  'forge-1.13 / neoforge / fabric (default forge-1.8; on 1.8 '
                                  'connections forge-1.8 also reproduces the legacy FML fingerprints)',
    'core.cli.spoof_brand_help': 'Client brand (MC|Brand) sent to the target server; empty = the '
                                 'preset default, e.g. fml,forge for Forge 1.8.x and forge for 1.13+',
    'core.cli.no_spoof_brand_help': 'Send no client identity at all (same as --spoof-client off)',
    'core.cli.cert_dir_help': 'Certificate directory (default certs)',
    'core.cli.regen_cert_help': 'Regenerate the certificate',
    'core.cli.install_cert_help': 'Import the certificate into the system trust store, then exit',
    'core.cli.check_help': 'Check the certificate and the connectivity to the target '
                           'server, then exit',
    'core.cli.selftest_help': 'Print an environment self-test (crypto backend / GUI / config); '
                              'use it after packaging to confirm every dependency is present',
    'core.cli.log_level_help': 'Log level',
    'core.cli.heartbeat_help': 'WebSocket heartbeat interval in seconds; 0 disables it',
    'core.cli.max_payload_help': 'Max size of a single frame (MB)',
    'core.cli.language_help': 'UI language: auto (follow the system) or en (English)',
    'core.cli.check_update_help': 'Ask the cloud endpoint for the newest release, print the '
                                  'result and exit (exit code 1 = a newer release exists)',
    'core.cli.no_update_check_help': 'Do not check for a newer release on startup',
    'core.cli.config_problem': 'Configuration: %(problem)s',
    'core.cli.config_dir': 'Configuration directory: %(path)s',
    'core.cli.target_line': 'Forward target: %(target)s',
    'core.cli.checking_cert': 'Checking the certificate ...',
    'core.cli.cert_ok': 'Certificate is usable: %(path)s',
    'core.cli.cert_thumbprint': 'SHA-256 fingerprint: %(thumbprint)s',
    'core.cli.cert_alt_names': 'Covered names: %(names)s',
    'core.cli.cert_trust_hint': 'If the browser still reports the certificate as untrusted, '
                                'run --install-cert and restart the browser.',
    'core.cli.cert_check_failed': 'Certificate check failed: %(error)s',
    'core.cli.probing': 'Testing connectivity to %(host)s:%(port)d ...',
    'core.cli.probe_ok': 'Target server reachable, handshake took %(ms)s ms',
    'core.cli.probe_failed': 'Target server unreachable: %(error)s',
    'core.cli.run_mode': 'Running from: %(mode)s',
    'core.cli.run_mode_frozen': 'packaged build',
    'core.cli.run_mode_source': 'source code',
    'core.cli.crypto_ok': 'Encryption handshake: available (backend %(backend)s) -- the proxy '
                          'can perform it when the target server requires it',
    'core.cli.crypto_missing': 'Encryption handshake: unavailable -- cryptography is required '
                               '(pip install cryptography)',
    'core.cli.gui_ok': 'GUI: available (embedded webview)',
    'core.cli.gui_missing': 'GUI: unavailable (%(error)s); the Web UI will open in the browser',
    'core.cli.difflib_ok': 'difflib: bundled (flask error formatting needs it)',
    'core.cli.difflib_missing': 'difflib: missing from this build (%(error)s)',
    'core.cli.regen_notice': 'Re-issuing the certificate ...',
    'core.cli.cert_generate_failed': 'Certificate generation failed: %(error)s',
    'core.cli.install_failed': 'Import failed: %(error)s',
    'core.cli.install_done': 'Done. Restart the browser, then use %(url)s',
    'core.cli.start_failed': 'Startup failed: %(error)s',
    'core.cli.wss_line': 'wss address: %(url)s',
    'core.cli.disabled': '(disabled)',
    'core.cli.fallback_ws_line': 'Fallback plaintext address: %(url)s',
    'core.cli.stop_hint': 'Press Ctrl+C to stop the service',
    'core.cli.ctrl_c': 'Received Ctrl+C, stopping ...',
    'core.cli.update_failed': 'Version check failed: %(error)s',
    'core.cli.update_available': 'A newer release is available: %(version)s (running %(current)s)',
    'core.cli.update_required': 'This update is required -- please install the new release.',
    'core.cli.update_min_version': 'The oldest supported version is %(version)s.',
    'core.cli.update_release_date': 'Release date: %(date)s',
    'core.cli.update_file_size': 'Download size: %(size)s',
    'core.cli.update_notes_header': 'Release notes:',
    'core.cli.update_page': 'Download page: %(url)s',
    'core.cli.update_source': 'Source code: %(url)s',
    'core.cli.update_latest': 'Version check: %(version)s is the newest release',
}

