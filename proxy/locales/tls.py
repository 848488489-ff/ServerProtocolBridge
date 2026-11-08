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

ZH = {
    # ------------------------------------------------------------ certs.py
    'certs.signing_openssl': '正在通过 openssl 签发证书...',
    'certs.openssl_failed': 'openssl 签发失败, 改用内置生成器',
    'certs.generating': '正在生成 RSA %(bits)d 位密钥并自签名(首次运行需要几秒)...',
    'certs.exists': '已存在可用证书: %(path)s',
    'certs.unusable': '现有证书不可用, 将重新签发: %(path)s',
    'certs.generate_failed': '证书签发失败, 请检查目录写入权限: %(path)s',
    'certs.generated': '证书已生成: %(path)s (生成器: %(generator)s)',
    'certs.thumbprint': '证书指纹 SHA-256: %(thumbprint)s',
    'certs.alt_names': '证书包含的名称: %(names)s',
    'certs.file_missing': '证书文件不存在: %(path)s',
    'certs.windows_only': '自动导入仅支持 Windows, 请手动把证书加入系统/浏览器信任库',
    'certs.android_no_import': 'Android 无法自动把证书导入系统信任库, 请在客户端应用内信任该证书',
    'certs.certutil_failed': '执行 certutil 失败: %(error)s',
    'certs.installed': '证书已导入当前用户的受信任根证书库: %(path)s',
    'certs.restart_browser': '请重启浏览器后生效(Firefox 需要单独导入, 见 README)。',
    'certs.import_failed': '导入失败: %(output)s',

    # ----------------------------------------------------------- crypto.py
    'crypto.missing_backend': '缺少 AES 库, 无法完成加密握手 —— 请安装 cryptography: '
                              'pip install cryptography',
    'crypto.key_not_sequence': '公钥不是 SEQUENCE',
    'crypto.key_no_bit_string': '公钥里没有 BIT STRING',
    'crypto.key_no_modulus': '公钥里没有模数',
    'crypto.key_no_exponent': '公钥里没有指数',
    'crypto.bad_key_size': 'AES-128 需要 16 字节密钥',
    'crypto.bad_iv_size': 'CFB8 需要 16 字节 IV',

    # -------------------------------------------------------------- der.py
    'der.bad_oid': '非法的 OID: %(oid)s',

    # ------------------------------------------------------------- x509.py
    'x509.bad_key_bits': 'RSA 密钥长度必须是 >=1024 的偶数',
    'x509.key_too_small': 'RSA 密钥过小, 无法完成签名',

    # ---------------------------------------------------------- wsproto.py
    'wsproto.rsv_set': 'RSV 位被置位(未协商任何扩展)',
    'wsproto.control_frame_rules': '控制帧必须不分片且长度不超过 125',
    'wsproto.bad_length': '帧长度非法',
    'wsproto.length_over_max': '帧长度 %(length)d 超过上限 %(limit)d',
    'wsproto.frame_after_fragment': '上一条分片消息尚未结束',
    'wsproto.unexpected_continuation': '收到续帧, 但此前没有分片消息',
    'wsproto.fragment_over_max': '分片消息超过上限',
    'wsproto.unknown_opcode': '未知 opcode: %(opcode)s',

    # --------------------------------------------------------- resolver.py
    'resolver.bad_label': '非法域名标签: %(label)s',
    'resolver.truncated': 'DNS 响应被截断',
    'resolver.pointer_loop': 'DNS 名称压缩指针循环',
    'resolver.rcode': 'DNS 服务器返回错误码 RCODE=%(code)d',
    'resolver.srv_failed': 'SRV 查询失败: %(error)s',
    'resolver.log_srv_failed': 'SRV 查询失败(%(host)s): %(error)s, 回落到默认端口 %(port)d',
    'resolver.log_srv_resolved': 'SRV 解析: %(host)s -> %(target)s:%(port)d',
    'resolver.log_no_srv': '%(host)s 没有 SRV 记录, 使用默认端口 %(port)d',
    'resolver.peer_closed': '对方关闭了连接',
    'resolver.varint_too_long': 'VarInt 字段太长',
    'resolver.bad_status_length': '状态响应长度异常: %(length)d',
    'resolver.bad_status_packet': '状态响应包 id 是 %(packet_id)s',
    'resolver.bad_status_json': '状态响应不是 JSON 对象',

    # -------------------------------------------------------- handshake.py
    'handshake.state_status': '状态查询(Server List Ping)',
    'handshake.state_login': '登录(Login)',
    'handshake.state_transfer': '传输(已废弃)',
    'handshake.state_unknown': '未知(%(state)d)',
    'handshake.varint_incomplete': 'VarInt 不完整',
    'handshake.varint_too_long': 'VarInt 超过 5 字节',
    'handshake.hex_more': ' ...(共 %(count)d 字节)',
    'handshake.describe': '协议版本 %(protocol)d, 客户端填写地址 "%(address)s:%(port)d", '
                          '下一步 %(next_state)s',
}
