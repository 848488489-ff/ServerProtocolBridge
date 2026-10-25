"""Chat / JSON / legacy-colour helpers, split from translator.py for size.

Module-level functions only; the translator imports them back so callers
inside and outside the package keep working with ``translator.chat_to_text``
etc.
"""

from __future__ import annotations

import json

import os

import threading

from . import accounts, crypto, eagler, vanilla

from .i18n import tr

from .logger import NullLogger



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
    """Flatten a chat component (JSON) into plain text.

    Handles the normal object form, arrays, nested ``extra`` arrays and the
    double-encoded strings some servers/proxies produce.
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
_LEGACY_COLOR_CODES = {
    'black': '0', 'dark_blue': '1', 'dark_green': '2', 'dark_aqua': '3',
    'dark_red': '4', 'dark_purple': '5', 'gold': '6', 'gray': '7',
    'dark_gray': '8', 'blue': '9', 'green': 'a', 'aqua': 'b', 'red': 'c',
    'light_purple': 'd', 'yellow': 'e', 'white': 'f',
}
_LEGACY_COLOR_RGB = {
    '0': (0, 0, 0), '1': (0, 0, 170), '2': (0, 170, 0), '3': (0, 170, 170),
    '4': (170, 0, 0), '5': (170, 0, 170), '6': (255, 170, 0),
    '7': (170, 170, 170), '8': (85, 85, 85), '9': (85, 85, 255),
    'a': (85, 255, 85), 'b': (85, 255, 255), 'c': (255, 85, 85),
    'd': (255, 85, 255), 'e': (255, 255, 85), 'f': (255, 255, 255),
}
_LEGACY_STYLE_CODES = (
    ('obfuscated', 'k'), ('bold', 'l'), ('strikethrough', 'm'),
    ('underlined', 'n'), ('italic', 'o'),
)
_LEGACY_COLOR_NAMES = {code: name for name, code in _LEGACY_COLOR_CODES.items()}
_LEGACY_STYLE_NAMES = {code: name for name, code in _LEGACY_STYLE_CODES}
def _legacy_color_code(value: str) -> str | None:
    """Map a chat-component colour name (or hex value) to a legacy code."""
    value = value.strip().lower()
    if value == 'reset':
        return ''
    if value in _LEGACY_COLOR_CODES:
        return _LEGACY_COLOR_CODES[value]
    if value.startswith('#') and len(value) in (4, 7):
        digits = value[1:]
        if len(digits) == 3:
            digits = ''.join(character * 2 for character in digits)
        try:
            red, green, blue = (int(digits[index:index + 2], 16)
                                for index in (0, 2, 4))
        except ValueError:
            return None
        # Legacy clients only understand the 16-colour palette.  Pick the
        # nearest entry instead of dropping the colour altogether.
        return min(_LEGACY_COLOR_RGB,
                   key=lambda code: sum(
                       (actual - target) ** 2
                       for actual, target in zip(
                           (red, green, blue), _LEGACY_COLOR_RGB[code])))
    return None
def _legacy_style(component: dict, parent: dict) -> dict:
    state = dict(parent)
    color = component.get('color')
    if isinstance(color, str):
        code = _legacy_color_code(color)
        if code == '':
            state = {}
        elif code:
            state['color'] = code
    for key, _code in _LEGACY_STYLE_CODES:
        if key in component and isinstance(component[key], bool):
            state[key] = component[key]
    return state
def _legacy_prefix(state: dict) -> str:
    codes = ''
    if state.get('color'):
        codes += '\u00a7' + state['color']
    codes += ''.join('\u00a7' + code for key, code in _LEGACY_STYLE_CODES
                     if state.get(key))
    return '\u00a7r' + codes
def _collect_legacy(raw, state: dict, out: list[tuple[str, dict]]) -> None:
    if isinstance(raw, str):
        if raw:
            out.append((raw, state))
        return
    if isinstance(raw, list):
        for item in raw:
            _collect_legacy(item, state, out)
        return
    if not isinstance(raw, dict):
        return
    state = _legacy_style(raw, state)
    text = raw.get('text')
    has_text = isinstance(text, str)
    if has_text:
        nested = _unwrap_chat_json(text)
        if isinstance(nested, (dict, list)):
            _collect_legacy(nested, state, out)
        elif text:
            out.append((text, state))
    translate = raw.get('translate')
    if isinstance(translate, str) and not has_text:
        out.append((translate, state))
    extra = raw.get('extra')
    if isinstance(extra, list):
        for item in extra:
            _collect_legacy(item, state, out)
def chat_to_legacy(raw) -> str:
    """Flatten a chat component into text with Minecraft legacy colour codes.

    The browser clients show disconnect and MOTD bodies as plain strings; JSON
    colour fields are therefore converted to the ``§`` codes their font
    renderer understands.  Plain strings that already contain ``§`` codes are
    returned unchanged.
    """
    if isinstance(raw, str):
        unwrapped = _unwrap_chat_json(raw)
        if isinstance(unwrapped, str):
            return unwrapped
        raw = unwrapped
    elif not isinstance(raw, (dict, list)):
        return ''
    segments: list[tuple[str, dict]] = []
    _collect_legacy(raw, {}, segments)
    parts: list[str] = []
    current: dict | None = None
    formatted = False
    for text, state in segments:
        if not text:
            continue
        notices = any(state.get(key) for key, _code in _LEGACY_STYLE_CODES)
        if current is None:
            if state.get('color') or notices:
                parts.append(_legacy_prefix(state))
                formatted = True
        elif state != current:
            codes = ''
            if state.get('color'):
                codes += '\u00a7' + state['color']
            codes += ''.join('\u00a7' + code for key, code in _LEGACY_STYLE_CODES
                             if state.get(key))
            parts.append('\u00a7r' + codes)
            formatted = True
        parts.append(text)
        current = state
    if formatted and current and (
            current.get('color') or any(current.get(key)
                                        for key, _code in _LEGACY_STYLE_CODES)):
        parts.append('\u00a7r')
    return ''.join(parts)
def _component_from_legacy(text: str) -> dict:
    """Turn a legacy ``§``-formatted string into one chat component.

    A component whose ``text`` still contains section-sign codes is rendered
    literally by several browser clients (the section sign becomes a missing
    glyph and the code letter stays visible).  Converting the codes to the
    JSON ``color`` / ``bold`` fields makes the same text render correctly in
    those clients.
    """
    segments: list[dict] = []
    state: dict = {}
    buffer: list[str] = []

    def flush() -> None:
        if not buffer:
            return
        part = {'text': ''.join(buffer)}
        if state.get('color'):
            part['color'] = state['color']
        for key, _code in _LEGACY_STYLE_CODES:
            if state.get(key):
                part[key] = True
        segments.append(part)
        buffer.clear()

    at = 0
    while at < len(text):
        character = text[at]
        if character == '\u00a7' and at + 1 < len(text):
            code = text[at + 1].lower()
            if code == 'r':
                flush()
                state.clear()
                at += 2
                continue
            if code in _LEGACY_COLOR_NAMES:
                flush()
                state['color'] = _LEGACY_COLOR_NAMES[code]
                at += 2
                continue
            if code in _LEGACY_STYLE_NAMES:
                flush()
                state[_LEGACY_STYLE_NAMES[code]] = True
                at += 2
                continue
        buffer.append(character)
        at += 1
    flush()
    if len(segments) == 1:
        return segments[0]
    if not segments:
        return {'text': ''}
    return {'text': '', 'extra': segments}
def chat_to_component_json(raw, fallback: str = 'Kicked') -> str:
    """Build a normalised JSON chat component with explicit colour fields.

    Server kick reasons arrive either as JSON components (often with colour
    fields) or as legacy ``§`` strings.  Both are first flattened to a legacy
    string, then converted back into a component whose colours are fields
    rather than inline section-sign codes, which is what the browser clients
    render on the disconnect screen.
    """
    legacy = chat_to_legacy(raw)
    if not legacy:
        legacy = fallback
    return json.dumps(_component_from_legacy(legacy), ensure_ascii=False)
def uuid_from_string(text: str) -> bytes | None:
    value = text.replace('-', '').strip()
    if len(value) != 32:
        return None
    try:
        return bytes.fromhex(value)
    except ValueError:
        return None
