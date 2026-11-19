"""Translations for the protocol translation layer.

Owner: ``translator.py`` / ``eagler.py`` / ``vanilla.py`` (keys prefixed
``translator.*``, ``eagler.*`` and ``vanilla.*``).

``translator.prefix`` is the tag prepended to every message the proxy injects
into the player's chat, so it must stay short.

EN carries the key set that the program uses; there is no separate language
table (the project is English-only).
"""

from __future__ import annotations

EN = {
    'translator.prefix': '[Protocol Adapter] ',

    # --- Messages shown to the player / reported as a close reason ---
    'translator.denied_login': 'Target server refused login: %(reason)s',
    'translator.empty_content': '(empty)',
    'translator.kick_fallback': 'Kicked',
    'translator.error.account_join_failed': 'Could not register the account session '
                                            'join: %(error)s',
    'translator.error.aes_missing': 'The target server requires an encrypted handshake, '
                                    'but this machine has no usable AES library, so the '
                                    'proxy cannot stand in for the client \u2014 install '
                                    'cryptography (pip install cryptography), or switch '
                                    'to an offline-mode server',
    'translator.error.backend_parse_failed': 'Failed to parse data from the target server: %(error)s',
    'translator.error.client_parse_failed': 'Failed to parse client data: %(error)s',
    'translator.error.duplicate_login_request': 'Duplicate login-request packet',
    'translator.error.encryption_handshake_failed': 'Failed to complete the encrypted handshake on behalf of the client: %(error)s',
    'translator.error.encryption_request_empty': 'The encryption request is empty',
    'translator.error.encryption_request_parse_failed': 'Failed to parse the encryption request: %(error)s',
    'translator.error.finish_login_malformed': 'Malformed finish-login packet',
    'translator.error.handshake_v1_too_old': 'The client offers the v1 handshake protocol, which is too old',
    'translator.error.login_request_parse_failed': 'Failed to parse the login request: %(error)s',
    'translator.error.login_success_parse_failed': "Could not parse the target server's login-success packet",
    'translator.error.unexpected_handshake_packet': 'Unexpected handshake packet 0x%(packet_id)02x',
    'translator.error.unrecognized_client_version': "The client's first packet is not a recognized WebSocket client handshake",

    # --- Log lines (the connection tag is prepended at the call site) ---
    'translator.direction.downstream': 'downstream',
    'translator.direction.upstream': 'upstream',
    'translator.log.account_joined': 'registered the account session join with the session service: %(label)s',
    'translator.log.account_selected': 'using the selected account: %(label)s (UUID %(uuid)s)',

    'translator.log.backend_disconnect': 'target server closed the connection: %(reason)s',
    'translator.log.backend_login_ok': 'target server login succeeded: %(username)s (UUID %(uuid)s); the client has been told it may log in',
    'translator.log.brand_spoofed': 'declared client brand %(brand)r to the target server (client identification spoof)',
    'translator.log.client_finished_login': 'client finished login',
    'translator.log.client_handshake': 'browser client handshake: %(detail)s',
    'translator.log.compression_enabled': 'target server enabled compression (threshold %(threshold)d); the proxy decompresses/recompresses and does not forward it to the client',
    'translator.log.drop_client_brand': "dropping the client's own MC|Brand (spoofed as %(brand)r)",
    'translator.log.drop_injected_frame': 'dropping client injected-message frame, %(size)d bytes',
    'translator.log.drop_plugin_message': 'dropping client extension plugin message: channel %(channel)s',
    'translator.log.rewrite_brand': 'rewriting the client brand to %(brand)r',
    'translator.log.drop_resource_pack': 'dropping resource pack prompt from the server',
    'translator.log.empty_username_fallback': 'login request carries no name; using the name from the client handshake packet %(name)r',
    'translator.log.encryption_done': 'completed the encrypted handshake on behalf of the client (server ID %(server_id)r, shared secret %(secret)s..., using %(backend)s); all traffic is now AES-128-CFB8',
    'translator.log.first_packet': '%(direction)s first-seen packet %(name)s (id 0x%(packet_id)02x)',
    'translator.log.flush_pending': 'sending the %(count)d game packets buffered during the handshake (%(size)d bytes) to the client',
    'translator.log.forge_channels': 'declared the Forge channel list (REGISTER %(channels)s) after login (Forge spoof)',
    'translator.log.forge_marker': 'attached the FML handshake marker to the upstream handshake (Forge spoof)',
    'translator.log.ignore_profile_data': 'ignoring client profile data (skins etc.), %(size)d bytes',
    'translator.log.cookie_discarded': 'discarding %(size)d bytes of client login cookie',
    'translator.log.login_request': 'client login request: %(detail)s',
    'translator.log.protocols_selected': 'selected handshake protocol v%(handshake)d / MC protocol %(mc)d; waiting for the client login request',
    'translator.log.translation_done': 'protocol translation complete; passing game data through',
    'translator.log.unexpected_login_packet': 'unexpected packet %(packet)s during the login phase',
    'translator.log.username_sanitized': 'client username %(raw)r does not meet server requirements; using %(clean)r instead',
    'translator.log.vanilla_login_sent': 'sent vanilla login to the target server (username %(username)s, protocol %(protocol)d)',
    'translator.log.resource_pack_prompt': 'resource pack prompt from server; mode=%(mode)s',
    'translator.log.client_status_sent': 'sent client status %(status)d to the server',
    'translator.log.unknown_resource_pack_mode': 'unknown resource pack mode %(mode)s; falling back to forward',

    # --- eagler.py: handshake parsing / descriptions ---
    'eagler.describe.auth_disabled': 'disabled',
    'eagler.describe.auth_enabled': 'enabled',
    'eagler.describe.client_version': 'brand %(brand)s %(version)s | supported handshake protocols %(handshake)s | supported MC protocols %(mc)s | authentication %(auth)s',
    'eagler.describe.login_request': 'username %(username)s | server address the client entered %(server)r | password %(password)s | client capability bits 0x%(caps)x',
    'eagler.describe.password_set': 'set',
    'eagler.describe.password_unset': 'not set',
    'eagler.name.warning': 'The name "%(name)s" is outside the usual server rules (3-16 letters, digits or underscores); some servers may reject it and you may be unable to join. Add it anyway?',
    'eagler.error.auth_username_out_of_range': 'authUsername out of range',
    'eagler.error.bad_extension_count': 'bad extension capability count: %(count)d',
    'eagler.error.bad_handshake_count': 'bad handshake protocol count: %(count)d',
    'eagler.error.bad_mc_count': 'bad Minecraft protocol count: %(count)d',
    'eagler.error.cookie_length_not_zero': 'cookie length is not 0',
    'eagler.error.cookie_out_of_range': 'cookie out of range',
    'eagler.error.extension_uuid_out_of_range': 'extension capability UUID out of range',
    'eagler.error.login_trailing_bytes': '%(count)d trailing bytes after the login request',
    'eagler.error.missing_auth_username': 'missing authUsername field',
    'eagler.error.missing_client_auth': 'missing clientAuth field',
    'eagler.error.missing_cookie_flag': 'missing cookie flag',
    'eagler.error.missing_cookie_length': 'missing cookie length',
    'eagler.error.missing_extension_count': 'missing extension capability count',
    'eagler.error.missing_password_field': 'missing password field',
    'eagler.error.not_login_request': 'not a login-request packet',
    'eagler.error.password_out_of_range': 'password field out of range',
    'eagler.error.string_length_out_of_range': 'string length out of range',
    'eagler.error.string_out_of_range': 'string body out of range',
    'eagler.error.trailing_bytes': '%(count)d trailing bytes after the first packet',
    'eagler.error.u16_out_of_range': 'u16 out of range',
    'eagler.error.uuid_not_16_bytes': 'UUID must be 16 bytes',
    'eagler.error.v1_packet_incomplete': 'incomplete v1 packet',
    'eagler.error.varint_out_of_range': 'VarInt out of range',
    'eagler.error.varint_too_long': 'VarInt longer than 5 bytes',

    # --- vanilla.py: framing / compression ---
    'vanilla.error.bad_packet_length': 'bad packet length: %(length)d',
    'vanilla.error.decompressed_length_mismatch': 'decompressed length %(actual)d does not match the declared %(declared)d',
    'vanilla.error.missing_packet_id': 'packet body contains no packet id',
    'vanilla.error.missing_uncompressed_length': 'compressed packet is missing the uncompressed length field',
    'vanilla.error.varint_too_long': 'VarInt longer than 5 bytes',
    'vanilla.error.zlib_failed': 'zlib decompression failed: %(error)s',
}

