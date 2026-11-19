"""Locale table for the gui namespace.

Split into themed fragments (gui_accounts, gui_about, gui_update, gui_dialog, gui_log, gui_controls); this module merges them so the rest of the program still does ``from proxy.locales import gui``.
"""

from . import gui_accounts, gui_about, gui_update, gui_dialog, gui_log, gui_controls


EN = {
    'gui.language': 'Language',
    'gui.language.auto': 'Auto',
    'gui.language.en': 'English',
    'gui.cert_generator.auto': 'Automatic',
    'gui.cert_generator.python': 'Python (built-in)',
    'gui.cert_generator.openssl': 'OpenSSL',
    'gui.settings.title': 'Settings',
    'gui.settings.tab.connection': 'Connection',
    'gui.settings.tab.accounts': 'Accounts',
    'gui.settings.tab.cert': 'Certificate',
    'gui.settings.tab.update': 'Updates',
    'gui.settings.apply': 'Apply & Save',
    'gui.settings.close': 'Close',
    'gui.settings.check_now': 'Check Now',
    'gui.settings.update_hint': 'The update endpoint is built into the program and cannot be '
                                'changed.',
    'gui.label.listen_host': 'Listen Address',
    'gui.label.wss_port': 'wss port',
    'gui.label.ws_port': 'ws port (0 = off)',
    'gui.label.target': 'Forward Target',
    'gui.label.use_srv': 'Resolve via SRV when no port is given',
    'gui.label.auto_exit': 'Auto exit (let connected clients leave the server '
                           'cleanly before stopping)',
    'gui.label.cert_dir': 'Certificate Directory',
    'gui.label.cert_cn': 'Name (CN)',
    'gui.label.cert_days': 'Valid for (days)',
    'gui.label.cert_extra': 'Extra Names',
    'gui.label.cert_generator': 'Generator',
    'gui.label.cert_fill': 'Enter this address in your client:',
    'gui.label.update_check': 'Check for a newer release on startup',
    'gui.cert.info_missing': 'No certificate yet -- a self-signed one is issued automatically '
                             'when the service starts',
    'gui.cert.info': 'File: %(file)s\nSHA-256 fingerprint: %(thumbprint)s\nCovers: %(names)s',
    'gui.cert.hint': 'Generate the certificate, install it into the system trust store, then '
                     'restart the browser. Clients can also open the certificate address and '
                     'trust it manually.',
    'gui.label.log_level': 'Log Level',
    'gui.label.log_max_lines': 'Log Buffer',
    'gui.hint.log_max_lines': 'How many recent lines are kept. Older lines scroll off, so a long '
                              'session cannot use unbounded memory. Raise it to look further back.',
    'gui.label.heartbeat': 'Heartbeat (s, 0 = off)',
    'gui.label.status_cache': 'Cache server-list status',
    'gui.label.status_cache_ttl': 'Cache lifetime (s)',
    'gui.label.status_cache_hint': 'Off: every list query waits for the target. On: cached results return '
                                   'immediately and refresh in the background.',
    'gui.label.connect_timeout': 'Connect Timeout (s)',
    'gui.label.max_payload': 'Max Frame Size (MB)',
    'gui.label.max_connections': 'Max connections (0 = unlimited)',
    'gui.label.spoof_client': 'Client identity and brand spoofing',
    'gui.spoof.off': 'Off (no spoofing)',
    'gui.spoof.vanilla': 'Vanilla',
    'gui.spoof.forge-1.8': 'Forge 1.8.x - 1.12.2',
    'gui.spoof.forge-1.13': 'Forge 1.13+',
    'gui.spoof.neoforge': 'NeoForge 1.20.2+',
    'gui.spoof.fabric': 'Fabric',
    'gui.spoof.custom': 'Custom',
    'gui.label.rewrite_host': 'Rewrite the handshake address to the target domain '
                              '(tick when the server validates or routes by address)',
    'gui.label.eagler_translate': 'WebSocket client protocol translation '
                                  '(required for clients that use wss:// or ws://)',
    'gui.label.login_ack': 'Login acknowledge for 1.20.2+ targets '
                            '(sent on the client\'s behalf; modern servers need it)',
    'gui.label.resource_pack_mode': 'Resource pack handling',
    'gui.resource_pack_mode.forward': 'Forward prompt',
    'gui.resource_pack_mode.accept': 'Accept if present',
    'gui.resource_pack_mode.reject': 'Reject',
    'gui.resource_pack_mode.spoof': 'Fake accept (no prompt)',
    'gui.label.theme': 'Theme',
    'gui.theme.light': 'Light',
    'gui.theme.dark': 'Dark',
    'gui.theme.system': 'Follow system',
    'gui.status.stopped': 'Stopped',
    'gui.status.starting': 'Starting',
    'gui.status.running': 'Running',
    'gui.status.stopping': 'Stopping',
    'gui.status.start_failed': 'Start Failed',
    'gui.status.installing_cert': 'Installing Certificate',
    'gui.endpoint.need_port': '(enter a port first)',
    'gui.endpoint.disabled': '(no listener enabled)',
    'gui.help.title': 'User Guide',
    'gui.help.text': """Steps

1. Enter the Java server address in "Forward Target". There is no default
   server: use the address you actually play on. A bare domain is enough --
   the program finds the real server node through its SRV record. Otherwise
   enter its domain or domain:port.
2. Click [Start Service]; the status at the bottom switches to "Running".
3. On first use open [Settings...] -> Certificate and click [Install into
   Trust Store], which adds the self-signed certificate to Windows'
   "Trusted Root Certification Authorities"; otherwise the browser warns
   that the wss:// certificate is untrusted.
   (Firefox needs a separate import under Settings -> Privacy & Security
   -> Certificates -> View Certificates.)
4. Enter the following in your client's server address field:
   wss://127.0.0.1:8443
   then connect. Native Java clients are forwarded byte for byte; WebSocket
   clients use the protocol translation their connection requires.

When a connection fails, check the "Runtime Log": every connection logs its
handshake details (protocol version / the address the client sent), the
up/down byte counts and the reason it closed.

FAQ

Q: The EXE won't open, it crashes on launch with an error.
A: Install the Visual C++ Redistributable, or run the program from source.
   The EXE is built with PyInstaller and requires the VC++ runtime to be
   present on the system. Download it from:
   https://aka.ms/vs/17/release/vc_redist.x64.exe

Q: The console prints "[0x...] ANOMALY: meaningless REX prefix used".
A: Ignore it. The line comes from the graphics driver, not from this program,
   and it does not affect any feature. If it keeps appearing while the app is
   running and you use an Intel iGPU, make sure the latest Intel graphics
   driver is installed.
""",
    'gui.label.web_host': 'Bind address',
    'gui.label.web_port': 'Bind port',
    'gui.hint.web_bind': '0.0.0.0 exposes the page on the LAN; 0 lets the system pick a free port.',
    'gui.label.web_password': 'Require access password',
    'gui.hint.web_password': 'Off by default. Applies to the Web UI only; saving settings never clears it.',
    'gui.label.web_password_new': 'New password',
    'gui.label.web_password_confirm': 'Confirm password',
    'gui.hint.web_password_keep': 'At least 4 characters. Leave both password fields blank to keep the current password.',
    'gui.status.web_password_on': 'Password: enabled',
    'gui.status.web_password_stored': 'Password: stored, not enabled',
    'gui.status.web_password_off': 'Password: not set',
    'gui.label.server_brand': 'Server brand',
    'gui.hint.server_brand': 'Brand shown to browser clients; keep the default unless you need another value.',
    'gui.label.server_brand_version': 'Server version',
    'gui.hint.server_brand_version': 'Optional version string sent with the brand; empty reports the program version.',
    'gui.label.spoof_brand': 'Custom client brand',
    'gui.hint.spoof_brand': 'Sent to the target server as the client brand. ASCII only. A trailing parenthesised suffix such as "(u1-beta)" is dropped on save.',
    'gui.label.suffix_route': 'Suffix routing',
    'gui.hint.suffix_route': 'The request path itself names the target server: /mc244.com -> mc244.com (SRV / default port), /hypixel.net -> hypixel.net, /127.0.0.1:25565 -> 127.0.0.1:25565. "/" uses the default target. Cannot be enabled together with the path routes below. Anyone who can reach the listener would be able to connect anywhere through the relay -- enable it only on a trusted network.',
    'gui.hint.suffix_route_disabled': 'Clear the path routes first to enable suffix routing',
    'gui.label.routes': 'Path routes',
    'gui.hint.routes': 'Connections to a listed path are sent to the server on the right; everything else uses the address above. A row is only used when both halves are filled in.',
    'gui.hint.routes_empty': 'No routes: every connection goes to the server address above.',
    'gui.hint.endpoint': 'Paste this address into the browser client.',
    'gui.web.title': 'Web UI',
    'gui.web.hint': 'The Web UI offers the same controls in a browser (start, stop, configure, monitor).',
    'gui.web.running': 'Web UI running at %(url)s',
    'gui.web.failed': 'The Web UI could not start: %(error)s',
}


for _sub in (gui_accounts, gui_about, gui_update, gui_dialog, gui_log, gui_controls,):
    EN.update(_sub.EN)
