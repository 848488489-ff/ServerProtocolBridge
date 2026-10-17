"""加密握手支持: RSA 公钥加密 + AES-128-CFB8 流加密。

原版服务器发加密请求 (Login Encryption Request, 0x01) 时, 正常流程是:

    服务器 → 客户端: 服务器 ID + RSA 公钥 + 验证令牌
    客户端 → 服务器: RSA(共享密钥) + RSA(验证令牌)
    之后两个方向: AES-128-CFB8(key = 共享密钥, iv = 共享密钥)

不少服务器(尤其是国内"看起来像正版"的)开着这套握手, 但并不真的拿它去 Mojang
校验会话 —— 也就是说**离线账号照样能进**。所以这层必须代做, 否则就会像只认识
离线模式服务器那样, 一看到加密请求就把玩家劝退。

AES 走 cryptography(或 pycryptodome): 纯 Python 版 AES-CFB8 每字节都要算一次
分组加密, 进游戏后连区块数据都收不顺, 没有实用价值。
"""

from __future__ import annotations

# 后端实现: 'cryptography' / 'pycryptodome' / ''(都不可用)
_BACKEND = ''

try:                                                    # 优先 cryptography
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import padding as _asym_padding
    from cryptography.hazmat.primitives.ciphers import Cipher as _Cipher
    from cryptography.hazmat.primitives.ciphers import algorithms as _cipher_algorithms

    try:                                                # cryptography >= 45 挪到了 decrepit
        from cryptography.hazmat.decrepit.ciphers.modes import CFB8 as _Cfb8
    except ImportError:                                 # 老版本还在原处
        from cryptography.hazmat.primitives.ciphers.modes import CFB8 as _Cfb8

    _BACKEND = 'cryptography'
except Exception:                                       # pragma: no cover - 环境相关
    try:
        from Crypto.Cipher import AES as _PyCryptoAes
        from Crypto.Cipher import PKCS1_v1_5 as _PyCryptoPkcs1
        from Crypto.PublicKey import RSA as _PyCryptoRsa

        _BACKEND = 'pycryptodome'
    except Exception:
        _BACKEND = ''


class CryptoUnavailable(RuntimeError):
    """没有可用的 AES 实现, 无法完成加密握手。"""


def available() -> bool:
    return bool(_BACKEND)


def backend_name() -> str:
    return _BACKEND


def _require() -> None:
    if not _BACKEND:
        raise CryptoUnavailable(
            '缺少 AES 库, 无法完成加密握手 —— 请安装 cryptography: pip install cryptography')


# ---------- RSA ----------

def _parse_public_key_der(der_bytes: bytes) -> tuple[int, int]:
    """从 SubjectPublicKeyInfo / RSAPublicKey 里取出 (模数, 指数)。"""

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
        raise ValueError('公钥不是 SEQUENCE')
    # 可能是 SubjectPublicKeyInfo: SEQUENCE { SEQUENCE{...}, BIT STRING { SEQUENCE{n,e} } }
    tag, first, after = read_element(body, 0)
    if tag == 0x30:                                     # SPKI: 跳过算法标识, 取 BIT STRING
        tag, bit_string, _ = read_element(body, after)
        if tag != 0x03:
            raise ValueError('公钥里没有 BIT STRING')
        body = bit_string[1:]                           # 去掉补零计数
        tag, rest, _ = read_element(body, 0)            # RSAPublicKey SEQUENCE
        if tag == 0x30:
            body = rest
    tag, modulus, after = read_element(body, 0)
    if tag != 0x02:
        raise ValueError('公钥里没有模数')
    tag, exponent, _ = read_element(body, after)
    if tag != 0x02:
        raise ValueError('公钥里没有指数')
    return (int.from_bytes(modulus, 'big'), int.from_bytes(exponent, 'big'))


def rsa_encrypt(public_key_der: bytes, data: bytes) -> bytes:
    """用服务器给的公钥做 PKCS#1 v1.5 加密(原版加密握手用的就是这个)。"""
    _require()
    if _BACKEND == 'cryptography':
        key = serialization.load_der_public_key(public_key_der)
        return key.encrypt(data, _asym_padding.PKCS1v15())
    modulus, exponent = _parse_public_key_der(public_key_der)
    key = _PyCryptoRsa.construct((modulus, exponent))
    return _PyCryptoPkcs1.new(key).encrypt(data)


# ---------- AES-128-CFB8 ----------

class AesCfb8:
    """AES-128-CFB8 流密码(原版 Minecraft 用的就是这个)。

    CFB8 是流模式, 加解密是同一个操作、长度不变, 所以一条流的**每个方向**各要
    一个实例(两边的状态各自独立推进)。
    """

    def __init__(self, key: bytes, iv: bytes):
        _require()
        if len(key) != 16:
            raise ValueError('AES-128 需要 16 字节密钥')
        if len(iv) != 16:
            raise ValueError('CFB8 需要 16 字节 IV')
        self.key = bytes(key)
        self.iv = bytes(iv)
        if _BACKEND == 'cryptography':
            self._encryptor = _Cipher(_cipher_algorithms.AES(self.key),
                                      _Cfb8(self.iv)).encryptor()
            self._decryptor = _Cipher(_cipher_algorithms.AES(self.key),
                                      _Cfb8(self.iv)).decryptor()
            self._aes_enc = self._aes_dec = None
        else:
            # pycryptodome 的 CFB 对象会保存链接状态, 一个对象不能同时当加密和解密用
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
