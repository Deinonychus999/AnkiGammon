"""Decisions from a BGBlitz .bgf match: a 5-point match between iddqd43 (green)
and DanielS (red), analyzed by BGBlitz at 4-ply.

BGBlitz stores each mistake's size in normalized equity next to the match
winning chances it analyzed in, which pins both the board replay and the
conversion from MWC that the cards show.
"""

import gzip
from pathlib import Path

import pytest

from ankigammon.gui.format_detector import FormatDetector, InputFormat
from ankigammon.import_filter import filter_decisions
from ankigammon.models import DecisionType, Player, Position
from ankigammon.parsers import bgf_parser
from ankigammon.parsers.bgf_parser import (
    BgfError, extract_player_names, is_bgf, parse_bgf_bytes, parse_bgf_file, read_bgf,
)
from ankigammon.settings import get_settings
from ankigammon.utils.met import get_met
from ankigammon.utils.move_parser import MoveParser

DATA = Path(__file__).parent / "data"
FILE = str(DATA / "bgblitz" / "match.bgf")


@pytest.fixture(scope="module")
def decisions():
    return parse_bgf_file(FILE)


@pytest.fixture(scope="module")
def match():
    return read_bgf(Path(FILE).read_bytes())


def _find(decisions, game, move, decision_type):
    return next(
        d for d in decisions
        if d.game_number == game and d.move_number == move and d.decision_type == decision_type
    )


def _best(decision):
    return min(decision.candidate_moves, key=lambda m: m.rank)


def _stored_error(record, field):
    value = float((record.get("pr") or {}).get(field, bgf_parser.NOT_ANALYZED))
    return None if value == bgf_parser.NOT_ANALYZED else -value


def test_player_names_green_first():
    assert extract_player_names(FILE) == ("iddqd43", "DanielS")


def test_counts(decisions):
    checker = [d for d in decisions if d.decision_type == DecisionType.CHECKER_PLAY]
    cube = [d for d in decisions if d.decision_type == DecisionType.CUBE_ACTION]
    assert (len(checker), len(cube)) == (42, 38)


def test_every_checker_error_is_the_one_bgblitz_stored(decisions, match):
    checked = 0
    for decision in decisions:
        if decision.decision_type != DecisionType.CHECKER_PLAY:
            continue
        record = match["games"][decision.game_number - 1]["moves"][decision.move_number - 1]
        stored = _stored_error(record, "checkerError")
        if stored is None:
            continue
        assert decision.xg_error_move == pytest.approx(stored, abs=1e-6)
        checked += 1
    assert checked == 41


def test_every_cube_error_is_the_one_bgblitz_stored(decisions, match):
    for decision in decisions:
        if decision.decision_type != DecisionType.CUBE_ACTION:
            continue
        record = match["games"][decision.game_number - 1]["moves"][decision.move_number - 1]
        assert (decision.cube_error or 0.0) == pytest.approx(_stored_error(record, "cubeError") or 0.0, abs=1e-6)


def test_wrong_double_and_correct_take(decisions):
    decision = _find(decisions, 2, 10, DecisionType.CUBE_ACTION)
    assert decision.on_roll == Player.O
    played = next(m for m in decision.candidate_moves if m.was_played)
    assert played.notation == "Double/Take"
    assert _best(decision).notation == "No Double/Take"
    assert decision.cube_error == pytest.approx(0.20450827, abs=1e-6)
    assert decision.take_error == pytest.approx(0.0, abs=1e-9)


def test_missed_redouble_on_a_roll_that_danced(decisions):
    decision = _find(decisions, 2, 13, DecisionType.CUBE_ACTION)
    assert decision.on_roll == Player.X
    assert decision.cube_value == 2
    assert decision.xgid == "XGID=a-BB-AC-AAA-bCba-d-c-b-A--:1:-1:-1:00:1:0:0:5:8"
    assert _best(decision).notation == "Redouble/Take"
    assert next(m for m in decision.candidate_moves if m.was_played).notation == "No Redouble/Take"
    assert decision.cube_error == pytest.approx(0.12736993, abs=1e-6)
    assert not any(d.game_number == 2 and d.move_number == 13 and d.decision_type == DecisionType.CHECKER_PLAY
                   for d in decisions)


def test_pass_is_exactly_one(decisions):
    """Double/Pass is +1 in normalized equity by definition. It only comes out
    at 1.000 when normalized with BGBlitz's own match equity table."""
    for decision in decisions:
        if decision.decision_type == DecisionType.CUBE_ACTION:
            double_pass = next(m for m in decision.candidate_moves if m.notation.endswith("ouble/Pass"))
            assert double_pass.equity == pytest.approx(1.0, abs=1e-6)


def test_checker_play_with_red_on_roll(decisions):
    decision = _find(decisions, 2, 5, DecisionType.CHECKER_PLAY)
    assert decision.on_roll == Player.X
    assert decision.dice == (4, 2)
    assert decision.score_o == 1 and decision.score_x == 0 and decision.match_length == 5
    assert decision.candidate_moves[0].notation == "bar/23 13/9"
    played = next(m for m in decision.candidate_moves if m.was_played)
    assert played.notation == "bar/21 13/11"
    assert played.analysis_level == "4-ply"
    assert played.player_win_pct == pytest.approx(47.277592)


def test_played_moves_replay_the_match(match):
    """Each played move's card notation, applied as a card applies it, gives
    the board the replay hands the next turn."""
    converter = bgf_parser._Converter(match, "test")
    rolls = [t for t in converter.turns if t.dice is not None]
    for turn in rolls:
        decision = converter._base(turn, DecisionType.CHECKER_PLAY, dice=turn.dice)
        after = list(turn.board)
        bgf_parser._apply(after, turn.player, turn.record)
        expected = Position(points=after, x_off=15 - sum(c for c in after if c > 0),
                            o_off=15 - sum(-c for c in after if c < 0))
        if decision.on_roll == Player.X:
            expected = expected.flipped()
        result = MoveParser.apply_move(decision.position, converter._notation(turn.record, decision), Player.O)
        assert (result.points, result.x_off, result.o_off) == (expected.points, expected.x_off, expected.o_off)
    assert len(rolls) == 45


def test_match_equities_come_from_the_file(match):
    table = bgf_parser._Converter(match, "test").table
    assert table.get(4, 5, False) == pytest.approx(0.57464602, abs=1e-7)
    assert table.get(3, 4, False) == pytest.approx(0.57155149, abs=1e-7)
    assert get_met().get_mwc(4, 5) != pytest.approx(0.57464602, abs=1e-4)


def test_entries_the_file_does_not_pin_fall_back_to_the_bundled_table():
    assert bgf_parser._MatchEquities().get(7, 9, False) == get_met().get_mwc(7, 9)


def test_import_filter(decisions):
    kept = filter_decisions(list(decisions), 0.08, 0.08, False, True, 5)
    assert sorted((d.game_number, d.move_number, d.decision_type.name) for d in kept) == [
        (1, 5, "CHECKER_PLAY"), (2, 8, "CHECKER_PLAY"), (2, 10, "CUBE_ACTION"),
    ]
    kept = filter_decisions(list(decisions), 0.08, 0.08, True, False, 5)
    assert [(d.game_number, d.move_number) for d in kept] == [(2, 13)]


def test_detection():
    data = Path(FILE).read_bytes()
    assert is_bgf(data)
    assert not is_bgf(b"OGXM" + bytes(32))
    assert not is_bgf(b'{"format":"other"}\n')
    result = FormatDetector(get_settings()).detect_binary(data, file_path="anything.dat")
    assert result.format == InputFormat.BGF_FILE


def test_plain_json_payload_reads_too(match):
    import json
    header = b'{"format":"BGF","version":"1.0","compress":true,"useSmile":false}\n'
    data = header + gzip.compress(json.dumps(match).encode())
    assert len(parse_bgf_bytes(data)) == 80


@pytest.mark.parametrize("data", [
    b"not a bgf",
    b'{"format":"BGF"}\n\x1f\x8b\x08 truncated',
    b'{"format":"BGF"}\n:)\n\x03\xfa\x80a',
    b'{"format":"BGF"}\n{"games": "none"}',
])
def test_damaged_files_are_refused(data):
    with pytest.raises(BgfError):
        parse_bgf_bytes(data)


def test_match_started_from_a_position():
    """A 7-point match BGBlitz started from 12.pos: TachiAI's double is taken
    before the first roll. The double itself carries no cube analysis, so the
    cards start with the first roll."""
    path = DATA / "bgblitz" / "from_position.bgf"
    decisions = parse_bgf_file(str(path))
    first = decisions[0]
    assert first.decision_type == DecisionType.CHECKER_PLAY
    assert first.xgid == "XGID=-a-B--ECCaa-d----bBb-bb---:1:-1:1:45:1:0:0:7:8"
    assert next(m for m in first.candidate_moves if m.was_played).notation == "7/2 6/2"
    last = decisions[-1]
    assert next(m for m in last.candidate_moves if m.was_played).notation == "24/16"
    assert last.xg_error_move == pytest.approx(0.00711383, abs=1e-6)


PLAIN_HEADER = b'{"format":"BGF","version":"1.0","compress":false,"useSmile":false}\n'


def _as_file(match) -> bytes:
    import json
    return PLAIN_HEADER + json.dumps(match).encode()


def _unanalyzed(match):
    """The match as BGBlitz saves one it has not analyzed: every game's opening
    record still carries its placeholder evaluation, without a cube analysis."""
    import copy
    bare = copy.deepcopy(match)
    for game in bare["games"]:
        for index, record in enumerate(game["moves"]):
            record.update(dancingEquity=None, moveAnalysis=[], pr=None)
            if index == 0 and record.get("equity"):
                record["equity"]["cubeDecision"] = None
            else:
                record["equity"] = None
    return bare


def test_match_saved_without_analysis_says_so(match):
    bare = _unanalyzed(match)
    assert all(game["moves"][0]["equity"] for game in bare["games"])
    assert not bgf_parser.has_analysis(bare)
    with pytest.raises(BgfError, match="no analysis"):
        parse_bgf_bytes(_as_file(bare))


def test_cube_analysis_from_the_take_when_the_double_has_none(match, decisions):
    """Game 2's double, with BGBlitz's cube analysis only on the take that answers it."""
    import copy
    patched = copy.deepcopy(match)
    patched["games"][1]["moves"][9]["equity"] = None
    original = _find(decisions, 2, 10, DecisionType.CUBE_ACTION)
    rebuilt = _find(parse_bgf_bytes(_as_file(patched)), 2, 10, DecisionType.CUBE_ACTION)
    assert rebuilt.cube_error == pytest.approx(original.cube_error, abs=1e-6)
    assert rebuilt.take_error == pytest.approx(original.take_error, abs=1e-6)
    assert rebuilt.player_win_pct == pytest.approx(original.player_win_pct, abs=1e-6)
    assert rebuilt.opponent_gammon_pct == pytest.approx(original.opponent_gammon_pct, abs=1e-6)


def test_set_up_match_cannot_go_to_another_engine():
    match = read_bgf((DATA / "bgblitz" / "from_position.bgf").read_bytes())
    with pytest.raises(BgfError, match="set-up position"):
        bgf_parser.to_mat(match)


def test_mat_names_cannot_break_the_file(match):
    from ankigammon.parsers.gnubg_match_parser import GNUBGMatchParser
    import copy
    import tempfile
    renamed = copy.deepcopy(match)
    renamed["nameGreen"], renamed["nameRed"] = 'Joe "JJ" Smith', "A:B"
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "match.mat"
        path.write_text(bgf_parser.to_mat(renamed), encoding="utf-8")
        assert GNUBGMatchParser.extract_player_names_from_mat(str(path)) == ("Joe 'JJ' Smith", "A B")
