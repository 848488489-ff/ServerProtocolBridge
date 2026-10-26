"""Client side of the login phase: version negotiation and the login request.

The first packet the browser client sends is not a vanilla packet at all -- it
is an Eaglercraft handshake carrying the versions it supports.  After the
proxy answers with the pair it will speak, the client asks to log in.
"""

from __future__ import annotations

from . import eagler
from .i18n import tr


class LoginHandshakeMixin:
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
