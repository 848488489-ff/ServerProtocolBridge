"""Bridge, assembled from its mixins.

The methods live in proxy_bridge_init.py, proxy_bridge_query.py, proxy_bridge_pump.py; this module only composes them
so the class keeps one name.
"""

from .proxy_bridge_init import BridgeInit
from .proxy_bridge_query import BridgeQuery
from .proxy_bridge_pump import BridgePump


class Bridge(BridgeInit, BridgeQuery, BridgePump):
    """One WebSocket client connection <-> one target server TCP connection.

    Data flow:
        client --(WebSocket messages)--> Bridge --(TCP byte stream)--> target server
        target server --(TCP byte stream)--> Bridge --(one frame per packet)--> client

    The browser client's protocol translation layer wants to emit several packets
    for a single frame (the handshake packet plus buffered game packets), and each
    of those packets must occupy a WebSocket frame of its own. Payloads destined
    for the client are therefore queued first and sent frame by frame in order by
    _drain_outbox; bytes destined for the target server go through
    _flush_to_server the same way.
    """
