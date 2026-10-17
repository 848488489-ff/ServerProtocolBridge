"""证书管理: 生成、校验、安装到系统信任库。

wss:// 必须有证书, 而浏览器不会默认信任自签名证书, 因此首次运行时
自动签发一张包含 localhost / 127.0.0.1 / ::1 / 主机名 的证书,
再由用户一键导入 Windows 受信任的根证书颁发机构。
"""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import socket
import subprocess
import time
from pathlib import Path

from . import x509

CERT_FILENAME = 'cert.pem'
KEY_FILENAME = 'key.pem'


def certificate_paths(cert_dir: Path) -> tuple[Path, Path]:
    cert_dir = Path(cert_dir)
    return cert_dir / CERT_FILENAME, cert_dir / KEY_FILENAME


def thumbprint(pem: str) -> str:
    """证书 SHA-256 指纹(冒号分隔), 便于用户核对与导入。"""
    digest = hashlib.sha256(x509.pem_to_der(pem)).hexdigest().upper()
    return ':'.join(digest[index:index + 2] for index in range(0, len(digest), 2))


def default_alt_names(common_name: str = 'localhost', extra_names=None) -> list[str]:
    """证书要覆盖的名称: 本机回环地址 + 常见主机名 + 用户自定义的名称。"""
    names = ['localhost', '127.0.0.1', '::1']
    if common_name:
        names.append(common_name)
    try:
        hostname = socket.gethostname()
        if hostname:
            names.append(hostname)
    except OSError:
        pass
    names.extend(str(name) for name in (extra_names or ()))
    unique: list[str] = []
    seen = set()
    for name in names:
        if name and name not in seen:
            seen.add(name)
            unique.append(name)
    return unique


def _looks_like_ip(text: str) -> bool:
    import ipaddress

    try:
        ipaddress.ip_address(text)
        return True
    except ValueError:
        return False


def _openssl_generate(cert_path: Path, key_path: Path, common_name: str,
                      alt_names: list[str], days: int, key_bits: int) -> bool:
    """如果系统里有 openssl, 用它签发(更快)。失败返回 False 由内置生成器兜底。"""
    executable = shutil.which('openssl')
    if not executable:
        return False
    subject_alt_name = ','.join(
        ('IP:' if _looks_like_ip(name) else 'DNS:') + name for name in alt_names)
    command = [
        executable, 'req', '-x509', '-nodes', '-newkey', 'rsa:%d' % key_bits,
        '-keyout', str(key_path), '-out', str(cert_path), '-days', str(days),
        '-subj', '/CN=%s' % common_name,
        '-addext', 'subjectAltName=%s' % subject_alt_name,
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=180)
    except Exception:
        return False
    return completed.returncode == 0 and cert_path.exists() and key_path.exists()


def _write_certificate_files(cert_path: Path, key_path: Path, certificate: dict) -> None:
    cert_path.write_text(certificate['cert_pem'], encoding='ascii')
    key_path.write_text(certificate['key_pem'], encoding='ascii')
    if os.name != 'nt':  # Windows 下没有 POSIX 权限位
        try:
            os.chmod(key_path, 0o600)
        except OSError:
            pass


def _flatten_names(values) -> tuple:
    """把 ssl._test_decode_cert 返回的嵌套元组压平成字符串元组。"""
    names = []
    for item in values or ():
        if isinstance(item, (tuple, list)):
            names.append(':'.join(str(part) for part in item))
        else:
            names.append(str(item))
    return tuple(names)


def _decode_cert_details(cert_path: Path) -> dict:
    """尝试用标准库自带的解码器取出证书信息(仅用于界面展示, 失败不影响功能)。"""
    details: dict = {}
    decoder = getattr(__import__('ssl'), '_ssl', None)
    if decoder is None or not hasattr(decoder, '_test_decode_cert'):
        return details
    try:
        info = decoder._test_decode_cert(str(cert_path))
        details['subject'] = _flatten_names(info.get('subject'))
        details['issuer'] = _flatten_names(info.get('issuer'))
        details['not_after'] = info.get('notAfter', '')
        details['not_before'] = info.get('notBefore', '')
        details['alt_names'] = _flatten_names(info.get('subjectAltName'))
    except Exception:
        pass
    return details


def inspect_certificate(cert_path: Path, key_path: Path) -> dict | None:
    """校验证书与私钥是否匹配、PEM/DER 是否合法, 顺便取出指纹等信息。"""
    import ssl

    try:
        pem = Path(cert_path).read_text(encoding='ascii', errors='ignore')
    except OSError:
        return None
    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(cert_path), str(key_path))
    except Exception:
        return None
    try:
        stamp = Path(cert_path).stat().st_mtime
        created = time.strftime('%Y-%m-%d %H:%M', time.localtime(stamp))
    except OSError:
        created = ''
    info = {
        'cert_path': str(cert_path),
        'key_path': str(key_path),
        'thumbprint': thumbprint(pem),
        'created': created,
        'size': Path(cert_path).stat().st_size if Path(cert_path).exists() else 0,
        'alt_names': (),
        'not_after': '',
        'not_before': '',
        'subject': (),
    }
    details = _decode_cert_details(Path(cert_path))
    if details:
        info['alt_names'] = tuple(details.get('alt_names', ()))
        info['not_after'] = details.get('not_after', '')
        info['not_before'] = details.get('not_before', '')
        info['subject'] = details.get('subject', ())
    return info


def generate_certificate(cert_dir: Path, common_name: str = 'localhost', extra_names=None,
                         days: int = 3650, generator: str = 'auto',
                         key_bits: int = 2048, logger=None) -> str:
    """签发证书到 cert_dir, 返回实际使用的生成器('python' / 'openssl')。"""
    cert_path, key_path = certificate_paths(cert_dir)
    cert_dir = Path(cert_dir)
    cert_dir.mkdir(parents=True, exist_ok=True)
    names = default_alt_names(common_name, extra_names)

    method = generator
    if method == 'auto':
        method = 'openssl' if shutil.which('openssl') else 'python'

    if method == 'openssl':
        if logger is not None:
            logger.info('正在通过 openssl 签发证书...')
        if _openssl_generate(cert_path, key_path, common_name, names, days, key_bits):
            return 'openssl'
        if logger is not None:
            logger.warn('openssl 签发失败, 改用内置生成器')

    if logger is not None:
        logger.info('正在生成 RSA %d 位密钥并自签名(首次运行需要几秒)...' % key_bits)
    certificate = x509.create_self_signed_certificate(
        common_name=common_name, alt_names=names, days=days, key_bits=key_bits)
    _write_certificate_files(cert_path, key_path, certificate)
    return 'python'


def ensure_certificate(cert_dir: Path, common_name: str = 'localhost', extra_names=None,
                       days: int = 3650, generator: str = 'auto', key_bits: int = 2048,
                       regenerate: bool = False, logger=None) -> dict:
    """确保证书存在且可用; 不存在(或被要求重建)时自动签发。"""
    cert_path, key_path = certificate_paths(cert_dir)
    if not regenerate and cert_path.exists() and key_path.exists():
        info = inspect_certificate(cert_path, key_path)
        if info is not None:
            if logger is not None:
                logger.info('已存在可用证书: %s' % cert_path)
            return info
        if logger is not None:
            logger.warn('现有证书不可用, 将重新签发: %s' % cert_path)

    used = generate_certificate(cert_dir, common_name, extra_names, days, generator, key_bits, logger)
    info = inspect_certificate(cert_path, key_path)
    if info is None:
        raise RuntimeError('证书签发失败, 请检查目录写入权限: %s' % cert_path)
    info['generator'] = used
    info['generated'] = True
    if logger is not None:
        logger.info('证书已生成: %s (生成器: %s)' % (cert_path, used))
        logger.info('证书指纹 SHA-256: %s' % info['thumbprint'])
        if info['alt_names']:
            logger.info('证书包含的名称: %s' % ', '.join(info['alt_names']))
    return info


def install_to_trust_store(cert_path: Path, logger=None) -> tuple[bool, str]:
    """把证书导入当前用户的"受信任的根证书颁发机构"(Windows)。"""
    cert_path = Path(cert_path)
    if not cert_path.exists():
        return False, '证书文件不存在: %s' % cert_path
    if platform.system() != 'Windows':
        return False, '自动导入仅支持 Windows, 请手动把证书加入系统/浏览器信任库'
    command = ['certutil', '-user', '-addstore', 'root', str(cert_path)]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=60)
    except Exception as exc:
        return False, '执行 certutil 失败: %s' % exc
    output = ((completed.stdout or '') + (completed.stderr or '')).strip()
    ok = completed.returncode == 0
    if logger is not None:
        if ok:
            logger.info('证书已导入当前用户的受信任根证书库: %s' % cert_path)
            logger.info('请重启浏览器后生效(Firefox 需要单独导入, 见 README)。')
        else:
            logger.error('导入失败: %s' % output)
    return ok, output