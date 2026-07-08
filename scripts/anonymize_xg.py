"""Anonymize an eXtreme Gammon .xg match file.

Copies an .xg file with all personal data replaced so the result can be
shared or committed as a test fixture:

  * GDF header (uncompressed, at the start of the file): the UTF-16
    GameName / SaveName / LevelName / Comments fields are replaced with
    generic values.
  * HeaderMatchEntry record (first 2560-byte record of the ``temp.xg``
    game-file segment, and its identical copy in ``temp.xgi``): the ANSI
    shortstring fields (SPlayer1/SPlayer2/SEvent/SLocation/SRound) and the
    UTF-16 fields (Player1/Player2/Event/Location/Round/Transcriber) are
    replaced/blanked.  Fields are fixed-size, so the record — and hence the
    parsed decision stream — stays byte-compatible.
  * The embedded board-thumbnail JPEG and all game/analysis records are
    kept verbatim.

Container format (ZLBArchive 1.52, mirrored from
ankigammon/thirdparty/xgdatatools/xgzarc.py which reads it):

    [ GDF header (HeaderSize bytes, starts with 'RGMH') ]
    [ thumbnail JPEG (ThumbnailSize bytes)              ]
    [ archive data: back-to-back zlib segments          ]  <- archivesize
    [ registry: N x 532-byte FileRecord, zlib-compressed]  <- registrysize
    [ 36-byte ArchiveRecord footer                      ]

The archive is rebuilt from scratch: each segment is inflated, patched if
it holds personal data, deflated again, and a new registry + footer
(sizes, offsets, CRC32s) is written.

After writing, the output is re-verified: the original player names must
not appear anywhere in the raw bytes or in any inflated segment (ASCII,
UTF-8 and UTF-16LE) — if they do (e.g. inside free-text RTF comments in a
``temp.xgc`` segment, which this script does not rewrite), nothing is
written and the script exits non-zero.

Usage:
    python scripts/anonymize_xg.py INPUT.xg OUTPUT.xg \
        [--player1 "Player One"] [--player2 "Player Two"]

Only Python stdlib is used (struct + zlib).
"""

from __future__ import annotations

import argparse
import os
import struct
import sys
import zlib
from dataclasses import dataclass
from typing import List, Optional

# ---------------------------------------------------------------------------
# Container constants (see xgzarc.py / xgstruct.py for the read-side twins)
# ---------------------------------------------------------------------------

ARCHIVE_RECORD_SIZE = 36     # trailing ArchiveRecord
FILE_RECORD_SIZE = 532       # one registry entry
GDF_HEADER_SIZE = 8232       # GameDataFormatHdrRecord.SIZEOFREC
GAME_RECORD_SIZE = 2560      # one temp.xg GameFileRecord slot

# Offsets of the UTF-16 string fields inside the GDF header
# ('<4BiiQiLHHBB6s1024H1024H1024H1024H'): 4+4+4+8+4+16 = 40 bytes of
# fixed fields, then four 1024-UTF-16-char arrays.
GDF_GAMENAME_OFF = 40
GDF_STRING_BYTES = 2048

# Offsets inside a HeaderMatchEntry record (EntryType 0), derived from
# xgstruct.HeaderMatchEntry.fromstream's struct format
# '<9x41B41BxllBBBBddlld129Bxxxlll BBB129BlB129Bxx...'.
HME_SPLAYER1_OFF = 9         # Delphi shortstring[40] -> 41 bytes
HME_SPLAYER2_OFF = 50
HME_SPLAYER_LEN = 41
HME_SEVENT_OFF = 136         # shortstring[128] -> 129 bytes
HME_SLOCATION_OFF = 283
HME_SROUND_OFF = 417
HME_SSTRING_LEN = 129
HME_VERSION_OFF = 552        # int32 file version
HME_MAGIC_OFF = 556          # 'DMLI'
# Version >= 24 trailer: base 612 + 8 (v8 CubeLimit/AutoDoubleMax) = 620,
# then <Bx> Transcribed + five 129-UTF-16-char fields.
HME_UNICODE_BASE = 622
HME_USTRING_BYTES = 258
HME_UNICODE_FIELDS = ("Event", "Player1", "Player2", "Location", "Round")
# Version >= 30: Transcriber after TimeSetting (32, v25) + 4 ints (16, v26).
HME_TRANSCRIBER_OFF = HME_UNICODE_BASE + 5 * HME_USTRING_BYTES + 32 + 16

SUSPECT_ENCODINGS = ("ascii", "utf-8", "utf-16-le")


class AnonymizeError(Exception):
    pass


# ---------------------------------------------------------------------------
# Registry / footer records
# ---------------------------------------------------------------------------

@dataclass
class SegmentRecord:
    name: str
    path: str
    data: bytes              # inflated payload
    compressed: bool
    compressionlevel: int


def _unsigned_to_int32(value: int) -> int:
    """struct '<l' needs a signed value; CRC32s are unsigned."""
    return value - 0x100000000 if value >= 0x80000000 else value


def _delphi_shortstring(text: str, field_size: int) -> bytes:
    """Length byte + payload, zero-padded to the full fixed field size."""
    payload = text.encode("latin-1")
    if len(payload) > field_size - 1:
        raise AnonymizeError(
            f"replacement {text!r} too long for {field_size - 1}-byte field")
    return bytes([len(payload)]) + payload.ljust(field_size - 1, b"\x00")


def _utf16_field(text: str, field_bytes: int) -> bytes:
    payload = text.encode("utf-16-le")
    if len(payload) > field_bytes - 2:   # keep at least one NUL terminator
        raise AnonymizeError(
            f"replacement {text!r} too long for {field_bytes}-byte UTF-16 field")
    return payload.ljust(field_bytes, b"\x00")


def _read_delphi_shortstring(buf: bytes, offset: int) -> str:
    length = buf[offset]
    return buf[offset + 1:offset + 1 + length].decode("latin-1")


def _read_utf16_field(buf: bytes, offset: int, field_bytes: int) -> str:
    raw = buf[offset:offset + field_bytes].decode("utf-16-le", errors="replace")
    return raw.split("\x00", 1)[0]


# ---------------------------------------------------------------------------
# Archive reading (mirrors xgzarc.ZlibArchive)
# ---------------------------------------------------------------------------

def read_archive(raw: bytes):
    """Return (start_of_arc_data, arc_version, reserved, [SegmentRecord])."""
    footer = raw[-ARCHIVE_RECORD_SIZE:]
    crc, filecount, version, registrysize, archivesize, compressedreg = (
        struct.unpack("<llllll", footer[:24]))
    reserved = footer[24:]
    crc &= 0xFFFFFFFF

    registry_start = len(raw) - ARCHIVE_RECORD_SIZE - registrysize
    start_of_arc_data = registry_start - archivesize

    body = raw[start_of_arc_data:len(raw) - ARCHIVE_RECORD_SIZE]
    if zlib.crc32(body) & 0xFFFFFFFF != crc:
        raise AnonymizeError("archive CRC mismatch - input file corrupt?")

    registry_blob = raw[registry_start:registry_start + registrysize]
    if compressedreg:
        registry_blob = zlib.decompressobj().decompress(registry_blob)
    if len(registry_blob) < filecount * FILE_RECORD_SIZE:
        raise AnonymizeError("registry shorter than filecount promises")

    segments: List[SegmentRecord] = []
    for i in range(filecount):
        rec = registry_blob[i * FILE_RECORD_SIZE:(i + 1) * FILE_RECORD_SIZE]
        name = _read_delphi_shortstring(rec, 0)
        path = _read_delphi_shortstring(rec, 256)
        osize, csize, start, fcrc = struct.unpack("<llll", rec[512:528])
        stored_flag, complevel = rec[528], rec[529]
        compressed = stored_flag == 0
        fcrc &= 0xFFFFFFFF

        payload = raw[start_of_arc_data + start:
                      start_of_arc_data + start + csize]
        data = zlib.decompressobj().decompress(payload) if compressed else payload
        if len(data) != osize:
            raise AnonymizeError(
                f"segment {name}: inflated to {len(data)} bytes, expected {osize}")
        if zlib.crc32(data) & 0xFFFFFFFF != fcrc:
            raise AnonymizeError(f"segment {name}: CRC mismatch")

        segments.append(SegmentRecord(name, path, data, compressed, complevel))

    return start_of_arc_data, version, reserved, segments


# ---------------------------------------------------------------------------
# Archive writing (write-side mirror of the above)
# ---------------------------------------------------------------------------

def write_archive(prefix: bytes, segments: List[SegmentRecord],
                  version: int, reserved: bytes) -> bytes:
    arc_data = bytearray()
    registry = bytearray()

    for seg in segments:
        if seg.compressed:
            # Always deflate at maximum level: the reader (and XG itself)
            # ignores the recorded level when inflating, and this keeps the
            # tracked fixture small.
            seg.compressionlevel = 9
            payload = zlib.compress(seg.data, 9)
        else:
            payload = seg.data
        start = len(arc_data)
        arc_data += payload

        rec = bytearray(FILE_RECORD_SIZE)
        rec[0:256] = _delphi_shortstring(seg.name, 256)
        rec[256:512] = _delphi_shortstring(seg.path, 256)
        struct.pack_into(
            "<llll", rec, 512,
            len(seg.data), len(payload), start,
            _unsigned_to_int32(zlib.crc32(seg.data) & 0xFFFFFFFF))
        rec[528] = 0 if seg.compressed else 1
        rec[529] = seg.compressionlevel
        registry += rec

    registry_blob = zlib.compress(bytes(registry), 6)

    body = bytes(arc_data) + registry_blob
    footer = struct.pack(
        "<llllll",
        _unsigned_to_int32(zlib.crc32(body) & 0xFFFFFFFF),
        len(segments), version, len(registry_blob), len(arc_data), 1,
    ) + reserved

    return prefix + body + footer


# ---------------------------------------------------------------------------
# Patching
# ---------------------------------------------------------------------------

def collect_personal_strings(gdf: bytes, segments: List[SegmentRecord]) -> List[str]:
    """Every personal string the input declares, for the final leak scan."""
    found = set()
    for off in (GDF_GAMENAME_OFF + GDF_STRING_BYTES,):   # SaveName
        found.add(_read_utf16_field(gdf, off, GDF_STRING_BYTES))
    for seg in segments:
        if seg.name not in ("temp.xg", "temp.xgi") or seg.data[8] != 0:
            continue
        found.add(_read_delphi_shortstring(seg.data, HME_SPLAYER1_OFF))
        found.add(_read_delphi_shortstring(seg.data, HME_SPLAYER2_OFF))
        ver = struct.unpack_from("<l", seg.data, HME_VERSION_OFF)[0]
        if ver >= 24:
            for i, _ in enumerate(HME_UNICODE_FIELDS):
                found.add(_read_utf16_field(
                    seg.data, HME_UNICODE_BASE + i * HME_USTRING_BYTES,
                    HME_USTRING_BYTES))
        if ver >= 30:
            found.add(_read_utf16_field(
                seg.data, HME_TRANSCRIBER_OFF, HME_USTRING_BYTES))
    # Names are what matters; ignore blanks/short tokens ("BM", "5", ...)
    return sorted(s for s in found if len(s) >= 4)


def patch_gdf_header(raw: bytes, player1: str, player2: str) -> bytes:
    if raw[:4] != b"RGMH":
        raise AnonymizeError("not an XG game-data file (missing RGMH magic)")
    header_size = struct.unpack_from("<i", raw, 8)[0]
    if header_size != GDF_HEADER_SIZE:
        raise AnonymizeError(f"unexpected GDF HeaderSize {header_size}")

    patched = bytearray(raw)
    replacements = (
        "Sample match",                        # GameName
        f"{player1} vs. {player2}",            # SaveName
        "",                                    # LevelName
        "",                                    # Comments
    )
    for i, text in enumerate(replacements):
        off = GDF_GAMENAME_OFF + i * GDF_STRING_BYTES
        patched[off:off + GDF_STRING_BYTES] = _utf16_field(text, GDF_STRING_BYTES)
    return bytes(patched)


def patch_header_match_entry(data: bytes, player1: str, player2: str,
                             seg_name: str) -> bytes:
    """Anonymize the HeaderMatchEntry at offset 0 of temp.xg / temp.xgi."""
    if data[8] != 0:   # EntryType HEADERMATCH
        raise AnonymizeError(
            f"{seg_name}: first record is EntryType {data[8]}, expected 0")
    if seg_name == "temp.xg" and data[HME_MAGIC_OFF:HME_MAGIC_OFF + 4] != b"DMLI":
        raise AnonymizeError(f"{seg_name}: DMLI magic not found")

    patched = bytearray(data)

    def put_short(off: int, size: int, text: str) -> None:
        patched[off:off + size] = _delphi_shortstring(text, size)

    put_short(HME_SPLAYER1_OFF, HME_SPLAYER_LEN, player1)
    put_short(HME_SPLAYER2_OFF, HME_SPLAYER_LEN, player2)
    put_short(HME_SEVENT_OFF, HME_SSTRING_LEN, "Sample event")
    put_short(HME_SLOCATION_OFF, HME_SSTRING_LEN, "")
    put_short(HME_SROUND_OFF, HME_SSTRING_LEN, "")

    version = struct.unpack_from("<l", patched, HME_VERSION_OFF)[0]
    if version >= 24:
        unicode_values = {
            "Event": "Sample event",
            "Player1": player1,
            "Player2": player2,
            "Location": "",
            "Round": "",
        }
        for i, field in enumerate(HME_UNICODE_FIELDS):
            off = HME_UNICODE_BASE + i * HME_USTRING_BYTES
            patched[off:off + HME_USTRING_BYTES] = _utf16_field(
                unicode_values[field], HME_USTRING_BYTES)
    if version >= 30:
        patched[HME_TRANSCRIBER_OFF:HME_TRANSCRIBER_OFF + HME_USTRING_BYTES] = (
            _utf16_field("", HME_USTRING_BYTES))

    return bytes(patched)


# ---------------------------------------------------------------------------
# Leak scan
# ---------------------------------------------------------------------------

def scan_for_leaks(raw: bytes, needles: List[str]) -> List[str]:
    """Return a description of every place a personal string survives."""
    _, _, _, segments = read_archive(raw)
    haystacks = [("raw file", raw)]
    haystacks += [(f"segment {s.name}", s.data) for s in segments]

    leaks = []
    tokens = set()
    for needle in needles:
        tokens.add(needle)
        for sep in ".,;:":
            needle = needle.replace(sep, " ")
        tokens.update(t for t in needle.split() if len(t) >= 4)
    for label, blob in haystacks:
        for token in sorted(tokens):
            for enc in SUSPECT_ENCODINGS:
                pattern = token.encode(enc)
                idx = blob.find(pattern)
                if idx != -1:
                    leaks.append(f"{token!r} ({enc}) in {label} @ {idx}")
    return leaks


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def anonymize(src: str, dst: str, player1: str, player2: str) -> None:
    with open(src, "rb") as f:
        raw = f.read()

    start_of_arc_data, version, reserved, segments = read_archive(raw)
    personal = collect_personal_strings(raw, segments)
    print(f"personal strings found in {os.path.basename(src)}:")
    for s in personal:
        print(f"  {s!r}")

    prefix = patch_gdf_header(raw[:start_of_arc_data], player1, player2)

    for seg in segments:
        if seg.name in ("temp.xg", "temp.xgi"):
            seg.data = patch_header_match_entry(
                seg.data, player1, player2, seg.name)

    out = write_archive(prefix, segments, version, reserved)

    leaks = scan_for_leaks(out, personal)
    if leaks:
        print("LEAK CHECK FAILED - output NOT written:", file=sys.stderr)
        for leak in leaks:
            print(f"  {leak}", file=sys.stderr)
        print("(free-text segments such as temp.xgc comments are not "
              "rewritten by this script; scrub them manually)", file=sys.stderr)
        raise SystemExit(1)

    with open(dst, "wb") as f:
        f.write(out)
    print(f"wrote {dst} ({len(out)} bytes; original {len(raw)} bytes)")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Copy an .xg match file with personal data replaced.")
    ap.add_argument("input", help="source .xg file")
    ap.add_argument("output", help="anonymized .xg file to write")
    ap.add_argument("--player1", default="Player One")
    ap.add_argument("--player2", default="Player Two")
    args = ap.parse_args()

    anonymize(args.input, args.output, args.player1, args.player2)


if __name__ == "__main__":
    main()
