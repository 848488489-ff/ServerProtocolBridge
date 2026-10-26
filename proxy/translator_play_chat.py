"""Chat bodies and the client capability they are formatted for.

Chat bodies are read straight out of the packet as the server wrote them.
Nothing is parsed back into component fields and nothing is re-encoded onto
the legacy palette; the pass-through helpers in ``eagler_chat`` pick the wire
mode from the content, and ``chat_to_text`` is only used to flatten a body
into log lines.
"""

from __future__ import annotations

from . import vanilla
from .translator_chat import chat_to_text


class PlayChatMixin:
    def _chat_raw(self, body: bytes) -> str:
        """Read the raw body text of a chat component (usually JSON)."""
        try:
            text, _ = vanilla.read_string(body, 0)
        except vanilla.ProtocolError:
            return ''
        return text

    def _flatten_chat(self, raw: str) -> str:
        """Flatten a chat component JSON into plain text for logging."""
        if not raw:
            return ''
        return chat_to_text(raw) or raw

    def _chat_text(self, body: bytes) -> str:
        return self._flatten_chat(self._chat_raw(body))

    def _client_parses_chat_json(self) -> bool:
        """Whether the client runs JSON chat bodies through jsonToComponent.

        Used for the proxy's own error messages (deny login, custom error):
        EaglercraftX (and forks that keep its brand) renders them, while other
        browser clients (Gaius, ...) display the body literally, so those get
        the plain text instead of a wall of JSON on screen.
        """
        brand = self.client_version.brand if self.client_version else ''
        return brand.strip().lower().startswith('eaglercraft')
