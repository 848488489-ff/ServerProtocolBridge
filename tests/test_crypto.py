"""加密模块的测试: RSA 公钥加密 / AES-128-CFB8 流加密。

    python -m unittest discover -s tests -v

CFB8 的对照实现直接照 NIST SP 800-38A 对 CFB 的定义逐字节写(每字节做一次分组加密,
移位寄存器里进的是密文字节), 用来验证我们调库的参数(段长度 = 1 字节)没配错。
"""

from __future__ import annotations

import sys
import unittest
import unittest.mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcjs_proxy import crypto, x509  # noqa: E402


def _aes_block(key: bytes, block: bytes) -> bytes:
    """单次 AES 分组加密(只给对照实现用)。"""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    encryptor = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    return encryptor.update(block) + encryptor.finalize()


def cfb8_by_spec(key: bytes, iv: bytes, data: bytes, decrypt: bool = False) -> bytes:
    """按定义逐字节算 CFB8。

    加密: 密文字节 = 明文字节 ^ AES(寄存器)[0], 寄存器左移一位并补入**密文**字节;
    解密: 明文字节 = 密文字节 ^ AES(寄存器)[0], 寄存器左移一位并补入**密文**字节。
    两者都补密文, 区别只在密文是自己算的还是输入给的。
    """
    register = bytearray(iv)
    out = bytearray()
    for byte in data:
        stream = _aes_block(key, bytes(register))
        value = byte ^ stream[0]
        out.append(value)
        register = register[1:] + bytes([byte if decrypt else value])
    return bytes(out)


class AvailabilityTests(unittest.TestCase):
    def test_available_here(self):
        # 开发机/打包机上都装了 cryptography, 这里应该可用
        self.assertTrue(crypto.available())
        self.assertIn(crypto.backend_name(), ('cryptography', 'pycryptodome'))

    def test_missing_library_reports_clearly(self):
        with unittest.mock.patch.object(crypto, '_BACKEND', ''):
            self.assertFalse(crypto.available())
            with self.assertRaises(crypto.CryptoUnavailable):
                crypto.AesCfb8(b'0' * 16, b'0' * 16)
            with self.assertRaises(crypto.CryptoUnavailable):
                crypto.rsa_encrypt(b'\x30\x00', b'x')


class RsaEncryptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = x509.generate_rsa_key(1024)

    def test_parse_spki(self):
        spki = x509.subject_public_key_info(self.key)
        self.assertEqual(crypto._parse_public_key_der(spki), (self.key['n'], self.key['e']))

    def test_parse_pkcs1(self):
        der = x509.public_key_der(self.key)
        self.assertEqual(crypto._parse_public_key_der(der), (self.key['n'], self.key['e']))

    def test_encrypt_is_decryptable(self):
        data = b'0123456789abcdef'
        encrypted = crypto.rsa_encrypt(x509.subject_public_key_info(self.key), data)
        size = (self.key['n'].bit_length() + 7) // 8
        self.assertEqual(len(encrypted), size)
        block = pow(int.from_bytes(encrypted, 'big'), self.key['d'], self.key['n']).to_bytes(size, 'big')
        self.assertTrue(block.startswith(b'\x00\x02'), block[:4].hex())
        self.assertEqual(block[block.index(b'\x00', 2) + 1:], data)


@unittest.skipUnless(crypto.available(), '缺少 AES 库')
class AesCfb8Tests(unittest.TestCase):
    KEY = bytes.fromhex('2b7e151628aed2a6abf7158809cf4f3c')
    IV = bytes.fromhex('000102030405060708090a0b0c0d0e0f')
    PLAIN = bytes.fromhex('6bc1bee22e409f96e93d7e117393172aae2d8a571e03ac9c9eb76fac45af8e51'
                          '30c81c46a35ce411e5fbc1191a0a52eff69f2445df4f9b17ad2b417be66c3710')

    def test_encrypt_matches_spec(self):
        expected = cfb8_by_spec(self.KEY, self.IV, self.PLAIN)
        self.assertEqual(crypto.AesCfb8(self.KEY, self.IV).encrypt(self.PLAIN), expected)

    def test_decrypt_matches_spec(self):
        cipher_text = cfb8_by_spec(self.KEY, self.IV, self.PLAIN)
        expected = cfb8_by_spec(self.KEY, self.IV, cipher_text, decrypt=True)
        self.assertEqual(crypto.AesCfb8(self.KEY, self.IV).decrypt(cipher_text), expected)
        self.assertEqual(expected, self.PLAIN)

    def test_roundtrip(self):
        # 两个方向的流各自独立: 加密用一条, 解密用另一条
        sender = crypto.AesCfb8(self.KEY, self.IV)
        receiver = crypto.AesCfb8(self.KEY, self.IV)
        self.assertEqual(receiver.decrypt(sender.encrypt(self.PLAIN)), self.PLAIN)

    def test_streaming_split_matches_one_shot(self):
        """分多次喂进来的结果必须和一次喂完完全一样(CFB8 是流模式)。"""
        chunks = [self.PLAIN[:1], self.PLAIN[1:7], b'', self.PLAIN[7:33], self.PLAIN[33:]]
        split = crypto.AesCfb8(self.KEY, self.IV)
        joined = b''.join(split.encrypt(chunk) for chunk in chunks)
        one_shot = crypto.AesCfb8(self.KEY, self.IV).encrypt(self.PLAIN)
        self.assertEqual(joined, one_shot)
        self.assertEqual(cfb8_by_spec(self.KEY, self.IV, joined, decrypt=True), self.PLAIN)

    def test_bad_key_size(self):
        with self.assertRaises(ValueError):
            crypto.AesCfb8(b'0123456789abcde', self.IV)
        with self.assertRaises(ValueError):
            crypto.AesCfb8(self.KEY, b'0123456789abcde')


if __name__ == '__main__':
    unittest.main()
