"""An unlimited-game reference on match cube cards.

Requested by a user: players learn the unlimited cube action first and then
adjust it for the score, so the score matrix of a match cube card should also
show the same position as an unlimited game.

It is analyzed in the matrix's own batch with beavers off, and shown without
the Jacoby rule first, so it differs from the match cells only in score. A
label on the row switches to the Jacoby analysis, the unlimited reference many
players learned. Jacoby stops applying once the cube has been turned, so a
redouble gets a single analysis and no switch. Real GnuBG honours the Jacoby
bit: the too-good position below is too good without it and double/pass with
it.
"""

import re
from unittest import mock

import pytest

from ankigammon.analysis.score_matrix import (
    UnlimitedReference,
    ScoreMatrixCell,
    count_score_matrix_analyses,
    format_matrix_as_html,
    generate_score_matrix,
)
from ankigammon.anki.card_generator import CardGenerator
from ankigammon.anki.optional_analysis import (
    CUBE_MATRIX_MARKER,
    UNLIMITED_REFERENCE_FAILED_MARKER,
    UNLIMITED_REFERENCE_MARKER,
    lost_optional_blocks,
    missing_optional_blocks,
)
from ankigammon.models import CubeState, Decision, DecisionType, Move, Player, Position
from ankigammon.parsers.gnubg_parser import GNUBGParser
from ankigammon.settings import Settings
from ankigammon.utils.xgid import parse_xgid
from tests.conftest import GNUBG_EXE

POSITION = "--BBbBB-----a-----Be-c-bbE"
MATCH_XGID = f"XGID={POSITION}:0:0:-1:00:0:0:0:3:8"
REDOUBLE_XGID = f"XGID={POSITION}:1:-1:-1:00:0:0:0:3:8"
UNLIMITED_XGID = f"XGID={POSITION}:0:0:-1:00:0:0:3:0:8"

MATCH_OUTPUT = """Cubeful equities:
1. No double           +0.412
2. Double, take        +0.556  (+0.144)
3. Double, pass        +1.000  (+0.588)

Proper cube action: Double, take
"""

UNLIMITED_OUTPUT = """Cubeful equities:
1. No double           +1.774
2. Double, take        +3.335  (+1.561)
3. Double, pass        +1.000  (-0.774)

Proper cube action: Too good to double, pass (33.2%)
"""

JACOBY_OUTPUT = """Cubeful equities:
1. Double, pass        +1.000
2. Double, take        +3.324  (+2.324)
3. No double           +1.000  (-0.000)

Proper cube action: Double, pass
"""

TABLE = f'<table class="{CUBE_MATRIX_MARKER}"></table>'
UNLIMITED_TABLE = f'<table {UNLIMITED_REFERENCE_MARKER}></table>'


def _is_unlimited(xgid: str) -> bool:
    return xgid.split(":")[8] == "0"


def _is_jacoby(xgid: str) -> bool:
    return _is_unlimited(xgid) and int(xgid.split(":")[7]) & 1 == 1


class FakeAnalyzer:
    """Answers match, unlimited and unlimited-with-Jacoby positions differently."""

    def __init__(self, unlimited_output=UNLIMITED_OUTPUT, jacoby_output=JACOBY_OUTPUT):
        self.batches = []
        self.unlimited_output = unlimited_output
        self.jacoby_output = jacoby_output

    def _output(self, xgid):
        if _is_jacoby(xgid):
            text = self.jacoby_output
        elif _is_unlimited(xgid):
            text = self.unlimited_output
        else:
            text = MATCH_OUTPUT
        return text, DecisionType.CUBE_ACTION

    def analyze_position(self, xgid):
        self.batches.append([xgid])
        return self._output(xgid)

    def analyze_positions_parallel(self, xgids, progress_callback=None, cancellation_callback=None):
        self.batches.append(list(xgids))
        for i in range(len(xgids)):
            if progress_callback:
                progress_callback(i, len(xgids))
        return [self._output(x) for x in xgids]

    def parse_cube_decision(self, raw_output, cube_value=1):
        return GNUBGParser._parse_cube_decision(raw_output, cube_value)

    def unlimited_ids(self):
        return [x for batch in self.batches for x in batch if _is_unlimited(x)]


def _cell(action="D/T", **equities) -> ScoreMatrixCell:
    return ScoreMatrixCell(
        player_away=2, opponent_away=2, best_action=action,
        error_no_double=0.05, error_double=0.0, error_pass=0.02, **equities,
    )


_EQUITIES = {"equity_no_double": 0.412, "equity_double_take": 0.556, "equity_double_pass": 1.0}


class TestUnlimitedIsAnalyzedWithTheMatrix:
    def test_both_unlimited_positions_ride_in_the_same_batch(self):
        analyzer = FakeAnalyzer()

        generate_score_matrix(MATCH_XGID, 3, analyzer, unlimited_reference=True)

        assert len(analyzer.batches) == 1, "the unlimited positions ran as a separate engine pass"
        assert len(analyzer.batches[0]) == 6
        assert len(analyzer.unlimited_ids()) == 2

    def test_unlimited_position_is_the_same_decision_as_an_unlimited_game(self):
        analyzer = FakeAnalyzer()

        generate_score_matrix(REDOUBLE_XGID, 3, analyzer, cube_value=2, unlimited_reference=True)

        source_position, source = parse_xgid(REDOUBLE_XGID)
        unlimited_position, unlimited = parse_xgid(analyzer.unlimited_ids()[0])
        assert unlimited_position.points == source_position.points
        assert unlimited["on_roll"] == source["on_roll"]
        assert unlimited["cube_value"] == 2
        assert unlimited["cube_owner"] == CubeState.X_OWNS
        assert unlimited["match_length"] == 0
        assert (unlimited["score_o"], unlimited["score_x"]) == (0, 0)
        assert "dice" not in unlimited

    def test_centred_cube_is_analyzed_without_and_with_jacoby(self):
        analyzer = FakeAnalyzer()

        generate_score_matrix(MATCH_XGID, 3, analyzer, unlimited_reference=True)

        rules = [parse_xgid(x)[1] for x in analyzer.unlimited_ids()]
        assert [r["jacoby"] for r in rules] == [False, True]
        assert not any(r["beavers_allowed"] for r in rules)

    def test_jacoby_is_not_analyzed_once_the_cube_is_turned(self):
        analyzer = FakeAnalyzer()

        _, unlimited = generate_score_matrix(
            REDOUBLE_XGID, 3, analyzer, cube_value=2, unlimited_reference=True
        )

        assert len(analyzer.unlimited_ids()) == 1
        assert not _is_jacoby(analyzer.unlimited_ids()[0])
        assert unlimited.jacoby is None

    def test_unlimited_cells_come_from_their_own_analyses(self):
        grid, unlimited = generate_score_matrix(MATCH_XGID, 3, FakeAnalyzer(), unlimited_reference=True)

        assert unlimited.no_jacoby.best_action == "TG/P"
        assert unlimited.no_jacoby.equity_no_double == pytest.approx(1.774)
        assert unlimited.jacoby.best_action == "D/P"
        assert unlimited.jacoby.equity_no_double == pytest.approx(1.0)
        assert [[c.best_action for c in row] for row in grid] == [["D/T", "D/T"], ["D/T", "D/T"]]

    def test_no_unlimited_analysis_unless_asked(self):
        analyzer = FakeAnalyzer()

        grid, unlimited = generate_score_matrix(MATCH_XGID, 3, analyzer)

        assert unlimited is None
        assert analyzer.unlimited_ids() == []
        assert len(grid) == 2

    @pytest.mark.parametrize("broken", ["unlimited_output", "jacoby_output"])
    def test_either_unlimited_analysis_unparseable_drops_the_reference_but_keeps_the_grid(self, broken):
        """A switch that flips to nothing would be worse than no row."""
        grid, unlimited = generate_score_matrix(
            MATCH_XGID, 3, FakeAnalyzer(**{broken: "garbage"}), unlimited_reference=True
        )

        assert unlimited is None
        assert len(grid) == 2 and len(grid[0]) == 2

    def test_progress_names_the_unlimited_positions(self):
        messages = []

        generate_score_matrix(
            MATCH_XGID, 3, FakeAnalyzer(), progress_callback=messages.append, unlimited_reference=True
        )

        assert messages[0] == "Analyzing score 2a-2a (1/6)..."
        assert messages[-2:] == [
            "Analyzing unlimited game (5/6)...",
            "Analyzing unlimited game with Jacoby (6/6)...",
        ]


class TestAnalysisCount:
    """Drives the export progress bar, one step per engine analysis."""

    @pytest.mark.parametrize("match_length,max_size,cube_centered,expected", [
        (7, 0, True, 38),
        (7, 0, False, 37),
        (13, 7, True, 38),
        (3, 0, True, 6),
        (0, 0, True, 36),
        (0, 3, False, 4),
        (1, 0, True, 0),
    ])
    def test_grid_plus_unlimited_for_a_match(self, match_length, max_size, cube_centered, expected):
        assert count_score_matrix_analyses(match_length, max_size, cube_centered) == expected


def _td_with(css_class: str, action: str, html: str) -> bool:
    pattern = rf'<td class="[^"]*\b{css_class}\b[^"]*"><div class="action">{re.escape(action)}</div>'
    return re.search(pattern, html) is not None


class TestUnlimitedRendering:
    CENTRED = UnlimitedReference(no_jacoby=_cell(action="TG/P"), jacoby=_cell(action="D/P"))
    TURNED = UnlimitedReference(no_jacoby=_cell(action="D/T"))

    def test_rendered_under_the_grid(self):
        html = format_matrix_as_html([[_cell()]], unlimited=self.CENTRED)

        assert html.index("</table>") < html.index(UNLIMITED_REFERENCE_MARKER)
        assert ">Unlimited<" in html

    def test_unlimited_table_shares_the_grid_styles_and_toggle(self):
        html = format_matrix_as_html([[_cell()]], unlimited=self.CENTRED)

        assert UNLIMITED_REFERENCE_MARKER in html
        assert CUBE_MATRIX_MARKER in UNLIMITED_REFERENCE_MARKER

    def test_centred_cube_carries_both_cells_and_the_switch(self):
        html = format_matrix_as_html([[_cell()]], unlimited=self.CENTRED)

        assert "unlimited-jacoby-toggle" in html
        assert _td_with("unlimited-no-jacoby", "TG/P", html)
        assert _td_with("unlimited-jacoby", "D/P", html)

    def test_turned_cube_has_one_cell_and_no_switch(self):
        html = format_matrix_as_html([[_cell()]], unlimited=self.TURNED)

        assert "unlimited-jacoby" not in html
        assert _td_with("unlimited-no-jacoby", "D/T", html)

    def test_absent_without_unlimited(self):
        assert UNLIMITED_REFERENCE_MARKER not in format_matrix_as_html([[_cell()]])

    def test_unlimited_equities_join_the_toggle(self):
        unlimited = UnlimitedReference(
            no_jacoby=_cell(equity_no_double=0.6, equity_double_take=0.7, equity_double_pass=1.0),
            jacoby=_cell(equity_no_double=1.0, equity_double_take=3.324, equity_double_pass=1.0),
        )

        html = format_matrix_as_html([[_cell(**_EQUITIES)]], unlimited=unlimited)

        assert "has-equities" in html
        assert '<div class="equities">+0.600/+0.700</div>' in html
        assert '<div class="equities">+1.000/+3.324</div>' in html

    def test_jacoby_cell_without_equities_turns_the_toggle_off(self):
        """Otherwise the equity view would show a dash after switching to Jacoby."""
        unlimited = UnlimitedReference(no_jacoby=_cell(**_EQUITIES), jacoby=_cell())

        html = format_matrix_as_html([[_cell(**_EQUITIES)]], unlimited=unlimited)

        assert "has-equities" not in html


@pytest.fixture
def card_gen(qapp, tmp_path):
    if GNUBG_EXE is None:
        pytest.skip("needs an executable to satisfy is_gnubg_available()")
    settings = Settings(config_path=tmp_path / "config.json")
    settings.analyzer_type = "gnubg"
    settings.gnubg_path = GNUBG_EXE
    settings.generate_score_matrix = True
    with mock.patch("ankigammon.anki.card_generator.get_settings", return_value=settings):
        yield CardGenerator(output_dir=tmp_path / "cards", analyzer=mock.MagicMock())


def _decision(xgid: str, match_length: int) -> Decision:
    return Decision(
        position=Position(points=[0] * 26), xgid=xgid, on_roll=Player.X, dice=None,
        match_length=match_length, cube_value=1, cube_owner=CubeState.CENTERED,
        decision_type=DecisionType.CUBE_ACTION,
        candidate_moves=[Move(notation="No double", equity=-0.08, rank=1)],
    )


class TestCardGenerator:
    GENERATE = "ankigammon.analysis.score_matrix.generate_score_matrix"

    def test_match_card_gets_the_unlimited_line(self, card_gen):
        unlimited = UnlimitedReference(no_jacoby=_cell(), jacoby=_cell())
        with mock.patch(self.GENERATE, return_value=([[_cell()]], unlimited)) as generate:
            html = card_gen._generate_score_matrix_html(_decision(MATCH_XGID, 3))

        assert generate.call_args.kwargs["unlimited_reference"] is True
        assert UNLIMITED_REFERENCE_MARKER in html
        assert not card_gen.generation_warnings

    def test_jacoby_switch_script_ships_without_the_equity_toggle(self, card_gen):
        """The switch must work even when the matrix has no errors/equities toggle."""
        unlimited = UnlimitedReference(no_jacoby=_cell(), jacoby=_cell())
        with mock.patch(self.GENERATE, return_value=([[_cell()]], unlimited)):
            back = card_gen.generate_card(_decision(MATCH_XGID, 3))["back"]

        assert '<div class="matrix-value-toggle">' not in back
        assert "showing-jacoby" in back

    def test_unlimited_card_is_already_unlimited(self, card_gen):
        with mock.patch(self.GENERATE, return_value=([[_cell()]], None)) as generate:
            html = card_gen._generate_score_matrix_html(_decision(UNLIMITED_XGID, 0))

        assert generate.call_args.kwargs["unlimited_reference"] is False
        assert UNLIMITED_REFERENCE_FAILED_MARKER not in html
        assert not card_gen.generation_warnings

    def test_failed_unlimited_on_a_match_card_is_reported(self, card_gen):
        with mock.patch(self.GENERATE, return_value=([[_cell()]], None)):
            html = card_gen._generate_score_matrix_html(_decision(MATCH_XGID, 3))

        assert CUBE_MATRIX_MARKER in html, "the grid should survive a failed unlimited line"
        assert UNLIMITED_REFERENCE_FAILED_MARKER in html
        assert card_gen.generation_warnings
        assert "unlimited" in card_gen.generation_warnings[0].lower()

    def test_the_switch_script_alone_does_not_count_as_the_row(self, card_gen):
        """The script names the row's class and ships on any card with the
        equity toggle, so a card without the row still carried the class name."""
        with mock.patch(self.GENERATE, return_value=([[_cell(**_EQUITIES)]], None)):
            back = card_gen.generate_card(_decision(UNLIMITED_XGID, 0))["back"]

        assert "showing-jacoby" in back, "precondition: the switch script is on the card"
        assert UNLIMITED_REFERENCE_MARKER not in back

    def test_a_rebuilt_card_that_lost_its_row_counts_as_lost(self, card_gen):
        """Caught against real Anki: a card whose unlimited analysis failed still
        read as having the row, so regenerate would overwrite a good one."""
        grid = [[_cell(**_EQUITIES)]]
        unlimited = UnlimitedReference(no_jacoby=_cell(**_EQUITIES), jacoby=_cell(**_EQUITIES))
        with mock.patch(self.GENERATE, return_value=(grid, unlimited)):
            old = card_gen.generate_card(_decision(MATCH_XGID, 3))["back"]
        with mock.patch(self.GENERATE, return_value=(grid, None)):
            new = card_gen.generate_card(_decision(MATCH_XGID, 3))["back"]

        assert lost_optional_blocks(old, new) == ["unlimited reference"]


class TestRegenerateSafeguards:
    def test_failed_unlimited_line_is_missing(self, tmp_path):
        settings = Settings(config_path=tmp_path / "config.json")
        settings.generate_score_matrix = True

        assert missing_optional_blocks(TABLE + UNLIMITED_REFERENCE_FAILED_MARKER, True, settings) == [
            "unlimited reference"
        ]

    def test_card_from_before_the_unlimited_line_is_not_missing(self, tmp_path):
        """Re-running every matrix to add the line is the user's call, not a repair."""
        settings = Settings(config_path=tmp_path / "config.json")
        settings.generate_score_matrix = True

        assert missing_optional_blocks(TABLE, True, settings) == []

    def test_losing_the_unlimited_line_counts_as_lost(self):
        assert lost_optional_blocks(TABLE + UNLIMITED_TABLE, TABLE) == ["unlimited reference"]
