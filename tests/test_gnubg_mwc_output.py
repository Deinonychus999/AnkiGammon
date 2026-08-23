"""GnuBG must report equities, never match winning chances.

A user could analyze unlimited-game positions but not match positions,
and their match-play cube cards were quietly wrong. GnuBG's "Show equity
as MWC" preference applies to match play only: with it on, moves come
back labelled "MWC: 0.4297" instead of "Eq.: -0.717" (no move matches the
pattern at all), and cube equities come back as "45.85%" - which the old
pattern happily read as an equity of +45.85.

"set output mwc off" is now sent with every analysis, and the parser
refuses percentages outright so a stale configuration can never be
mistaken for equities again.
"""

from pathlib import Path
from unittest import mock

import pytest

from ankigammon.models import DecisionType
from ankigammon.parsers.gnubg_parser import GNUBGParser
from ankigammon.utils.gnubg_analyzer import GNUBGAnalyzer


# Captured from gnubg-cli 1.08.003 with "set output mwc on", 13-point match.
MWC_MOVES = """    1. Cubeful 2-ply    13/9 5/4*                    MWC: 0.4297
       0.315 0.138 0.002 - 0.685 0.500 0.086
        2-ply cubeful prune [world class]
    2. Cubeful 2-ply    18/14 5/4*                   MWC: 0.4087 (+-0.0211)
       0.262 0.107 0.002 - 0.738 0.534 0.108
"""

MWC_CUBE = """Cubeful equities:
1. No double            45.85%
2. Double, pass         59.79%  (+13.94%)
3. Double, take         36.41%  ( -9.45%)
Proper cube action: No redouble, take (40.4%)
"""

EQUITY_CUBE = """Cubeful equities:
1. No double           +0.172
2. Double, take        -0.361  (-0.533)
3. Double, pass        +1.000  (+0.828)
Proper cube action: No double
"""

MATCH_XGID = "XGID=-BBAaCB-----bB-a--BbcbbbA-:1:1:1:41:2:2:0:13:10"


@pytest.fixture
def analyzer():
    with mock.patch.object(Path, "exists", return_value=True):
        return GNUBGAnalyzer("/fake/gnubg", analysis_ply=2)


class TestEquityIsRequested:
    def test_position_analysis_turns_mwc_off(self, analyzer):
        path = analyzer._create_command_file(MATCH_XGID, DecisionType.CHECKER_PLAY)
        try:
            commands = Path(path).read_text().splitlines()
        finally:
            Path(path).unlink()

        assert "set output mwc off" in commands
        # Before the position, or gnubg formats this analysis the old way.
        assert commands.index("set output mwc off") < commands.index("hint")

    def test_match_analysis_turns_mwc_off(self, analyzer, tmp_path):
        mat = tmp_path / "match.mat"
        mat.write_text("; dummy")
        captured = []

        def capture(commands):
            captured.append(list(commands))
            raise RuntimeError("stop before launching gnubg")

        with mock.patch.object(analyzer, "_create_command_file_from_list", capture):
            with pytest.raises(RuntimeError, match="stop before launching gnubg"):
                analyzer.analyze_match_file(str(mat))

        assert "set output mwc off" in captured[0]


class TestPercentagesAreNeverEquities:
    def test_mwc_cube_output_yields_no_moves(self):
        # Reading these as equities is worse than failing: the card looks
        # fine and every number on it is wrong.
        assert GNUBGParser._parse_cube_decision(MWC_CUBE) == []

    def test_equity_cube_output_still_parses(self):
        moves = GNUBGParser._parse_cube_decision(EQUITY_CUBE)

        by_notation = {m.notation: m.equity for m in moves}
        assert by_notation["No Double/Take"] == pytest.approx(0.172)
        assert by_notation["Double/Take"] == pytest.approx(-0.361)
        assert by_notation["Double/Pass"] == pytest.approx(1.0)

    def test_mwc_move_output_yields_no_moves(self):
        assert GNUBGParser._parse_checker_play(MWC_MOVES) == []


class TestMwcIsNamedInTheError:
    def test_checker_play(self):
        message = GNUBGParser._describe_empty_analysis(
            MWC_MOVES, DecisionType.CHECKER_PLAY
        )

        assert "match winning chances" in message
        assert "MWC" in message

    def test_cube_action(self):
        message = GNUBGParser._describe_empty_analysis(
            MWC_CUBE, DecisionType.CUBE_ACTION
        )

        assert "match winning chances" in message

    def test_plain_failure_keeps_its_own_reason(self):
        # "%" appears in gnubg's take-point text, but only alongside equities.
        message = GNUBGParser._describe_empty_analysis(
            "No game in progress.", DecisionType.CHECKER_PLAY
        )

        assert "match winning chances" not in message
        assert "No game in progress." in message

    def test_take_point_percentage_is_not_mistaken_for_mwc(self):
        # Equity output carries a percentage in its cube-action line.
        text = (
            "Cube analysis\n"
            "Proper cube action: No double, take (24.0%)\n"
            "No game in progress.\n"
        )

        message = GNUBGParser._describe_empty_analysis(text, DecisionType.CUBE_ACTION)

        assert "match winning chances" not in message
