"""Login-phase methods of EaglerTranslator, split out for file size."""

from __future__ import annotations
import json
import os
import threading
from . import accounts, crypto, eagler, vanilla
from .i18n import tr
from .logger import NullLogger

from .translator_chat import PACKET_NAMES, _CHAT_KEYS, _LEGACY_COLOR_CODES, _LEGACY_COLOR_NAMES, _LEGACY_COLOR_RGB, _LEGACY_STYLE_CODES, _LEGACY_STYLE_NAMES, _collect_legacy, _component_from_legacy, _legacy_color_code, _legacy_prefix, _legacy_style, _looks_like_chat_component, _unwrap_chat_json, chat_to_component_json, chat_to_legacy, chat_to_text, note, packet_name, uuid_from_string

class LoginMixin:
    # ---------- Client: first packet ----------
    def _handle_client_version(self, data: bytes) -> bytes:
        version = eagler.parse_client_version(data)
        if version is None:
            self._fail(tr('translator.error.unrecognized_client_version'))
            return b''
        self.client_version = version
        self.log.info('%s %s' % (self.tag, tr(
            'translator.log.client_handshake', detail=version.describe())))

        picked = eagler.select_protocols(version)
        if picked is None:
            # Only the v1 handshake lands here: it carries no version list, so
            # there is nothing to negotiate from
            message = tr('translator.error.handshake_v1_too_old')
            self.log.warn('%s %s' % (self.tag, message))
            self._send(eagler.pack_version_mismatch(
                eagler.SUPPORTED_HANDSHAKE_PROTOCOLS, *eagler.MC_PROTOCOL_RANGE,
                'Outdated Client'))
            # A version-mismatch packet has already been sent; no extra error packet
            self._fail(message, notify_client=False)
            return b''

        self.handshake_protocol, self.mc_protocol = picked
        self.phase = 'request_login'
        self._send(eagler.pack_server_version(
            self.handshake_protocol, self.mc_protocol, self.brand, self.brand_version))
        self.log.info('%s %s' % (self.tag, tr(
            'translator.log.protocols_selected',
            handshake=self.handshake_protocol, mc=self.mc_protocol)))
        return b''
    # ---------- Client: login request / finish login ----------
    def _handle_handshake_packet(self, data: bytes) -> bytes:
        packet_id = data[0]
        if packet_id == eagler.PROTOCOL_CLIENT_REQUEST_LOGIN:
            if self.phase != 'request_login':
                self._fail(tr('translator.error.duplicate_login_request'))
                return b''
            try:
                request = eagler.parse_request_login(data, self.handshake_protocol)
            except eagler.HandshakeError as exc:
                self._fail(tr('translator.error.login_request_parse_failed', error=exc))
                return b''
            if request.cookie:
                self.log.debug('%s %s' % (self.tag, tr(
                    'translator.log.cookie_discarded', size=len(request.cookie))))
                request.cookie = b''
            return self._begin_backend_login(request)
        if packet_id == eagler.PROTOCOL_CLIENT_PROFILE_DATA:
            self.log.debug('%s %s' % (self.tag, tr(
                'translator.log.ignore_profile_data', size=len(data))))
            return b''
        if packet_id == eagler.PROTOCOL_CLIENT_FINISH_LOGIN:
            if len(data) != 1:
                self._fail(tr('translator.error.finish_login_malformed'))
                return b''
            self.client_finished = True
            self.log.debug('%s %s' % (self.tag, tr('translator.log.client_finished_login')))
            self._maybe_finish_login()
            return b''
        self._fail(tr('translator.error.unexpected_handshake_packet', packet_id=packet_id))
        return b''
    def _begin_backend_login(self, request: eagler.LoginRequest) -> bytes:
        raw_name = (request.username or '').strip()
        account = self.account
        if account is not None and (account.username or '').strip():
            # An account is selected: it dictates the identity -- the exact
            # name and profile UUID a server that validates logins expects to
            # see together.  The name the client asked for is only used when
            # no account is set.
            username = account.username.strip()
            self.username = username
            self.uuid = account.uuid_bytes or eagler.offline_uuid(username)
            self.log.info('%s %s' % (self.tag, tr(
                'translator.log.account_selected', label=account.label,
                uuid=self.uuid.hex())))
        elif not raw_name and self.client_version is not None:
            # Some browser clients (observed in practice) send an empty name in
            # the login request; the real name sits in the authUsername field of the
            # handshake packet and is preferred here, so that not everyone ends up
            # sharing the same fallback name.  Non-ASCII names are accepted too: the
            # target decides what it will take, not the proxy.
            candidate = eagler.usable_name(
                self.client_version.auth_username.decode('utf-8', 'replace'))
            if candidate:
                raw_name = candidate
                self.log.info('%s %s' % (self.tag, tr(
                    'translator.log.empty_username_fallback', name=candidate)))
        if not (self.username and self.uuid):
            username = eagler.sanitize_username(raw_name)
            if username != raw_name:
                self.log.warn('%s %s' % (self.tag, tr(
                    'translator.log.username_sanitized', raw=raw_name, clean=username)))
            self.username = username
            self.uuid = eagler.offline_uuid(username)
        username = self.username
        self.log.info('%s %s' % (self.tag, tr('translator.log.login_request',
                                              detail=request.describe())))
        self.phase = 'backend_login'

        # Vanilla handshake packet (next state = login) + login-start packet
        address = self.target_host.encode('utf-8')
        if self.spoof_client == 'forge-1.8' and self.mc_protocol == 47:
            # Legacy Forge clients append the FML marker to the address they put
            # into their handshake packet (see C00Handshake in the Forge patch
            # set); the remote end stores that marker as the connection's "this
            # is a modded client" flag.  The marker, the REGISTER channel list
            # and the brand are reproduced on 1.8 connections only: that is the
            # only generation whose packet numbers and channel names this proxy
            # knows by heart, and guessing others would put malformed packets
            # on the wire.
            address += b'\x00FML\x00'
        handshake = vanilla.pack(0x00, (
            vanilla.write_varint(self.mc_protocol)
            + vanilla.write_varint(len(address)) + address
            + int(self.target_port).to_bytes(2, 'big')
            + vanilla.write_varint(2)))
        name_bytes = username.encode('utf-8')
        login_start_body = vanilla.write_varint(len(name_bytes)) + name_bytes
        # Login Start gained optional (1.19) and then required (1.20.2) fields.
        # The target server parses the packet with its own version's layout, so
        # the fields it expects must be present: where they are optional the
        # "absent" flag is written, where the UUID is required ours is sent
        if self.mc_protocol >= 764:
            login_start_body += self.uuid
        elif self.mc_protocol >= 761:
            login_start_body += b'\x00'
        elif self.mc_protocol >= 760:
            login_start_body += b'\x00\x00'
        elif self.mc_protocol >= 759:
            login_start_body += b'\x00'
        login_start = vanilla.pack(0x00, login_start_body)
        self.log.info('%s %s' % (self.tag, tr(
            'translator.log.vanilla_login_sent',
            username=username, protocol=self.mc_protocol)))
        if self.spoof_client == 'forge-1.8' and self.mc_protocol == 47:
            self.log.info('%s %s' % (self.tag, tr('translator.log.forge_marker')))
        return handshake + login_start
    # ---------- Backend: login phase ----------
    def _handle_login_packet(self, packet: vanilla.Packet, frames: list[bytes]) -> None:
        packet_id = packet.packet_id
        if packet_id == vanilla.LOGIN_SET_COMPRESSION:
            threshold = 256
            try:
                threshold, _ = vanilla.read_varint(packet.body, 0)
            except vanilla.ProtocolError:
                pass
            self.server_decoder.threshold = threshold
            self.server_encoder.threshold = threshold
            self.log.debug('%s %s' % (self.tag, tr(
                'translator.log.compression_enabled', threshold=threshold)))
            return
        if packet_id == vanilla.LOGIN_DISCONNECT:
            raw = self._chat_raw(packet.body)
            reason = self._flatten_chat(raw)
            denied = tr('translator.denied_login',
                        reason=reason or tr('translator.empty_content'))
            self.log.warn('%s %s' % (self.tag, denied))
            # The kick reason the target server provides is usually JSON.  The
            # log has already flattened it correctly, but several browser
            # clients (including some that advertise an EaglercraftX brand)
            # show the deny body as literal text.  Sending the component JSON
            # therefore produces a wall of JSON on the disconnect screen, so
            # always send the flattened reason.
            fallback = tr('translator.kick_fallback')
            # The modern EaglercraftX launcher displays the deny body as a
            # plain string (a JSON body is shown literally), while its font
            # renderer understands legacy colour codes.  Send the flattened
            # string with the § prefixes intact.
            body = chat_to_legacy(raw) or fallback
            self._send(eagler.pack_deny_login(body, self.handshake_protocol,
                                              chat_json=False))
            self._fail(denied, notify_client=False)
            return
        if packet_id == vanilla.LOGIN_ENCRYPTION_REQUEST:
            self._handle_encryption_request(packet)
            return
        if packet_id == vanilla.LOGIN_PLUGIN_REQUEST:
            self._decline_login_plugin_request(packet)
            return
        if packet_id == vanilla.LOGIN_COOKIE_REQUEST:
            self._decline_login_cookie_request(packet)
            return
        if packet_id == vanilla.LOGIN_SUCCESS:
            self._handle_login_success(packet, frames)
            return
        self.log.warn('%s %s' % (self.tag, tr(
            'translator.log.unexpected_login_packet',
            packet=packet_name(packet_id, 'login'))))
    def _handle_encryption_request(self, packet: vanilla.Packet) -> None:
        """Complete the encryption handshake on behalf of the client.

        An encryption request does not imply a premium account: many servers
        (especially ones that "look like" premium) merely want the link
        encrypted and never actually check the session with Mojang, so offline
        names are let in all the same. This step is therefore done in the
        client's place: a random shared secret is encrypted with the server's
        public key and sent back, after which both directions use AES-128-CFB8.
        If the server really does validate, it will send a kick reason
        afterwards, and that text is forwarded to the client verbatim.
        """
        if not crypto.available():
            message = tr('translator.error.aes_missing')
            self.log.warn('%s %s' % (self.tag, message))
            self._send(eagler.pack_error(eagler.ERROR_CUSTOM_MESSAGE, note(message),
                                         self.handshake_protocol,
                                         chat_json=self._client_parses_chat_json()))
            self._fail(message, notify_client=False)
            return
        try:
            pos = 0
            server_id, pos = vanilla.read_string(packet.body, pos)
            length, pos = vanilla.read_varint(packet.body, pos)
            key_der = packet.body[pos:pos + length]
            pos += length
            length, pos = vanilla.read_varint(packet.body, pos)
            token = packet.body[pos:pos + length]
        except vanilla.ProtocolError as exc:
            self._fail(tr('translator.error.encryption_request_parse_failed', error=exc))
            return
        if not key_der or not token:
            self._fail(tr('translator.error.encryption_request_empty'))
            return
        try:
            secret = os.urandom(16)
            enc_secret = crypto.rsa_encrypt(key_der, secret)
            enc_token = crypto.rsa_encrypt(key_der, token)
        except Exception as exc:                     # bad public key or a library error
            message = tr('translator.error.encryption_handshake_failed', error=exc)
            self.log.warn('%s %s' % (self.tag, message))
            self._send(eagler.pack_error(eagler.ERROR_CUSTOM_MESSAGE, note(message),
                                         self.handshake_protocol,
                                         chat_json=self._client_parses_chat_json()))
            self._fail(message, notify_client=False)
            return
        account = self.account
        if account is not None and account.joinable():
            # An authenticated account is selected and the server wants the
            # link encrypted: if it really validates logins, it will now ask
            # the session service about this join, so the join has to be
            # registered first -- in the client's place, because the browser
            # client cannot do that part (and this is the reason accounts
            # exist here at all).  Blocking by design: the caller runs the
            # translation layer off the event loop.
            try:
                accounts.join_session(account,
                                      accounts.join_hash(server_id, secret, key_der),
                                      log=self.log)
            except accounts.AccountError as exc:
                message = tr('translator.error.account_join_failed', error=exc)
                self.log.warn('%s %s' % (self.tag, message))
                self._send(eagler.pack_error(eagler.ERROR_CUSTOM_MESSAGE, note(message),
                                             self.handshake_protocol,
                                             chat_json=self._client_parses_chat_json()))
                self._fail(message, notify_client=False)
                return
            self.log.info('%s %s' % (self.tag, tr(
                'translator.log.account_joined', label=account.label)))
        body = (vanilla.write_varint(len(enc_secret)) + enc_secret
                + vanilla.write_varint(len(enc_token)) + enc_token)
        payload = vanilla.write_varint(vanilla.LOGIN_ENCRYPTION_RESPONSE) + body
        # This one is plaintext (encryption starts only once the server has received
        # it), so it is sent directly and does not go through _encode_for_backend
        self._send_backend(self.server_encoder.frame(payload))
        self.server_decrypt = crypto.AesCfb8(secret, secret)
        self.server_encrypt = crypto.AesCfb8(secret, secret)
        self.log.info('%s %s' % (self.tag, tr(
            'translator.log.encryption_done', server_id=server_id,
            secret=secret.hex()[:8], backend=crypto.backend_name())))
    def _handle_login_success(self, packet: vanilla.Packet, frames: list[bytes]) -> None:
        raw_uuid: bytes | None = None
        try:
            if self.mc_protocol >= 735:
                # Since 1.16 the UUID is 16 raw bytes; whatever follows the name
                # (profile properties since 1.19) is not needed here
                raw_uuid = packet.body[:16]
                name, _ = vanilla.read_string(packet.body, 16)
                text = raw_uuid.hex()
                uuid_text = '%s-%s-%s-%s-%s' % (
                    text[:8], text[8:12], text[12:16], text[16:20], text[20:])
            else:
                uuid_text, pos = vanilla.read_string(packet.body, 0)
                name, _ = vanilla.read_string(packet.body, pos)
        except vanilla.ProtocolError:
            self._fail(tr('translator.error.login_success_parse_failed'))
            return
        uuid_bytes = raw_uuid or uuid_from_string(uuid_text) or self.uuid
        # A name back from the target is trusted whether or not it is ASCII:
        # offline-mode servers routinely return the client's original name, and
        # Chinese servers return Chinese names, which the old ASCII gate silently
        # discarded and replaced with whatever the proxy had guessed.
        accepted = eagler.usable_name(name)
        if accepted:
            self.username = accepted
            if raw_uuid is None and uuid_from_string(uuid_text) is None:
                uuid_bytes = eagler.offline_uuid(accepted)
        self.uuid = uuid_bytes
        self.login_done = True
        self.phase = 'allow_sent'
        if self.login_ack and self.mc_protocol >= 764:
            # 1.20.2+ servers hold the connection in the login state until the
            # login result is acknowledged (the configuration phase only starts
            # afterwards).  A browser client never sends that acknowledge -- its
            # login phase ends with the EaglercraftX handshake -- and the first
            # thing it sends after the handshake is already configuration data,
            # which a target still waiting in the login state answers by
            # dropping the connection; so the proxy acknowledges on its behalf.
            # This is the "login acknowledge" switch in the settings.
            self._acknowledge_login()
        self.log.info('%s %s' % (self.tag, tr(
            'translator.log.backend_login_ok', username=self.username, uuid=uuid_text)))
        self._send(eagler.pack_allow_login(self.username, self.uuid, self.handshake_protocol))
        self._maybe_finish_login()
    # ---------- Winding down ----------
    def _maybe_finish_login(self) -> None:
        if self.phase != 'allow_sent' or not (self.client_finished and self.login_done):
            return
        self.phase = 'play'
        self._send(eagler.pack_finish_login())
        if self.pending_to_client:
            total = sum(len(frame) for frame in self.pending_to_client)
            self.log.debug('%s %s' % (self.tag, tr(
                'translator.log.flush_pending',
                count=len(self.pending_to_client), size=total)))
            for frame in self.pending_to_client:      # one packet per frame; send separately
                self._send(frame)
            self.pending_to_client.clear()
        self.log.info('%s %s' % (self.tag, tr('translator.log.translation_done')))
        self._announce_brand()
