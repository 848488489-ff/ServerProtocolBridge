"""Packet-field reader and per-packet readers, split from check_frames.py."""

from __future__ import annotations
import argparse
import base64
import json
import os
import socket
import ssl
import struct
import sys
import threading
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse
from proxy import eagler, vanilla, wsproto
from proxy.config import Config

class Reader:
    """Read a packet body using the 1.8 data types; reading past the end is an error."""

    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def left(self) -> int:
        return len(self.data) - self.pos

    def take(self, size: int) -> bytes:
        if self.pos + size > len(self.data):
            raise ValueError('read past the end at byte %d (missing %d)'
                             % (self.pos, self.pos + size - len(self.data)))
        chunk = self.data[self.pos:self.pos + size]
        self.pos += size
        return chunk

    def varint(self) -> int:
        value, self.pos = vanilla.read_varint(self.data, self.pos)
        return value

    def u8(self) -> int:
        return self.take(1)[0]

    def i8(self) -> int:
        return int.from_bytes(self.take(1), 'big', signed=True)

    def u16(self) -> int:
        return int.from_bytes(self.take(2), 'big')

    def i16(self) -> int:
        return int.from_bytes(self.take(2), 'big', signed=True)

    def i32(self) -> int:
        return int.from_bytes(self.take(4), 'big', signed=True)

    def i64(self) -> int:
        return int.from_bytes(self.take(8), 'big', signed=True)

    def f32(self) -> float:
        return struct.unpack('>f', self.take(4))[0]

    def f64(self) -> float:
        return struct.unpack('>d', self.take(8))[0]

    def boolean(self) -> bool:
        return self.u8() != 0

    def string(self) -> str:
        return self.take(self.varint()).decode('utf-8', 'replace')

    def uuid(self) -> bytes:
        return self.take(16)

    def rest(self) -> bytes:
        return self.take(self.left())
def _chunk_data(r: Reader):
    chunk_x, chunk_z, full = r.i32(), r.i32(), r.boolean()
    size = r.varint()
    if size < 0 or size > r.left():
        raise ValueError('ChunkData declares %d bytes but only %d remain' % (size, r.left()))
    r.take(size)
def _map_chunk_bulk(r: Reader):
    r.boolean()
    count = r.varint()
    for _ in range(count):
        r.i32(), r.i32(), r.u16()
    for _ in range(count):
        size = r.varint()
        if size < 0 or size > r.left():
            raise ValueError('MapChunkBulk declares %d bytes but only %d remain' % (size, r.left()))
        r.take(size)
def _explosion(r: Reader):
    r.f32(), r.f32(), r.f32(), r.f32()
    count = r.i32()
    if count < 0 or count * 3 > r.left() + 12:
        raise ValueError('Explosion declares %d blocks but only %d bytes remain' % (count, r.left()))
    for _ in range(count):
        r.i8(), r.i8(), r.i8()
    r.f32(), r.f32(), r.f32()
def _particle(r: Reader):
    r.i32(), r.boolean()
    r.f32(), r.f32(), r.f32()
    r.f32(), r.f32(), r.f32()
    r.f32()
    for _ in range(r.i32()):
        r.varint()
def _entity_properties(r: Reader):
    r.varint()
    for _ in range(r.i32()):
        r.string(), r.f64()
        for _ in range(r.i16()):
            r.uuid(), r.f64(), r.i8()
def _player_list_item(r: Reader):
    action = r.varint()
    for _ in range(r.varint()):
        r.uuid()
        if action == 0:                      # add player: name + property list (skin signatures take a lot of space)
            r.string()
            for _ in range(r.varint()):
                r.string(), r.string()
                if r.boolean():
                    r.string()
        elif action == 1:
            r.varint()
        elif action == 2:
            r.varint()
        elif action == 3:
            r.boolean()
        elif action == 4:
            r.string()
def _scoreboard_objective(r: Reader):
    r.string()
    mode = r.u8()
    if mode != 1:                            # 1 = remove, no display name / type fields follow
        r.string(), r.string()               # display name + type (integer/hearts)
def _combat_event(r: Reader):
    event = r.varint()
    if event == 0:
        r.varint(), r.i32()
    elif event == 1:
        r.varint()
    elif event == 2:
        r.varint(), r.i32(), r.i32()
