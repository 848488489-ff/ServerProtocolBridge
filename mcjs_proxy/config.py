"""配置: 载入、保存、校验与地址解析。"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .utils import app_dir, resolve_path

CONFIG_FILENAME = 'config.json'

# 支持的地址写法前缀
_SCHEMES = ('minecraft://', 'mc://', 'tcp://', 'wss://', 'ws://', 'https://', 'http://')


def parse_address(text: str, default_port: int | None = None) -> tuple[str, int | None]:
    """解析转发目标。

    支持: host / host:port / [IPv6]:port / 裸 IPv6 / mc://host:port, 自动忽略路径部分。
    没有端口时返回 default_port(通常是 None, 表示交给 SRV 解析)。
    """
    value = (text or '').strip()
    if not value:
        raise ValueError('地址不能为空')
    lowered = value.lower()
    for scheme in _SCHEMES:
        if lowered.startswith(scheme):
            value = value[len(scheme):]
            break
    value = value.split('/', 1)[0].strip()
    if not value:
        raise ValueError('地址不能为空')
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
    """把路径映射转成界面里可编辑的文本: 每行 `路径=目标`。"""
    return '\n'.join('%s=%s' % (path, target) for path, target in (routes or {}).items())


def parse_routes_text(text: str) -> dict:
    """解析界面里的路径映射文本, 每行 `路径=目标`。"""
    routes: dict = {}
    for raw_line in (text or '').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue
        if '=' not in line:
            raise ValueError('路径映射格式应为 "路径=目标", 例如: /mc244=mc244.com')
        path, _, target = line.partition('=')
        path = path.strip()
        target = target.strip()
        if not path.startswith('/'):
            path = '/' + path
        if not target:
            raise ValueError('路径映射 "%s" 缺少目标地址' % path)
        routes[path.rstrip('/') or '/'] = target
    return routes


@dataclass
class Config:
    """全部可配置项, 与 config.json 一一对应。"""

    # 监听
    listen_host: str = '127.0.0.1'
    wss_port: int = 8443          # wss://(TLS) 监听端口
    ws_port: int = 8080           # ws://(明文, 备用) 监听端口, 0 = 不监听

    # 转发目标
    target: str = 'mc244.com'
    routes: dict = field(default_factory=dict)   # {'/路径': 'host:port'}
    use_srv: bool = True
    # 把上行握手包里的服务器地址改写成真实目标域名(默认关闭: 只在确实需要时才动数据)
    rewrite_handshake_host: bool = False

    # 证书
    tls_enabled: bool = True
    cert_dir: str = 'certs'
    cert_common_name: str = 'localhost'
    cert_extra_names: list = field(default_factory=list)
    cert_days: int = 3650
    cert_generator: str = 'auto'  # auto / python / openssl

    # 运行参数
    connect_timeout: float = 10.0
    heartbeat_sec: int = 30       # WebSocket 心跳间隔, 0 = 关闭
    max_payload_mb: int = 16      # 单帧上限
    log_level: str = 'info'

    # ---------- 序列化 ----------
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

    # ---------- 路径 ----------
    @property
    def config_path(self) -> Path:
        return resolve_path(CONFIG_FILENAME)

    @property
    def resolved_cert_dir(self) -> Path:
        return resolve_path(self.cert_dir)

    @property
    def max_payload_bytes(self) -> int:
        return max(1, int(self.max_payload_mb)) * 1024 * 1024

    # ---------- 载入 / 保存 ----------
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
        """载入配置; 不存在时用默认值写一份, 方便用户直接改。"""
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
            logger.info('已生成默认配置文件: %s' % target)
        return config, target, created

    def save(self, path: str | Path | None = None) -> Path:
        target = Path(path) if path else resolve_path(CONFIG_FILENAME)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + '\n'
        target.write_text(payload, encoding='utf-8')
        return target

    # ---------- 校验 ----------
    def validate(self) -> list[str]:
        """返回配置问题列表(空列表表示没问题)。"""
        problems: list[str] = []
        if not (self.listen_host or '').strip():
            problems.append('监听地址不能为空')
        for name, port in (('wss 端口', self.wss_port), ('ws 端口', self.ws_port)):
            if not 0 <= int(port) <= 65535:
                problems.append('%s 必须在 0~65535 之间' % name)
        if self.tls_enabled and int(self.wss_port) <= 0:
            problems.append('启用了 TLS 就必须设置 wss 端口(或关闭 TLS 只用 ws)')
        if not self.tls_enabled and int(self.ws_port) <= 0:
            problems.append('TLS 已关闭, 必须设置 ws 端口')
        if self.tls_enabled and int(self.wss_port) > 0 and int(self.ws_port) == int(self.wss_port):
            problems.append('wss 端口与 ws 端口不能相同')
        try:
            host, _ = parse_address(self.target)
            if not host:
                problems.append('转发目标不能为空')
        except ValueError as exc:
            problems.append('转发目标无效: %s' % exc)
        for path, target in (self.routes or {}).items():
            try:
                parse_address(target)
            except ValueError:
                problems.append('路径映射 %s 的目标无效: %s' % (path, target))
        if int(self.max_payload_mb) <= 0:
            problems.append('单帧上限必须大于 0')
        if float(self.connect_timeout) <= 0:
            problems.append('连接超时必须大于 0')
        if int(self.heartbeat_sec) < 0:
            problems.append('心跳间隔不能为负数')
        if self.log_level not in ('debug', 'info', 'warn', 'error'):
            problems.append('日志级别只能是 debug / info / warn / error')
        return problems

    # ---------- 展示 ----------
    def describe_target(self) -> str:
        try:
            host, port = parse_address(self.target)
        except ValueError:
            return self.target
        return '%s:%d' % (host, port) if port else '%s (按 SRV 解析, 缺省 25565)' % host

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