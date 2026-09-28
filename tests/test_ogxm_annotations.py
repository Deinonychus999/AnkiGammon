"""OGXM annotations (ANNO, spec 8.4) becoming card notes.

The notes are added to HedgeHog's real analysis of match_files/rchoicebug.mat,
so they land on positions whose cards the other OGXM tests already pin.
"""

import struct
from pathlib import Path

import pytest

from ankigammon.models import DecisionType
from ankigammon.parsers.ogxm_parser import parse_ogxm_bytes
from ankigammon.utils.ogxm_reader import read_ogxm

DATA = Path(__file__).parent / "data" / "hedgehog"
FILE = (DATA / "analysis.ogxm").read_bytes()

MATCH, GAME, PLY, DECISION, ALTERNATIVE = range(5)
CHECKER_KIND, CUBE_KIND = 0, 1
# Game 4 move 14 (a checker play) and the double at game 1 move 12, dropped on the next ply.
CHECKER_PLY = 13 + 57 + 12 + 13
DOUBLE_PLY, DROP_PLY = 11, 12


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def _string(text: str) -> bytes:
    raw = text.encode("utf-8")
    return _varint(len(raw)) + raw


def _anno(scope, ref, value="", key=None, kind=None, alt_index=None, lang=None,
          author=None, at=None, drawings=None, analysis=None) -> bytes:
    fields = [key and _string(key), kind is not None and _varint(kind),
              alt_index is not None and _varint(alt_index), lang and _string(lang),
              author and _string(author), at is not None and _varint(at),
              drawings is not None and _varint(len(drawings)) + b"".join(drawings),
              analysis]
    mask = sum(1 << bit for bit, field in enumerate(fields) if field)
    body = _varint(mask) + _varint(scope) + _varint(ref) + _string(value) + b"".join(f for f in fields if f)
    return _varint(len(body)) + body


def _arrow(tail: int, head: int) -> bytes:
    body = _varint(1) + _varint(1) + bytes([tail, head])
    return _varint(len(body)) + body


def _with_anno(*records: bytes) -> bytes:
    payload = b"".join(records)
    body = FILE[:-4] + b"ANNO" + struct.pack("<IB", len(payload), 0) + payload + b"END!"
    return body[:12] + struct.pack("<I", len(body)) + body[16:]


def _decision(data: bytes, game: int, move: int, decision_type: DecisionType):
    return next(
        d for d in parse_ogxm_bytes(data)
        if d.game_number == game and d.move_number == move and d.decision_type == decision_type
    )


@pytest.fixture(scope="module")
def analysis_id() -> bytes:
    return read_ogxm(FILE).analysis.analysis_id


def test_a_note_on_a_move_goes_on_its_card():
    data = _with_anno(_anno(PLY, CHECKER_PLY, "Hitting loose on the ace point loses the race."))
    assert _decision(data, 4, 14, DecisionType.CHECKER_PLAY).note == "Hitting loose on the ace point loses the race."


def test_notes_on_the_double_and_on_the_drop_go_on_the_cube_card(analysis_id):
    data = _with_anno(
        _anno(PLY, DOUBLE_PLY, "An early double."),
        _anno(DECISION, DOUBLE_PLY, "The market is not close.", kind=CUBE_KIND, analysis=analysis_id),
        _anno(PLY, DROP_PLY, "This is an easy take."),
    )
    note = _decision(data, 1, 12, DecisionType.CUBE_ACTION).note
    assert note == "An early double.\n\nThe market is not close.\n\nThis is an easy take."


def test_a_note_on_one_alternative_names_the_move(analysis_id):
    data = _with_anno(_anno(ALTERNATIVE, CHECKER_PLY, "Too passive.", kind=CHECKER_KIND,
                            alt_index=1, analysis=analysis_id))
    assert _decision(data, 4, 14, DecisionType.CHECKER_PLAY).note == "16/15 16/10: Too passive."


def test_drawings_before_the_analysis_id_are_stepped_over(analysis_id):
    data = _with_anno(_anno(DECISION, CHECKER_PLY, "See the arrows.", kind=CHECKER_KIND,
                            drawings=[_arrow(13, 7), _arrow(6, 5)], analysis=analysis_id))
    assert _decision(data, 4, 14, DecisionType.CHECKER_PLAY).note == "See the arrows."


def test_prose_keeps_the_writers_order():
    data = _with_anno(_anno(PLY, CHECKER_PLY, "First."), _anno(PLY, CHECKER_PLY, "Second."))
    assert _decision(data, 4, 14, DecisionType.CHECKER_PLAY).note == "First.\n\nSecond."


def test_what_is_not_a_note_on_this_position_is_left_out(analysis_id):
    other_block = bytes(16)
    data = _with_anno(
        _anno(MATCH, 0, "A great match."),
        _anno(GAME, 3, "Game four."),
        _anno(PLY, CHECKER_PLY, "12", key="x-rating"),
        _anno(PLY, CHECKER_PLY, drawings=[_arrow(13, 7)]),
        _anno(PLY, CHECKER_PLY, "Kept.", lang="en", author="dgadg", at=1790000000000,
              drawings=[_arrow(6, 5)]),
        _anno(DECISION, CHECKER_PLY, "Another analysis.", kind=CHECKER_KIND, analysis=other_block),
        _anno(DECISION, CHECKER_PLY, "About the cube.", kind=CUBE_KIND, analysis=analysis_id),
    )
    assert _decision(data, 4, 14, DecisionType.CHECKER_PLAY).note == "Kept."


def test_files_without_annotations_leave_notes_empty():
    assert all(decision.note is None for decision in parse_ogxm_bytes(FILE))
