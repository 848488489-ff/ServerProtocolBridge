"""命令行模式(无 GUI)。

适合服务器/计划任务场景, 也用于给 GUI 版本做无界面冒烟测试:

    python main.py --no-gui
    python main.py --no-gui --target mc244.com --port 8443
    python main.py --check
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time

from . import certs, resolver
from .config import Config, parse_address
from .logger import Logger
from .proxy import ProxyServer
from .utils import app_dir
from .version import APP_NAME, VERSION


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog='mcjs-proxy', description='%s v%s —— 把普通 Minecraft 服务器转换为本地 wss:// 端点' % (APP_NAME, VERSION))
    parser.add_argument('-c', '--config', help='配置文件路径(默认程序目录下的 config.json)')
    parser.add_argument('-t', '--target', help='转发目标, 例如 mc244.com(按 SRV 解析) 或 127.0.0.1:25565')
    parser.add_argument('-l', '--listen', help='监听地址(默认 127.0.0.1)')
    parser.add_argument('-p', '--port', type=int, help='wss:// 监听端口(默认 8443)')
    parser.add_argument('--ws-port', type=int, help='ws://(明文, 备用)监听端口, 0 表示关闭')
    parser.add_argument('--no-srv', action='store_true', help='不做 SRV 解析, 目标不带端口时直接用 25565')
    parser.add_argument('--rewrite-handshake-host', action='store_true',
                        help='把握手包里的服务器地址改写成目标域名(服务器按地址校验/分流时使用)')
    parser.add_argument('--no-eagler-translate', action='store_true',
                        help='关闭浏览器客户端(EaglercraftX)协议翻译, 只做纯字节转发')
    parser.add_argument('--cert-dir', help='证书目录(默认 certs)')
    parser.add_argument('--regen-cert', action='store_true', help='重新生成证书')
    parser.add_argument('--install-cert', action='store_true', help='把证书导入系统信任库后退出')
    parser.add_argument('--check', action='store_true', help='检查证书与目标服务器连通性后退出')
    parser.add_argument('--log-level', choices=('debug', 'info', 'warn', 'error'), help='日志级别')
    parser.add_argument('--heartbeat', type=int, help='WebSocket 心跳间隔秒数, 0 关闭')
    parser.add_argument('--max-payload', type=int, help='单帧上限(MB)')
    parser.add_argument('--version', action='version', version='%s v%s' % (APP_NAME, VERSION))
    return parser


def apply_arguments(config: Config, args: argparse.Namespace) -> Config:
    if args.target:
        config.target = args.target
    if args.listen:
        config.listen_host = args.listen
    if args.port is not None:
        config.wss_port = args.port
    if args.ws_port is not None:
        config.ws_port = args.ws_port
    if args.no_srv:
        config.use_srv = False
    if args.rewrite_handshake_host:
        config.rewrite_handshake_host = True
    if args.no_eagler_translate:
        config.eagler_translate = False
    if args.cert_dir:
        config.cert_dir = args.cert_dir
    if args.log_level:
        config.log_level = args.log_level
    if args.heartbeat is not None:
        config.heartbeat_sec = args.heartbeat
    if args.max_payload is not None:
        config.max_payload_mb = args.max_payload
    return config


def run_check(config: Config, logger: Logger) -> int:
    """检查配置、证书与目标服务器连通性。"""
    problems = config.validate()
    for problem in problems:
        logger.error('配置: %s' % problem)
    logger.info('工作目录: %s' % app_dir())
    logger.info('转发目标: %s' % config.describe_target())

    if config.tls_enabled:
        logger.info('正在检查证书...')
        try:
            info = certs.ensure_certificate(
                config.resolved_cert_dir, common_name=config.cert_common_name,
                extra_names=config.cert_extra_names, days=int(config.cert_days),
                generator=config.cert_generator, regenerate=False, logger=logger)
            logger.info('证书可用: %s' % info['cert_path'])
            logger.info('指纹 SHA-256: %s' % info['thumbprint'])
            if info.get('alt_names'):
                logger.info('覆盖名称: %s' % ', '.join(info['alt_names']))
            logger.warn('如果浏览器仍提示证书不受信任, 请执行 --install-cert 后重启浏览器。')
        except Exception as exc:
            logger.error('证书检查失败: %s' % exc)
            return 2

    try:
        host, port = parse_address(config.target)
        if not port:
            host, port = resolver.resolve_target(host, None, logger=logger, use_srv=config.use_srv)
    except ValueError as exc:
        logger.error('转发目标无效: %s' % exc)
        return 2
    logger.info('正在测试 %s:%d 的连通性...' % (host, port))
    ok, elapsed, message = resolver.probe(host, port)
    if ok:
        logger.info('目标服务器可达, 握手耗时 %.0f ms' % elapsed)
    else:
        logger.error('目标服务器不可达: %s' % message)
    return 0 if (ok and not problems) else 1


def run_install_certificate(config: Config, logger: Logger, regenerate: bool) -> int:
    if regenerate:
        logger.info('将重新签发证书...')
    try:
        info = certs.ensure_certificate(
            config.resolved_cert_dir, common_name=config.cert_common_name,
            extra_names=config.cert_extra_names, days=int(config.cert_days),
            generator=config.cert_generator, regenerate=regenerate, logger=logger)
    except Exception as exc:
        logger.error('证书生成失败: %s' % exc)
        return 2
    ok, message = certs.install_to_trust_store(info['cert_path'], logger=logger)
    if not ok:
        logger.error('导入失败: %s' % message)
        return 1
    logger.info('完成。请重启浏览器后使用 %s' % config.wss_url())
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    config = apply_arguments(Config.load(args.config), args)
    logger = Logger(config.log_level)

    if args.check:
        return run_check(config, logger)
    if args.install_cert:
        return run_install_certificate(config, logger, args.regen_cert)

    try:
        server = ProxyServer(config, logger)
        info = server.start()
    except Exception as exc:
        logger.error('启动失败: %s' % exc)
        return 1

    logger.info('wss 地址: %s' % (info.get('wss_url') or '(未启用)'))
    for listener in info.get('listeners', []):
        if listener.startswith('ws://'):
            logger.info('备用明文地址: %s' % listener)
    logger.info('按 Ctrl+C 停止服务')

    stop_event = threading.Event()
    try:
        while not stop_event.wait(0.5):
            pass
    except KeyboardInterrupt:
        logger.info('收到 Ctrl+C, 正在停止...')
    finally:
        server.stop()
    return 0


if __name__ == '__main__':
    sys.exit(main())