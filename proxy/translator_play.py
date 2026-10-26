"""Play-phase methods of EaglerTranslator, composed from focused mixins.

Each sibling translator_play_*.py owns one direction or one responsibility, so
a file only has to explain one thing.
"""

from __future__ import annotations

from .translator_play_backend import PlayBackendMixin
from .translator_play_chat import PlayChatMixin
from .translator_play_client import PlayClientMixin
from .translator_play_resourcepack import PlayResourcePackMixin
from .translator_play_session import PlaySessionMixin
from .translator_play_spoof import PlaySpoofMixin


class PlayMixin(PlayBackendMixin, PlayClientMixin, PlayChatMixin,
                PlayResourcePackMixin, PlaySpoofMixin, PlaySessionMixin):
    """Everything the translation layer does once the backend is in play."""
