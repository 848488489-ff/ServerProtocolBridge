"""Chat-component helpers, split from translator.py for size.

Module-level functions only; the translator imports them back so callers
inside and outside the package keep working with ``translator.chat_to_text``
etc.

Only text extraction and JSON unwrapping live here.  There is deliberately no
colour conversion: a server's chat body is forwarded as the client can read
it -- a JSON component stays a JSON component, and a ``§``-coded string is
left byte for byte.  Collapsing a JSON component into the 16-colour legacy
palette (matching arbitrary hex to the nearest palette entry) throws away the
colour the server actually chose, and modern servers speak JSON rather than
section signs, so the code that used to do it is gone.
"""

from __future__ import annotations

import json

from . import vanilla
from .i18n import tr

# Human-readable names for the common packet ids, used in log lines.
PACKET_NAMES = {
    (vanilla.LOGIN_DISCONNECT, 'login'): 'LoginDisconnect',
    (vanilla.LOGIN_ENCRYPTION_REQUEST, 'login'): 'EncryptionRequest',
    (vanilla.LOGIN_SUCCESS, 'login'): 'LoginSuccess',
    (vanilla.LOGIN_SET_COMPRESSION, 'login'): 'SetCompression',
    (vanilla.PLAY_KEEP_ALIVE, 'play'): 'KeepAlive',
    (vanilla.PLAY_JOIN_GAME, 'play'): 'JoinGame',
    (0x02, 'play'): 'ChatMessage',
    (0x08, 'play'): 'PlayerPositionAndLook',
    (0x21, 'play'): 'ChunkData',
    (0x26, 'play'): 'MapChunkBulk',
    (vanilla.PLAY_PLUGIN_MESSAGE, 'play'): 'PluginMessage',
    (vanilla.PLAY_DISCONNECT, 'play'): 'Disconnect',
    (vanilla.CLIENT_PLUGIN_MESSAGE, 'play'): 'PluginMessage',
}


def packet_name(packet_id: int, state: str) -> str:
    return PACKET_NAMES.get((packet_id, state), '0x%02x' % packet_id)


def note(text: str) -> str:
    """Tag a text meant for the player with this proxy's own prefix, so that it
    stays distinguishable from whatever the server says."""
    return tr('translator.prefix') + text


_CHAT_KEYS = ('text', 'translate', 'extra', 'with', 'score', 'selector',
              'keybind', 'nbt', 'clickEvent', 'hoverEvent')


def _looks_like_chat_component(value) -> bool:
    """Whether a decoded JSON value is a Minecraft chat component.

    A kick reason is sometimes serialized twice, so the first ``json.loads``
    returns a string that still contains the actual component.  Plain player
    chat may also look like JSON, so only unwrap objects with component keys
    (or lists of component-ish values) to avoid turning a literal message such
    as ``{"foo": "bar"}`` into an empty string.
    """
    if isinstance(value, dict):
        return any(key in value for key in _CHAT_KEYS)
    if isinstance(value, list):
        return bool(value) and all(
            isinstance(item, (str, dict, list)) for item in value)
    return False


def _unwrap_chat_json(value, depth: int = 0):
    """Remove one or more JSON-string wrappers around a chat component."""
    if depth >= 8 or not isinstance(value, str):
        return value
    text = value.strip().lstrip('\ufeff')
    if not text or text[0] not in '{["':
        return value
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        return value
    if isinstance(parsed, str):
        if parsed == value:
            return value
        return _unwrap_chat_json(parsed, depth + 1)
    if _looks_like_chat_component(parsed):
        return parsed
    return value


def chat_to_text(raw) -> str:
    """Flatten a chat component (JSON) into plain text for logs and status.

    Handles the normal object form, arrays, nested ``extra`` arrays and the
    double-encoded strings some servers/proxies produce.  Text fields are
    returned verbatim, so a ``§``-coded string keeps its codes.
    """
    if isinstance(raw, str):
        raw = _unwrap_chat_json(raw)
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        parts = []
        text = raw.get('text')
        if isinstance(text, str):
            nested = _unwrap_chat_json(text)
            if isinstance(nested, (dict, list)):
                parts.append(chat_to_text(nested))
            else:
                parts.append(text)
        translate = raw.get('translate')
        if isinstance(translate, str) and not parts:
            parts.append(translate)
        extra = raw.get('extra')
        if isinstance(extra, list):
            parts.append(''.join(chat_to_text(item) for item in extra))
        return ''.join(parts)
    if isinstance(raw, list):
        return ''.join(chat_to_text(item) for item in raw)
    return ''


def uuid_from_string(text: str) -> bytes | None:
    value = text.replace('-', '').strip()
    if len(value) != 32:
        return None
    try:
        return bytes.fromhex(value)
    except ValueError:
        return None
