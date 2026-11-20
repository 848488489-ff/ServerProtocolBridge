"""Certificate management: generation, validation, installation into the system trust store.

wss:// requires a certificate, and browsers do not trust self-signed
certificates out of the box, so the first run issues one covering
localhost / 127.0.0.1 / ::1 / the machine host name, which the user can
then import into the Windows Trusted Root Certification Authorities store
with a single click.
"""

from __future__ import annotations

import hashlib
import os
import platform
import locale
import shutil
import socket
import subprocess
import time
from pathlib import Path

from . import x509
from .i18n import tr
from .utils import is_android

CERT_FILENAME = 'cert.pem'
KEY_FILENAME = 'key.pem'


def certificate_paths(cert_dir: Path) -> tuple[Path, Path]:
    cert_dir = Path(cert_dir)
    return cert_dir / CERT_FILENAME, cert_dir / KEY_FILENAME


def thumbprint(pem: str) -> str:
    """SHA-256 fingerprint of the certificate (colon-separated), so the user can verify it before importing."""
    digest = hashlib.sha256(x509.pem_to_der(pem)).hexdigest().upper()
    return ':'.join(digest[index:index + 2] for index in range(0, len(digest), 2))


def default_alt_names(common_name: str = 'localhost', extra_names=None) -> list[str]:
    """Names the certificate must cover: loopback addresses + common host names + user-supplied names."""
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
    """Sign with the system openssl when it is available (faster). Returns False on failure, letting the built-in generator take over."""
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
        completed = subprocess.run(command, capture_output=True, timeout=180)
    except Exception:
        return False
    if completed.returncode != 0:
        _decode_command_output(completed.stdout, completed.stderr)
        return False
    return cert_path.exists() and key_path.exists()


def _write_certificate_files(cert_path: Path, key_path: Path, certificate: dict) -> None:
    cert_path.write_text(certificate['cert_pem'], encoding='ascii')
    key_path.write_text(certificate['key_pem'], encoding='ascii')
    if os.name != 'nt':  # Windows has no POSIX permission bits
        try:
            os.chmod(key_path, 0o600)
        except OSError:
            pass


def _flatten_names(values) -> tuple:
    """Flatten the nested tuples returned by ssl._test_decode_cert into a tuple of strings."""
    names = []
    for item in values or ():
        if isinstance(item, (tuple, list)):
            names.append(':'.join(str(part) for part in item))
        else:
            names.append(str(item))
    return tuple(names)


def _decode_cert_details(cert_path: Path) -> dict:
    """Try to pull certificate details out of the standard library decoder (display only; a failure here must not break anything)."""
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
    """Check that certificate and private key match and that the PEM/DER is valid; also collect the fingerprint and related details."""
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
    """Issue a certificate into cert_dir; returns the generator that actually produced it ('python' / 'openssl')."""
    cert_path, key_path = certificate_paths(cert_dir)
    cert_dir = Path(cert_dir)
    cert_dir.mkdir(parents=True, exist_ok=True)
    names = default_alt_names(common_name, extra_names)

    method = generator
    if method == 'auto':
        method = 'openssl' if shutil.which('openssl') else 'python'

    if method == 'openssl':
        if logger is not None:
            logger.info(tr('certs.signing_openssl'))
        if _openssl_generate(cert_path, key_path, common_name, names, days, key_bits):
            return 'openssl'
        if logger is not None:
            logger.warn(tr('certs.openssl_failed'))

    if logger is not None:
        logger.info(tr('certs.generating', bits=key_bits))
    certificate = x509.create_self_signed_certificate(
        common_name=common_name, alt_names=names, days=days, key_bits=key_bits)
    _write_certificate_files(cert_path, key_path, certificate)
    return 'python'


def ensure_certificate(cert_dir: Path, common_name: str = 'localhost', extra_names=None,
                       days: int = 3650, generator: str = 'auto', key_bits: int = 2048,
                       regenerate: bool = False, logger=None) -> dict:
    """Make sure a usable certificate exists; issue one automatically when it is missing (or regeneration was requested)."""
    cert_path, key_path = certificate_paths(cert_dir)
    if not regenerate and cert_path.exists() and key_path.exists():
        info = inspect_certificate(cert_path, key_path)
        if info is not None:
            if logger is not None:
                logger.info(tr('certs.exists', path=cert_path))
            return info
        if logger is not None:
            logger.warn(tr('certs.unusable', path=cert_path))

    used = generate_certificate(cert_dir, common_name, extra_names, days, generator, key_bits, logger)
    info = inspect_certificate(cert_path, key_path)
    if info is None:
        raise RuntimeError(tr('certs.generate_failed', path=cert_path))
    info['generator'] = used
    info['generated'] = True
    if logger is not None:
        logger.info(tr('certs.generated', path=cert_path, generator=used))
        logger.info(tr('certs.thumbprint', thumbprint=info['thumbprint']))
        if info['alt_names']:
            logger.info(tr('certs.alt_names', names=', '.join(info['alt_names'])))
    return info


def _decode_command_output(stdout: bytes, stderr: bytes) -> str:
    """Decode command output with the system code page, without crashing on odd bytes."""
    encoding = locale.getpreferredencoding(False) or 'utf-8'
    return ((stdout or b'').decode(encoding, errors='replace') +
            (stderr or b'').decode(encoding, errors='replace'))


def _normalize_pem(text: str) -> str:
    """Normalise a PEM blob: strip the BOM, unify line endings, keep one trailing newline."""
    text = (text or '').replace('\ufeff', '')
    text = text.replace('\r\n', '\n').replace('\r', '\n').strip()
    return text + '\n' if text else ''


def validate_certificate_pair(cert_pem: str, key_pem: str) -> tuple[bool, str]:
    """Validate a TLS server certificate + private key pair before it is used.

    The relay answers browsers over ``wss://``, so the imported identity must
    actually work as a TLS server certificate.  Checks, in order:

    * both blobs are PEM of the expected kind (certificate / private key),
    * the private key matches the certificate's public key,
    * the certificate is inside its validity window,
    * the certificate may be used for server authentication (a ``serverAuth``
      extended-key-usage, or no EKU at all),
    * there is at least one usable name (a subjectAltName, else the CN).

    Returns ``(ok, error)`` where ``error`` is a localised reason when ``ok``
    is false.  Nothing is written to disk here; callers decide what to do with
    a valid pair.
    """
    import datetime as _dt

    from cryptography import x509 as cx509
    from cryptography.hazmat.primitives import serialization
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    cert_pem = _normalize_pem(cert_pem)
    key_pem = _normalize_pem(key_pem)
    if '-----BEGIN CERTIFICATE-----' not in cert_pem:
        return False, tr('certs.import_no_cert')
    if '-----BEGIN' not in key_pem or 'PRIVATE KEY-----' not in key_pem:
        return False, tr('certs.import_no_key')

    try:
        cert = cx509.load_pem_x509_certificate(cert_pem.encode('ascii'))
    except Exception as exc:
        return False, tr('certs.import_bad_cert', error=exc)
    try:
        key = serialization.load_pem_private_key(key_pem.encode('ascii'), password=None)
    except Exception as exc:
        return False, tr('certs.import_bad_key', error=exc)
    if not hasattr(key, 'public_key'):
        return False, tr('certs.import_bad_key', error=tr('certs.import_not_rsa'))

    # The private key must belong to the certificate.
    try:
        cert_numbers = cert.public_key().public_numbers()
        key_numbers = key.public_key().public_numbers()
    except Exception as exc:
        return False, tr('certs.import_bad_pair', error=exc)
    if cert_numbers != key_numbers:
        return False, tr('certs.import_mismatch')

    # Validity window.
    now = _dt.datetime.now(_dt.timezone.utc)
    if now < cert.not_valid_before_utc:
        return False, tr('certs.import_not_yet')
    if now > cert.not_valid_after_utc:
        return False, tr('certs.import_expired')

    # Server-authentication usage (browsers require it for wss://).
    try:
        eku = cert.extensions.get_extension_for_class(cx509.ExtendedKeyUsage).value
        server_auth = ExtendedKeyUsageOID.SERVER_AUTH in eku
    except cx509.ExtensionNotFound:
        server_auth = True  # no EKU: usable for any purpose
    if not server_auth:
        return False, tr('certs.import_not_server')

    # A usable name, otherwise the browser cannot match it to the host.
    names = []
    try:
        san = cert.extensions.get_extension_for_class(cx509.SubjectAlternativeName).value
        names = [str(value) for value in san.get_values_for_type(cx509.DNSName)]
        names += [str(value) for value in san.get_values_for_type(cx509.IPAddress)]
    except cx509.ExtensionNotFound:
        pass
    common_name = ''
    try:
        common_name = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
    except Exception:
        pass
    if not names and not common_name:
        return False, tr('certs.import_no_name')

    return True, ''


def import_certificate(cert_dir, cert_pem: str | None = None, key_pem: str | None = None,
                       cert_path: str | None = None, key_path: str | None = None,
                       logger=None) -> dict:
    """Import a user-supplied TLS certificate + private key into ``cert_dir``.

    The pair may be given as PEM text or as file paths (or a mix).  The pair is
    validated first; an invalid pair is refused and the existing certificate is
    left untouched.  On success the files are written as ``cert.pem`` /
    ``key.pem`` and picked up by the normal TLS loading path, so a user can use
    a certificate issued by a real CA (e.g. Let's Encrypt) instead of the
    built-in self-signed one.  Returns the same shape as ``inspect_certificate``
    plus ``source='custom'`` / ``imported=True``.
    """
    cert_dir = Path(cert_dir)
    if cert_pem is None and cert_path:
        cert_pem = Path(cert_path).read_text(encoding='ascii', errors='ignore')
    if key_pem is None and key_path:
        key_pem = Path(key_path).read_text(encoding='ascii', errors='ignore')
    if not _normalize_pem(cert_pem) or not _normalize_pem(key_pem):
        raise ValueError(tr('certs.import_missing'))

    ok, error = validate_certificate_pair(cert_pem, key_pem)
    if not ok:
        raise ValueError(error)

    cert_dir.mkdir(parents=True, exist_ok=True)
    cert_out, key_out = certificate_paths(cert_dir)
    cert_out.write_text(_normalize_pem(cert_pem), encoding='ascii')
    key_out.write_text(_normalize_pem(key_pem), encoding='ascii')
    if os.name != 'nt':  # Windows has no POSIX permission bits
        try:
            os.chmod(key_out, 0o600)
        except OSError:
            pass

    info = inspect_certificate(cert_out, key_out) or {}
    info['source'] = 'custom'
    info['imported'] = True
    if logger is not None:
        logger.info(tr('certs.imported', path=cert_out))
        logger.info(tr('certs.thumbprint', thumbprint=info.get('thumbprint', '')))
        if info.get('alt_names'):
            logger.info(tr('certs.alt_names', names=', '.join(info['alt_names'])))
    return info


def install_to_trust_store(cert_path: Path, logger=None) -> tuple[bool, str]:
    """Import the certificate into the current user's "Trusted Root Certification Authorities" store (Windows)."""
    cert_path = Path(cert_path)
    # Android has no certutil / system trust-store import; the client app must
    # trust the certificate itself, so the whole flow is skipped there.
    if is_android():
        return False, tr('certs.android_no_import')
    if not cert_path.exists():
        return False, tr('certs.file_missing', path=cert_path)
    if platform.system() != 'Windows':
        return False, tr('certs.windows_only')
    command = ['certutil', '-user', '-addstore', 'root', str(cert_path)]
    try:
        completed = subprocess.run(command, capture_output=True, timeout=60)
    except Exception as exc:
        return False, tr('certs.certutil_failed', error=exc)
    output = _decode_command_output(completed.stdout, completed.stderr).strip()
    ok = completed.returncode == 0
    if logger is not None:
        if ok:
            logger.info(tr('certs.installed', path=cert_path))
            logger.info(tr('certs.restart_browser'))
        else:
            logger.error(tr('certs.import_failed', output=output))
    return ok, output
