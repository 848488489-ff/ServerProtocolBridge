"""ProxyServer, assembled from its mixins.

The methods live in proxy_server_core.py, proxy_server_status.py; this module only composes them
so the class keeps one name.
"""

from .proxy_server_core import ProxyCore
from .proxy_server_status import ProxyStatus


class ProxyServer(ProxyCore, ProxyStatus):
    """WebSocket listeners + connection management + status page."""
