"""Protocol translation layer: connects EaglercraftX-family browser clients to
real vanilla Minecraft 1.8 servers.

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
* then moves game data in both directions, patching up the places where the
  two sides differ:
    - framing: vanilla TCP is a byte stream of [VarInt length][body], while
      the browser client uses "one WebSocket frame = one bare packet (id +
      content)" with neither length prefix nor compression, so every packet
      has to be sent as its own frame and every frame has to be wrapped back
      into one packet;
    - compression: the server may enable compression while the client never
      compresses (its setCompressionTreshold throws
      CompressionNotSupportedException outright), so the proxy
      decompresses/recompresses and never forwards Set Compression to the
      client;
    - game data the server sends before the handshake completes is buffered
      and released to the client after "finish login";
    - client-specific "EAG|..." plugin messages and 0xEE-prefixed injected
      message frames are dropped -- vanilla servers do not understand them.

All protocol formats come from the EaglercraftX server implementation
(lax1dude/eaglerxserver) and the client u53 socket-layer sources.

This file is only the shell: the state, the two feed directions and the
per-phase handlers live in the sibling translator_*.py files, one
responsibility each.
"""

from __future__ import annotations

from .translator_chat import (PACKET_NAMES, _CHAT_KEYS, _looks_like_chat_component,
                              _unwrap_chat_json, chat_to_text, note, packet_name,
                              uuid_from_string)  # noqa: F401
from .translator_feed import TranslatorFeedMixin  # noqa: F401
from .translator_login import LoginMixin  # noqa: F401
from .translator_login_queries import TranslatorLoginQueriesMixin  # noqa: F401
from .translator_play import PlayMixin  # noqa: F401
from .translator_state import TranslatorStateMixin  # noqa: F401


class EaglerTranslator(TranslatorStateMixin, TranslatorFeedMixin,
                       TranslatorLoginQueriesMixin, LoginMixin, PlayMixin):
    """Translates between the EaglercraftX browser protocol and the vanilla
    Minecraft protocol (login and play phases).

    The state lives on TranslatorStateMixin, the two feed entry points and the
    backend encoder on TranslatorFeedMixin, the login-phase handshakes on
    TranslatorLoginQueriesMixin, and the per-phase packet handlers on
    LoginMixin / PlayMixin.
    """
