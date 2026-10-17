"""转发核心: 把本地 wss:// / ws:// 的 WebSocket 连接桥接成目标 Minecraft 服务器的 TCP 连接。

每条 WebSocket 连接都会独立建立一条到目标服务器的 TCP 连接, 双向原样搬运字节,
不做任何协议解析与修改 —— 与原版客户端直连服务器的数据完全一致。
"""

from __future__ import annotations

import base64
import json
import socket
import ssl
import threading
import time

from . import certs, handshake, resolver, wsproto
from .config import Config, parse_address
from .logger import NullLogger
from .utils import human_bytes
from .version import APP_NAME, SERVICE_NAME, VERSION

RECV_SIZE = 65536
HANDSHAKE_TIMEOUT = 15.0
HTTP_HEAD_TIMEOUT = 15.0
HTTP_HEAD_MAX = 16384
HANDSHAKE_MAX_BUFFER = 4096
SRV_CACHE_SECONDS = 300.0


class _Abort(Exception):
    """握手阶段的正常终止。"""


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


class Bridge:
    """一条 WebSocket 客户端连接 <-> 一条目标服务器 TCP 连接。"""

    def __init__(self, server: 'ProxyServer', sock: socket.socket, addr, scheme: str, log):
        self.server = server
        self.config = server.config
        self.log = log
        self.sock: socket.socket | None = sock
        self.tcp: socket.socket | None = None
        self.addr = addr
        self.scheme = scheme
        self.id = server.next_id()
        self.decoder = wsproto.FrameDecoder(max_payload=server.config.max_payload_bytes)
        self.subprotocol: str | None = None
        self.base64_mode = False
        self.handshake_done = False
        self.closing = threading.Event()
        self.close_sent = False
        self.ws_closed = False
        self.close_reason = ''
        self.bytes_to_server = 0
        self.bytes_to_client = 0
        self.last_pong = time.time()
        self.started_at = time.time()
        self.route_label = ''
        self.endpoint: tuple[str, int] | None = None
        self._pending = b''
        self._handshake_buffer = b''
        self.frames_in = 0
        self.handshake_seen = False          # 上行开头的握手包是否已解析过
        self.handshake_info: dict | None = None
        self.target_sent_any = False         # 目标服务器是否回过数据

    # ---------- 生命周期 ----------
    def run(self) -> None:
        try:
            self._handle()
        except _Abort:
            pass
        except Exception as exc:  # 保证单条连接出错不会拖垮服务
            self.log.error('#%d 连接处理异常: %s' % (self.id, exc))
        finally:
            self._cleanup()

    def _handle(self) -> None:
        config = self.config
        sock = self.sock
        sock.settimeout(HANDSHAKE_TIMEOUT)
        if self.scheme == 'wss':
            try:
                sock = self.sock = self.server.tls_context.wrap_socket(sock, server_side=True)
            except (ssl.SSLError, OSError) as exc:
                self.log.debug('#%d TLS 握手失败: %s' % (self.id, exc))
                raise _Abort()
        sock.settimeout(HTTP_HEAD_TIMEOUT)

        head = self._read_http_head(sock)
        if head is None:
            raise _Abort()
        try:
            request_line, headers = wsproto.parse_http_head(head)
        except Exception:
            self._send_error(400, 'Bad Request')
            raise _Abort()
        parts = request_line.split(' ')
        if len(parts) < 3:
            self._send_error(400, 'Bad Request')
            raise _Abort()
        method, raw_path = parts[0], parts[1]
        path = raw_path.split('?', 1)[0]

        if headers.get('upgrade', '').lower() != 'websocket':
            self._send_status_page(method, path)
            raise _Abort()

        key = headers.get('sec-websocket-key', '')
        if not key:
            self._send_error(400, 'Missing Sec-WebSocket-Key')
            raise _Abort()
        if headers.get('sec-websocket-version', '') != '13':
            self._send_error(426, 'Upgrade Required', extra='Sec-WebSocket-Version: 13\r\n')
            raise _Abort()

        self.subprotocol = wsproto.first_subprotocol(headers.get('sec-websocket-protocol'))
        if self.subprotocol and self.subprotocol.lower() == 'base64':
            self.base64_mode = True
        sock.sendall(wsproto.handshake_response(key, self.subprotocol))
        self.handshake_done = True
        self._pending = head.split(b'\r\n\r\n', 1)[1]
        sock.settimeout(None)
        _set_nodelay(sock)
        self.last_pong = time.time()

        route = self.server.resolve_route(path)
        self.route_label = route['label']
        host, port = self.server.resolve_endpoint(route['host'], route['port'])
        self.endpoint = (host, port)
        self.log.info('#%d %s 接入 %s:%s -> %s [%s]'
                      % (self.id, self.scheme.upper(), self.addr[0], self.addr[1],
                         route['source'], route['label']))

        try:
            self.tcp = socket.create_connection((host, port), timeout=float(config.connect_timeout))
        except OSError as exc:
            self.log.warn('#%d 连接目标服务器 %s:%d 失败: %s' % (self.id, host, port, exc))
            self.close_reason = '无法连接目标服务器 %s:%d' % (host, port)
            self._send_close(1011, 'cannot reach target')
            raise _Abort()
        self.tcp.settimeout(None)
        _set_nodelay(self.tcp)
        try:
            self.tcp.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        except OSError:
            pass
        self.log.info('#%d 已连接目标服务器 %s:%d' % (self.id, host, port))

        if int(config.heartbeat_sec) > 0:
            threading.Thread(target=self._heartbeat_loop, daemon=True,
                             name='mcjs-hb-%d' % self.id).start()
        threading.Thread(target=self._pump_from_client, daemon=True,
                         name='mcjs-ws-%d' % self.id).start()
        self._pump_from_server()

    # ---------- WebSocket 侧读取(客户端 -> 目标服务器) ----------
    def _pump_from_client(self) -> None:
        sock = self.sock
        try:
            while not self.closing.is_set():
                if self._pending:
                    chunk, self._pending = self._pending, b''
                else:
                    chunk = sock.recv(RECV_SIZE)
                if not chunk:
                    self.close_reason = self.close_reason or '客户端关闭了连接'
                    self._send_close(1001, 'client gone')
                    break
                try:
                    frames = self.decoder.feed(chunk)
                except wsproto.ProtocolError as exc:
                    self.log.warn('#%d 协议错误: %s' % (self.id, exc))
                    self.close_reason = '协议错误: %s' % exc
                    self._send_close(exc.close_code, 'protocol error')
                    break
                for frame in frames:
                    if not self._handle_frame(frame):
                        break
        except (OSError, ssl.SSLError) as exc:
            if not self.closing.is_set():
                self.log.debug('#%d 客户端连接中断: %s' % (self.id, exc))
                self.close_reason = self.close_reason or '客户端连接中断'
        finally:
            self._shutdown_tcp()

    def _handle_frame(self, frame: wsproto.Frame) -> bool:
        if frame.opcode in (wsproto.OP_BINARY, wsproto.OP_TEXT):
            self.frames_in += 1
            if self.frames_in <= 4:      # 前几帧的内容对排查很关键, 只写 debug 日志
                self.log.debug('#%d 上行帧 #%d %s 长度 %d, 内容: %s'
                               % (self.id, self.frames_in,
                                  '文本帧' if frame.opcode == wsproto.OP_TEXT else '二进制帧',
                                  len(frame.payload), handshake.hex_preview(frame.payload)))
            self._forward_to_server(self._decode_payload(frame))
            return not self.closing.is_set()
        if frame.opcode == wsproto.OP_PING:
            self._send_frame(wsproto.OP_PONG, frame.payload)
            return True
        if frame.opcode == wsproto.OP_PONG:
            self.last_pong = time.time()
            return True
        if frame.opcode == wsproto.OP_CLOSE:
            code, reason = wsproto.parse_close_payload(frame.payload)
            if code in (1005, 1006):
                code = 1000
            self.close_reason = '客户端关闭连接 (code=%d%s)' % (code, ' ' + reason if reason else '')
            self._send_close(code, '')
            return False
        return True

    def _decode_payload(self, frame: wsproto.Frame) -> bytes:
        if frame.opcode != wsproto.OP_TEXT:
            return frame.payload
        if not self.base64_mode:
            self.base64_mode = True
            self.log.warn('#%d 收到文本帧, 自动切换为 base64 传输模式' % self.id)
        data = wsproto.decode_base64_text(frame.payload)
        if data is None:
            preview = frame.payload[:100].decode('utf-8', 'replace')
            self.log.warn('#%d 文本帧不是有效的 base64, 已丢弃 %d 字节 (开头: %r)'
                          % (self.id, len(frame.payload), preview))
            return b''
        self.log.debug('#%d 文本帧 %d 字节 -> base64 解码出 %d 字节'
                       % (self.id, len(frame.payload), len(data)))
        return data

    def _forward_to_server(self, data: bytes) -> None:
        if not data or self.closing.is_set():
            return
        data = self._inspect_handshake(data)
        # 注意: self.tcp 可能刚被服务端线程关掉并置空, 所以这里用局部变量并且判空
        tcp = self.tcp
        if not data or tcp is None or self.closing.is_set():
            return
        try:
            tcp.sendall(data)
        except OSError as exc:
            if not self.closing.is_set():
                self.log.warn('#%d 发送到目标服务器失败: %s' % (self.id, exc))
                self.close_reason = '发送到目标服务器失败: %s' % exc
            self.closing.set()
            return
        self.bytes_to_server += len(data)
        self.server.stats.add_bytes(to_server=len(data))

    def _inspect_handshake(self, data: bytes) -> bytes:
        """只对上行开头的握手包做一次解析(写日志), 必要时按配置改写其中的地址。

        客户端有可能把握手包拆成几次发送, 这里会先攒齐再转发;
        其余所有字节一律原样转发, 不改任何游戏数据。
        """
        if self.handshake_seen:
            return data
        buffer = self._handshake_buffer + data
        size = handshake.packet_size(buffer)
        if (size is not None and size <= HANDSHAKE_MAX_BUFFER and len(buffer) < size
                and handshake.looks_like_handshake(buffer)):
            self._handshake_buffer = buffer
            self.log.debug('#%d 握手包还差 %d 字节, 先缓存等收齐' % (self.id, size - len(buffer)))
            return b''
        self.handshake_seen = True
        self._handshake_buffer = b''
        info = handshake.parse_handshake(buffer)
        if info is None:
            self.log.debug('#%d 上行首包不是握手包, 原样转发; 前 64 字节: %s'
                           % (self.id, handshake.hex_preview(buffer)))
            return buffer
        self.handshake_info = info
        self.log.info('#%d 握手包: %s' % (self.id, handshake.describe_handshake(info)))
        if not getattr(self.config, 'rewrite_handshake_host', False) or not self.endpoint:
            return buffer
        host, port = self.endpoint
        rewritten = handshake.rewrite_handshake(buffer, host, port)
        if rewritten is None:
            self.log.warn('#%d 握手地址改写失败, 已按原样转发' % self.id)
            return buffer
        if rewritten == buffer:
            return buffer
        self.log.info('#%d 已把握手地址改写为 %s:%d' % (self.id, host, port))
        return rewritten

    # ---------- TCP 侧读取(目标服务器 -> 客户端) ----------
    def _pump_from_server(self) -> None:
        tcp = self.tcp
        try:
            while not self.closing.is_set():
                data = tcp.recv(RECV_SIZE)
                if not data:
                    self.close_reason = self.close_reason or '目标服务器关闭了连接'
                    break
                self.target_sent_any = True
                self._send_payload(data)
                self.bytes_to_client += len(data)
                self.server.stats.add_bytes(to_client=len(data))
        except (OSError, ssl.SSLError) as exc:
            if not self.closing.is_set():
                self.log.debug('#%d 与目标服务器的连接中断: %s' % (self.id, exc))
                self.close_reason = self.close_reason or '与目标服务器的连接中断'
        finally:
            self._send_close(1000, 'session closed')
            self._shutdown_ws()

    def _send_payload(self, data: bytes) -> None:
        if self.base64_mode:
            self._send_frame(wsproto.OP_TEXT, base64.b64encode(data))
        else:
            self._send_frame(wsproto.OP_BINARY, data)

    # ---------- WebSocket 发送 ----------
    def _send_frame(self, opcode: int, payload: bytes) -> None:
        if not self.handshake_done or self.close_sent or self.ws_closed:
            return
        try:
            self.sock.sendall(wsproto.encode_frame(opcode, payload))
        except (OSError, ssl.SSLError) as exc:
            if not self.closing.is_set():
                self.log.debug('#%d 发送到客户端失败: %s' % (self.id, exc))
            self.closing.set()

    def _send_close(self, code: int, reason: str) -> None:
        """发送关闭帧并收尾(重复调用无副作用)。"""
        if not self.close_sent:
            self.close_sent = True
            if self.handshake_done and not self.ws_closed:
                try:
                    self.sock.sendall(wsproto.encode_frame(
                        wsproto.OP_CLOSE, wsproto.close_payload(code, reason)))
                except (OSError, ssl.SSLError):
                    pass
        self.closing.set()
        self._shutdown_tcp()

    def request_shutdown(self, reason: str) -> None:
        """服务端主动断开(停止监听时调用)。"""
        if not self.close_reason:
            self.close_reason = reason
        self._send_close(1001, 'server stopping')

    # ---------- 套接字收尾 ----------
    def _shutdown_tcp(self) -> None:
        tcp, self.tcp = self.tcp, None
        if tcp is not None:
            try:
                tcp.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                tcp.close()
            except OSError:
                pass

    def _shutdown_ws(self) -> None:
        if self.ws_closed:
            return
        self.ws_closed = True
        sock, self.sock = self.sock, None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass

    # ---------- HTTP / 握手辅助 ----------
    def _read_http_head(self, sock: socket.socket) -> bytes | None:
        data = b''
        deadline = time.time() + HTTP_HEAD_TIMEOUT
        while b'\r\n\r\n' not in data:
            if len(data) > HTTP_HEAD_MAX or time.time() > deadline:
                return None
            try:
                chunk = sock.recv(4096)
            except (socket.timeout, OSError, ssl.SSLError):
                return None
            if not chunk:
                return None
            data += chunk
        return data

    def _send_error(self, status: str, message: str, extra: str = '') -> None:
        body = json.dumps({'error': message, 'service': SERVICE_NAME},
                          ensure_ascii=False).encode('utf-8')
        head = ('HTTP/1.1 %s\r\nContent-Type: application/json; charset=utf-8\r\n'
                'Content-Length: %d\r\nConnection: close\r\n%s\r\n' % (status, len(body), extra))
        try:
            if self.sock is not None:
                self.sock.sendall(head.encode('ascii') + body)
        except (OSError, ssl.SSLError):
            pass
        if not self.close_reason:
            self.close_reason = 'HTTP %s' % status

    def _send_status_page(self, method: str, path: str) -> None:
        body = json.dumps(self.server.status(path), ensure_ascii=False, indent=2).encode('utf-8')
        try:
            if self.sock is not None:
                self.sock.sendall(wsproto.http_response('200 OK', body))
        except (OSError, ssl.SSLError):
            pass
        self.log.debug('#%d 状态页请求 %s %s' % (self.id, method, path))

    # ---------- 心跳 ----------
    def _heartbeat_loop(self) -> None:
        interval = max(1, int(self.config.heartbeat_sec))
        while not self.closing.wait(interval):
            if time.time() - self.last_pong > interval * 2 + 5:
                self.log.warn('#%d 心跳超时, 断开连接' % self.id)
                self.close_reason = '心跳超时'
                self._send_close(1001, 'heartbeat timeout')
                return
            self._send_frame(wsproto.OP_PING, b'')

    # ---------- 收尾 ----------
    def _cleanup(self) -> None:
        self._shutdown_tcp()
        self._shutdown_ws()
        self.log.info('#%d 连接结束, 持续 %.1f 秒: %s | 上行 %s, 下行 %s'
                      % (self.id, time.time() - self.started_at,
                         self.close_reason or '正常关闭',
                         human_bytes(self.bytes_to_server), human_bytes(self.bytes_to_client)))
        for hint in self._diagnose():
            self.log.warn('#%d %s' % (self.id, hint))
        self.server.forget(self)

    def _diagnose(self) -> list[str]:
        """连接异常结束时给出一句可能原因, 免得只能看到"连接结束"四个字。"""
        hints: list[str] = []
        if self.target_sent_any:
            return hints
        info = self.handshake_info
        if info is None:
            return hints
        if info['next_state'] == 2:      # 登录
            hints.append('目标服务器收到登录请求后一个字节都没回就把连接关了, 常见原因:')
            if info['address'] not in ('',) and self.endpoint:
                host = self.endpoint[0]
                if info['address'] not in host and ':' not in info['address']:
                    hints.append('  · 握手里的地址 "%s" 和服务器的真实域名 "%s" 不一致, '
                                 '部分服务器会按地址校验/分流 —— 可以试试打开"握手地址改写"'
                                 % (info['address'], host))
            hints.append('  · 客户端协议版本 %d 不被该服务器支持(服务端有时直接断开而不发提示)'
                         % info['protocol'])
            hints.append('  · 该服务器要求正版/白名单/特定端口, 或按访问来源做了拦截')
        return hints


def _set_nodelay(sock: socket.socket) -> None:
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except OSError:
        pass


class ProxyServer:
    """监听器 + 连接管理。"""

    def __init__(self, config: Config, logger=None):
        self.config = config
        self.log = logger or NullLogger()
        self.stats = Stats()
        self.tls_context: ssl.SSLContext | None = None
        self.certificate: dict | None = None
        self.running = False
        self._listeners: list[tuple[socket.socket, str]] = []
        self._connections: set[Bridge] = set()
        self._accept_threads: list[threading.Thread] = []
        self._conn_threads: set[threading.Thread] = set()
        self._lock = threading.Lock()
        self._srv_cache: dict[str, tuple[str, int, float]] = {}
        self._id_counter = 0

    # ---------- 公共接口 ----------
    def next_id(self) -> int:
        with self._lock:
            self._id_counter += 1
            return self._id_counter

    def start(self) -> dict:
        config = self.config
        problems = config.validate()
        if problems:
            raise ValueError('配置有误: ' + '; '.join(problems))

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
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(self.certificate['cert_path'], self.certificate['key_path'])
            self.tls_context = context

        listeners: list[str] = []
        self.running = True
        try:
            if config.tls_enabled and int(config.wss_port) > 0:
                listeners.append(self._start_listener(int(config.wss_port), 'wss'))
            if int(config.ws_port) > 0:
                listeners.append(self._start_listener(int(config.ws_port), 'ws'))
        except Exception:
            self.running = False
            for listener, _scheme in self._listeners:
                try:
                    listener.close()
                except OSError:
                    pass
            self._listeners = []
            raise
        self.log.info('监听就绪: %s' % ', '.join(listeners))
        return self.describe()

    def stop(self) -> None:
        if not self.running:
            return
        self.running = False
        for listener, _scheme in self._listeners:
            try:
                listener.close()
            except OSError:
                pass
        self._listeners = []
        with self._lock:
            bridges = list(self._connections)
        for bridge in bridges:
            try:
                bridge.request_shutdown('本地服务已停止')
            except Exception:
                pass
        for thread in list(self._accept_threads) + list(self._conn_threads):
            thread.join(timeout=2.0)
        self._accept_threads = []
        self.log.info('服务已停止')

    def describe(self) -> dict:
        config = self.config
        data = {
            'service': SERVICE_NAME,
            'app': APP_NAME,
            'version': VERSION,
            'running': self.running,
            'target': config.describe_target(),
            'routes': dict(config.routes or {}),
            'use_srv': bool(config.use_srv),
            'listeners': config.listeners() if self.running else [],
            'wss_url': config.wss_url() if self.running else None,
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

    def status(self, path: str = '/') -> dict:
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
        return data

    def forget(self, bridge: Bridge) -> None:
        with self._lock:
            if bridge in self._connections:
                self._connections.discard(bridge)
                self.stats.connection_closed()

    # ---------- 路由 / 目标解析 ----------
    def resolve_route(self, path: str) -> dict:
        routes = self.config.routes or {}
        key = (path or '/').rstrip('/') or '/'
        candidates = [key, path or '/']
        if key != '/':
            candidates.append(key + '/')
        for candidate in candidates:
            if candidate in routes:
                try:
                    host, port = parse_address(routes[candidate])
                except ValueError as exc:
                    self.log.warn('路径映射 %s 的目标无效(%s), 使用默认目标' % (candidate, exc))
                    break
                return {'label': '路径 %s' % candidate, 'source': routes[candidate],
                        'host': host, 'port': port}
        try:
            host, port = parse_address(self.config.target)
        except ValueError:
            raise
        label = '默认目标' if key == '/' else '默认目标(路径 %s 无映射)' % path
        return {'label': label, 'source': self.config.target, 'host': host, 'port': port}

    def resolve_endpoint(self, host: str, port: int | None) -> tuple[str, int]:
        if port:
            return host, int(port)
        now = time.time()
        cached = self._srv_cache.get(host)
        if cached and cached[2] > now:
            return cached[0], cached[1]
        resolved = resolver.resolve_target(host, None, logger=self.log, use_srv=self.config.use_srv)
        self._srv_cache[host] = (resolved[0], resolved[1], now + SRV_CACHE_SECONDS)
        return resolved

    # ---------- 监听 ----------
    def _start_listener(self, port: int, scheme: str) -> str:
        host = self.config.listen_host or '127.0.0.1'
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((host, port))
        listener.listen(64)
        self._listeners.append((listener, scheme))
        thread = threading.Thread(target=self._accept_loop, args=(listener, scheme),
                                  daemon=True, name='mcjs-accept-%s' % scheme)
        self._accept_threads.append(thread)
        thread.start()
        display_host = host if host not in ('0.0.0.0', '') else '127.0.0.1'
        return '%s://%s:%d' % (scheme, display_host, port)

    def _accept_loop(self, listener: socket.socket, scheme: str) -> None:
        listener.settimeout(0.5)
        while self.running:
            try:
                conn, addr = listener.accept()
            except socket.timeout:
                self._prune_threads()
                continue
            except OSError:
                break
            bridge = Bridge(self, conn, addr, scheme, self.log)
            with self._lock:
                self._connections.add(bridge)
                self.stats.connection_opened()
            thread = threading.Thread(target=bridge.run, daemon=True,
                                      name='mcjs-conn-%d' % bridge.id)
            with self._lock:
                self._conn_threads.add(thread)
            thread.start()

    def _prune_threads(self) -> None:
        """清掉已经结束的连接线程, 避免长时间运行时集合无限增长。"""
        with self._lock:
            self._conn_threads = {thread for thread in self._conn_threads if thread.is_alive()}