"""ProxyServer configuration, lifecycle and route resolution. Split from proxy.py for file size.

Method bodies are unchanged; they are methods of ProxyServer, reached
through ``self``.
"""

import asyncio
import ssl
import threading
import time
from . import (certs, resolver)
from .config import (Config, parse_address)
from .i18n import tr, tr_in
from .logger import NullLogger
from .proxy import (Bridge, STATUS_TIMEOUT, Stats, _discard_future_result, motd_lines)
from .utils import human_bytes
from .version import (SERVICE_NAME, VERSION)
class ProxyCore:
    """ProxyCore mixin for ProxyServer."""
    def __init__(self, config: Config, logger=None):
        self.config = config
        self.log = logger or NullLogger()
        self.stats = Stats()
        self.certificate: dict | None = None
        self.running = False
        self._servers: list[dict] = []
        self._connections: set[Bridge] = set()
        self._lock = threading.Lock()
        self._srv_cache: dict[str, tuple[str, int, float]] = {}
        self._status_cache: dict[str, dict] = {}
        self._status_refreshing: set[str] = set()
        self._status_warming: set[str] = set()
        self._id_counter = 0
    # ---------- public API ----------
    def next_id(self) -> int:
        with self._lock:
            self._id_counter += 1
            return self._id_counter
    def start(self) -> dict:
        config = self.config
        problems = config.validate()
        if problems:
            raise ValueError(tr_in('en', 'proxy.error.bad_config',
                                   problems='; '.join(problems)))

        ssl_context: ssl.SSLContext | None = None
        if config.tls_enabled:
            self.certificate = certs.ensure_certificate(
                config.resolved_cert_dir,
                common_name=config.cert_common_name or 'localhost',
                extra_names=config.cert_extra_names,
                days=int(config.cert_days),
                generator=config.cert_generator,
                regenerate=False,
                logger=self.log,
            )
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2
            ssl_context.options |= ssl.OP_NO_COMPRESSION
            ssl_context.load_cert_chain(
                self.certificate['cert_path'], self.certificate['key_path'])

        listeners: list[str] = []
        self.running = True
        try:
            if config.tls_enabled and int(config.wss_port) > 0:
                listeners.append(self._start_listener(
                    int(config.wss_port), 'wss', ssl_context))
            if int(config.ws_port) > 0:
                listeners.append(self._start_listener(int(config.ws_port), 'ws', None))
        except Exception:
            self.running = False
            self._shutdown_servers()
            raise
        self.log.info(tr('proxy.log.listeners_ready', listeners=', '.join(listeners)))
        # No status-cache pre-warm: server-list MOTD queries always hit the
        # target live (caching was removed as meaningless), so there is nothing
        # to warm and the first browser connection gets the real MOTD directly.
        return self.describe()
    def stop(self) -> None:
        if not self.running:
            return
        self.running = False
        # let every connection wind down normally first (so the client still gets
        # its close frame), then stop the listeners
        with self._lock:
            bridges = list(self._connections)
        for bridge in bridges:
            loop = bridge.loop
            if loop is None or loop.is_closed():
                continue
            try:
                future = asyncio.run_coroutine_threadsafe(
                    bridge.shutdown(tr('proxy.reason.service_stopped')), loop)
                future.add_done_callback(_discard_future_result)
            except Exception:
                pass
        deadline = time.time() + 1.0
        while time.time() < deadline:
            with self._lock:
                if not self._connections:
                    break
            time.sleep(0.02)
        self._shutdown_servers()
        self.log.info(tr('proxy.log.stopped'))
    def describe(self) -> dict:
        config = self.config
        data = {
            'service': SERVICE_NAME,
            'app': tr('core.app_name'),
            'version': VERSION,
            'running': self.running,
            'target': config.describe_target(),
            'target_source': (config.target or '').strip(),
            'target_resolved': self._resolved_target(),
            'routes': dict(config.routes or {}),
            'suffix_route': bool(getattr(config, 'suffix_route', False)),
            'use_srv': bool(config.use_srv),
            'listeners': config.listeners() if self.running else [],
            'wss_url': config.wss_url() if self.running else None,
            'server_brand': config.server_brand,
            'server_brand_version': config.server_brand_version or VERSION,
            'spoof_client': getattr(config, 'spoof_client', 'off'),
            'spoof_brand': config.spoof_brand_value(),
            'status_cache': bool(config.status_cache),
            'status_cache_ttl': int(config.status_cache_ttl),
            'certificate': None,
        }
        if self.certificate:
            data['certificate'] = {
                'path': self.certificate['cert_path'],
                'thumbprint': self.certificate['thumbprint'],
                'alt_names': list(self.certificate.get('alt_names', ())),
                'not_after': self.certificate.get('not_after', ''),
            }
        return data
    def status(self, path: str = '/', with_target: bool = False) -> dict:
        snapshot = self.stats.snapshot()
        data = self.describe()
        data.update({
            'path': path,
            'uptime_seconds': round(snapshot['uptime'], 1),
            'active_connections': snapshot['active'],
            'total_connections': snapshot['total'],
            'bytes_to_server': snapshot['bytes_to_server'],
            'bytes_to_client': snapshot['bytes_to_client'],
            'bytes_to_server_human': human_bytes(snapshot['bytes_to_server']),
            'bytes_to_client_human': human_bytes(snapshot['bytes_to_client']),
        })
        if with_target:
            host, port = self._resolve_for_status()
            if host:
                info = self.target_status(host, port, STATUS_TIMEOUT)
                status = info.get('status') or {}
                data['target_probe'] = {
                    'ok': bool(info.get('ok')),
                    'host': host,
                    'port': port,
                    'ping_ms': round(info['ms'], 1) if info.get('ms') else None,
                    'error': info.get('error', ''),
                    'motd': motd_lines(status.get('description')),
                    'version': (status.get('version') or {}).get('name', ''),
                    'players': status.get('players') or {},
                }
        return data
    def forget(self, bridge: Bridge) -> None:
        with self._lock:
            if bridge in self._connections:
                self._connections.discard(bridge)
                self.stats.connection_closed()
    # ---------- routing / target resolution ----------
    def resolve_route(self, path: str) -> dict:
        config = self.config
        raw = (path or '/').strip()
        key = raw.rstrip('/') or '/'
        if getattr(config, 'suffix_route', False):
            return self._resolve_suffix(raw, key)
        routes = self.config.routes or {}
        candidates = [key, path or '/']
        if key != '/':
            candidates.append(key + '/')
        for candidate in candidates:
            if candidate in routes:
                try:
                    host, port = parse_address(routes[candidate])
                except ValueError as exc:
                    self.log.warn(tr('proxy.log.bad_route', path=candidate, error=exc))
                    break
                return {'label': tr('proxy.route.path', path=candidate),
                        'source': routes[candidate], 'host': host, 'port': port}
        host, port = parse_address(self.config.target)
        label = tr('proxy.route.default') if key == '/' \
            else tr('proxy.route.default_missing', path=path)
        return {'label': label, 'source': self.config.target, 'host': host, 'port': port}
    def _resolve_suffix(self, raw: str, key: str) -> dict:
        """Interpret the request path itself as the target server address.

        ``/mc244.com`` forwards to mc244.com (SRV/default port), ``/hypixel.net``
        to hypixel.net, ``/127.0.0.1:25565`` to 127.0.0.1:25565.  ``/`` or a path
        that cannot stand for a server address falls back to the default target.
        """
        config = self.config
        suffix = raw[1:] if raw.startswith('/') else raw
        host, port = '', None
        bad = (not suffix) or ('/' in suffix) or any(
            ch.isspace() or ord(ch) < 0x20 for ch in suffix)
        if not bad:
            try:
                host, port = parse_address(suffix)
            except ValueError:
                host, port = '', None
        if host:
            return {'label': tr('proxy.route.suffix', path='/' + suffix),
                    'source': suffix, 'host': host, 'port': port}
        if raw not in ('', '/'):
            self.log.warn(tr('proxy.log.bad_suffix', path=raw))
        target_host, target_port = parse_address(config.target)
        label = tr('proxy.route.default') if key == '/' \
            else tr('proxy.route.default_missing', path=raw)
        return {'label': label, 'source': config.target,
                'host': target_host, 'port': target_port}
    def resolve_endpoint(self, host: str, port: int | None) -> tuple[str, int]:
        if port:
            return host, int(port)
        now = time.time()
        cached = self._srv_cache.get(host)
        if cached and cached[2] > now:
            return cached[0], cached[1]
        resolved = resolver.resolve_target(host, None, logger=self.log, use_srv=self.config.use_srv)
        self._srv_cache[host] = (resolved[0], resolved[1], now + 300.0)
        return resolved
    def cached_endpoint(self, host: str, port: int | None) -> tuple[str, int] | None:
        """Return an endpoint only when no live DNS query is needed.

        The server-list answer is timed by the browser as ping, so callers on
        that path must not block on SRV/DNS.  An explicit port is always
        immediate; a bare hostname is returned only from the resolve cache.
        """
        if port:
            return host, int(port)
        cached = self._srv_cache.get(host)
        if cached and cached[2] > time.time():
            return cached[0], cached[1]
        return None
    def _resolved_target(self) -> str:
        """Already-resolved target address (report the cache only, no live DNS lookup)."""
        try:
            host, port = parse_address(self.config.target)
        except ValueError:
            return ''
        if port:
            return '%s:%d' % (host, int(port))
        cached = self._srv_cache.get(host)
        if cached:
            return '%s:%d' % (cached[0], cached[1])
        return ''
    def _resolve_for_status(self, timeout: float = STATUS_TIMEOUT) -> tuple[str, int]:
        try:
            host, port = parse_address(self.config.target)
        except ValueError:
            return '', 0
        try:
            return self.resolve_endpoint(host, port)
        except Exception as exc:
            self.log.debug(tr('proxy.log.status_resolve_failed', error=exc))
            return host, int(port or 25565)
