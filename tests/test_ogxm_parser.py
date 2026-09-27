"""Decisions built from HedgeHog's OGXM analysis of match_files/rchoicebug.mat."""

import json
from pathlib import Path

import pytest

from ankigammon.import_filter import filter_decisions
from ankigammon.models import DecisionType, Player
from ankigammon.parsers.ogxm_parser import extract_player_names, parse_ogxm_file
from ankigammon.utils.hedgehog_met import MET, normalize_cube_triple
from ankigammon.utils.ogid import parse_ogid
from ankigammon.utils.xgid import parse_xgid

DATA = Path(__file__).parent / "data" / "hedgehog"
FILE = str(DATA / "analysis.ogxm")


@pytest.fixture(scope="module")
def decisions():
    return parse_ogxm_file(FILE)


def _find(decisions, game, move, decision_type):
    return next(
        d for d in decisions
        if d.game_number == game and d.move_number == move and d.decision_type == decision_type
    )


def test_counts(decisions):
    checker = [d for d in decisions if d.decision_type == DecisionType.CHECKER_PLAY]
    cube = [d for d in decisions if d.decision_type == DecisionType.CUBE_ACTION]
    assert (len(checker), len(cube)) == (93, 77)


def test_checker_play_with_white_on_roll(decisions):
    decision = _find(decisions, 4, 14, DecisionType.CHECKER_PLAY)
    assert decision.on_roll == Player.X
    assert decision.dice == (6, 1)
    assert decision.crawford
    best, second = decision.candidate_moves[:2]
    assert (best.notation, best.equity) == ("13/7 6/5", pytest.approx(-0.1159))
    assert second.notation == "16/15 16/10"
    played = [m for m in decision.candidate_moves if m.was_played]
    assert [m.notation for m in played] == ["7/6 7/1*"]
    assert decision.xg_error_move == pytest.approx(0.5613)
    assert best.player_win_pct == pytest.approx(58.82)


def test_positions_agree_with_hedgehogs_ogids(decisions):
    decision = _find(decisions, 4, 14, DecisionType.CHECKER_PLAY)
    position, metadata = parse_ogid("99cchhiijjjkkmm:223334455666ddo:N0N:16:B:R:2:1:3C:13")
    parsed, _ = parse_xgid(decision.xgid)
    assert parsed.points == position.points
    assert metadata["on_roll"] == decision.on_roll


def test_a_double_and_its_drop_make_one_cube_decision(decisions):
    decision = _find(decisions, 1, 12, DecisionType.CUBE_ACTION)
    assert decision.on_roll == Player.O
    assert decision.cube_error == pytest.approx(0.2354)
    assert decision.take_error == pytest.approx(0.9087)
    moves = {m.notation: m for m in decision.candidate_moves}
    assert moves["No Double/Take"].equity == pytest.approx(0.3263, abs=1e-4)
    assert moves["Double/Take"].equity == pytest.approx(0.0909, abs=1e-4)
    assert moves["No Double/Take"].rank == 1
    assert [m.notation for m in decision.candidate_moves if m.was_played] == ["Double/Pass"]
    assert decision.player_win_pct == pytest.approx(58.12)


def test_import_filter_keeps_the_blunders(decisions):
    kept = filter_decisions(decisions, 0.080, 0.080, True, True, 5)
    assert len(kept) == 11


def test_player_names_follow_the_import_dialogs_numbering():
    assert extract_player_names(FILE) == ("Jezebel", "rchoice")


def test_hedgehogs_match_equity_table():
    assert MET[2][3] == pytest.approx(0.598994)
    position_cube = json.loads((DATA / "position_cube.json").read_text())["result"]["cube_decision"]
    normalized = normalize_cube_triple(
        3, 0, 0, 1,
        position_cube["no_double_equity"], position_cube["double_take_equity"],
        position_cube["double_pass_equity"],
    )
    expected = (
        position_cube["no_double_norm_eq"], position_cube["double_take_norm_eq"],
        position_cube["double_pass_norm_eq"],
    )
    # HedgeHog's own values come from MWC before rounding to 4 places
    assert normalized == pytest.approx(expected, abs=5e-4)


def test_a_triple_off_the_scale_is_withheld():
    assert normalize_cube_triple(3, 0, 0, 1, 0.3, 0.1, 1.0) is None
    assert normalize_cube_triple(0, 0, 0, 1, 0.3, 0.1, 1.0) is None
