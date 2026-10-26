"""Chat-component JSON helpers, split from eagler.py for file size.

Servers and proxies sometimes double-encode kick reasons (an already-serialized
chat component serialized again); these unwrap that nesting so the client shows
the message instead of a wall of JSON.  Re-exported by ``eagler``.
"""
import json


def _unwrap_json_strings(value, depth: int = 0):
    """Decode a JSON value, following string-wrapped JSON (max 8 levels).

    Some servers/proxies serialize an already-serialized chat component, so
    the first ``json.loads`` returns a string containing the real object.
    Keeping that string would make the client display a wall of JSON.
    """
    if depth >= 8 or not isinstance(value, str):
        return value
    value = value.strip().lstrip('\ufeff')
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return value
    if isinstance(parsed, str) and parsed != value:
        return _unwrap_json_strings(parsed, depth + 1)
    return parsed


def as_chat_json(raw: str, fallback: str = 'Kicked') -> str:
    """Turn a piece of text into chat-component JSON the client can parse.

    Since v3, the client parses the body of "deny login" and "custom error"
    packets as JSON (IChatComponent.Serializer.jsonToComponent); sending plain
    text makes it throw and show nothing but "Invalid packet received", wasting
    the kick reason the server gave. Kick reasons coming from vanilla servers
    are already valid JSON and pass through unchanged. Nested JSON strings are
    unwrapped, because a double-encoded reason is otherwise shown verbatim.
    """
    text = (raw or '').strip() or fallback
    parsed = _unwrap_json_strings(text)
    if isinstance(parsed, (dict, list)):
        return json.dumps(parsed, ensure_ascii=False)
    if isinstance(parsed, str):
        return json.dumps({'text': parsed}, ensure_ascii=False)
    return json.dumps({'text': text}, ensure_ascii=False)


def chat_passthrough(raw: str, fallback: str = 'Kicked') -> tuple[str, bool]:
    """Return a chat body together with the mode that matches its content.

    A server's chat string is forwarded the way the client reads it: a JSON
    component is sent as JSON (``chat_json=True``, so jsonToComponent renders
    its colour fields) and a ``§``-coded or plain string is sent verbatim as
    plain text (``chat_json=False``, so the client's plain-text renderer draws
    the codes).  Double-encoded components are unwrapped either way.

    Nothing is converted in either direction: a JSON component is never
    collapsed onto the 16-colour legacy palette, and a legacy string is never
    parsed back into component fields.
    """
    text = (raw or '').strip()
    parsed = _unwrap_json_strings(text)
    if isinstance(parsed, (dict, list)):
        return json.dumps(parsed, ensure_ascii=False), True
    return text or fallback, False
