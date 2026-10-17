"""Forwarding core: bridges a local wss:// / ws:// WebSocket connection to the
target Minecraft server's TCP connection.

The HTTP and WebSocket layer is delegated to FastAPI + uvicorn -- fragment
reassembly, heartbeats (PING/PONG), subprotocol negotiation, the closing
handshake and frame size limits are all left to that mature implementation.
This module only does three things:

* move the messages coming from the client over to the target server's TCP
  connection verbatim, and the other way around;
* once the peer turns out to be a browser (EaglercraftX-family) client, hand it
  to translator.py for protocol translation;
* answer the browser client's server-list MOTD query locally (it sends the
  text frame ``Accept: MOTD``), otherwise it would keep showing "unable to
  connect".

On top of that, FastAPI serves a status page: opening
http://<listen address>:<ws port>/ in a browser shows the "current server
address", the target server status, the connection count and the traffic.
"""

from __future__ import annotations

import asyncio
import base64
import html
import json
import socket
import threading
import time

import uvicorn
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse, Response

from . import certs, eagler, handshake, resolver, wsproto
from .config import Config, parse_address
from .i18n import get_language, tr
from .logger import NullLogger
from .translator import EaglerTranslator, chat_to_text, note
from .utils import human_bytes
from .version import SERVICE_NAME, VERSION

RECV_SIZE = 65536
CLOSE_GRACE = 0.35           # finish the closing words before disconnecting; give the client time to read them
FIRST_MESSAGE_WAIT = 1.0     # how long to wait for the client's first message (tells list queries and game handshakes apart)
CONNECT_FAIL_WAIT = 1.0      # when the target is down, wait a bit longer for the client's first packet (we need its handshake version)
QUERY_IDLE_SECONDS = 300.0   # max idle time of a "server list" query connection
STATUS_MAX_AGE = 5.0         # cache lifetime of target server status queries in seconds
STATUS_TIMEOUT = 4.0         # timeout of the status page's query to the target server


class _SessionClosed(Exception):
    """This connection should wind down now (not a failure)."""


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
    """Split the server's title screen (chat components) into at most ``limit`` plain-text lines."""
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


def _discard_task_result(task: asyncio.Task) -> None:
    """Drop the task result (handled elsewhere) but retrieve any exception, so no
    unhandled-exception warning is left behind."""
    if not task.cancelled():
        task.exception()


def _set_socket_options(writer: asyncio.StreamWriter) -> None:
    sock = writer.get_extra_info('socket')
    if sock is None:
        return
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    except OSError:
        pass


class Bridge:
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

    def __init__(self, server: 'ProxyServer', websocket: WebSocket, path: str,
                 scheme: str, addr, log, subprotocol: str | None = None):
        self.server = server
        self.config = server.config
        self.log = log
        self.ws = websocket
        self.path = path
        self.scheme = scheme
        self.addr = addr
        self.subprotocol = subprotocol
        self.id = server.next_id()
        self.base64_mode = bool(subprotocol and subprotocol.lower() == 'base64')

        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.loop: asyncio.AbstractEventLoop | None = None

        self.started_at = time.time()
        self.close_reason = ''
        self.close_code = 1000
        self.close_text = 'session closed'
        self.bytes_to_server = 0
        self.bytes_to_client = 0
        self.frames_in = 0

        self.route_label = ''
        self.route_host = ''
        self.target_text = ''
        self.endpoint: tuple[str, int] | None = None

        self.handshake_seen = False          # whether the handshake packet at the start of the upstream has been parsed
        self._handshake_buffer = b''
        self.handshake_info: dict | None = None
        self.target_sent_any = False         # whether the target server has sent any data back
        self.protocol_checked = False        # whether the first upstream data frame was already checked for the client type
        self.query_mode = False              # this is only a server list query, not joining the game
        self.translator: EaglerTranslator | None = None

        self._outbox: list[bytes] = []       # payloads to send to the client (one frame each)
        self._to_server: list[bytes] = []    # bytes to write to the target server
        self._close_after_flush = False
        self._ws_closed = False
        self._first_task: asyncio.Task | None = None

    # ---------- lifecycle ----------
    async def run(self) -> None:
        self.loop = asyncio.get_running_loop()
        try:
            await self._handle()
        except (_SessionClosed, eagler.HandshakeError):
            pass
        except asyncio.CancelledError:
            self.close_reason = self.close_reason or tr('proxy.reason.service_stopped')
            raise
        except Exception as exc:  # one bad connection must not take the whole service down
            self.log.error(tr('proxy.log.connection_error', id=self.id, error=exc))
        finally:
            await self._cleanup()

    async def shutdown(self, reason: str) -> None:
        """Server-initiated disconnect (called while the listeners stop): send the
        close frame first so the client doesn't only see the connection cut."""
        if not self.close_reason:
            self.close_reason = reason
        self.close_code = 1001
        self.close_text = 'server stopping'
        await self._close_ws()
        self._close_writer()

    async def _handle(self) -> None:
        config = self.config
        route = self.server.resolve_route(self.path)
        self.route_label = route['label']
        self.route_host = route['host']
        self.target_text = (route['source'] or config.target or '').strip()

        await self.ws.accept(subprotocol=self.subprotocol)
        self.log.info(tr('proxy.log.accepted', id=self.id, scheme=self.scheme.upper(),
                         host=self.addr[0], port=self.addr[1],
                         source=route['source'], label=route['label']))

        first = await self._wait_first_message(FIRST_MESSAGE_WAIT)
        if first is not None and first[1] and self._is_query(first[0]):
            # "server list" query: answer locally, no need to connect to the target server
            await self._serve_query(first[0])
            return

        try:
            host, port = await asyncio.to_thread(
                self.server.resolve_endpoint, route['host'], route['port'])
        except Exception as exc:
            self.close_reason = tr('proxy.error.resolve_failed', error=exc)
            self.close_code = 1011
            self.log.warn('#%d %s' % (self.id, self.close_reason))
            return
        self.endpoint = (host, port)

        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=max(1.0, float(config.connect_timeout)))
        except Exception as exc:
            await self._report_connect_failure(host, port, exc, first)
            return
        self.reader, self.writer = reader, writer
        _set_socket_options(writer)
        self.log.info(tr('proxy.log.connected', id=self.id, host=host, port=port))

        # if the first packet is already in hand, handle it right away; otherwise
        # leave it to the pumps to keep waiting
        if first is not None:
            self._first_task = None
            await self._handle_incoming(first[0], first[1])
        tasks = [
            asyncio.create_task(self._pump_from_client(), name='mcjs-ws-%d' % self.id),
            asyncio.create_task(self._pump_from_server(), name='mcjs-tcp-%d' % self.id),
        ]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _receive_one(self) -> tuple[bytes, bool] | None:
        """Receive one message from the client, returning (payload, is_text);
        None when the peer disconnects."""
        try:
            while True:
                message = await self.ws.receive()
                kind = message.get('type')
                if kind == 'websocket.disconnect':
                    code = message.get('code')
                    if not self.close_reason:
                        self.close_reason = tr('proxy.reason.client_closed_code', code=code) \
                            if code else tr('proxy.reason.client_closed')
                    self.close_code = 1001
                    return None
                if kind != 'websocket.receive':
                    continue
                payload = message.get('bytes')
                if payload is None:
                    return (message.get('text') or '').encode('utf-8'), True
                return payload, False
        except Exception:
            return None

    async def _wait_first_message(self, timeout: float) -> tuple[bytes, bool] | None:
        """Wait for the client's first message after it connects.

        The client always speaks first (game handshake / ``Accept: MOTD`` list
        query), so it is used to tell what this connection is for. A timeout is
        fine -- the read task stays around for the pumps, so no message is lost.
        """
        if self._first_task is None:
            self._first_task = asyncio.ensure_future(self._receive_one())
            self._first_task.add_done_callback(_discard_task_result)
        try:
            return await asyncio.wait_for(asyncio.shield(self._first_task), timeout=timeout)
        except asyncio.TimeoutError:
            return None
        except Exception:
            return None

    async def _report_connect_failure(self, host: str, port: int, exc: BaseException,
                                      first: tuple[bytes, bool] | None) -> None:
        """Target server unreachable: try to tell the player the reason directly
        instead of leaving them with a bare Connection Closed."""
        reason = describe_connect_error(exc)
        self.close_reason = tr('proxy.error.connect_failed', host=host, port=port, reason=reason)
        self.close_code = 1011
        self.close_text = 'cannot reach target'
        self.log.warn('#%d %s' % (self.id, self.close_reason))
        if first is None:
            first = await self._wait_first_message(CONNECT_FAIL_WAIT)
        self._first_task = None
        payload = first[0] if first else b''
        if not payload or eagler.parse_client_version(payload) is None:
            # not a browser client (or it has not started talking yet); closing
            # the connection is all we can do
            return
        message = note(tr('proxy.error.connect_note', host=host, port=port, reason=reason))
        try:
            await self.ws.send_bytes(
                eagler.pack_error_pre_version(eagler.ERROR_CUSTOM_MESSAGE, message))
            self.log.info(tr('proxy.log.failure_sent', id=self.id))
            await asyncio.sleep(CLOSE_GRACE)
        except Exception as exc2:
            self.log.debug(tr('proxy.log.failure_send_error', id=self.id, error=exc2))

    # ---------- server list query (Accept: MOTD) ----------
    @staticmethod
    def _is_query(payload: bytes) -> bool:
        return payload.lstrip()[:7].lower() == b'accept:'

    async def _serve_query(self, payload: bytes) -> None:
        """The browser client's "server list" query.

        Its ServerQueryImpl sends only one text frame, ``Accept: MOTD``, right
        after connecting, then waits for a JSON text frame. Without an answer it
        would keep showing "cannot connect to the server", so this answers
        locally and also puts the "current server address" into its details (the
        players list).
        """
        self.query_mode = True
        self.log.info(tr('proxy.log.query_received', id=self.id, scheme=self.scheme.upper(),
                         payload=payload[:80].decode('utf-8', 'replace')))
        await self._answer_query(payload)
        deadline = time.time() + QUERY_IDLE_SECONDS
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                self.close_reason = tr('proxy.reason.query_idle_timeout')
                return
            try:
                item = await asyncio.wait_for(self._receive_one(), timeout=remaining)
            except asyncio.TimeoutError:
                self.close_reason = tr('proxy.reason.query_idle_timeout')
                return
            if item is None:
                return
            if item[1]:
                await self._answer_query(item[0])
            else:
                self.log.debug(tr('proxy.log.query_binary_ignored',
                                  id=self.id, size=len(item[0])))

    async def _answer_query(self, payload: bytes) -> None:
        wants = {item.strip().upper()
                 for item in payload.decode('utf-8', 'replace').partition(':')[2].split(',')
                 if item.strip()}
        self.log.debug(tr('proxy.log.query_wants', id=self.id,
                          wants=','.join(sorted(wants)) or tr('proxy.log.empty')))
        if wants and 'MOTD' not in wants:
            return
        route = self.server.resolve_route(self.path)
        try:
            host, port = await asyncio.to_thread(
                self.server.resolve_endpoint, route['host'], route['port'])
        except Exception as exc:
            self.log.warn(tr('proxy.log.query_resolve_failed', id=self.id, error=exc))
            host, port = None, None
        status = None
        if host:
            status = await asyncio.to_thread(
                self.server.target_status, host, port, STATUS_TIMEOUT, STATUS_MAX_AGE)
        data = self._build_query_response(status)
        try:
            await self.ws.send_text(json.dumps(data, ensure_ascii=False))
        except Exception as exc:
            self.log.debug(tr('proxy.log.query_send_failed', id=self.id, error=exc))
            raise _SessionClosed()

    def _build_query_response(self, status: dict | None) -> dict:
        """Build the JSON that the client's ServerData.setMOTDFromQuery wants.

        Field meanings (from the client source):
            type/vers/brand/name/time/cracked  +  data{ motd[at most two lines],
            online, max, players, icon }
        data.players is what the list shows as "details" on hover.
        """
        config = self.config
        detail = [tr('proxy.query.target', address=self.target_text or config.describe_target())]
        motd: list[str] = []
        online = 0
        max_players = 0
        version_name = '1.8.8'
        raw = (status or {}).get('status') or {}
        if raw:
            motd = motd_lines(raw.get('description'))
            version = raw.get('version') or {}
            version_name = str(version.get('name') or version_name)
            players = raw.get('players') or {}
            try:
                online = int(players.get('online') or 0)
                max_players = int(players.get('max') or 0)
            except (TypeError, ValueError):
                online = max_players = 0
            for item in (players.get('sample') or [])[:12]:
                name = chat_to_text(item.get('name') if isinstance(item, dict) else item).strip()
                if name:
                    detail.append(name)
        if not motd:
            motd = ['%s %s' % (tr('core.app_name'), VERSION)]
        brand = (config.server_brand or SERVICE_NAME).strip() or SERVICE_NAME
        # the "version" column in the client's list: use the configured value when
        # one is set, otherwise show the version name reported by the target server
        shown_version = (getattr(config, 'server_brand_version', '') or '').strip() or version_name
        return {
            'type': 'MOTD',
            'name': brand,
            'brand': brand,
            'vers': shown_version,
            'cracked': True,
            'time': int(time.time() * 1000),
            'data': {
                'motd': motd,
                'online': online,
                'max': max_players,
                'players': detail,
                'icon': False,
            },
        }

    # ---------- client -> target server ----------
    async def _pump_from_client(self) -> None:
        pending, self._first_task = self._first_task, None
        while True:
            if pending is not None:
                item = await pending
                pending = None
            else:
                item = await self._receive_one()
            if item is None:
                self.close_reason = self.close_reason or tr('proxy.reason.client_closed')
                self.close_code = 1001
                return
            await self._handle_incoming(item[0], item[1])

    async def _handle_incoming(self, payload: bytes, is_text: bool) -> None:
        self.frames_in += 1
        if self.frames_in <= 4:      # the first frames matter for debugging; log them at debug level only
            self.log.debug(tr('proxy.log.frame_in', id=self.id, index=self.frames_in,
                              kind=tr('proxy.frame.text') if is_text else tr('proxy.frame.binary'),
                              size=len(payload), preview=handshake.hex_preview(payload)))
        if self.translator is not None and is_text:
            # browser clients only use binary frames for game data, so a text
            # frame means the peer is not one of them
            self.log.warn(tr('proxy.log.text_frame_closing', id=self.id))
            self.close_reason = tr('proxy.reason.text_frame_in_translate')
            self.close_code = 1003
            self.close_text = 'text frame not allowed'
            raise _SessionClosed()
        data = self._decode_payload(payload, is_text)
        if self.translator is not None:
            to_server = self.translator.feed_client(data)
        else:
            if not self.protocol_checked and data:
                self.protocol_checked = True
                if (getattr(self.config, 'eagler_translate', True)
                        and eagler.parse_client_version(data) is not None):
                    self._start_translator()
                    data = self.translator.feed_client(data) if self.translator else data
            to_server = self._inspect_handshake(data)
        if to_server:
            self._to_server.append(to_server)
        await self._flush_to_server()
        await self._drain_outbox()

    def _decode_payload(self, payload: bytes, is_text: bool) -> bytes:
        if not is_text:
            return payload
        if not self.base64_mode:
            self.base64_mode = True
            self.log.warn(tr('proxy.log.base64_switch', id=self.id))
        data = wsproto.decode_base64_text(payload)
        if data is None:
            preview = payload[:100].decode('utf-8', 'replace')
            self.log.warn(tr('proxy.log.bad_base64', id=self.id,
                             size=len(payload), preview=preview))
            return b''
        self.log.debug(tr('proxy.log.base64_decoded', id=self.id,
                          size=len(payload), decoded=len(data)))
        return data

    def _start_translator(self) -> None:
        """The peer turned out to be a browser client: set up the protocol translation layer."""
        config = self.config
        host, port = self.endpoint if self.endpoint else (self.route_host or '', 25565)
        self.translator = EaglerTranslator(
            target_host=self.route_host or host,
            target_port=port,
            log=self.log,
            tag='#%d' % self.id,
            send_client=self._queue_to_client,
            send_backend=self._queue_to_backend,
            request_close=self._translator_close,
            brand=(config.server_brand or SERVICE_NAME).strip() or SERVICE_NAME,
            brand_version=(config.server_brand_version or '').strip() or VERSION,
            spoof_brand=getattr(config, 'spoof_brand', ''),
        )
        self.log.info(tr('proxy.log.translator_enabled', id=self.id))

    def _queue_to_client(self, data: bytes) -> None:
        """Translator callback: queue one frame to be sent to the client (sent one
        by one, see _drain_outbox)."""
        self._outbox.append(data)

    def _queue_to_backend(self, data: bytes) -> None:
        """Translator callback: queue a chunk of bytes to write to the target server."""
        self._to_server.append(data)

    def _translator_close(self, reason: str) -> None:
        """The translator asks to wind down: let it send what it has to say first,
        wait a moment, and only then disconnect.

        Closing right away would often cut the client off before it has read *why*
        it was rejected.
        """
        if not self.close_reason:
            self.close_reason = reason
        self._close_after_flush = True

    def _inspect_handshake(self, data: bytes) -> bytes:
        """Parse the handshake packet at the start of the upstream once (for the
        log) and, when configured, rewrite the address inside it.

        A client may split the handshake packet across several sends, so this
        buffers until it is complete before forwarding; every other byte is
        forwarded verbatim -- no game data is ever modified.
        """
        if self.handshake_seen:
            return data
        buffer = self._handshake_buffer + data
        size = handshake.packet_size(buffer)
        if (size is not None and size <= 4096 and len(buffer) < size
                and handshake.looks_like_handshake(buffer)):
            self._handshake_buffer = buffer
            self.log.debug(tr('proxy.log.handshake_incomplete',
                              id=self.id, missing=size - len(buffer)))
            return b''
        self.handshake_seen = True
        self._handshake_buffer = b''
        info = handshake.parse_handshake(buffer)
        if info is None:
            self.log.debug(tr('proxy.log.not_handshake',
                              id=self.id, preview=handshake.hex_preview(buffer)))
            return buffer
        self.handshake_info = info
        self.log.info(tr('proxy.log.handshake',
                         id=self.id, info=handshake.describe_handshake(info)))
        if not getattr(self.config, 'rewrite_handshake_host', False) or not self.endpoint:
            return buffer
        host, port = self.endpoint
        rewritten = handshake.rewrite_handshake(buffer, host, port)
        if rewritten is None:
            self.log.warn(tr('proxy.log.rewrite_failed', id=self.id))
            return buffer
        if rewritten == buffer:
            return buffer
        self.log.info(tr('proxy.log.address_rewritten', id=self.id, host=host, port=port))
        return rewritten

    # ---------- target server -> client ----------
    async def _pump_from_server(self) -> None:
        reader = self.reader
        while True:
            data = await reader.read(RECV_SIZE)
            if not data:
                break
            self.target_sent_any = True
            self.bytes_to_client += len(data)
            self.server.stats.add_bytes(to_client=len(data))
            translator = self.translator
            if translator is not None:
                frames = translator.feed_server(data)
                if translator.close_reason and not self.close_reason:
                    self.close_reason = translator.close_reason
                await self._send_payloads(frames)
                await self._flush_to_server()
                await self._drain_outbox()
            else:
                await self._send_payload(data)
        if not self.close_reason:
            self.close_reason = tr('proxy.reason.target_closed')
            self.close_code = 1000
        translator = self.translator
        if translator is not None and not translator.login_done:
            # closed by the peer during login: give the player a reason, otherwise
            # they would only see Connection Closed
            translator.fail(tr('proxy.error.login_stage_closed'))
        await self._flush_to_server()
        await self._drain_outbox()

    # ---------- send/receive queues ----------
    async def _flush_to_server(self) -> None:
        if not self._to_server:
            return
        # Note: the list must be cleared in place. The translation layer holds
        # _to_server.append as its callback; swapping the attribute for a fresh
        # list would send every later append into an orphaned list nobody reads,
        # and not a single byte would go out.
        chunks = list(self._to_server)
        self._to_server.clear()
        writer = self.writer
        if writer is None:
            return
        total = sum(len(chunk) for chunk in chunks)
        try:
            for chunk in chunks:
                writer.write(chunk)
            await writer.drain()
        except (OSError, RuntimeError) as exc:
            self.close_reason = self.close_reason or tr('proxy.reason.send_to_target_failed',
                                                        error=exc)
            self.close_code = 1001
            raise _SessionClosed()
        self.bytes_to_server += total
        self.server.stats.add_bytes(to_server=total)

    async def _drain_outbox(self) -> None:
        if self._outbox:
            # same as _flush_to_server: must be cleared in place, or frames the
            # translation layer appends later would be lost
            frames = list(self._outbox)
            self._outbox.clear()
            await self._send_payloads(frames)
        if self._close_after_flush:
            self._close_after_flush = False
            await asyncio.sleep(CLOSE_GRACE)
            raise _SessionClosed()

    async def _send_payloads(self, frames: list[bytes]) -> None:
        """Send a run of payloads coming from the protocol translation layer: each packet must occupy its own WebSocket frame."""
        for frame in frames:
            if frame:
                await self._send_payload(frame)

    async def _send_payload(self, data: bytes) -> None:
        if not data or self._ws_closed:
            return
        try:
            if self.base64_mode:
                await self.ws.send_text(base64.b64encode(data).decode('ascii'))
            else:
                await self.ws.send_bytes(data)
        except Exception as exc:
            self.log.debug(tr('proxy.log.send_client_failed', id=self.id, error=exc))
            self.close_code = 1001
            raise _SessionClosed()

    # ---------- wind-down ----------
    async def _close_ws(self) -> None:
        if self._ws_closed:
            return
        self._ws_closed = True
        try:
            await self.ws.close(code=self.close_code, reason=self.close_text)
        except Exception:
            pass

    def _close_writer(self) -> None:
        writer, self.writer = self.writer, None
        if writer is not None:
            try:
                writer.close()
            except Exception:
                pass

    async def _cleanup(self) -> None:
        self._close_writer()
        translator = self.translator
        if translator is not None and translator.close_reason and not self.close_reason:
            self.close_reason = translator.close_reason
        await self._close_ws()
        if self.query_mode and not self.close_reason:
            self.close_reason = tr('proxy.reason.normal_close')
        self.log.info(tr('proxy.log.session_end', id=self.id,
                         seconds=time.time() - self.started_at,
                         reason=self.close_reason or tr('proxy.reason.normal_close'),
                         up=human_bytes(self.bytes_to_server),
                         down=human_bytes(self.bytes_to_client)))
        for hint in self._diagnose():
            self.log.warn('#%d %s' % (self.id, hint))
        self.server.forget(self)

    def _diagnose(self) -> list[str]:
        """Give one plausible cause when a connection ends abnormally, so the log
        does not end on a bare "connection ended"."""
        if self.translator is not None or self.query_mode:
            # the translation layer's log already explains the reason; no guessing needed
            return []
        hints: list[str] = []
        if self.target_sent_any:
            return hints
        info = self.handshake_info
        if info is None:
            return hints
        if info['next_state'] == 2:      # login
            hints.append(tr('proxy.diag.no_reply'))
            if info['address'] not in ('',) and self.endpoint:
                host = self.endpoint[0]
                if info['address'] not in host and ':' not in info['address']:
                    hints.append(tr('proxy.diag.address_mismatch',
                                    shown=info['address'], actual=host))
            hints.append(tr('proxy.diag.protocol_unsupported',
                            version=info['protocol']))
            hints.append(tr('proxy.diag.policy'))
        return hints


class ProxyServer:
    """uvicorn listeners + connection management + status page."""

    def __init__(self, config: Config, logger=None):
        self.config = config
        self.log = logger or NullLogger()
        self.stats = Stats()
        self.certificate: dict | None = None
        self.running = False
        self.app: FastAPI | None = None
        self._servers: list[tuple[uvicorn.Server, threading.Thread]] = []
        self._connections: set[Bridge] = set()
        self._lock = threading.Lock()
        self._srv_cache: dict[str, tuple[str, int, float]] = {}
        self._status_cache: dict[str, dict] = {}
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
            raise ValueError(tr('proxy.error.bad_config', problems='; '.join(problems)))

        ssl_options: dict = {}
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
            ssl_options = {
                'ssl_certfile': self.certificate['cert_path'],
                'ssl_keyfile': self.certificate['key_path'],
            }

        self.app = self._build_app(config)
        listeners: list[str] = []
        self.running = True
        try:
            if config.tls_enabled and int(config.wss_port) > 0:
                listeners.append(self._start_listener(int(config.wss_port), 'wss', ssl_options))
            if int(config.ws_port) > 0:
                listeners.append(self._start_listener(int(config.ws_port), 'ws', {}))
        except Exception:
            self.running = False
            self._shutdown_servers()
            raise
        self.log.info(tr('proxy.log.listeners_ready', listeners=', '.join(listeners)))
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
                future.add_done_callback(lambda fut: fut.exception())
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
            'use_srv': bool(config.use_srv),
            'listeners': config.listeners() if self.running else [],
            'wss_url': config.wss_url() if self.running else None,
            'server_brand': config.server_brand,
            'server_brand_version': config.server_brand_version or VERSION,
            'spoof_brand': config.spoof_brand,
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
                info = self.target_status(host, port, STATUS_TIMEOUT, STATUS_MAX_AGE)
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
                    self.log.warn(tr('proxy.log.bad_route', path=candidate, error=exc))
                    break
                return {'label': tr('proxy.route.path', path=candidate),
                        'source': routes[candidate], 'host': host, 'port': port}
        host, port = parse_address(self.config.target)
        label = tr('proxy.route.default') if key == '/' \
            else tr('proxy.route.default_missing', path=path)
        return {'label': label, 'source': self.config.target, 'host': host, 'port': port}

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

    def target_status(self, host: str, port: int, timeout: float = STATUS_TIMEOUT,
                      max_age: float = STATUS_MAX_AGE) -> dict:
        """Query the target server status once (cached); used by both the status page and the server list."""
        key = '%s:%d' % (host, int(port))
        now = time.time()
        with self._lock:
            cached = self._status_cache.get(key)
            if cached and now - cached['time'] < max_age:
                return cached
        result = resolver.query_status(host, int(port), timeout=timeout)
        result['time'] = time.time()
        with self._lock:
            self._status_cache[key] = result
        return result

    # ---------- FastAPI ----------
    def _build_app(self, config: Config) -> FastAPI:
        app = FastAPI(title=tr('core.app_name'), docs_url=None, redoc_url=None, openapi_url=None)

        @app.get('/status', include_in_schema=False)
        @app.get('/status.json', include_in_schema=False)
        async def status_json(request: Request):
            return JSONResponse(self.status(request.url.path))

        @app.get('/favicon.ico', include_in_schema=False)
        async def favicon():
            return Response(status_code=204)

        @app.get('/', include_in_schema=False)
        @app.get('/{path:path}', include_in_schema=False)
        async def status_page(path: str = ''):
            return HTMLResponse(self.status_page_html('/' + path if path else '/'))

        @app.websocket('/')
        @app.websocket('/{path:path}')
        async def websocket_route(websocket: WebSocket, path: str = ''):
            await self.handle_websocket(websocket, '/' + path if path else '/')

        return app

    async def handle_websocket(self, websocket: WebSocket, path: str) -> None:
        scope = websocket.scope
        scheme = 'wss' if str(scope.get('scheme', 'ws')).lower() in ('wss', 'https') else 'ws'
        client = scope.get('client')
        addr = (client[0], client[1]) if client else ('?', 0)
        subprotocols = [item.strip() for item in (scope.get('subprotocols') or []) if item.strip()]
        bridge = Bridge(self, websocket, path, scheme, addr, self.log,
                        subprotocols[0] if subprotocols else None)
        with self._lock:
            self._connections.add(bridge)
            self.stats.connection_opened()
        await bridge.run()

    # ---------- status page ----------
    def status_page_html(self, path: str = '/') -> str:
        data = self.status(path, with_target=True)
        probe = data.get('target_probe') or {}
        rows: list[tuple[str, str]] = []

        def add(key: str, value: str) -> None:
            rows.append((key, value))

        def code(text: str) -> str:
            return '<code>%s</code>' % html.escape(str(text))

        address = data.get('target_source') or data.get('target') or ''
        resolved = data.get('target_resolved')
        address_html = code(address)
        if resolved and resolved != address:
            address_html += '<br><span class="dim">%s</span>' % html.escape(
                tr('proxy.page.resolved', address=resolved))
        add(tr('proxy.page.address'), address_html)

        if probe.get('ok'):
            detail = tr('proxy.page.online', ping=probe.get('ping_ms'))
            motd = probe.get('motd') or []
            if motd:
                detail += ' · %s' % '<br>'.join(html.escape(line) for line in motd)
            players = probe.get('players') or {}
            if players:
                detail += '<br><span class="dim">%s</span>' % html.escape(
                    tr('proxy.page.players', online=players.get('online', 0),
                       max=players.get('max', 0)))
            add(tr('proxy.page.target_status'), '<span class="ok">%s</span>' % detail)
        else:
            add(tr('proxy.page.target_status'),
                '<span class="warn">%s</span>'
                '<br><span class="dim">%s</span>' % (
                    tr('proxy.page.unreachable'), html.escape(probe.get('error') or '')))

        listeners = data.get('listeners') or []
        if data.get('wss_url'):
            add(tr('proxy.page.wss_url'), code(data['wss_url']))
        others = [item for item in listeners if item != data.get('wss_url')]
        if others:
            add(tr('proxy.page.alt_addresses'), code(' , '.join(others)))
        add(tr('proxy.page.app'), code('%s %s' % (tr('core.app_name'), VERSION)))
        state = tr('proxy.page.running') if data.get('running') else tr('proxy.page.stopped')
        add(tr('proxy.page.state'),
            '<span class="ok">%s</span>' % state if data.get('running') else state)
        add(tr('proxy.page.uptime'),
            code(tr('proxy.page.uptime_value', seconds=data.get('uptime_seconds', 0))))
        add(tr('proxy.page.connections'),
            code(tr('proxy.page.connections_value',
                    active=data.get('active_connections'),
                    total=data.get('total_connections'))))
        add(tr('proxy.page.traffic'),
            code(tr('proxy.page.traffic_value',
                    up=data.get('bytes_to_server_human'),
                    down=data.get('bytes_to_client_human'))))
        add(tr('proxy.page.server_brand'),
            code('%s %s' % (data.get('server_brand'), data.get('server_brand_version'))))
        add(tr('proxy.page.spoof_brand'),
            code(data.get('spoof_brand') or tr('proxy.page.spoof_off')))
        if data.get('routes'):
            items = '<br>'.join('%s → %s' % (html.escape(str(k)), html.escape(str(v)))
                                for k, v in data['routes'].items())
            add(tr('proxy.page.routes'), '<code>%s</code>' % items)
        cert = data.get('certificate') or {}
        if cert:
            add(tr('proxy.page.cert_thumbprint'), code(cert.get('thumbprint', '')))

        body = '\n'.join('  <tr><td class="k">%s</td><td>%s</td></tr>' % (html.escape(k), v)
                         for k, v in rows)
        return STATUS_PAGE.format(
            lang=html.escape(get_language()),
            title=html.escape(tr('proxy.page.title', app=tr('core.app_name'))),
            app=html.escape(tr('core.app_name')),
            subtitle=html.escape(tr('proxy.page.subtitle', version=VERSION, state=state)),
            rows=body,
            details=html.escape(tr('proxy.page.details')),
            json_text=html.escape(json.dumps(data, ensure_ascii=False, indent=2)))

    # ---------- listeners ----------
    def _start_listener(self, port: int, scheme: str, ssl_options: dict) -> str:
        """Create the listening socket first (a busy port surfaces right away),
        then hand it to uvicorn.

        The socket is already listening, so client connections can arrive as soon
        as start() returns and the kernel queues them until uvicorn's event loop
        is up and processing -- no extra "ready" wait is needed.
        """
        config = self.config
        host = config.listen_host or '127.0.0.1'
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            listener.bind((host, int(port)))
        except OSError as exc:
            listener.close()
            raise OSError(tr('proxy.error.listen_failed',
                             host=host, port=int(port), error=exc))
        listener.listen(64)

        heartbeat = max(0, int(config.heartbeat_sec))
        uvicorn_config = uvicorn.Config(
            app=self.app,
            host=host,
            port=int(port),
            log_config=None,
            log_level='warning',
            access_log=False,
            ws_max_size=int(config.max_payload_bytes),
            ws_ping_interval=float(heartbeat) if heartbeat else None,
            ws_ping_timeout=float(max(1, heartbeat)) * 2 if heartbeat else None,
            timeout_graceful_shutdown=3,
            **ssl_options,
        )
        uvicorn_config.load()     # certificate / logging / protocol implementation problems surface here
        server = uvicorn.Server(uvicorn_config)
        thread = threading.Thread(target=self._serve, args=(server, listener),
                                  daemon=True, name='mcjs-%s' % scheme)
        self._servers.append((server, thread))
        thread.start()
        display_host = host if host not in ('0.0.0.0', '') else '127.0.0.1'
        return '%s://%s:%d' % (scheme, display_host, int(port))

    @staticmethod
    def _serve(server: uvicorn.Server, listener: socket.socket) -> None:
        try:
            asyncio.run(server.serve(sockets=[listener]))
        except Exception:      # errors in a thread cannot be raised to the caller; record them
            import traceback
            traceback.print_exc()

    def _shutdown_servers(self) -> None:
        servers = self._servers
        self._servers = []
        for server, _thread in servers:
            server.should_exit = True
        deadline = time.time() + 3.0
        for _server, thread in servers:
            thread.join(max(0.1, deadline - time.time()))
        for server, thread in servers:
            if thread.is_alive():
                server.force_exit = True
        for _server, thread in servers:
            thread.join(2.0)


STATUS_PAGE = """<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  body {{ margin: 0; padding: 26px 20px 40px; background: #14171c; color: #e6e9ef;
         font: 15px/1.65 "Microsoft YaHei", system-ui, sans-serif; }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  .sub {{ color: #8b95a5; font-size: 13px; margin-bottom: 18px; }}
  table {{ border-collapse: collapse; width: 100%; max-width: 820px; background: #1b2028;
           border-radius: 10px; overflow: hidden; }}
  td {{ padding: 11px 16px; border-top: 1px solid #262d38; vertical-align: top; }}
  tr:first-child td {{ border-top: none; }}
  td.k {{ color: #9aa6b8; width: 200px; white-space: nowrap; }}
  code {{ font-family: Consolas, "Courier New", monospace; font-size: 13px;
          word-break: break-all; }}
  .ok {{ color: #4ade80; }}
  .warn {{ color: #fbbf24; }}
  .dim {{ color: #8b95a5; font-size: 13px; }}
  details {{ margin-top: 18px; max-width: 820px; color: #9aa6b8; }}
  pre {{ background: #1b2028; padding: 14px; border-radius: 10px; overflow: auto;
         font-size: 12px; line-height: 1.5; }}
</style>
</head>
<body>
<h1>{app}</h1>
<div class="sub">{subtitle}</div>
<table>
{rows}
</table>
<details><summary>{details}</summary><pre>{json_text}</pre></details>
</body>
</html>
"""
