"""Protocol translation layer: connects EaglercraftX-family browser clients to real
vanilla Minecraft 1.8 servers.

The difference between a vanilla server and a browser client is confined to
"the very beginning of the connection":

    browser client                        vanilla server
    --------------                        --------------
    1. private handshake (version      ->  (cannot make sense of it,
       negotiation / login / finish)       drops the connection)
    2. vanilla 1.8.8 game data after   <-> vanilla 1.8.8 game data

So this module:
* answers step 1 -- it plays an EaglercraftX server towards the client;
* at the same time plays a vanilla 1.8.8 client towards the server (vanilla
  handshake + login start; offline mode is enough);
* translates the login result from the server into the client's
  "allow login / finish login";
* then moves game data in both directions, patching up the places where the two
  sides differ:
    - framing: vanilla TCP is a byte stream of [VarInt length][body], while the
      browser client uses "one WebSocket frame = one bare packet (id + content)"
      with neither length prefix nor compression, so every packet has to be sent
      as its own frame and every frame has to be wrapped back into one packet;
    - compression: the server may enable compression while the client never
      compresses (its setCompressionTreshold throws
      CompressionNotSupportedException outright), so the proxy
      decompresses/recompresses and never forwards Set Compression to the
      client;
    - game data the server sends before the handshake completes is buffered and
      released to the client after "finish login";
    - client-specific "EAG|..." plugin messages and 0xEE-prefixed injected
      message frames are dropped -- vanilla servers do not understand them.

All protocol formats come from the EaglercraftX server implementation
(lax1dude/eaglerxserver) and the client u53 socket-layer sources.
"""

from __future__ import annotations

import json
import os
import threading

from . import accounts, crypto, eagler, vanilla
from .i18n import tr
from .logger import NullLogger

from .translator_chat import PACKET_NAMES, _CHAT_KEYS, _LEGACY_COLOR_CODES, _LEGACY_COLOR_NAMES, _LEGACY_COLOR_RGB, _LEGACY_STYLE_CODES, _LEGACY_STYLE_NAMES, _collect_legacy, _component_from_legacy, _legacy_color_code, _legacy_prefix, _legacy_style, _looks_like_chat_component, _unwrap_chat_json, chat_to_component_json, chat_to_legacy, chat_to_text, note, packet_name, uuid_from_string  # noqa: F401
from .translator_login import LoginMixin  # noqa: F401
from .translator_play import PlayMixin  # noqa: F401


class EaglerTranslator(LoginMixin, PlayMixin):
    """Translates between the EaglercraftX browser protocol and the vanilla
    Minecraft protocol (login and play phases).

    The login- and play-phase handlers live on the LoginMixin and PlayMixin
    in translator_login.py / translator_play.py; this shell holds the state,
    the feed entry points and the encoder.
    """
    def __init__(self, target_host: str, target_port: int, log=None, tag: str = '',
                 send_client=None, send_backend=None, request_close=None,
                 brand: str = 'ServerProtocolBridge', brand_version: str = '1.0',
                 spoof_client: str = 'off', spoof_brand: str = '',
                 login_ack: bool = True, resource_pack_mode: str = 'forward', account=None):
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
        self.pending_to_client: list[bytes] = []            # game frames buffered while the
                                                            # handshake completes (one packet per frame)
        self._lock = threading.Lock()

        self.packets_to_server = 0
        self.packets_to_client = 0
        self._seen_client_ids: set[tuple[int, str]] = set()
        self._seen_server_ids: set[tuple[int, str]] = set()
    # ---------- Public API: the two directions ----------
    def feed_client(self, data: bytes) -> bytes:
        """Feed in one WebSocket frame from the client; return the bytes to write
        to the backend server.

        Note: on the client side one frame is one bare packet (id + content) with
        neither a length prefix nor compression, so a whole frame is treated as a
        single packet here.
        """
        if not data or self.phase == 'closed':
            return b''
        with self._lock:
            if self.phase == 'play':
                out = self._client_play(data)
            elif self.phase == 'client_version':
                out = self._handle_client_version(data)
            else:
                out = self._handle_handshake_packet(data)
            return self._encode_for_backend(out)
    def feed_server(self, data: bytes) -> list[bytes]:
        """Feed in the byte stream from the backend server; return the WebSocket
        frames to send to the client.

        The result is a *list of frames* rather than one blob: the client requires
        exactly one packet per frame, so every packet has to be sent as its own
        frame and the caller must send them one by one.
        """
        if not data or self.phase == 'closed':
            return []
        with self._lock:
            if self.server_decrypt is not None:
                data = self.server_decrypt.decrypt(data)
            self.server_decoder.push(data)
            frames: list[bytes] = []
            while True:
                try:
                    packet = self.server_decoder.next_packet()
                except vanilla.ProtocolError as exc:
                    self._fail(tr('translator.error.backend_parse_failed', error=exc))
                    return frames
                if packet is None:
                    return frames
                self.packets_to_client += 1
                if not self.login_done:
                    self._handle_login_packet(packet, frames)
                else:
                    self._handle_play_packet(packet, frames)
                if self.phase == 'closed':
                    return frames
    def _encode_for_backend(self, data: bytes) -> bytes:
        """Before writing to the backend server: wrap in AES once encryption is on."""
        if not data:
            return b''
        if self.server_encrypt is not None:
            data = self.server_encrypt.encrypt(data)
        return data
    def _decline_login_plugin_request(self, packet: vanilla.Packet) -> None:
        """Answer a login plugin request (1.13+) with "not understood".

        A modded server, or one sitting behind a forwarding proxy, may ask the
        connecting client questions during login; an answer is expected either
        way, so staying silent would leave the login hanging until the server's
        timeout.
        """
        try:
            message_id, _ = vanilla.read_varint(packet.body, 0)
        except vanilla.ProtocolError:
            return
        payload = (vanilla.write_varint(vanilla.LOGIN_PLUGIN_RESPONSE)
                   + vanilla.write_varint(message_id) + b'\x00')
        self._send_backend(self._encode_for_backend(self.server_encoder.frame(payload)))
    def _decline_login_cookie_request(self, packet: vanilla.Packet) -> None:
        """Answer a login cookie request (1.20.5+) with "no cookie stored"."""
        try:
            key, _ = vanilla.read_string(packet.body, 0)
        except vanilla.ProtocolError:
            return
        payload = (vanilla.write_varint(vanilla.LOGIN_COOKIE_RESPONSE)
                   + vanilla.write_string(key) + b'\x00')
        self._send_backend(self._encode_for_backend(self.server_encoder.frame(payload)))
    def _acknowledge_login(self) -> None:
        """Acknowledge the login result (1.20.2+) in the client's place.

        The packet carries nothing beyond its id; see _handle_login_success for
        why the proxy has to send it instead of the browser client.
        """
        payload = vanilla.write_varint(vanilla.LOGIN_ACKNOWLEDGED)
        self._send_backend(self._encode_for_backend(self.server_encoder.frame(payload)))

