"""The Smile decoder that reads BGBlitz .bgf files, checked token by token
against the Smile format specification."""

import struct

import pytest

from ankigammon.utils import smile

SHARED_NAMES_AND_VALUES = b":)\n\x03"


def _packed(bits: int, groups: int) -> bytes:
    return bytes((bits >> (7 * k)) & 0x7F for k in reversed(range(groups)))


def _double(value: float) -> bytes:
    return b"\x29" + _packed(struct.unpack(">Q", struct.pack(">d", value))[0], 10)


def _float(value: float) -> bytes:
    return b"\x28" + _packed(struct.unpack(">I", struct.pack(">f", value))[0], 5)


def test_scalars():
    doc = (
        SHARED_NAMES_AND_VALUES + b"\xf8"
        + b"\x21\x22\x23\x20"               # null, false, true, ""
        + b"\xc6\xc1"                       # small ints 3, -1
        + b"\x24\x1f\x8f"                   # VInt over two bytes: zigzag 1999 = -1000
        + b"\x25\x01\x00\x80"               # VLong over three bytes: zigzag 8192 = 4096
        + _double(1.5) + _float(2.5)
        + b"\xf9"
    )
    assert smile.decode(doc) == [None, False, True, "", 3, -1, -1000, 4096, 1.5, 2.5]


def test_strings_of_every_length_class():
    doc = (
        SHARED_NAMES_AND_VALUES + b"\xf8"
        + b"\x41ab"                                  # tiny ASCII, 2 bytes
        + b"\x67" + b"x" * 40                        # short ASCII, 33-64 bytes
        + b"\x80\xc3\xa9"                            # tiny Unicode, 2 bytes
        + b"\xe0" + b"y" * 70 + b"\xfc"              # long ASCII
        + b"\xe4" + "é".encode() * 40 + b"\xfc"      # long Unicode
        + b"\xf9"
    )
    assert smile.decode(doc) == ["ab", "x" * 40, "é", "y" * 70, "é" * 40]


def test_shared_names_and_values_are_back_referenced():
    doc = (
        SHARED_NAMES_AND_VALUES + b"\xf8"
        + b"\xfa\x80a\xc6\x83name\x67" + b"x" * 40 + b"\xfb"
        + b"\xfa\x40\xc2\x41\x01\xfb"       # key refs 0 and 1, value ref 0
        + b"\xfa\x30\x01\xc0\xfb"           # long key ref to index 1
        + b"\xf9"
    )
    assert smile.decode(doc) == [
        {"a": 3, "name": "x" * 40},
        {"a": 1, "name": "x" * 40},
        {"name": 0},
    ]


def test_long_strings_are_never_shared():
    doc = (
        SHARED_NAMES_AND_VALUES + b"\xf8"
        + b"\xe0" + b"y" * 70 + b"\xfc" + b"\x40z" + b"\x01"
        + b"\xf9"
    )
    assert smile.decode(doc) == ["y" * 70, "z", "z"]


def test_names_are_not_shared_unless_the_header_says_so():
    doc = b":)\n\x00" + b"\xfa\x80a\xc2\xfb"
    assert smile.decode(doc) == {"a": 1}
    with pytest.raises(smile.SmileError):
        smile.decode(b":)\n\x00\xf8\xfa\x80a\xc2\xfb\xfa\x40\xc2\xfb\xf9")


@pytest.mark.parametrize("doc", [b"{}", b":)\n", b":)\n\x03\xf8\x41a", b":)\n\x03\x26\x00"])
def test_bad_input_is_refused(doc):
    with pytest.raises(smile.SmileError):
        smile.decode(doc)
