"""Translations for the bridge / server (``proxy.py``).

Owner: ``proxy.py`` (keys prefixed ``proxy.*``): log messages, close reasons,
connection diagnostics, the status page and the server list ("Accept: MOTD")
response.
"""

from __future__ import annotations

EN = {
    # -- configuration / listener errors (raised towards the GUI) --
    'proxy.error.bad_config': 'Invalid configuration: %(problems)s',
    'proxy.error.listen_failed': 'cannot listen on %(host)s:%(port)d (%(error)s); '
                                 'the port may be in use or reserved by the system',
    'proxy.error.listen_failed_owner': 'cannot listen on %(host)s:%(port)d: the '
                                       'port is already used by %(process)s '
                                       '(PID %(pid)d)',
    'proxy.error.listener_failed': 'the %(scheme)s WebSocket listener did not start',

    # -- connection failure reasons (logged and sent to the player) --
    'proxy.error.timeout': 'Connection timed out; the server may be offline',
    'proxy.error.dns': 'Domain name lookup failed; the address may be misspelled',
    'proxy.error.refused': 'The other side refused the connection; the port is '
                           'closed or the service is not running',
    'proxy.error.unreachable': 'Network unreachable',
    'proxy.error.resolve_failed': 'Failed to resolve the target server address: %(error)s',
    'proxy.error.connect_failed': 'Cannot connect to the target server '
                                  '%(host)s:%(port)d (%(reason)s)',
    'proxy.error.connect_note': 'Cannot reach the target server. Check that the '
                                'address is correct, or try again later\n'
                                'Target: %(host)s:%(port)d\nReason: %(reason)s',
    'proxy.error.login_stage_closed': 'The target server closed the connection during '
                                      'login; it may not support this version, or it may '
                                      'restrict where connections come from',

    # -- close reasons (shown in the log / GUI) --
    'proxy.reason.service_stopped': 'local service stopped',
    'proxy.log.goodbye_sent': '#%(id)d disconnect packet sent to the client',
    'proxy.log.goodbye_skipped': '#%(id)d stopping: no known disconnect packet for '
                                 'protocol %(protocol)s',
    'proxy.reason.client_closed': 'client closed the connection',
    'proxy.reason.client_closed_code': 'client closed the connection (code=%(code)s)',
    'proxy.reason.query_idle_timeout': 'server list query connection idle timeout',
    'proxy.reason.text_frame_in_translate': 'text frame received in protocol translation mode',
    'proxy.reason.target_closed': 'target server closed the connection',
    'proxy.reason.send_to_target_failed': 'sending to the target server failed: %(error)s',
    'proxy.reason.normal_close': 'closed normally',

    # -- route labels (used in log lines) --
    'proxy.route.path': 'path %(path)s',
    'proxy.route.default': 'default target',
    'proxy.route.default_missing': 'default target (no route for %(path)s)',
    'proxy.route.suffix': 'path %(path)s (suffix routing)',

    # -- connection diagnostics --
    'proxy.diag.no_reply': 'The target server closed the connection without sending '
                           'back a single byte after the login request. Common causes:',
    'proxy.diag.address_mismatch': '  · the address "%(shown)s" in the handshake does '
                                   'not match the server\'s real hostname "%(actual)s"; '
                                   'some servers validate or split traffic by address '
                                   '-- try enabling the handshake address rewrite',
    'proxy.diag.protocol_unsupported': '  · client protocol version %(version)d is not '
                                       'supported by that server (servers sometimes just '
                                       'disconnect without sending a message)',
    'proxy.diag.policy': '  · the server requires a Microsoft account sign-in / whitelist / '
                         'a specific port, or it blocks connections based on where they '
                         'come from',

    # -- frame kinds --
    'proxy.frame.text': 'text frame',
    'proxy.frame.binary': 'binary frame',

    # -- log messages --
    'proxy.log.connection_error': '#%(id)d connection handler failed: %(error)s',
    'proxy.log.accepted': '#%(id)d %(scheme)s accepted %(host)s:%(port)s -> '
                          '%(source)s [%(label)s]',
    'proxy.log.connected': '#%(id)d connected to the target server %(host)s:%(port)d',
    'proxy.log.failure_sent': '#%(id)d sent the connection failure reason to the client',
    'proxy.log.failure_send_error': '#%(id)d error while sending the failure reason: '
                                    '%(error)s',
    'proxy.log.query_received': '#%(id)d %(scheme)s server list query: %(payload)r',
    'proxy.log.query_binary_ignored': '#%(id)d server list query received a binary frame '
                                      'of %(size)d bytes, ignoring it',
    'proxy.log.query_wants': '#%(id)d server list query request types: %(wants)s',
    'proxy.log.empty': '(none)',
    'proxy.log.query_resolve_failed': '#%(id)d failed to resolve the target address for '
                                      'the server list query: %(error)s',
    'proxy.log.query_send_failed': '#%(id)d failed to send the server list query result: '
                                   '%(error)s',
    'proxy.log.frame_in': '#%(id)d inbound frame #%(index)d: %(kind)s, %(size)d bytes, '
                          'content: %(preview)s',
    'proxy.log.text_frame_closing': '#%(id)d text frame received in protocol translation '
                                    'mode, closing the connection',
    'proxy.log.base64_switch': '#%(id)d text frame received, switching to base64 '
                               'transport mode automatically',
    'proxy.log.bad_base64': '#%(id)d text frame is not valid base64, dropped %(size)d '
                            'bytes (starts with: %(preview)r)',
    'proxy.log.base64_decoded': '#%(id)d text frame of %(size)d bytes -> %(decoded)d '
                                'bytes after base64 decoding',
    'proxy.log.translator_enabled': '#%(id)d WebSocket client detected, enabling the '
                                    'protocol translation layer',

    'proxy.log.account_not_found': '#%(id)d account %(name)r is not in the account '
                                   'list; connecting without one',
    'proxy.log.account_load_failed': '#%(id)d could not read the account list '
                                     '(%(error)s); connecting without one',
    'proxy.log.handshake_incomplete': '#%(id)d handshake packet is still %(missing)d '
                                      'bytes short, buffering until it is complete',
    'proxy.log.not_handshake': '#%(id)d first inbound packet is not a handshake, '
                               'forwarding as-is; first 64 bytes: %(preview)s',
    'proxy.log.handshake': '#%(id)d handshake packet: %(info)s',
    'proxy.log.rewrite_failed': '#%(id)d handshake address rewrite failed, forwarding '
                                'as-is',
    'proxy.log.address_rewritten': '#%(id)d handshake address rewritten to '
                                   '%(host)s:%(port)d',
    'proxy.log.send_client_failed': '#%(id)d failed to send to the client: %(error)s',
    'proxy.log.session_end': '#%(id)d connection ended after %(seconds).1f seconds: '
                             '%(reason)s | up %(up)s, down %(down)s',
    'proxy.log.listeners_ready': 'listeners ready: %(listeners)s',
    'proxy.log.stopped': 'service stopped',
    'proxy.log.bad_route': 'route %(path)s has an invalid target (%(error)s), using the default target',
    'proxy.log.bad_suffix': 'the path %(path)s cannot be read as a server address, using the default target',
    'proxy.log.status_resolve_failed': 'failed to resolve the target address for the '
                                       'status request: %(error)s',

    # -- status endpoint --

    # -- server list ("Accept: MOTD") response --
    'proxy.query.no_motd': 'The server did not return any MOTD information',
    'proxy.query.status_error': 'Could not read the server status: %(error)s',
}

