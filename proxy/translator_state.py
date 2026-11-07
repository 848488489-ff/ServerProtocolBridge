"""Connection state of the translation layer.

Everything an EaglerTranslator instance owns: the negotiated protocols, the
identity the backend login produced, the two encoders and the buffered frames.
Kept apart from the behaviour so a file only has to describe the shape.
"""

from __future__ import annotations

import threading

from . import crypto, eagler, vanilla
from .logger import NullLogger


class TranslatorStateMixin:
    def __init__(self, target_host: str, target_port: int, log=None, tag: str = '',
                 send_client=None, send_backend=None, request_close=None,
                 brand: str = 'ServerProtocolBridge', brand_version: str = '1.0',
                 spoof_client: str = 'off', spoof_brand: str = '',
                 login_ack: bool = True, resource_pack_mode: str = 'forward',
                 account=None):
        self.target_host = target_host
        self.target_port = int(target_port)
        self.log = log or NullLogger()
        self.tag = tag
        self.brand = brand
        self.brand_version = brand_version
        # Client identification spoof: the preset decides which handshake
        # fingerprints (FML marker / channel registration) are reproduced on
        # the upstream connection; the brand is the MC|Brand value sent to the
        # target server after login, and empty means "do not send one"
        self.spoof_client = (spoof_client or 'off').strip().lower()
        self.spoof_brand = (spoof_brand or '').strip()
        # Whether the 1.20.2+ login acknowledge is sent in the client's place
        # (see _handle_login_success); switchable because it is a guess about
        # what the browser client does, not part of the classic flow
        self.login_ack = bool(login_ack)
        # How to treat the server's resource pack prompt (see config.py).
        self.resource_pack_mode = (resource_pack_mode or 'forward').strip().lower()
        # The account selected in the settings (accounts.py), if any: it
        # dictates the name/UUID the target sees and, for authenticated kinds,
        # the session join done before the encryption answer
        self.account = account
        self._send_client = send_client or (lambda data: None)
        self._send_backend = send_backend or (lambda data: None)
        self._request_close = request_close or (lambda reason: None)

        self.phase = 'client_version'     # client_version -> request_login -> backend_login
                                           # -> allow_sent -> play / closed
        self.client_version: eagler.ClientVersion | None = None
        self.handshake_protocol = 0
        self.mc_protocol = eagler.DEFAULT_MC_PROTOCOL
        self.username = ''
        self.uuid = b''
        self.client_finished = False      # has the client sent "finish login" yet?
        self.login_done = False           # has the backend login succeeded yet?
        self.close_reason = ''

        # The client direction uses no Decoder/Encoder: there, one frame is one bare
        # packet -- see feed_client/feed_server
        self.server_decoder = vanilla.Decoder(0)
        self.server_encoder = vanilla.Encoder(0)
        self.server_decrypt: crypto.AesCfb8 | None = None   # target server -> proxy (AES)
        self.server_encrypt: crypto.AesCfb8 | None = None   # proxy -> target server (AES)
        self.pending_to_client: list[bytes] = []     # frames buffered while the
                                                      # handshake completes (1 packet/frame)
        self._lock = threading.Lock()

        self.packets_to_server = 0
        self.packets_to_client = 0
        self._seen_client_ids: set[tuple[int, str]] = set()
        self._seen_server_ids: set[tuple[int, str]] = set()
        # True once a brand packet from the client has been rewritten to the
        # spoofed value, so the synthesized brand is not announced a second time
        self._brand_rewritten = False
