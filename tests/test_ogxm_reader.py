"""OGXM v2 reading, checked against an analysis HedgeHog produced.

analysis.ogxm is HedgeHog's 2ply analysis of match_files/rchoicebug.mat;
import.json holds the positions HedgeHog itself replayed for every ply, and
blunders.json the mistakes it reported.
"""

import json
import struct
from pathlib import Path

import pytest

from ankigammon.models import Position
from ankigammon.utils.ogid import encode_ogid
from ankigammon.utils.ogxm_reader import CENTRED, OgxmError, read_ogxm

DATA = Path(__file__).parent / "data" / "hedgehog"
FILE = (DATA / "analysis.ogxm").read_bytes()
GOLDEN_PLIES = [
    ply for game in json.loads((DATA / "import.json").read_text())["data"]["games"]
    for ply in game["plies"]
]


@pytest.fixture(scope="module")
def match():
    return read_ogxm(FILE)


def test_match_header(match):
    assert (match.match_length, match.white_name, match.black_name) == (3, "rchoice", "Jezebel")
    assert match.crawford_rule
    assert [len(game.plies) for game in match.games] == [13, 57, 12, 35]


def test_analysis_block(match):
    analysis = match.analysis
    assert (analysis.model_name, analysis.checker_ply, analysis.met_id) == ("xerxes", 2, "rockwell-kazaross")
    assert (len(analysis.checker), len(analysis.cube)) == (113, 79)


def test_every_replayed_ply_matches_hedgehogs_own_replay(match):
    for ply, golden in zip(match.plies, GOLDEN_PLIES):
        fields = golden["ogid_before"].split(":")
        board = ply.board
        position = Position(
            points=list(board),
            x_off=15 - sum(c for c in board if c > 0),
            o_off=15 - sum(-c for c in board if c < 0),
        )
        assert encode_ogid(position, only_position=True).split(":")[:2] == fields[:2], ply.ply_ref
        assert ply.cube_value == 2 ** int(fields[2][1])
        assert ply.cube_owner == {"N": CENTRED, "W": 0, "B": 1}[fields[2][0]]
        assert ply.score == (int(fields[6]), int(fields[7]))
        assert ply.crawford == fields[8].endswith("C")


def test_checker_decision_from_the_raw_bytes(match):
    # Game 3 ply 13: HedgeHog reports best 13/7 6/5 at -0.1159, played 7/6 7/1* at -0.6772
    record = match.analysis.checker[13 + 57 + 12 + 13]
    assert len(record.alternatives) == 25
    assert record.alternatives[0].equity == pytest.approx(-0.1159)
    assert record.played.equity == pytest.approx(-0.6772)
    assert record.loss == pytest.approx(0.5613)
    assert record.alternatives[0].probs["win"] == pytest.approx(0.5882)


def test_cube_decision_from_the_raw_bytes(match):
    # Game 0 ply 12: White drops a double it should have taken
    record = match.analysis.cube[12]
    assert record.verdict == 2
    assert (record.no_double, record.double_take, record.double_pass) == pytest.approx((0.5323, 0.509, 0.599))
    assert record.equity_loss == pytest.approx(0.9087)
    assert record.take_point == pytest.approx(0.3408)


def _with_section(data: bytes, kind: bytes, payload: bytes, critical: bool) -> bytes:
    body = data[:-4] + kind + struct.pack("<IB", len(payload), 1 if critical else 0) + payload + b"END!"
    return body[:12] + struct.pack("<I", len(body)) + body[16:]


def test_unknown_ancillary_sections_are_skipped():
    assert len(read_ogxm(_with_section(FILE, b"ZZZZ", b"\x01\x02\x03", critical=False)).plies) == 117


def test_unknown_critical_sections_are_refused():
    with pytest.raises(OgxmError, match="critical"):
        read_ogxm(_with_section(FILE, b"ZZZZ", b"\x01", critical=True))


def test_v1_files_are_refused_with_a_message():
    v1 = FILE[:4] + struct.pack("<H", 1) + FILE[6:]
    with pytest.raises(OgxmError, match="v1"):
        read_ogxm(v1)


def test_truncated_files_are_refused():
    with pytest.raises(OgxmError):
        read_ogxm(FILE[:1000])


def test_other_files_are_refused():
    with pytest.raises(OgxmError, match="Not an OGXM"):
        read_ogxm(b"RGMH" + b"\x00" * 100)
