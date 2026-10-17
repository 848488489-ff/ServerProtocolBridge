"""Generate self-signed X.509 certificates in pure Python (RSA + SHA-256).

Browsers only accept wss://, and they do not trust self-signed certificates,
so this tool issues a self-signed certificate with SANs for
localhost / 127.0.0.1 / ::1 and friends, which the user imports into the
system trust store.  No third-party libraries such as cryptography are
needed here -- the standard library is enough to build the whole
certificate.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import ipaddress
import math
import secrets

from . import der
from .i18n import tr

OID_RSA_ENCRYPTION = '1.2.840.113549.1.1.1'
OID_SHA256_WITH_RSA = '1.2.840.113549.1.1.11'
OID_COMMON_NAME = '2.5.4.3'
OID_ORGANIZATION = '2.5.4.10'
OID_KEY_USAGE = '2.5.29.15'
OID_SUBJECT_ALT_NAME = '2.5.29.17'
OID_BASIC_CONSTRAINTS = '2.5.29.19'
OID_EXT_KEY_USAGE = '2.5.29.37'
OID_SUBJECT_KEY_ID = '2.5.29.14'
OID_AUTHORITY_KEY_ID = '2.5.29.35'
OID_SERVER_AUTH = '1.3.6.1.5.5.7.3.1'

# DER prefix: DigestInfo(SHA-256, no parameters) + digest placeholder
_SHA256_DIGEST_INFO = bytes.fromhex('3031300d060960864801650304020105000420')

# keyUsage bits (from the MSB): digitalSignature(0) | keyEncipherment(2) | keyCertSign(5) => 0b10100100
_KEY_USAGE_BITS = (0xA4, 2)


def _sha1(data: bytes) -> bytes:
    try:
        return hashlib.sha1(data, usedforsecurity=False).digest()
    except TypeError:  # very old Pythons have no usedforsecurity argument
        return hashlib.sha1(data).digest()


def _small_primes(limit: int = 4096) -> list[int]:
    sieve = bytearray([1]) * (limit + 1)
    sieve[0:2] = b'\x00\x00'
    for number in range(2, int(limit ** 0.5) + 1):
        if sieve[number]:
            sieve[number * number::number] = bytearray(len(sieve[number * number::number]))
    return [i for i, flag in enumerate(sieve) if flag]


_SMALL_PRIMES = _small_primes()


def _is_probable_prime(number: int, rounds: int = 24) -> bool:
    """Miller-Rabin primality test."""
    if number < 2:
        return False
    for prime in _SMALL_PRIMES:
        if number % prime == 0:
            return number == prime
    exponent, remainder = number - 1, 0
    while exponent % 2 == 0:
        exponent //= 2
        remainder += 1
    for _ in range(rounds):
        base = secrets.randbelow(number - 3) + 2
        value = pow(base, exponent, number)
        if value in (1, number - 1):
            continue
        for _ in range(remainder - 1):
            value = value * value % number
            if value == number - 1:
                break
        else:
            return False
    return True


def _generate_prime(bits: int) -> int:
    while True:
        candidate = secrets.randbits(bits) | (1 << (bits - 1)) | (1 << (bits - 2)) | 1
        divisible = False
        for prime in _SMALL_PRIMES:
            if prime * prime > candidate:
                break
            if candidate % prime == 0:
                divisible = True
                break
        if not divisible and _is_probable_prime(candidate):
            return candidate


def generate_rsa_key(bits: int = 2048, public_exponent: int = 65537) -> dict:
    """Generate an RSA private key (returns the components; the key itself never leaves this process)."""
    if bits < 1024 or bits % 2:
        raise ValueError(tr('x509.bad_key_bits'))
    while True:
        p = _generate_prime(bits // 2)
        q = _generate_prime(bits - bits // 2)
        if p == q:
            continue
        n = p * q
        if n.bit_length() != bits:
            continue
        phi = (p - 1) * (q - 1)
        if math.gcd(public_exponent, phi) != 1:
            continue
        d = pow(public_exponent, -1, phi)
        if d.bit_length() < bits // 2:  # keep the private exponent long enough
            continue
        if p < q:
            p, q = q, p
        return {
            'n': n, 'e': public_exponent, 'd': d, 'p': p, 'q': q,
            'dp': d % (p - 1), 'dq': d % (q - 1), 'qinv': pow(q, -1, p),
            'bits': bits,
        }


def public_key_der(key: dict) -> bytes:
    """RSAPublicKey ::= SEQUENCE { modulus INTEGER, publicExponent INTEGER }"""
    return der.sequence(der.integer(key['n']), der.integer(key['e']))


def subject_public_key_info(key: dict) -> bytes:
    """SubjectPublicKeyInfo (the public key structure used inside X.509)."""
    algorithm = der.sequence(der.oid(OID_RSA_ENCRYPTION), der.null())
    return der.sequence(algorithm, der.bit_string(public_key_der(key), 0))


def private_key_der(key: dict) -> bytes:
    """PKCS#1 RSAPrivateKey."""
    return der.sequence(
        der.integer(0), der.integer(key['n']), der.integer(key['e']), der.integer(key['d']),
        der.integer(key['p']), der.integer(key['q']), der.integer(key['dp']),
        der.integer(key['dq']), der.integer(key['qinv']),
    )


def sign_sha256(key: dict, data: bytes) -> bytes:
    """RSASSA-PKCS1-v1_5 signature (used to self-sign the certificate)."""
    digest_info = _SHA256_DIGEST_INFO + hashlib.sha256(data).digest()
    size = (key['bits'] + 7) // 8
    if len(digest_info) + 11 > size:
        raise ValueError(tr('x509.key_too_small'))
    block = b'\x00\x01' + b'\xff' * (size - len(digest_info) - 3) + b'\x00' + digest_info
    signature = pow(int.from_bytes(block, 'big'), key['d'], key['n'])
    return signature.to_bytes(size, 'big')


def to_pem(label: str, data: bytes) -> str:
    encoded = base64.b64encode(data).decode('ascii')
    lines = [encoded[i:i + 64] for i in range(0, len(encoded), 64)]
    return '-----BEGIN %s-----\n%s\n-----END %s-----\n' % (label, '\n'.join(lines), label)


def pem_to_der(pem: str) -> bytes:
    body = ''.join(line.strip() for line in pem.splitlines() if '-----' not in line)
    return base64.b64decode(body)


def _general_name(value: str) -> bytes:
    """GeneralName: IP addresses use [7] IMPLICIT OCTET STRING, domain names use [2] IMPLICIT IA5String."""
    text = value.strip()
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        address = None
    if address is not None:
        return der.context(7, address.packed, constructed=False)
    try:
        return der.context(2, text.encode('ascii'), constructed=False)
    except UnicodeEncodeError:
        return der.context(2, text.encode('utf-8'), constructed=False)


def _name(common_name: str, organization: str | None) -> bytes:
    rdns = [der.set_of(der.sequence(der.oid(OID_COMMON_NAME), der.utf8_string(common_name)))]
    if organization:
        rdns.append(der.set_of(der.sequence(der.oid(OID_ORGANIZATION), der.utf8_string(organization))))
    return der.sequence(*rdns)


def _extension(oid_value: str, critical: bool, value: bytes) -> bytes:
    items = [der.oid(oid_value)]
    if critical:
        items.append(der.boolean(True))
    items.append(der.octet_string(value))
    return der.sequence(*items)


def _signature_algorithm() -> bytes:
    return der.sequence(der.oid(OID_SHA256_WITH_RSA), der.null())


def _build_certificate_body(key: dict, common_name: str, organization: str | None,
                           alt_names: list[str], days: int) -> bytes:
    now = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    not_before = now - dt.timedelta(days=1)
    not_after = now + dt.timedelta(days=days)
    serial = bytearray(secrets.token_bytes(16))
    serial[0] &= 0x7F
    if serial[0] == 0:
        serial[0] = 1

    public_der = public_key_der(key)
    key_id = _sha1(public_der)
    subject_alt_name = der.sequence(*[_general_name(name) for name in alt_names])

    extensions = der.context(3, der.sequence(
        _extension(OID_SUBJECT_KEY_ID, False, der.octet_string(key_id)),
        _extension(OID_AUTHORITY_KEY_ID, False, der.sequence(der.context(0, key_id, constructed=False))),
        _extension(OID_BASIC_CONSTRAINTS, True, der.sequence(der.boolean(True))),
        _extension(OID_KEY_USAGE, True, der.bit_string(bytes((_KEY_USAGE_BITS[0],)), _KEY_USAGE_BITS[1])),
        _extension(OID_EXT_KEY_USAGE, False, der.sequence(der.oid(OID_SERVER_AUTH))),
        _extension(OID_SUBJECT_ALT_NAME, False, subject_alt_name),
    ), constructed=True)

    name = _name(common_name, organization)
    return der.sequence(
        der.context(0, der.integer(2), constructed=True),   # version v3
        der.integer(bytes(serial)),
        _signature_algorithm(),
        name,                                                 # issuer (self-signed, same as subject)
        der.sequence(der.utc_time(not_before), der.utc_time(not_after)),
        name,                                                 # subject
        subject_public_key_info(key),
        extensions,
    )


def create_self_signed_certificate(common_name: str = 'localhost',
                                   alt_names: list[str] | None = None,
                                   days: int = 3650,
                                   key_bits: int = 2048,
                                   organization: str = 'Server Protocol Bridge') -> dict:
    """Generate a self-signed certificate; returns the PEM text and the raw DER."""
    names = list(alt_names) if alt_names else ['localhost', '127.0.0.1', '::1']
    if common_name and common_name not in names:
        names.insert(0, common_name)
    key = generate_rsa_key(key_bits)
    body = _build_certificate_body(key, common_name, organization, names, days)
    signature = sign_sha256(key, body)
    certificate = der.sequence(body, _signature_algorithm(), der.bit_string(signature, 0))
    return {
        'cert_pem': to_pem('CERTIFICATE', certificate),
        'key_pem': to_pem('RSA PRIVATE KEY', private_key_der(key)),
        'cert_der': certificate,
        'common_name': common_name,
        'alt_names': names,
        'days': days,
        'key_bits': key_bits,
    }
