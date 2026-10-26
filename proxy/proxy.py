"""Forwarding core: bridges a local wss:// / ws:// WebSocket connection to the
target Minecraft server's TCP connection.

The HTTP and WebSocket layer is handled directly by the ``websockets`` library:
fragment reassembly, heartbeats (PING/PONG), subprotocol negotiation, the
closing handshake and frame size limits are all left to that implementation.
There is no ASGI layer and no FastAPI/uvicorn process in front of the game
traffic.  This module only does three things:

* move the messages coming from the client over to the target server's TCP
  connection verbatim, and the other way around;
* once the peer turns out to be a browser (EaglercraftX-family) client, hand it
  to translator.py for protocol translation;
* answer the browser client's server-list MOTD query locally (it sends the
  text frame ``Accept: MOTD``), otherwise it would keep showing "unable to
  connect".

On top of that the same listener serves a status page: opening
http://<listen address>:<ws port>/ in a browser shows the "current server
address", the target server status, the connection count and the traffic.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import socket
import threading
import time
from .i18n import tr
from .translator import chat_to_text
from websockets.asyncio.server import ServerConnection
RECV_SIZE = 262144           # one TCP read often contains a whole burst of game packets
WS_MAX_QUEUE = 32            # incoming message queue: absorb bursts without backpressure
WS_WRITE_LIMIT = 262144      # outgoing high-water mark: do not pause on every small packet
CLOSE_GRACE = 0.35           # finish the closing words before disconnecting; give the client time to read them
PLAIN_WATCH_BYTES = 64 * 1024   # how far a plain session's login stage is watched before giving up on it
FIRST_MESSAGE_WAIT = 1.0     # how long to wait for the client's first message (tells list queries and game handshakes apart)
CONNECT_FAIL_WAIT = 1.0      # when the target is down, wait a bit longer for the client's first packet (we need its handshake version)
QUERY_IDLE_SECONDS = 300.0   # max idle time of a "server list" query connection
STATUS_TIMEOUT = 4.0         # timeout of a live target status query


class _SessionClosed(Exception):
    """This connection should wind down now (not a failure)."""


class _NoDelayServerConnection(ServerConnection):
    """Server connection that disables Nagle before the first game packet.

    Game packets are small and latency-sensitive; batching them in the kernel
    adds avoidable delay.  The TCP socket is only reachable from the transport,
    so this is done at connection setup rather than in the message handler.
    """

    def connection_made(self, transport) -> None:
        super().connection_made(transport)
        try:
            sock = transport.get_extra_info('socket')
            if sock is not None:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except (OSError, AttributeError):
            pass


def describe_connect_error(exc: BaseException) -> str:
    """Turn a connection failure into one sentence the player can understand."""
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        return tr('proxy.error.timeout')
    if isinstance(exc, socket.gaierror):
        return tr('proxy.error.dns')
    if isinstance(exc, ConnectionRefusedError):
        return tr('proxy.error.refused')
    if isinstance(exc, OSError):
        mapping = {
            110: tr('proxy.error.timeout'),
            10060: tr('proxy.error.timeout'),
            111: tr('proxy.error.refused'),
            10061: tr('proxy.error.refused'),
            113: tr('proxy.error.unreachable'),
            101: tr('proxy.error.unreachable'),
            10051: tr('proxy.error.unreachable'),
            10065: tr('proxy.error.unreachable'),
        }
        text = mapping.get(getattr(exc, 'errno', None))
        if text:
            return text
    text = str(exc).strip()
    return text or exc.__class__.__name__


def motd_lines(raw, limit: int = 2) -> list[str]:
    """Split the server's title screen into at most ``limit`` lines.

    ``chat_to_text`` flattens a JSON description to its text while leaving a
    ``§``-coded description byte for byte, which is what the server-list query
    wants: no colour is invented here, the client sees what the server sent.
    """
    text = chat_to_text(raw)
    lines = [line.strip() for line in text.split('\n')]
    return [line for line in lines if line][:limit]


class Stats:
    def __init__(self):
        self._lock = threading.Lock()
        self.started_at = time.time()
        self.active = 0
        self.total = 0
        self.bytes_to_server = 0
        self.bytes_to_client = 0

    def add_bytes(self, to_server: int = 0, to_client: int = 0) -> None:
        with self._lock:
            self.bytes_to_server += to_server
            self.bytes_to_client += to_client

    def connection_opened(self) -> None:
        with self._lock:
            self.active += 1
            self.total += 1

    def connection_closed(self) -> None:
        with self._lock:
            if self.active > 0:
                self.active -= 1

    def snapshot(self) -> dict:
        with self._lock:
            return {
                'uptime': time.time() - self.started_at,
                'active': self.active,
                'total': self.total,
                'bytes_to_server': self.bytes_to_server,
                'bytes_to_client': self.bytes_to_client,
            }


def _discard_future_result(future: asyncio.Future | concurrent.futures.Future) -> None:
    """Drop a task/future result (handled elsewhere) but retrieve any exception, so
    no unhandled-exception warning is left behind.

    A cancelled one raises CancelledError from .exception(), and a future scheduled
    onto an event loop is cancelled when that loop shuts down, so the state is
    checked first -- otherwise the done callback itself blows up with "exception
    calling callback for <Future ... state=cancelled>" during a normal shutdown.
    """
    if not future.cancelled():
        future.exception()


def _set_socket_options(writer: asyncio.StreamWriter) -> None:
    sock = writer.get_extra_info('socket')
    if sock is None:
        return
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    except OSError:
        pass

# Bridge and ProxyServer live in their own modules: their methods need
# the constants and helpers above, so these imports come last.  They keep
# ``from .proxy import Bridge`` / ``ProxyServer`` working.
from .proxy_bridge import Bridge
from .proxy_server import ProxyServer
