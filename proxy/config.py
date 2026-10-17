"""Configuration: loading, saving, validation and address parsing."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .i18n import LANGUAGES, tr
from .update import DEFAULT_UPDATE_URL, split_urls
from .utils import app_dir, resolve_path

CONFIG_FILENAME = 'config.json'

# Address prefixes we accept; anything else is treated as host[:port] text.
_SCHEMES = ('minecraft://', 'mc://', 'tcp://', 'wss://', 'ws://', 'https://', 'http://')


def parse_address(text: str, default_port: int | None = None) -> tuple[str, int | None]:
    """Parse a forward target.

    Accepts: host / host:port / [IPv6]:port / bare IPv6 / mc://host:port; the
    path part, if any, is ignored.  When the text carries no port this returns
    ``default_port`` (usually None, which hands the decision to SRV lookup).
    """
    value = (text or '').strip()
    if not value:
        raise ValueError(tr('core.config.address_empty'))
    lowered = value.lower()
    for scheme in _SCHEMES:
        if lowered.startswith(scheme):
            value = value[len(scheme):]
            break
    value = value.split('/', 1)[0].strip()
    if not value:
        raise ValueError(tr('core.config.address_empty'))
    if value.startswith('['):
        host, _, rest = value[1:].partition(']')
        port_text = rest.lstrip(':').strip()
        return host, int(port_text) if port_text.isdigit() else default_port
    if value.count(':') == 1:
        host, _, port_text = value.partition(':')
        if port_text.isdigit():
            return host.strip(), int(port_text)
    return value, default_port


def format_routes_text(routes: dict) -> str:
    """Render the path map as editable text: one ``path=target`` per line."""
    return '\n'.join('%s=%s' % (path, target) for path, target in (routes or {}).items())


def parse_routes_text(text: str) -> dict:
    """Parse the path map text from the UI: one ``path=target`` per line."""
    routes: dict = {}
    for raw_line in (text or '').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            raise ValueError(tr('core.config.route_format'))
        path, _, target = line.partition('=')
        path = path.strip()
        target = target.strip()
        if not path.startswith('/'):
            path = '/' + path
        if not target:
            raise ValueError(tr('core.config.route_missing_target', path=path))
        routes[path.rstrip('/') or '/'] = target
    return routes


@dataclass
class Config:
    """Every configurable option; maps one-to-one onto config.json."""

    # Listening
    listen_host: str = '127.0.0.1'
    wss_port: int = 8443          # wss:// (TLS) listen port
    ws_port: int = 8080           # ws:// (plaintext fallback) listen port; 0 = disabled

    # Forward target
    target: str = 'mc244.com'
    routes: dict = field(default_factory=dict)   # {'/path': 'host:port'}
    use_srv: bool = True
    # Rewrite the server address in the upstream handshake to the real target
    # domain (off by default: data is only touched when it is really needed)
    rewrite_handshake_host: bool = False
    # Protocol translation for browser clients (EaglercraftX family, e.g. MCJS):
    # autodetect them and answer their private handshake on the server's behalf
    eagler_translate: bool = True

    # Identity spoofing
    # Server brand: the "server identity" browser clients see after connecting
    # (shown in their debug info)
    server_brand: str = 'MCJS-Proxy'
    # Server version: same as above; empty = use the program version
    server_brand_version: str = ''
    # Spoofed client brand: MC|Brand value sent to the target server after login;
    # empty = do not send.  A vanilla 1.8.8 client sends "vanilla"; use another
    # brand name (e.g. forge/1.8.8) to pretend to be a different client
    spoof_brand: str = 'vanilla'

    # Certificates
    tls_enabled: bool = True
    cert_dir: str = 'certs'
    cert_common_name: str = 'localhost'
    cert_extra_names: list = field(default_factory=list)
    cert_days: int = 3650
    cert_generator: str = 'auto'  # auto / python / openssl

    # Run-time options
    # Language for all user-visible text: 'en' (English, default) or 'zh' (Chinese)
    language: str = 'en'
    connect_timeout: float = 10.0
    heartbeat_sec: int = 30       # WebSocket heartbeat interval in seconds; 0 = disabled
    max_payload_mb: int = 16      # Max size of a single frame
    log_level: str = 'info'

    # Cloud version check: on startup the program asks the endpoint(s) below for
    # the newest release and says so when a newer one exists; several URLs may be
    # listed (comma/space separated) and are tried in order, empty = disabled
    update_check: bool = True
    update_url: str = DEFAULT_UPDATE_URL

    # ---------- Serialization ----------
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'Config':
        config = cls()
        if not isinstance(data, dict):
            return config
        known = {item.name: item for item in fields(cls)}
        for name, value in data.items():
            if name not in known:
                continue
            current = getattr(config, name)
            try:
                if isinstance(current, bool):
                    value = bool(value)
                elif isinstance(current, int) and not isinstance(value, bool):
                    value = int(value)
                elif isinstance(current, float):
                    value = float(value)
                elif isinstance(current, str):
                    value = str(value)
                elif isinstance(current, list):
                    value = list(value)
                elif isinstance(current, dict):
                    value = dict(value)
            except (TypeError, ValueError):
                continue
            setattr(config, name, value)
        return config

    # ---------- Paths ----------
    @property
    def config_path(self) -> Path:
        return resolve_path(CONFIG_FILENAME)

    @property
    def resolved_cert_dir(self) -> Path:
        return resolve_path(self.cert_dir)

    @property
    def max_payload_bytes(self) -> int:
        return max(1, int(self.max_payload_mb)) * 1024 * 1024

    # ---------- Load / save ----------
    @classmethod
    def load(cls, path: str | Path | None = None) -> 'Config':
        target = Path(path) if path else resolve_path(CONFIG_FILENAME)
        try:
            raw = target.read_text(encoding='utf-8-sig')
            return cls.from_dict(json.loads(raw))
        except FileNotFoundError:
            return cls()
        except (OSError, ValueError):
            return cls()

    @classmethod
    def load_or_create(cls, path: str | Path | None = None, logger=None) -> tuple['Config', Path, bool]:
        """Load the configuration; when the file does not exist yet, write one
        with the defaults so the user can simply edit it."""
        target = Path(path) if path else resolve_path(CONFIG_FILENAME)
        if target.exists():
            return cls.load(target), target, False
        config = cls()
        try:
            config.save(target)
            created = True
        except OSError:
            created = False
        if logger is not None and created:
            logger.info(tr('core.config.default_created', path=target))
        return config, target, created

    def save(self, path: str | Path | None = None) -> Path:
        target = Path(path) if path else resolve_path(CONFIG_FILENAME)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + '\n'
        target.write_text(payload, encoding='utf-8')
        return target

    # ---------- Validation ----------
    def validate(self) -> list[str]:
        """Return a list of configuration problems (empty means all good)."""
        problems: list[str] = []
        if not (self.listen_host or '').strip():
            problems.append(tr('core.config.listen_host_empty'))
        for name, port in ((tr('core.config.port_wss'), self.wss_port),
                           (tr('core.config.port_ws'), self.ws_port)):
            if not 0 <= int(port) <= 65535:
                problems.append(tr('core.config.port_range', name=name))
        if self.tls_enabled and int(self.wss_port) <= 0:
            problems.append(tr('core.config.tls_needs_wss_port'))
        if not self.tls_enabled and int(self.ws_port) <= 0:
            problems.append(tr('core.config.tls_needs_ws_port'))
        if self.tls_enabled and int(self.wss_port) > 0 and int(self.ws_port) == int(self.wss_port):
            problems.append(tr('core.config.ports_conflict'))
        try:
            host, _ = parse_address(self.target)
            if not host:
                problems.append(tr('core.config.target_empty'))
        except ValueError as exc:
            problems.append(tr('core.config.target_invalid', error=exc))
        for path, target in (self.routes or {}).items():
            try:
                parse_address(target)
            except ValueError:
                problems.append(tr('core.config.route_target_invalid', path=path, target=target))
        # Brand / version strings are written into the handshake packet one byte
        # per character, and the client reads them back as ASCII.
        for name, value, limit, required in (
            (tr('core.config.brand_server'), self.server_brand, 128, True),
            (tr('core.config.brand_server_version'), self.server_brand_version, 128, False),
            (tr('core.config.brand_spoof'), self.spoof_brand, 200, False),
        ):
            text = (value or '').strip()
            if not text:
                if required:
                    problems.append(tr('core.config.name_required', name=name))
                continue
            try:
                text.encode('ascii')
            except UnicodeEncodeError:
                problems.append(tr('core.config.brand_ascii', name=name))
                continue
            if len(text) > limit:
                problems.append(tr('core.config.brand_too_long', name=name, limit=limit))
        if int(self.max_payload_mb) <= 0:
            problems.append(tr('core.config.max_payload_positive'))
        if float(self.connect_timeout) <= 0:
            problems.append(tr('core.config.connect_timeout_positive'))
        if int(self.heartbeat_sec) < 0:
            problems.append(tr('core.config.heartbeat_non_negative'))
        if self.log_level not in ('debug', 'info', 'warn', 'error'):
            problems.append(tr('core.config.log_level_invalid'))
        if (self.language or '').strip().lower() not in LANGUAGES:
            problems.append(tr('core.config.language_invalid'))
        if self.update_check:
            for url in split_urls(self.update_url):
                if not url.lower().startswith(('https://', 'http://')):
                    problems.append(tr('core.config.update_url_invalid'))
                    break
        return problems

    # ---------- Display ----------
    def describe_target(self) -> str:
        try:
            host, port = parse_address(self.target)
        except ValueError:
            return self.target
        return '%s:%d' % (host, port) if port else tr('core.config.target_srv', host=host)

    def listeners(self) -> list[str]:
        host = self.listen_host or '127.0.0.1'
        result = []
        if self.tls_enabled and int(self.wss_port) > 0:
            result.append('wss://%s:%d' % (host, int(self.wss_port)))
        if int(self.ws_port) > 0:
            result.append('ws://%s:%d' % (host, int(self.ws_port)))
        return result

    def wss_url(self) -> str | None:
        host = self.listen_host or '127.0.0.1'
        if self.tls_enabled and int(self.wss_port) > 0:
            return 'wss://%s:%d' % (host, int(self.wss_port))
        if int(self.ws_port) > 0:
            return 'ws://%s:%d' % (host, int(self.ws_port))
        return None


def default_config_path() -> Path:
    return app_dir() / CONFIG_FILENAME
