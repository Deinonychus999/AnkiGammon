"""BGBlitz position files (.pos), checked against the XGIDs BGBlitz shows for
the same positions. 9.pos is 6.pos with the other player on roll, and 10.pos
is 9.pos with the cube owned by the other side."""

from pathlib import Path

import pytest

from ankigammon.gui.format_detector import FormatDetector, InputFormat
from ankigammon.models import CubeState, DecisionType, Player
from ankigammon.parsers.bgblitz_pos_parser import (
    is_bgblitz_position, parse_position_bytes, parse_position_file,
)
from ankigammon.parsers.bgf_parser import BgfError
from ankigammon.parsers.hedgehog_parser import decision_from_xgid
from ankigammon.settings import get_settings

DATA = Path(__file__).parent / "data" / "bgblitz" / "positions"

XGIDS = {
    1: "XGID=-----CDB----eBa--cad-Aa-BA:0:0:1:65:0:4:1:5:8",
    2: "XGID=----a-EaB--AdD-a-c-e----BA:0:0:1:51:1:1:0:7:8",
    3: "XGID=----ACC-A-A-----a--fcBeBB-:0:0:1:62:6:6:0:7:8",
    4: "XGID=----B-EaC---dCb--b-d--AbA-:0:0:1:66:3:4:1:5:8",
    5: "XGID=--aCb-C-B---BB-a-bbeBbA---:0:0:1:65:0:2:0:7:8",
    6: "XGID=-aBBBBB------A----AB-bAdh-:1:-1:1:63:0:0:0:0:8",
    7: "XGID=bCCBBBB-----e----b-d--b---:1:-1:1:21:0:0:0:0:8",
    8: "XGID=-BCCCA-------------da-caa-:1:1:1:00:0:0:0:0:8",
}


def _read(number: int):
    return parse_position_file(str(DATA / f"{number}.pos"))[0]


def _as_seen_on_roll(decision):
    """What a card shows: the board from the side to act, and score and cube
    relative to that side."""
    me, opponent = ((decision.score_o, decision.score_x) if decision.on_roll == Player.O
                    else (decision.score_x, decision.score_o))
    owner = {CubeState.CENTERED: "centered", CubeState.O_OWNS: Player.O, CubeState.X_OWNS: Player.X}[
        decision.cube_owner]
    if owner != "centered":
        owner = "on roll" if owner == decision.on_roll else "opponent"
    return (decision.position.points, decision.position.x_off, decision.position.o_off,
            tuple(sorted(decision.dice or ())), decision.cube_value, owner, me, opponent,
            decision.match_length, decision.crawford, decision.decision_type)


@pytest.mark.parametrize("number", sorted(XGIDS))
def test_position_matches_bgblitz(number):
    xgid = XGIDS[number]
    kind = DecisionType.CUBE_ACTION if ":00:" in xgid else DecisionType.CHECKER_PLAY
    assert _as_seen_on_roll(_read(number)) == _as_seen_on_roll(decision_from_xgid(xgid, kind))


def test_no_analysis_comes_with_it():
    decision = _read(1)
    assert decision.candidate_moves == []
    assert decision.source_description == "Position from BGBlitz file '1.pos'"


def test_other_player_on_roll_sees_the_same_board_from_the_other_side():
    six, nine = _read(6), _read(9)
    assert six.on_roll != nine.on_roll
    assert nine.position.points == six.position.flipped().points
    assert _as_seen_on_roll(nine)[5] == "on roll"


def test_cube_owner_swapped():
    nine, ten = _read(9), _read(10)
    assert ten.position.points == nine.position.points
    assert _as_seen_on_roll(ten)[5] == "opponent"


def test_before_the_roll():
    """11.pos is 9.pos before TachiAI rolls; BGBlitz stores the dice as 1 and -1."""
    nine, eleven = _read(9), _read(11)
    assert eleven.dice is None
    assert eleven.decision_type == DecisionType.CUBE_ACTION
    assert eleven.on_roll == nine.on_roll
    assert eleven.position.points == nine.position.points


def test_to_roll_marked_by_the_on_roll_value():
    """12.pos has TachiAI to roll (on-roll value 3) at a centered cube, before
    the double BGBlitz then played; the XGID is that position after the take
    and the roll."""
    twelve = _read(12)
    after = decision_from_xgid("XGID=---BB-BbB----D-AAcce--b-A-:1:1:-1:54:0:1:0:7:10", DecisionType.CHECKER_PLAY)
    assert twelve.decision_type == DecisionType.CUBE_ACTION
    assert (twelve.cube_value, twelve.cube_owner) == (1, CubeState.CENTERED)
    assert twelve.position.points == after.position.points
    assert _as_seen_on_roll(twelve)[6:9] == _as_seen_on_roll(after)[6:9]


def _after_names(data: bytes) -> int:
    at = 32
    for _ in range(2):
        at += 1 + data[at]
    return at


def test_last_move_string_is_skipped():
    """JellyFish stores the move it played last before the dice; BGBlitz leaves it empty."""
    data = (DATA / "1.pos").read_bytes()
    length_at = _after_names(data) + 6
    move = b"13/7 8/7"
    patched = data[:length_at] + bytes([len(move)]) + move + data[length_at + 1:]
    assert _as_seen_on_roll(parse_position_bytes(patched, "t")) == _as_seen_on_roll(_read(1))


def test_board_before_the_last_move_is_not_the_position():
    data = bytearray((DATA / "1.pos").read_bytes())
    board_at = _after_names(bytes(data)) + 11
    data[board_at + 2] = 20 + 7
    assert _as_seen_on_roll(parse_position_bytes(bytes(data), "t")) == _as_seen_on_roll(_read(1))


def test_opening_position_is_refused_with_a_way_out():
    data = bytearray((DATA / "1.pos").read_bytes())
    data[12] = 0
    with pytest.raises(BgfError, match="Set who is on roll"):
        parse_position_bytes(bytes(data), "test")


def test_unlimited_game_rules_reach_the_xgid():
    data = bytearray((DATA / "6.pos").read_bytes())
    data[4] = data[6] = 1
    decision = parse_position_bytes(bytes(data), "t")
    assert (decision.jacoby, decision.beavers_allowed) == (True, True)
    assert decision.xgid.endswith(":3:0:8")


def test_detection():
    data = (DATA / "1.pos").read_bytes()
    assert is_bgblitz_position(data)
    assert not is_bgblitz_position(data[:100])
    assert not is_bgblitz_position(b"OGXM" + bytes(200))
    result = FormatDetector(get_settings()).detect_binary(data, file_path="1.pos")
    assert result.format == InputFormat.BGBLITZ_POSITION
