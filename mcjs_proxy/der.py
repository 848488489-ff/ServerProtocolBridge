"""极简 DER(ASN.1 Distinguished Encoding Rules) 编码器。

只包含生成 X.509 证书所需要的结构, 不依赖任何第三方库。
"""

from __future__ import annotations

import datetime as dt

TAG_BOOLEAN = 0x01
TAG_INTEGER = 0x02
TAG_BIT_STRING = 0x03
TAG_OCTET_STRING = 0x04
TAG_NULL = 0x05
TAG_OID = 0x06
TAG_UTF8_STRING = 0x0C
TAG_PRINTABLE_STRING = 0x13
TAG_IA5_STRING = 0x16
TAG_UTC_TIME = 0x17
TAG_GENERALIZED_TIME = 0x18
TAG_SEQUENCE = 0x30
TAG_SET = 0x31


def encode_length(length: int) -> bytes:
    """DER 长度: 短格式(<128) 或长格式(首字节高位 1 + 字节数 + 大端字节)。"""
    if length < 0x80:
        return bytes((length,))
    raw = length.to_bytes((length.bit_length() + 7) // 8, 'big')
    return bytes((0x80 | len(raw),)) + raw


def tlv(tag: int, value: bytes) -> bytes:
    """构造一个 TLV: 标签 + 长度 + 内容。"""
    return bytes((tag,)) + encode_length(len(value)) + value


def boolean(value: bool) -> bytes:
    return tlv(TAG_BOOLEAN, b'\xff' if value else b'\x00')


def integer(value: int | bytes) -> bytes:
    """INTEGER。整数按最短形式编码并保证是正数(最高位不是 1 时不补 0)。"""
    if isinstance(value, int):
        if value == 0:
            raw = b'\x00'
        else:
            # 多留一个字节, 保证最高位为 0 时不会被误认为负数
            raw = value.to_bytes((value.bit_length() + 8) // 8, 'big')
    else:
        raw = bytes(value).lstrip(b'\x00') or b'\x00'
    if raw[0] & 0x80:
        raw = b'\x00' + raw
    return tlv(TAG_INTEGER, raw)


def oid(dotted: str) -> bytes:
    """OBJECT IDENTIFIER, 例如 '1.2.840.113549.1.1.11'。"""
    parts = [int(p) for p in dotted.split('.')]
    if len(parts) < 2:
        raise ValueError('非法的 OID: %s' % dotted)
    data = bytearray([parts[0] * 40 + parts[1]])
    for value in parts[2:]:
        chunk = [value & 0x7F]
        value >>= 7
        while value:
            chunk.insert(0, (value & 0x7F) | 0x80)
            value >>= 7
        data.extend(chunk)
    return tlv(TAG_OID, bytes(data))


def bit_string(data: bytes, unused_bits: int = 0) -> bytes:
    """BIT STRING, unused_bits 为末尾未使用位数。"""
    return tlv(TAG_BIT_STRING, bytes((unused_bits,)) + data)


def octet_string(data: bytes) -> bytes:
    return tlv(TAG_OCTET_STRING, data)


def null() -> bytes:
    return tlv(TAG_NULL, b'')


def utf8_string(text: str) -> bytes:
    return tlv(TAG_UTF8_STRING, text.encode('utf-8'))


def printable_string(text: str) -> bytes:
    return tlv(TAG_PRINTABLE_STRING, text.encode('ascii'))


def ia5_string(text: str) -> bytes:
    return tlv(TAG_IA5_STRING, text.encode('ascii'))


def sequence(*items: bytes) -> bytes:
    return tlv(TAG_SEQUENCE, b''.join(items))


def set_of(*items: bytes) -> bytes:
    return tlv(TAG_SET, b''.join(items))


def context(number: int, data: bytes, constructed: bool = True) -> bytes:
    """上下文标签 [n]: 构造类型(EXPLICIT) 或基本类型(IMPLICIT)。"""
    return tlv((0xA0 if constructed else 0x80) | number, data)


def generalized_time(value: dt.datetime) -> bytes:
    text = '%04d%02d%02d%02d%02d%02dZ' % (
        value.year, value.month, value.day, value.hour, value.minute, value.second)
    return tlv(TAG_GENERALIZED_TIME, text.encode('ascii'))


def utc_time(value: dt.datetime) -> bytes:
    """1950~2049 年用 UTCTime, 其余年份用 GeneralizedTime。"""
    if 1950 <= value.year < 2050:
        text = '%02d%02d%02d%02d%02d%02dZ' % (
            value.year % 100, value.month, value.day, value.hour, value.minute, value.second)
        return tlv(TAG_UTC_TIME, text.encode('ascii'))
    return generalized_time(value)