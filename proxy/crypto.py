"""Encryption handshake support: RSA public-key encryption + AES-128-CFB8 stream cipher.

When a vanilla server sends the Login Encryption Request (0x01), the normal
flow is:

    server -> client: server id + RSA public key + verify token
    client -> server: RSA(shared secret) + RSA(verify token)
    afterwards both directions: AES-128-CFB8(key = shared secret, iv = shared secret)

Plenty of servers (especially the ones that "look official") enable this
handshake but never actually validate the session against Mojang -- in other
words **offline accounts can still join**.  The bridge must therefore perform
this step on the client's behalf; otherwise it would look just like an
offline-mode-only server and turn players away the moment the encryption
request arrives.

AES runs through cryptography (or pycryptodome): a pure-Python AES-CFB8 would
have to compute one block-cipher call per byte, and even receiving chunk data
in-game would stall, so it has no practical value.
"""

from __future__ import annotations

import threading

from .i18n import tr

# Backend implementation: 'cryptography' / 'pycryptodome' / '' (neither available).
# Both packages pull in native libraries, so the probe runs on the first
# encrypted handshake instead of while the window is opening.  A plain bridge
# session against an offline-mode server never pays for it.
_BACKEND = ''
_BACKEND_PROBED = False
_BACKEND_LOCK = threading.Lock()
serialization = None
_asym_padding = None
_Cipher = None
_cipher_algorithms = None
_Cfb8 = None
_PyCryptoAes = None
_PyCryptoPkcs1 = None
_PyCryptoRsa = None


def _load_backend() -> None:
    global _BACKEND, _BACKEND_PROBED
    global serialization, _asym_padding, _Cipher, _cipher_algorithms, _Cfb8
    global _PyCryptoAes, _PyCryptoPkcs1, _PyCryptoRsa
    if _BACKEND_PROBED:
        return
    with _BACKEND_LOCK:
        if _BACKEND_PROBED:
            return
        _BACKEND_PROBED = True
        try:                                            # cryptography first
            from cryptography.hazmat.primitives import serialization as _serialization
            from cryptography.hazmat.primitives.asymmetric import padding as _padding
            from cryptography.hazmat.primitives.ciphers import Cipher as _cipher
            from cryptography.hazmat.primitives.ciphers import algorithms as _algorithms

            try:                                        # cryptography >= 45 moved this to decrepit
                from cryptography.hazmat.decrepit.ciphers.modes import CFB8 as _cfb8
            except ImportError:                         # older versions keep it in place
                from cryptography.hazmat.primitives.ciphers.modes import CFB8 as _cfb8
        except Exception:                               # pragma: no cover - environment dependent
            pass
        else:
            serialization = _serialization
            _asym_padding = _padding
            _Cipher = _cipher
            _cipher_algorithms = _algorithms
            _Cfb8 = _cfb8
            _BACKEND = 'cryptography'
            return
        try:
            from Crypto.Cipher import AES as _aes
            from Crypto.Cipher import PKCS1_v1_5 as _pkcs1
            from Crypto.PublicKey import RSA as _rsa
        except Exception:
            _BACKEND = ''
            return
        _PyCryptoAes = _aes
        _PyCryptoPkcs1 = _pkcs1
        _PyCryptoRsa = _rsa
        _BACKEND = 'pycryptodome'


class CryptoUnavailable(RuntimeError):
    """No AES implementation is available, so the encrypted handshake cannot be completed."""


def available() -> bool:
    _load_backend()
    return bool(_BACKEND)


def backend_name() -> str:
    _load_backend()
    return _BACKEND


def _require() -> None:
    _load_backend()
    if not _BACKEND:
        raise CryptoUnavailable(tr('crypto.missing_backend'))


# ---------- RSA ----------

def _parse_public_key_der(der_bytes: bytes) -> tuple[int, int]:
    """Extract (modulus, exponent) from a SubjectPublicKeyInfo / RSAPublicKey blob."""

    def read_element(data: bytes, pos: int) -> tuple[int, bytes, int]:
        tag = data[pos]
        length = data[pos + 1]
        pos += 2
        if length & 0x80:
            count = length & 0x7F
            length = int.from_bytes(data[pos:pos + count], 'big')
            pos += count
        return tag, data[pos:pos + length], pos + length

    tag, body, _ = read_element(der_bytes, 0)
    if tag != 0x30:
        raise ValueError(tr('crypto.key_not_sequence'))
    # May be a SubjectPublicKeyInfo: SEQUENCE { SEQUENCE{...}, BIT STRING { SEQUENCE{n,e} } }
    tag, first, after = read_element(body, 0)
    if tag == 0x30:                                     # SPKI: skip the algorithm identifier, take the BIT STRING
        tag, bit_string, _ = read_element(body, after)
        if tag != 0x03:
            raise ValueError(tr('crypto.key_no_bit_string'))
        body = bit_string[1:]                           # drop the unused-bits count
        tag, rest, _ = read_element(body, 0)            # RSAPublicKey SEQUENCE
        if tag == 0x30:
            body = rest
    tag, modulus, after = read_element(body, 0)
    if tag != 0x02:
        raise ValueError(tr('crypto.key_no_modulus'))
    tag, exponent, _ = read_element(body, after)
    if tag != 0x02:
        raise ValueError(tr('crypto.key_no_exponent'))
    return (int.from_bytes(modulus, 'big'), int.from_bytes(exponent, 'big'))


def rsa_encrypt(public_key_der: bytes, data: bytes) -> bytes:
    """Encrypt with the server's public key using PKCS#1 v1.5 (what the vanilla encryption handshake uses)."""
    _require()
    if _BACKEND == 'cryptography':
        key = serialization.load_der_public_key(public_key_der)
        return key.encrypt(data, _asym_padding.PKCS1v15())
    modulus, exponent = _parse_public_key_der(public_key_der)
    key = _PyCryptoRsa.construct((modulus, exponent))
    return _PyCryptoPkcs1.new(key).encrypt(data)


# ---------- AES-128-CFB8 ----------

class AesCfb8:
    """AES-128-CFB8 stream cipher (what vanilla Minecraft uses).

    CFB8 is a stream mode: encryption and decryption are the same operation
    and the length never changes, so one connection needs **one instance per
    direction** (the two sides advance their own state independently).
    """

    def __init__(self, key: bytes, iv: bytes):
        _require()
        if len(key) != 16:
            raise ValueError(tr('crypto.bad_key_size'))
        if len(iv) != 16:
            raise ValueError(tr('crypto.bad_iv_size'))
        self.key = bytes(key)
        self.iv = bytes(iv)
        if _BACKEND == 'cryptography':
            self._encryptor = _Cipher(_cipher_algorithms.AES(self.key),
                                      _Cfb8(self.iv)).encryptor()
            self._decryptor = _Cipher(_cipher_algorithms.AES(self.key),
                                      _Cfb8(self.iv)).decryptor()
            self._aes_enc = self._aes_dec = None
        else:
            # pycryptodome CFB objects keep the chaining state, so one object cannot encrypt and decrypt at the same time
            self._aes_enc = _PyCryptoAes.new(self.key, _PyCryptoAes.MODE_CFB,
                                             iv=self.iv, segment_size=8)
            self._aes_dec = _PyCryptoAes.new(self.key, _PyCryptoAes.MODE_CFB,
                                             iv=self.iv, segment_size=8)
            self._encryptor = self._decryptor = None

    def encrypt(self, data: bytes) -> bytes:
        if not data:
            return b''
        if self._aes_enc is not None:
            return self._aes_enc.encrypt(data)
        return self._encryptor.update(data)

    def decrypt(self, data: bytes) -> bytes:
        if not data:
            return b''
        if self._aes_dec is not None:
            return self._aes_dec.decrypt(data)
        return self._decryptor.update(data)
