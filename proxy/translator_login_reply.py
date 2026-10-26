"""Client-facing error replies for the login phase.

A browser client only understands the Eaglercraft error packet, so a failure
that happens on the backend has to be reported there before the connection
closes -- otherwise the player just sees "Connection Closed" and has no idea
whether the problem is the target server or this proxy.
"""

from __future__ import annotations

from . import eagler
from .translator_chat import note


class LoginReplyMixin:
    def _error_and_fail(self, message: str) -> None:
        """Send ``message`` to the client and close the connection."""
        self.log.warn('%s %s' % (self.tag, message))
        self._send(eagler.pack_error(eagler.ERROR_CUSTOM_MESSAGE, note(message),
                                     self.handshake_protocol,
                                     chat_json=self._client_parses_chat_json()))
        self._fail(message, notify_client=False)
