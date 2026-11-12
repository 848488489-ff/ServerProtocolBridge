"""Connection lifecycle shared by the login and play phases: teardown and send.

``_fail`` is the single place that flips the session to ``closed``; it reports
to the client at most once, and a failed notification never blocks teardown.
"""

from __future__ import annotations

from . import eagler
from .i18n import tr
from .translator_chat import note, packet_name


class PlaySessionMixin:
    def _note_packet(self, packet_id: int, state: str, to_client: bool) -> None:
        # Hot path: this runs for every play packet.  Building the translated
        # message only makes sense when debug logging is actually on.
        if not self.log.enabled('debug'):
            return
        seen = self._seen_server_ids if to_client else self._seen_client_ids
        key = (packet_id, state)
        if key in seen or len(seen) > 60:
            return
        seen.add(key)
        direction = tr('translator.direction.downstream' if to_client
                       else 'translator.direction.upstream')
        self.log.debug('%s %s' % (self.tag, tr(
            'translator.log.first_packet', direction=direction,
            name=packet_name(packet_id, state), packet_id=packet_id)))

    def _send(self, data: bytes) -> None:
        if data:
            self._send_client(data)

    def fail(self, reason: str, notify_client: bool = True) -> None:
        """For the bridge layer: report a connection-level problem through the
        same teardown path as an internal failure.

        Takes the lock because the bridge may call this while a feed call is
        still running on a worker thread (see proxy.py's asyncio.to_thread).
        """
        with self._lock:
            self._fail(reason, notify_client)

    def _fail(self, reason: str, notify_client: bool = True) -> None:
        if self.phase == 'closed':
            return
        self.phase = 'closed'
        self.close_reason = reason
        if notify_client:
            try:
                self._send(eagler.pack_error(eagler.ERROR_CUSTOM_MESSAGE, note(reason),
                                             max(self.handshake_protocol, 3),
                                             chat_json=self._client_parses_chat_json()))
            except Exception:      # a failed notification must not break teardown
                pass
        self._request_close(reason)
