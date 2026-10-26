"""Identity resolution and the vanilla login the proxy starts on the backend.

A browser client has no notion of vanilla login, so this is where the proxy
turns the requested name into the name and UUID the target server will see, and
then opens the vanilla handshake and login-start on the backend connection.
"""

from __future__ import annotations

from . import eagler, vanilla
from .i18n import tr


class LoginBackendMixin:
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
