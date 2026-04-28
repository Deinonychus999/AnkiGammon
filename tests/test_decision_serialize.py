"""Round-trip tests for Decision JSON serialization."""

import json

import pytest

from ankigammon.anki.decision_serialize import (
    SCHEMA_VERSION,
    decision_from_json,
    decision_to_json,
)
from ankigammon.models import (
    CubeState,
    Decision,
    DecisionType,
    Move,
    Player,
    Position,
)


def _make_position() -> Position:
    pos = Position()
    pos.points[1] = -2
    pos.points[24] = 2
    pos.points[6] = -5
    pos.points[19] = 5
    pos.x_off = 1
    pos.o_off = 0
    return pos


def _make_move(notation: str, rank: int, with_resulting: bool = True) -> Move:
    return Move(
        notation=notation,
        equity=-0.123 + rank * 0.01,
        error=0.05 * rank,
        rank=rank,
        xg_rank=rank,
        xg_error=0.02 * rank,
        xg_notation=f"XG:{notation}",
        resulting_position=_make_position() if with_resulting else None,
        from_xg_analysis=True,
        was_played=(rank == 1),
        player_win_pct=52.68,
        player_gammon_pct=14.35,
        player_backgammon_pct=0.69,
        opponent_win_pct=47.32,
        opponent_gammon_pct=12.42,
        opponent_backgammon_pct=0.55,
        cubeless_equity=0.234,
    )


def _make_decision(decision_type: DecisionType = DecisionType.CHECKER_PLAY) -> Decision:
    return Decision(
        position=_make_position(),
        xgid="XGID=---BBBBAAA---Ac-bbccbAA-A-:1:1:-1:63:4:3:0:5:8",
        on_roll=Player.X,
        dice=(3, 6),  # __post_init__ will sort to (6, 3)
        score_x=4,
        score_o=3,
        match_length=5,
        crawford=False,
        cube_value=2,
        cube_owner=CubeState.O_OWNS,
        decision_type=decision_type,
        candidate_moves=[
            _make_move("13/9 6/5", rank=1),
            _make_move("13/4", rank=2),
            _make_move("24/18", rank=3, with_resulting=False),
        ],
        cube_error=None,
        take_error=None,
        cubeless_equity=0.345,
        double_cubeless_equity=0.567,
        xg_error_move=0.012,
        player_win_pct=52.68,
        source_description="Rolled out 1296 trials",
        original_position_format="XGID",
        game_number=2,
        move_number=15,
        note="Critical pip race",
    )


def _assert_positions_equal(a: Position, b: Position) -> None:
    assert a.points == b.points
    assert a.x_off == b.x_off
    assert a.o_off == b.o_off


def _assert_moves_equal(a: Move, b: Move) -> None:
    assert a.notation == b.notation
    assert a.equity == b.equity
    assert a.error == b.error
    assert a.rank == b.rank
    assert a.xg_rank == b.xg_rank
    assert a.xg_error == b.xg_error
    assert a.xg_notation == b.xg_notation
    assert a.from_xg_analysis == b.from_xg_analysis
    assert a.was_played == b.was_played
    assert a.player_win_pct == b.player_win_pct
    assert a.player_gammon_pct == b.player_gammon_pct
    assert a.player_backgammon_pct == b.player_backgammon_pct
    assert a.opponent_win_pct == b.opponent_win_pct
    assert a.opponent_gammon_pct == b.opponent_gammon_pct
    assert a.opponent_backgammon_pct == b.opponent_backgammon_pct
    assert a.cubeless_equity == b.cubeless_equity
    if a.resulting_position is None:
        assert b.resulting_position is None
    else:
        _assert_positions_equal(a.resulting_position, b.resulting_position)


def _assert_decisions_equal(a: Decision, b: Decision) -> None:
    _assert_positions_equal(a.position, b.position)
    assert a.xgid == b.xgid
    assert a.on_roll == b.on_roll
    assert a.dice == b.dice
    assert a.score_x == b.score_x
    assert a.score_o == b.score_o
    assert a.match_length == b.match_length
    assert a.crawford == b.crawford
    assert a.cube_value == b.cube_value
    assert a.cube_owner == b.cube_owner
    assert a.decision_type == b.decision_type
    assert len(a.candidate_moves) == len(b.candidate_moves)
    for m_a, m_b in zip(a.candidate_moves, b.candidate_moves):
        _assert_moves_equal(m_a, m_b)
    assert a.cube_error == b.cube_error
    assert a.take_error == b.take_error
    assert a.cubeless_equity == b.cubeless_equity
    assert a.double_cubeless_equity == b.double_cubeless_equity
    assert a.xg_error_move == b.xg_error_move
    assert a.player_win_pct == b.player_win_pct
    assert a.player_gammon_pct == b.player_gammon_pct
    assert a.player_backgammon_pct == b.player_backgammon_pct
    assert a.opponent_win_pct == b.opponent_win_pct
    assert a.opponent_gammon_pct == b.opponent_gammon_pct
    assert a.opponent_backgammon_pct == b.opponent_backgammon_pct
    assert a.source_description == b.source_description
    assert a.original_position_format == b.original_position_format
    assert a.game_number == b.game_number
    assert a.move_number == b.move_number
    assert a.note == b.note


class TestDecisionRoundTrip:
    def test_checker_play_roundtrip(self):
        original = _make_decision(DecisionType.CHECKER_PLAY)
        blob = decision_to_json(original)
        rebuilt = decision_from_json(blob)
        _assert_decisions_equal(original, rebuilt)

    def test_cube_action_roundtrip(self):
        original = _make_decision(DecisionType.CUBE_ACTION)
        original.dice = None
        original.cube_error = 0.045
        original.take_error = 0.012
        blob = decision_to_json(original)
        rebuilt = decision_from_json(blob)
        _assert_decisions_equal(original, rebuilt)

    def test_dice_invariant_preserved_on_deserialize(self):
        """Decision.__post_init__ sorts dice descending; deserialize must re-apply."""
        d = _make_decision()
        blob = decision_to_json(d)

        # Surgically reverse the dice in the JSON to simulate a malformed/older blob.
        parsed = json.loads(blob)
        parsed["decision"]["dice"] = [3, 6]
        tampered = json.dumps(parsed)

        rebuilt = decision_from_json(tampered)
        assert rebuilt.dice == (6, 3), "Constructor's __post_init__ must re-sort dice"

    def test_dice_none_for_cube(self):
        d = _make_decision(DecisionType.CUBE_ACTION)
        d.dice = None
        rebuilt = decision_from_json(decision_to_json(d))
        assert rebuilt.dice is None

    def test_move_with_no_resulting_position(self):
        d = _make_decision()
        d.candidate_moves = [_make_move("13/9", rank=1, with_resulting=False)]
        rebuilt = decision_from_json(decision_to_json(d))
        assert rebuilt.candidate_moves[0].resulting_position is None

    def test_empty_candidate_moves(self):
        d = _make_decision()
        d.candidate_moves = []
        rebuilt = decision_from_json(decision_to_json(d))
        assert rebuilt.candidate_moves == []

    def test_blob_is_valid_json(self):
        d = _make_decision()
        blob = decision_to_json(d)
        parsed = json.loads(blob)
        assert parsed["version"] == SCHEMA_VERSION
        assert "decision" in parsed

    def test_unknown_version_rejected(self):
        with pytest.raises(ValueError, match="schema version"):
            decision_from_json(json.dumps({"version": 99, "decision": {}}))

    def test_enums_serialize_as_values(self):
        d = _make_decision()
        blob = decision_to_json(d)
        parsed = json.loads(blob)
        assert parsed["decision"]["on_roll"] == "X"
        assert parsed["decision"]["cube_owner"] == "o_owns"
        assert parsed["decision"]["decision_type"] == "checker_play"
