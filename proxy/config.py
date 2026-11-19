"""Configuration: loading, saving, validation and address parsing.

``config.json`` lives in the user's configuration folder (see
:func:`proxy.utils.config_dir`), never beside the executable: a build under
Program Files cannot write there, and replacing the install would otherwise
throw the settings away with it.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .i18n import LANGUAGES, tr, tr_in
from .utils import config_dir, resolve_path

CONFIG_FILENAME = 'config.json'

# Address prefixes we accept; anything else is treated as host[:port] text.
_SCHEMES = ('minecraft://', 'mc://', 'tcp://', 'wss://', 'ws://', 'https://', 'http://')


def _problem(key: str, **values) -> str:
    """Configuration problems are always reported in English.

    They are meant for logs, automation scripts and troubleshooting rather
    than for end users.  Fixed English keeps the diagnostics stable when the
    interface language changes, and avoids falling back to a raw key when a
    translation is missing.
    """
    return tr_in('en', key, **values)


def _bracket_host(host: str) -> str:
    """Wrap an IPv6 literal in brackets for a URL, leaving IPv4 / DNS names
    and hosts already bracketed untouched."""
    host = (host or '').strip()
    if ':' in host and not host.startswith('['):
        return '[%s]' % host
    return host


def parse_address(text: str, default_port: int | None = None) -> tuple[str, int | None]:
    """Parse a forward target.

    Accepts: host / host:port / [IPv6]:port / bare IPv6 / mc://host:port; the
    path part, if any, is ignored.  When the text carries no port this returns
    ``default_port`` (usually None, which hands the decision to SRV lookup).
    """
    value = (text or '').strip()
    if not value:
        raise ValueError(_problem('core.config.address_empty'))
    lowered = value.lower()
    for scheme in _SCHEMES:
        if lowered.startswith(scheme):
            value = value[len(scheme):]
            break
    value = value.split('/', 1)[0].strip()
    if not value:
        raise ValueError(_problem('core.config.address_empty'))
    if value.startswith('['):
        host, _, rest = value[1:].partition(']')
        port_text = rest.lstrip(':').strip()
        return host, int(port_text) if port_text.isdigit() else default_port
    if value.count(':') == 1:
        host, _, port_text = value.partition(':')
        if port_text.isdigit():
            return host.strip(), int(port_text)
    return value, default_port


def normalize_route_path(path: str) -> str:
    """Normalize a route path: trimmed, leading slash, no trailing slash.

    The path ``/`` is the catch-all and is kept as-is; anything else loses its
    trailing slashes (``/minigame/`` becomes ``/minigame``), matching what
    :func:`parse_routes_text` produces.
    """
    text = str(path or '').strip()
    if not text:
        raise ValueError(_problem('core.config.route_missing_path'))
    if not text.startswith('/'):
        text = '/' + text
    return text.rstrip('/') or '/'


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
            raise ValueError(_problem('core.config.route_format'))
        path, _, target = line.partition('=')
        path = path.strip()
        target = target.strip()
        # Neither side may be empty: a blank path would silently become the
        # catch-all "/" route, and a blank target would route to nowhere.
        if not path:
            raise ValueError(_problem('core.config.route_missing_path'))
        if not target:
            raise ValueError(_problem('core.config.route_missing_target', path=path))
        routes[normalize_route_path(path)] = target
    return routes


# Client identity spoof presets for the upstream (target server) side, split by
# the Minecraft era: the identity a client flavour leaves on the wire differs
# with the version the target server runs (see translator.py).
# SPOOF_DEFAULT_BRANDS is the MC|Brand value each preset reports by default.
# Forge up to 1.12.2 speaks the legacy FML handshake and reports "fml,forge";
# Forge 1.13+ reports "forge"; NeoForge (1.20.2+) "neoforge".  The "custom"
# preset reports the user-editable spoof_brand for cases the presets do not
# cover; every other preset uses its own default brand.
SPOOF_CLIENTS = ('off', 'vanilla', 'forge-1.8', 'forge-1.13', 'neoforge', 'fabric', 'custom')
RESOURCE_PACK_MODES = ('forward', 'accept', 'reject', 'spoof')
THEME_MODES = ('light', 'dark', 'system')
# Appearance personalization presets.  A preset is a named (accent, background)
# palette; the Web UI applies the palette's colours when the preset is picked,
# and falls back to 'custom' when the colours no longer match any preset.
# APPEARANCE_PALETTES is the single source of truth for that mapping.
APPEARANCE_PRESETS = ('default', 'ocean', 'forest', 'sunset', 'mono', 'custom')
APPEARANCE_DENSITIES = ('compact', 'comfortable', 'spacious')
APPEARANCE_PALETTES = {
    'default': ('#2f6fed', '#eef1f6'),
    'ocean': ('#0ea5e9', '#e0f2fe'),
    'forest': ('#16a34a', '#dcfce7'),
    'sunset': ('#f97316', '#ffedd5'),
    'mono': ('#525252', '#f5f5f5'),
}


def match_appearance_preset(accent: str, bg_color: str) -> str:
    """Return the preset whose palette matches both colours, or ``'custom'``."""
    pair = ((accent or '').strip().lower(), (bg_color or '').strip().lower())
    for name, (preset_accent, preset_bg) in APPEARANCE_PALETTES.items():
        if pair == (preset_accent, preset_bg):
            return name
    return 'custom'


SPOOF_DEFAULT_BRANDS = {
    'off': '',
    'vanilla': 'vanilla',
    'forge-1.8': 'fml,forge',     # Forge 1.8.x - 1.12.2 (legacy FML handshake)
    'forge-1.13': 'forge',        # Forge 1.13 and newer
    'neoforge': 'neoforge',       # NeoForge 1.20.2 and newer
    'fabric': 'fabric',
    'custom': '',
}


@dataclass
class Config:
    """Every configurable option; maps one-to-one onto config.json."""

    # Schema marker.  Old files predate this key; it lets from_dict() migrate
    # settings whose meaning changed without touching choices made afterwards.
    config_version: int = 2

    # Listening
    listen_host: str = '127.0.0.1'
    wss_port: int = 8443          # wss:// (TLS) listen port
    ws_port: int = 8080           # ws:// (plaintext fallback) listen port; 0 = disabled

    # Forward target.  Empty on purpose: every user connects to a different
    # server, so the app must not ship with a default address.
    target: str = ''
    routes: dict = field(default_factory=dict)   # {'/path': 'host:port'}
    # Connect to any server by interpreting the WebSocket request path as the
    # target address: '/mc244.com' forwards to mc244.com (SRV/default port),
    # '/hypixel.net' to hypixel.net, '/127.0.0.1:25565' to 127.0.0.1:25565.
    # '/' falls back to the default target.  Mutually exclusive with routes:
    # the same path cannot be read as both a route key and a server address,
    # so validate() refuses to start the proxy while both are set.
    suffix_route: bool = False
    use_srv: bool = True
    # Rewrite the server address in the upstream handshake to the real target
    # domain (off by default: data is only touched when it is really needed)
    rewrite_handshake_host: bool = False
    # Protocol translation for browser clients (the EaglercraftX family):
    # autodetect them and answer their private handshake on the server's behalf
    eagler_translate: bool = True
    # 1.20.2+ targets hold the connection in the login state until the client
    # acknowledges the login result, which browser clients never do (their
    # login phase is the EaglercraftX handshake); send that acknowledge in
    # their place so the target can leave the login state (see translator.py).
    # Off = nothing is sent and everything passes through untouched.
    login_ack: bool = True
    # How the proxy handles the server's resource pack prompt. The choices are
    # 'forward' (pass the prompt through), 'accept' (answer accept and drop the
    # prompt), 'reject' (answer reject and drop the prompt), or 'spoof' (answer
    # accept but still drop the prompt so the client never sees it).
    resource_pack_mode: str = 'forward'

    # UI theme: 'light' (always light), 'dark' (always dark), 'system' (follow
    # the OS setting)
    theme: str = 'system'
    # UI appearance / personalization (all optional, persisted in config.json)
    appearance: dict = field(default_factory=dict)
    # Identity spoofing
    # Server brand: the "server identity" browser clients see after connecting
    # (shown in their debug info)
    server_brand: str = 'ServerProtocolBridge'
    # Server version: same as above; empty = use the program version
    server_brand_version: str = ''
    # Client identity spoof preset: which client flavour the proxy imitates at
    # the target server.  'off' is the default and spoofs nothing; 'vanilla'
    # reports a vanilla brand; 'forge-1.8' reproduces the legacy Forge
    # fingerprints (FML marker in the handshake address, REGISTER channel list,
    # "fml,forge" brand); 'forge-1.13' / 'neoforge' / 'fabric' report their own
    # brand.  The FML marker and REGISTER broadcast stay 1.8-only (packet
    # numbers are version-specific); the brand itself is rewritten on every
    # game version, see PlayClientMixin._maybe_rewrite_brand.
    spoof_client: str = 'off'
    # Spoofed client brand: value sent to the target server as the client
    # brand.  Empty = the preset's default (SPOOF_DEFAULT_BRANDS).  On 1.8 it
    # is announced as MC|Brand after login; on every version the client's own
    # brand packet is rewritten to this value (when set), so the target never
    # sees the browser's identity.
    spoof_brand: str = ''

    # Certificates
    tls_enabled: bool = True
    cert_dir: str = 'certs'
    cert_common_name: str = 'localhost'
    cert_extra_names: list = field(default_factory=list)
    cert_days: int = 3650
    cert_generator: str = 'auto'  # auto / python / openssl

    # Run-time options
    # Language for all user-visible text: 'zh' (Chinese, default), 'en'
    # (English) or 'auto' (detect the system language)
    language: str = 'auto'
    # Show the "not yet mature" notice once the proxy starts listening.
    startup_notice: bool = True
    # Web UI: the browser interface the window starts automatically.  It binds
    # to loopback by default; set web_host to 0.0.0.0 to expose it on the LAN.
    # web_port 0 lets the operating system pick a free port.
    web_host: str = '127.0.0.1'
    web_port: int = 8765
    connect_timeout: float = 10.0
    heartbeat_sec: int = 30       # WebSocket heartbeat interval in seconds; 0 = disabled
    max_payload_mb: int = 16      # Max size of a single frame
    # Upper bound on simultaneous client connections.  0 = unlimited.  A
    # listener exposed beyond loopback should set this so one peer cannot fill
    # the process with idle sockets.
    max_connections: int = 0
    # Server-list (Accept: MOTD) status cache.  When enabled, a fresh cached
    # answer is returned immediately and a stale one is refreshed in the
    # background.  When disabled, every list query asks the target server.
    status_cache: bool = True
    status_cache_ttl: int = 30    # seconds a cached status stays fresh
    log_level: str = 'info'
    # Upper bound on how many log lines the hub keeps in memory.  The buffer is
    # a ring: once it is full the oldest line is dropped, so a very long or very
    # chatty session cannot grow memory without limit.  A small value keeps the
    # footprint tiny; a large one leaves room to look back over a whole
    # connection before the earliest lines scroll away.
    log_max_lines: int = 4000
    # Before the service stops -- or the program closes -- tell every connected
    # client why the session is over, using the game's own disconnect packet:
    # a bare socket close is what clients show as an ended data stream
    auto_exit: bool = True

    # Cloud version check: on startup the program asks its update endpoint for
    # the newest release and reports a newer one.  The endpoint is compiled into
    # the program (proxy/update.py) and is deliberately not a setting: it is not
    # read from this file and no window or option offers to edit it.
    update_check: bool = True

    # ---------- Serialization ----------
    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> 'Config':
        config = cls()
        if not isinstance(data, dict):
            return config
        known = {item.name: item for item in fields(cls)}
        data = dict(data)
        try:
            legacy = int(data.get('config_version', 1)) < 2
        except (TypeError, ValueError):
            legacy = True
        if 'spoof_client' not in data:
            # Configurations written before the spoof presets existed carry no
            # preset key; back then the built-in brand default was literally
            # "vanilla", so an untouched value is cleared here to let the
            # current default provide it.  A user-chosen value never changes.
            if str(data.get('spoof_brand', '')).strip().lower() == 'vanilla':
                data['spoof_brand'] = ''
        elif (legacy
              and str(data.get('spoof_client', '')).strip().lower() == 'forge-1.8'
              and not str(data.get('spoof_brand', '')).strip()):
            # The legacy Forge preset was the old default; migrate the old
            # default silently.  A custom brand means the user chose Forge
            # deliberately, so that file is left alone.
            data['spoof_client'] = 'off'
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

    # ---------- Spoofing ----------
    def spoof_brand_value(self) -> str:
        """The exact MC|Brand value to send upstream; empty = send none.

        ``spoof_brand`` overrides the preset default (the ported legacy
        behaviour), and the ``off`` preset means "no spoofing at all", so it
        suppresses the brand regardless.  The ``custom`` preset reports the
        user's brand verbatim and has no default of its own.
        """
        preset = (self.spoof_client or 'off').strip().lower()
        if preset == 'off':
            return ''
        override = (self.spoof_brand or '').strip()
        if override:
            return override
        return SPOOF_DEFAULT_BRANDS.get(preset, '')

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
        # Write a sibling temp file and swap it in: a crash, a disk-full error
        # or a power loss during the write can then never leave a truncated
        # config.json behind (os.replace is atomic on Windows and POSIX).
        temp = target.with_name(target.name + '.tmp')
        try:
            with open(temp, 'w', encoding='utf-8') as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, target)
        except OSError:
            try:
                temp.unlink()
            except OSError:
                pass
            raise
        return target

    # ---------- Validation ----------
    def validate(self) -> list[str]:
        """Return a list of configuration problems (empty means all good).

        The messages are always English so logs stay searchable and
        automation stays stable when the interface language changes.
        """
        problems: list[str] = []
        if not (self.listen_host or '').strip():
            problems.append(_problem('core.config.listen_host_empty'))
        for name, port in ((_problem('core.config.port_wss'), self.wss_port),
                           (_problem('core.config.port_ws'), self.ws_port)):
            if not 0 <= int(port) <= 65535:
                problems.append(_problem('core.config.port_range', name=name))
        if self.tls_enabled and int(self.wss_port) <= 0:
            problems.append(_problem('core.config.tls_needs_wss_port'))
        if not self.tls_enabled and int(self.ws_port) <= 0:
            problems.append(_problem('core.config.tls_needs_ws_port'))
        if self.tls_enabled and int(self.wss_port) > 0 and int(self.ws_port) == int(self.wss_port):
            problems.append(_problem('core.config.ports_conflict'))
        if int(self.max_connections) < 0:
            problems.append(_problem('core.config.max_connections_range'))
        if not (self.target or '').strip():
            problems.append(_problem('core.config.target_empty'))
        else:
            try:
                host, _ = parse_address(self.target)
                if not host:
                    problems.append(_problem('core.config.target_empty'))
            except ValueError as exc:
                problems.append(_problem('core.config.target_invalid', error=exc))
        for path, target in (self.routes or {}).items():
            # Both sides of a route must be non-empty; a hand-edited config file
            # can carry a half route that parse_routes_text would never produce.
            if not (path or '').strip():
                problems.append(_problem('core.config.route_missing_path'))
            if not (target or '').strip():
                problems.append(_problem('core.config.route_missing_target', path=path))
                continue
            try:
                parse_address(target)
            except ValueError:
                problems.append(_problem('core.config.route_target_invalid', path=path, target=target))
        if self.suffix_route and (self.routes or {}):
            problems.append(_problem('core.config.suffix_route_conflict'))
        # Brand / version strings are written into the handshake packet one byte
        # per character, and the client reads them back as ASCII.
        for name, value, limit, required in (
            (_problem('core.config.brand_server'), self.server_brand, 128, True),
            (_problem('core.config.brand_server_version'), self.server_brand_version, 128, False),
            (_problem('core.config.brand_spoof'), self.spoof_brand, 200, False),
        ):
            text = (value or '').strip()
            if not text:
                if required:
                    problems.append(_problem('core.config.name_required', name=name))
                continue
            try:
                text.encode('ascii')
            except UnicodeEncodeError:
                problems.append(_problem('core.config.brand_ascii', name=name))
                continue
            if len(text) > limit:
                problems.append(_problem('core.config.brand_too_long', name=name, limit=limit))
        preset = (self.spoof_client or '').strip().lower()
        if preset not in SPOOF_CLIENTS:
            problems.append(_problem('core.config.spoof_client_invalid',
                                     choices=' / '.join(SPOOF_CLIENTS)))
        if preset == 'custom' and not (self.spoof_brand or '').strip():
            problems.append(_problem('core.config.spoof_custom_required'))
        if int(self.max_payload_mb) <= 0:
            problems.append(_problem('core.config.max_payload_positive'))
        if float(self.connect_timeout) <= 0:
            problems.append(_problem('core.config.connect_timeout_positive'))
        if int(self.heartbeat_sec) < 0:
            problems.append(_problem('core.config.heartbeat_non_negative'))
        if not 1 <= int(self.status_cache_ttl) <= 86400:
            problems.append(_problem('core.config.status_cache_ttl_range'))
        if self.log_level not in ('debug', 'info', 'warn', 'error'):
            problems.append(_problem('core.config.log_level_invalid'))
        if not 50 <= int(self.log_max_lines) <= 100000:
            problems.append(_problem('core.config.log_max_lines_invalid'))
        if (self.language or '').strip().lower() not in LANGUAGES:
            problems.append(_problem('core.config.language_invalid'))
        return problems

    # ---------- Display ----------
    def describe_target(self) -> str:
        try:
            host, port = parse_address(self.target)
        except ValueError:
            return self.target
        host = _bracket_host(host)
        return '%s:%d' % (host, port) if port else tr('core.config.target_srv', host=host)

    def listeners(self) -> list[str]:
        host = _bracket_host(self.listen_host or '127.0.0.1')
        result = []
        if self.tls_enabled and int(self.wss_port) > 0:
            result.append('wss://%s:%d' % (host, int(self.wss_port)))
        if int(self.ws_port) > 0:
            result.append('ws://%s:%d' % (host, int(self.ws_port)))
        return result

    def web_url(self) -> str:
        """The URL a browser on this machine should open for the Web UI."""
        host = (self.web_host or '127.0.0.1').strip() or '127.0.0.1'
        if host in ('0.0.0.0', '::', '[::]'):
            host = '127.0.0.1'
        host = _bracket_host(host)
        return 'http://%s:%d/' % (host, int(self.web_port))

    def validate_web(self) -> list[str]:
        """Problems that only concern the Web UI listener (never the proxy).

        Like validate(), the messages are always English.
        """
        problems: list[str] = []
        if not (self.web_host or '').strip():
            problems.append(_problem('core.config.web_host_empty'))
        if not 0 <= int(self.web_port) <= 65535:
            problems.append(_problem('core.config.web_port_range'))
        return problems

    def wss_url(self) -> str | None:
        host = _bracket_host(self.listen_host or '127.0.0.1')
        if self.tls_enabled and int(self.wss_port) > 0:
            return 'wss://%s:%d' % (host, int(self.wss_port))
        if int(self.ws_port) > 0:
            return 'ws://%s:%d' % (host, int(self.ws_port))
        return None


def default_config_path() -> Path:
    """Where ``config.json`` is read from and written to: the user's
    configuration folder, so it survives reinstalls and Program Files."""
    return config_dir() / CONFIG_FILENAME
