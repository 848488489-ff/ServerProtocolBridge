"""Translations for TLS, crypto and address helpers.

Owner: ``certs.py`` / ``crypto.py`` / ``der.py`` / ``x509.py`` / ``wsproto.py`` /
``resolver.py`` / ``handshake.py`` (keys prefixed after the module they belong
to, e.g. ``certs.*``, ``resolver.*``, ``wsproto.*``).
"""

from __future__ import annotations

EN = {
    # ------------------------------------------------------------ certs.py
    'certs.signing_openssl': 'Signing the certificate with openssl...',
    'certs.openssl_failed': 'openssl signing failed, falling back to the built-in generator',
    'certs.generating': 'Generating a %(bits)d-bit RSA key and self-signing '
                        '(a few seconds on the first run)...',
    'certs.exists': 'Using the existing valid certificate: %(path)s',
    'certs.unusable': 'The existing certificate is unusable, regenerating: %(path)s',
    'certs.generate_failed': 'Certificate generation failed, please check the write '
                             'permissions of: %(path)s',
    'certs.generated': 'Certificate generated: %(path)s (generator: %(generator)s)',
    'certs.thumbprint': 'Certificate SHA-256 fingerprint: %(thumbprint)s',
    'certs.alt_names': 'Names covered by the certificate: %(names)s',
    'certs.file_missing': 'Certificate file not found: %(path)s',
    'certs.windows_only': 'Automatic import is only supported on Windows; add the '
                          'certificate to the system / browser trust store manually',
    'certs.android_no_import': 'Android cannot import certificates into the system '
                               'trust store automatically; trust the certificate '
                               'in the client app instead',
    'certs.certutil_failed': 'Failed to run certutil: %(error)s',
    'certs.installed': "Certificate imported into the current user's Trusted Root "
                       'Certification Authorities store: %(path)s',
    'certs.restart_browser': 'Restart the browser for it to take effect (Firefox needs '
                             'a separate import, see README).',
    'certs.import_failed': 'Import failed: %(output)s',

    # ----------------------------------------------------------- crypto.py
    'crypto.missing_backend': 'No AES library available, cannot complete the encrypted '
                              'handshake -- please install cryptography: '
                              'pip install cryptography',
    'crypto.key_not_sequence': 'Public key is not a SEQUENCE',
    'crypto.key_no_bit_string': 'Public key contains no BIT STRING',
    'crypto.key_no_modulus': 'Public key contains no modulus',
    'crypto.key_no_exponent': 'Public key contains no exponent',
    'crypto.bad_key_size': 'AES-128 requires a 16-byte key',
    'crypto.bad_iv_size': 'CFB8 requires a 16-byte IV',

    # -------------------------------------------------------------- der.py
    'der.bad_oid': 'Invalid OID: %(oid)s',

    # ------------------------------------------------------------- x509.py
    'x509.bad_key_bits': 'RSA key size must be an even number >= 1024',
    'x509.key_too_small': 'RSA key is too small to sign with',

    # ---------------------------------------------------------- wsproto.py
    'wsproto.rsv_set': 'RSV bit set (no extension was negotiated)',
    'wsproto.control_frame_rules': 'Control frames must not be fragmented and must not '
                                   'exceed 125 bytes',
    'wsproto.bad_length': 'Invalid frame length',
    'wsproto.length_over_max': 'Frame length %(length)d exceeds the limit of %(limit)d',
    'wsproto.frame_after_fragment': 'The previous fragmented message has not finished yet',
    'wsproto.unexpected_continuation': 'Continuation frame received without an open '
                                       'fragmented message',
    'wsproto.fragment_over_max': 'Fragmented message exceeds the payload limit',
    'wsproto.unknown_opcode': 'Unknown opcode: %(opcode)s',

    # --------------------------------------------------------- resolver.py
    'resolver.bad_label': 'Invalid domain label: %(label)s',
    'resolver.truncated': 'DNS response is truncated',
    'resolver.pointer_loop': 'DNS name compression pointer loop',
    'resolver.rcode': 'DNS server returned error code RCODE=%(code)d',
    'resolver.srv_failed': 'SRV lookup failed: %(error)s',
    'resolver.log_srv_failed': 'SRV lookup failed (%(host)s): %(error)s, falling back '
                               'to the default port %(port)d',
    'resolver.log_srv_resolved': 'SRV resolved: %(host)s -> %(target)s:%(port)d',
    'resolver.log_no_srv': 'No SRV record for %(host)s, using the default port %(port)d',
    'resolver.peer_closed': 'The peer closed the connection',
    'resolver.varint_too_long': 'VarInt field is too long',
    'resolver.bad_status_length': 'Unexpected status response length: %(length)d',
    'resolver.bad_status_packet': 'Status response packet id is %(packet_id)s',
    'resolver.bad_status_json': 'Status response is not a JSON object',

    # -------------------------------------------------------- handshake.py
    'handshake.state_status': 'status (Server List Ping)',
    'handshake.state_login': 'login',
    'handshake.state_transfer': 'transfer (obsolete)',
    'handshake.state_unknown': 'unknown (%(state)d)',
    'handshake.varint_incomplete': 'VarInt is incomplete',
    'handshake.varint_too_long': 'VarInt is longer than 5 bytes',
    'handshake.hex_more': ' ...(%(count)d bytes total)',
    'handshake.describe': 'protocol %(protocol)d, client-supplied address '
                          '"%(address)s:%(port)d", next state %(next_state)s',
}

