"""ProxyServer status queries, the HTTP/upgrade front door and the listener lifecycle.  Split from proxy.py for file size.

Method bodies are unchanged; they are methods of ProxyServer, reached
through ``self``.
"""

import asyncio
import json
import os
import socket
import ssl
import threading
import time
from . import portowner, resolver
from .i18n import tr
from .proxy import (Bridge, STATUS_TIMEOUT, WS_MAX_QUEUE, WS_WRITE_LIMIT, _NoDelayServerConnection)
from .version import (SERVICE_NAME, VERSION)
from websockets.asyncio.server import (ServerConnection, serve)
from websockets.datastructures import Headers
from websockets.http11 import (Request, Response)
class ProxyStatus:
    """ProxyStatus mixin for ProxyServer."""
    def status_for_query(self, host: str, port: int | None,
                         timeout: float = STATUS_TIMEOUT) -> dict:
        """Return the status used for an ``Accept: MOTD`` answer.

        This runs in a worker thread.  Caching is deliberately disabled: every
        list query hits the target server live, so the MOTD, player count and
        version the client sees are always current instead of a stale cached
        value.  (The status cache was removed as meaningless -- a server list
        should never show yesterday's MOTD.)
        """
        resolved_host, resolved_port = self.resolve_endpoint(host, port)
        resolved_port = int(resolved_port)
        result = resolver.query_status(resolved_host, resolved_port, timeout=timeout)
        result['time'] = time.time()
        return result
    def target_status(self, host: str, port: int, timeout: float = STATUS_TIMEOUT,
                      max_age: float | None = None, wait: bool = True) -> dict:
        """Return the target server status.

        Caching is disabled: every call performs a live query so the status page
        always shows the current MOTD, players and ping.  ``wait=False`` is kept
        for compatibility but no longer returns a cached/placeholder value; a
        caller that must not block should pass ``wait=False`` and accept that the
        query still runs (the status page refreshes on its own timer).
        """
        result = resolver.query_status(host, int(port), timeout=timeout)
        result['time'] = time.time()
        return result
    # ---------- HTTP / WebSocket transport ----------
    @staticmethod
    def _http_response(status: int, reason: str, body: bytes,
                       content_type: str = '') -> Response:
        headers = Headers()
        if content_type:
            headers['Content-Type'] = content_type
        headers['Content-Length'] = str(len(body))
        headers['Cache-Control'] = 'no-store'
        headers['X-Content-Type-Options'] = 'nosniff'
        # The status page is a diagnostic endpoint, not a browser application:
        # closing the connection keeps the response bounded and avoids keeping
        # idle HTTP sockets around on the game port.
        headers['Connection'] = 'close'
        return Response(status, reason, headers, body)
    async def _process_http(self, connection: ServerConnection,
                            request: Request) -> Response | None:
        """Serve diagnostic HTTP on the same port, hand WebSocket upgrades on.

        Returning None lets ``websockets`` complete the WebSocket handshake.
        Everything else is answered here without touching the game path.
        """
        if request.headers.get('Upgrade', '').lower() == 'websocket':
            return None

        path = (request.path or '/').split('?', 1)[0] or '/'
        # websockets 15 only parses GET handshake requests and has no method
        # attribute; 17 adds one.  Treat the absent attribute as GET.
        method = getattr(request, 'method', 'GET')
        head = method == 'HEAD'
        if method not in ('GET', 'HEAD'):
            return self._http_response(
                405, 'Method Not Allowed', b'',
                'text/plain; charset=utf-8')

        if path in ('/status', '/status.json'):
            body = json.dumps(self.status(path), ensure_ascii=False).encode('utf-8')
            return self._http_response(
                200, 'OK', b'' if head else body,
                'application/json; charset=utf-8')
        if path == '/favicon.ico':
            return self._http_response(204, 'No Content', b'')
        return self._http_response(
            404, 'Not Found', b'Not Found\n', 'text/plain; charset=utf-8')
    @staticmethod
    def _select_subprotocol(connection: ServerConnection,
                            subprotocols: list[str]) -> str | None:
        # Preserve the previous gateway's behaviour: use the first protocol the
        # client offered, so ``base64`` remains an explicit opt-in.
        return subprotocols[0] if subprotocols else None
    async def handle_websocket(self, connection: ServerConnection, scheme: str) -> None:
        request = connection.request
        path = ((request.path if request is not None else '/') or '/').split('?', 1)[0] or '/'
        if request is not None:
            # Some browser clients attach a Cookie header to the WebSocket
            # upgrade.  The Eagler protocol has no use for it and it must never
            # leak into a backend handshake or a log line, so drop it before
            # anything else can see it.
            try:
                del request.headers['Cookie']
            except KeyError:
                pass
        client = connection.remote_address or ('?', 0)
        addr = (client[0], client[1])
        bridge = Bridge(self, connection, path, scheme, addr, self.log,
                        connection.subprotocol)
        with self._lock:
            self._connections.add(bridge)
            self.stats.connection_opened()
        await bridge.run()
    # ---------- listeners ----------
    def _start_listener(self, port: int, scheme: str,
                        ssl_context: ssl.SSLContext | None) -> str:
        """Create the listening socket first (a busy port surfaces right away),
        then hand it to a dedicated ``websockets`` event loop.

        The socket is already listening, so client connections can arrive as
        soon as start() returns; the kernel queues them until the loop is up.
        """
        config = self.config
        host = config.listen_host or '127.0.0.1'
        family = socket.AF_INET6 if ':' in host else socket.AF_INET
        listener = socket.socket(family, socket.SOCK_STREAM)
        if os.name == 'nt' and hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
            # Windows: SO_REUSEADDR lets another process bind the same port
            # (port hijacking) and turns an honest conflict into a confusing
            # WinError 10013.  Either this process owns the port or start()
            # fails; a listener is never shared and never moved.
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind((host, int(port)))
            listener.listen(128)
        except OSError as exc:
            listener.close()
            owner = portowner.listener(int(port))
            if owner:
                raise OSError(tr('proxy.error.listen_failed_owner',
                                 host=host, port=int(port),
                                 process=owner['process'],
                                 pid=owner['pid'])) from None
            raise OSError(tr('proxy.error.listen_failed',
                             host=host, port=int(port), error=exc)) from None

        entry = {
            'server': None,
            'loop': None,
            'serve_task': None,
            'thread': None,
            'listener': listener,
            'ready': threading.Event(),
            'error': None,
        }
        thread = threading.Thread(
            target=self._serve, args=(entry, scheme, ssl_context),
            daemon=True, name='spb-%s' % scheme)
        entry['thread'] = thread
        self._servers.append(entry)
        thread.start()
        # Waiting for the loop to install the server means a failure inside
        # the thread is raised from start() instead of disappearing into it.
        if not entry['ready'].wait(5.0):
            try:
                listener.close()
            except OSError:
                pass
            raise RuntimeError(tr('proxy.error.listener_failed', scheme=scheme))
        if entry['error'] is not None:
            thread.join(1.0)
            raise entry['error']
        display_host = host if host not in ('0.0.0.0', '') else '127.0.0.1'
        return '%s://%s:%d' % (scheme, display_host, int(port))
    def _serve(self, entry: dict, scheme: str,
               ssl_context: ssl.SSLContext | None) -> None:
        async def main() -> None:
            config = self.config
            heartbeat = max(0, int(config.heartbeat_sec))
            try:
                server = await serve(
                    lambda connection: self.handle_websocket(connection, scheme),
                    sock=entry['listener'],
                    ssl=ssl_context,
                    process_request=self._process_http,
                    select_subprotocol=self._select_subprotocol,
                    compression=None,       # avoid per-message latency and CPU
                    max_size=int(config.max_payload_bytes),
                    max_queue=WS_MAX_QUEUE,
                    write_limit=WS_WRITE_LIMIT,
                    ping_interval=float(heartbeat) if heartbeat else None,
                    ping_timeout=float(max(1, heartbeat)) * 2 if heartbeat else None,
                    close_timeout=2,
                    server_header='%s/%s' % (SERVICE_NAME, VERSION),
                    create_connection=_NoDelayServerConnection,
                )
            except BaseException as exc:
                entry['error'] = exc
                entry['ready'].set()
                return
            entry['server'] = server
            entry['loop'] = asyncio.get_running_loop()
            serve_task = asyncio.create_task(server.serve_forever())
            entry['serve_task'] = serve_task
            entry['ready'].set()
            try:
                await serve_task
            except asyncio.CancelledError:
                pass
            finally:
                server.close()
                await server.wait_closed()

        try:
            asyncio.run(main())
        except asyncio.CancelledError:
            pass
        except Exception:      # errors in a thread cannot be raised to the caller; record them
            import traceback
            traceback.print_exc()
            entry['error'] = entry['error'] or True
    def _shutdown_servers(self) -> None:
        servers = self._servers
        self._servers = []
        # Ask each loop to close its listener and terminate the remaining
        # connections.  Server.close() is thread-safe only through the loop.
        for entry in servers:
            loop = entry.get('loop')
            server = entry.get('server')
            serve_task = entry.get('serve_task')
            if loop is not None and server is not None and not loop.is_closed():
                try:
                    loop.call_soon_threadsafe(server.close)
                except RuntimeError:
                    pass
            if loop is not None and serve_task is not None and not loop.is_closed():
                # asyncio.Server.serve_forever() only returns when cancelled;
                # close() stops accepting but leaves the wait itself pending.
                try:
                    loop.call_soon_threadsafe(serve_task.cancel)
                except RuntimeError:
                    pass
        deadline = time.time() + 3.0
        for entry in servers:
            thread = entry.get('thread')
            if thread is not None:
                thread.join(max(0.1, deadline - time.time()))
        # A handler stuck in a blocking call would keep its loop alive; stop
        # the loop so the process can still exit cleanly.
        for entry in servers:
            thread = entry.get('thread')
            loop = entry.get('loop')
            if thread is not None and thread.is_alive() and loop is not None:
                try:
                    loop.call_soon_threadsafe(loop.stop)
                except RuntimeError:
                    pass
        for entry in servers:
            thread = entry.get('thread')
            if thread is not None:
                thread.join(2.0)
            listener = entry.get('listener')
            try:
                if listener is not None:
                    listener.close()
            except OSError:
                pass
