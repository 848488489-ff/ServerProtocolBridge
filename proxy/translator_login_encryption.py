"""The encryption request: answered on the client's behalf.

Browser clients cannot do the AES handshake vanilla servers ask for, so the
proxy encrypts a random shared secret with the server's public key, registers
the session with the join service if an authenticated account is selected, and
then switches both directions to AES-128-CFB8.
"""

from __future__ import annotations

import os

from . import accounts, crypto, vanilla
from .i18n import tr
from .translator_chat import note


class LoginEncryptionMixin:
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
            self._error_and_fail(message)
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
            self._error_and_fail(message)
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
                self._error_and_fail(message)
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
