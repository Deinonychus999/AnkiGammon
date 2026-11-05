"""Decoder for Smile, the binary JSON that BGBlitz writes inside .bgf files.

Spec: github.com/FasterXML/smile-format-specification. Covers every token
except BigInteger, BigDecimal and binary data, which BGBlitz does not write.
"""

import struct
from typing import Any, List

MAGIC = b':)\n'
_SHARED_NAMES, _SHARED_VALUES = 0x01, 0x02
_TABLE_LIMIT = 1024

_END = object()


class SmileError(ValueError):
    pass


class _Decoder:
    def __init__(self, data: bytes):
        if data[:3] != MAGIC or len(data) < 4:
            raise SmileError("missing Smile header")
        self.buf = data
        self.pos = 4
        self.names: List[str] = []
        self.values: List[str] = []
        self.share_names = bool(data[3] & _SHARED_NAMES)
        self.share_values = bool(data[3] & _SHARED_VALUES)

    def byte(self) -> int:
        if self.pos >= len(self.buf):
            raise SmileError("Smile data ends early")
        b = self.buf[self.pos]
        self.pos += 1
        return b

    def take(self, n: int) -> bytes:
        end = self.pos + n
        if end > len(self.buf):
            raise SmileError("Smile data ends early")
        chunk = self.buf[self.pos:end]
        self.pos = end
        return chunk

    def text(self, n: int) -> str:
        return self.take(n).decode('utf-8')

    def until_end_marker(self) -> str:
        end = self.buf.find(0xFC, self.pos)
        if end < 0:
            raise SmileError("unterminated Smile string")
        chunk = self.buf[self.pos:end]
        self.pos = end + 1
        return chunk.decode('utf-8')

    def vint(self) -> int:
        acc = 0
        while True:
            b = self.byte()
            if b & 0x80:
                acc = (acc << 6) | (b & 0x3F)
                return (acc >> 1) ^ -(acc & 1)
            acc = (acc << 7) | b

    def packed(self, n: int) -> int:
        acc = 0
        for b in self.take(n):
            acc = (acc << 7) | (b & 0x7F)
        return acc

    @staticmethod
    def lookup(table: List[str], index: int) -> str:
        if index >= len(table):
            raise SmileError("Smile back-reference to an unknown string")
        return table[index]

    @staticmethod
    def remember(table: List[str], s: str) -> None:
        if len(table) >= _TABLE_LIMIT:
            table.clear()
        table.append(s)

    def short_value(self, s: str) -> str:
        if self.share_values:
            self.remember(self.values, s)
        return s

    def key(self) -> Any:
        b = self.byte()
        if b == 0xFB:
            return _END
        if b == 0x20:
            return ''
        if 0x30 <= b <= 0x33:
            return self.lookup(self.names, ((b & 0x03) << 8) | self.byte())
        if b == 0x34:
            return self.until_end_marker()
        if 0x40 <= b <= 0x7F:
            return self.lookup(self.names, b - 0x40)
        if 0x80 <= b <= 0xBF:
            name = self.text((b & 0x3F) + 1)
        elif 0xC0 <= b <= 0xF7:
            name = self.text(b - 0xC0 + 2)
        else:
            raise SmileError(f"unknown Smile key token 0x{b:02x}")
        if self.share_names:
            self.remember(self.names, name)
        return name

    def value(self) -> Any:
        b = self.byte()
        if 0x01 <= b <= 0x1F:
            return self.lookup(self.values, b - 1)
        if b == 0x20:
            return ''
        if b == 0x21:
            return None
        if b == 0x22:
            return False
        if b == 0x23:
            return True
        if b in (0x24, 0x25):
            return self.vint()
        if b == 0x28:
            return struct.unpack('>f', struct.pack('>I', self.packed(5) & 0xFFFFFFFF))[0]
        if b == 0x29:
            return struct.unpack('>d', struct.pack('>Q', self.packed(10) & 0xFFFFFFFFFFFFFFFF))[0]
        if 0x40 <= b <= 0x5F:
            return self.short_value(self.text((b & 0x1F) + 1))
        if 0x60 <= b <= 0x7F:
            return self.short_value(self.text((b & 0x1F) + 33))
        if 0x80 <= b <= 0x9F:
            return self.short_value(self.text((b & 0x1F) + 2))
        if 0xA0 <= b <= 0xBF:
            return self.short_value(self.text((b & 0x1F) + 34))
        if 0xC0 <= b <= 0xDF:
            n = b & 0x1F
            return (n >> 1) ^ -(n & 1)
        if b in (0xE0, 0xE4):
            return self.until_end_marker()
        if 0xEC <= b <= 0xEF:
            return self.lookup(self.values, ((b & 0x03) << 8) | self.byte())
        if b == 0xF8:
            items = []
            while True:
                item = self.value()
                if item is _END:
                    return items
                items.append(item)
        if b == 0xF9:
            return _END
        if b == 0xFA:
            obj = {}
            while True:
                k = self.key()
                if k is _END:
                    return obj
                obj[k] = self.value()
        raise SmileError(f"unsupported Smile value token 0x{b:02x}")


def decode(data: bytes) -> Any:
    return _Decoder(data).value()
