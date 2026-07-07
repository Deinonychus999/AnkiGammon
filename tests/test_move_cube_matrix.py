"""Tests for move_cube_matrix (issue #50).

The matrix re-analyzes a checker play at three cube positions (Neutral =
centered 1-cube, Player = cube owned by the player on roll, Opponent = cube
owned by the opponent), preserving score, match length, Crawford/Jacoby
flags and max cube. The card back only gets the (spoiler-wrapped) table
when the best move actually differs between cube positions.
"""

import tempfile
from pathlib import Path

import pytest

from ankigammon.analysis.move_cube_matrix import (
    CUBE_CONFIGS,
    CubeMatrixColumn,
    MoveAtCubeState,
    best_move_differs,
    format_move_cube_matrix_as_html,
    generate_move_cube_matrix,
)
from ankigammon.models import CubeState, Decision, DecisionType, Move, Player
from ankigammon.utils.xgid import parse_xgid


class _CaptureAnalyzer:
    """Minimal analyzer stub that records the XGIDs it is asked to analyze.

    Returns canned ranked moves per position so the matrix can be built
    without touching gnubg/XG. When ``move_lists`` is given, the Nth
    parse_checker_play call returns the Nth list (one per analyzed
    position, in CUBE_CONFIGS order).
    """

    def __init__(self, move_lists=None):
        self.seen_ids = []
        self._move_lists = move_lists
        self._parse_calls = 0

    def _fake_result(self, position_id):
        self.seen_ids.append(position_id)
        return (position_id, DecisionType.CHECKER_PLAY)

    def analyze_positions_parallel(self, position_ids, progress_callback=None,
                                   cancellation_callback=None):
        return [self._fake_result(pid) for pid in position_ids]

    def analyze_position(self, position_id):
        return self._fake_result(position_id)

    def parse_checker_play(self, output):
        if self._move_lists is None:
            return [Move(notation="13/11 2/1", equity=-0.5, rank=1, error=0.0)]
        moves = self._move_lists[self._parse_calls % len(self._move_lists)]
        self._parse_calls += 1
        return moves


# Issue #50 example position: O on roll with 66, unlimited game, Jacoby on,
# centered cube.
ISSUE_50_XGID = "XGID=-aBa--D-CB--cB---d-cB-ba--:0:0:1:66:0:0:1:0:10"


def _variant_meta(analyzer):
    """Parse the three captured variant XGIDs, keyed by cube config type."""
    assert len(analyzer.seen_ids) == len(CUBE_CONFIGS)
    return {
        config['type']: parse_xgid(xgid)[1]
        for config, xgid in zip(CUBE_CONFIGS, analyzer.seen_ids)
    }


# --- Variant XGID construction ---


def test_three_cube_variants_from_centered_cube():
    """Neutral = centered 1-cube; Player/Opponent = 2-cube owned by the
    on-roll player (O here) / the opponent. CubeState is absolute."""
    analyzer = _CaptureAnalyzer()
    generate_move_cube_matrix(ISSUE_50_XGID, analyzer, max_moves=3)

    meta = _variant_meta(analyzer)

    assert meta['Neutral']['cube_value'] == 1
    assert meta['Neutral']['cube_owner'] == CubeState.CENTERED

    assert meta['Player']['cube_value'] == 2
    assert meta['Player']['cube_owner'] == CubeState.O_OWNS

    assert meta['Opponent']['cube_value'] == 2
    assert meta['Opponent']['cube_owner'] == CubeState.X_OWNS


def test_variants_preserve_original_metadata():
    """Dice, scores, match length, Jacoby flag and max cube must carry over."""
    analyzer = _CaptureAnalyzer()
    generate_move_cube_matrix(ISSUE_50_XGID, analyzer, max_moves=3)

    for variant_xgid in analyzer.seen_ids:
        _, meta = parse_xgid(variant_xgid)
        assert meta['dice'] == (6, 6), f"dice not preserved in {variant_xgid}"
        assert meta['score_o'] == 0 and meta['score_x'] == 0
        assert meta['match_length'] == 0
        assert meta['jacoby'] is True, f"jacoby not preserved in {variant_xgid}"
        assert meta['max_cube'] == 1024, f"max cube not preserved in {variant_xgid}"
        assert meta['on_roll'] == Player.O


def test_player_opponent_mapping_when_x_on_roll():
    """With turn = -1, Player maps to X_OWNS and Opponent to O_OWNS —
    absolute CubeState semantics, no manual flipping."""
    xgid_x_on_roll = "XGID=-aBa--D-CB--cB---d-cB-ba--:0:0:-1:66:0:0:1:0:10"
    analyzer = _CaptureAnalyzer()
    generate_move_cube_matrix(xgid_x_on_roll, analyzer, max_moves=3)

    meta = _variant_meta(analyzer)

    assert meta['Neutral']['cube_owner'] == CubeState.CENTERED
    assert meta['Player']['cube_owner'] == CubeState.X_OWNS
    assert meta['Opponent']['cube_owner'] == CubeState.O_OWNS
    for variant in meta.values():
        assert variant['on_roll'] == Player.X


def test_owned_cube_value_is_preserved():
    """When the original cube is already owned (4-cube here), the owned
    variants keep its value; Neutral is still a centered 1-cube."""
    owned_xgid = "XGID=-aBa--D-CB--cB---d-cB-ba--:2:1:1:66:0:0:1:0:10"
    analyzer = _CaptureAnalyzer()
    generate_move_cube_matrix(owned_xgid, analyzer, max_moves=3)

    meta = _variant_meta(analyzer)

    assert meta['Neutral']['cube_value'] == 1
    assert meta['Neutral']['cube_owner'] == CubeState.CENTERED
    assert meta['Player']['cube_value'] == 4
    assert meta['Player']['cube_owner'] == CubeState.O_OWNS
    assert meta['Opponent']['cube_value'] == 4
    assert meta['Opponent']['cube_owner'] == CubeState.X_OWNS


# --- Error gates (dead cube / not a checker play) ---


def test_raises_without_dice():
    no_dice_xgid = "XGID=-aBa--D-CB--cB---d-cB-ba--:0:0:1:00:0:0:1:0:10"
    with pytest.raises(ValueError, match="dice"):
        generate_move_cube_matrix(no_dice_xgid, _CaptureAnalyzer(), max_moves=3)


def test_raises_in_crawford_game():
    crawford_xgid = "XGID=-aBa--D-CB--cB---d-cB-ba--:0:0:1:66:0:0:1:3:10"
    with pytest.raises(ValueError, match="Crawford"):
        generate_move_cube_matrix(crawford_xgid, _CaptureAnalyzer(), max_moves=3)


def test_raises_in_one_point_match():
    one_pointer_xgid = "XGID=-aBa--D-CB--cB---d-cB-ba--:0:0:1:66:0:0:0:1:10"
    with pytest.raises(ValueError, match="1-point"):
        generate_move_cube_matrix(one_pointer_xgid, _CaptureAnalyzer(), max_moves=3)


# --- best_move_differs ---


def _column(cube_type, best_notation, second_notation="24/18 13/7"):
    return CubeMatrixColumn(cube_type=cube_type, top_moves=[
        MoveAtCubeState(notation=best_notation, equity=0.1, error=0.0, rank=1),
        MoveAtCubeState(notation=second_notation, equity=0.05, error=0.05, rank=2),
    ])


def test_best_move_differs_false_when_identical():
    columns = [
        _column("Neutral", "13/7 13/7"),
        _column("Player", "13/7 13/7"),
        _column("Opponent", "13/7 13/7"),
    ]
    assert best_move_differs(columns) is False


def test_best_move_differs_ignores_whitespace_variance():
    columns = [
        _column("Neutral", "13/7 13/7"),
        _column("Player", "13/7  13/7"),
        _column("Opponent", " 13/7 13/7 "),
    ]
    assert best_move_differs(columns) is False


def test_best_move_differs_true_when_any_column_differs():
    columns = [
        _column("Neutral", "13/7 13/7"),
        _column("Player", "13/7 13/7"),
        _column("Opponent", "24/18 18/12"),
    ]
    assert best_move_differs(columns) is True


def test_best_move_differs_false_for_empty_input():
    assert best_move_differs([]) is False


# --- Formatter markup ---


def test_formatter_emits_spoiler_with_wrapped_matrix_table():
    columns = [
        _column("Neutral", "13/7 13/7"),
        _column("Player", "13/7 13/7"),
        _column("Opponent", "24/18 18/12"),
    ]
    html = format_move_cube_matrix_as_html(columns, analysis_label="World Class")

    # Collapsed spoiler with the exact summary text
    assert '<details' in html
    assert '<summary>Best move differs for a different cube position</summary>' in html

    # The .move-score-matrix wrapper div is REQUIRED: the responsive
    # hide/compaction CSS rules are scoped to the wrapper, not the table.
    assert '<div class="move-score-matrix">' in html
    assert '<table class="move-score-matrix-table">' in html

    # One header cell per cube position
    assert html.count('</th>') == 3
    for label in ("Neutral", "Player", "Opponent"):
        assert f'>{label}</th>' in html

    # Analysis label shown when provided
    assert '<span class="ply-indicator">(World Class)</span>' in html


def test_formatter_returns_empty_for_no_columns():
    assert format_move_cube_matrix_as_html([]) == ""


# --- Card generator gate ---


class _FakeSettings:
    """Just enough of Settings for _generate_move_cube_matrix_html."""

    analyzer_type = 'gnubg'
    gnubg_analysis_ply = 3
    max_moves = 3

    def is_gnubg_available(self):
        return True

    def is_xg_available(self):
        return False


def _checker_decision(**overrides):
    position, metadata = parse_xgid(ISSUE_50_XGID)
    kwargs = dict(
        position=position,
        xgid=ISSUE_50_XGID,
        on_roll=metadata['on_roll'],
        dice=metadata['dice'],
        match_length=0,
        crawford=False,
        jacoby=True,
        decision_type=DecisionType.CHECKER_PLAY,
    )
    kwargs.update(overrides)
    return Decision(**kwargs)


def _card_generator(analyzer, tmpdir):
    from ankigammon.anki.card_generator import CardGenerator
    gen = CardGenerator(Path(tmpdir), analyzer=analyzer)
    gen.settings = _FakeSettings()
    return gen


def test_card_generator_returns_empty_when_best_move_identical():
    """Per issue #50: nothing on the card when all three best moves agree."""
    analyzer = _CaptureAnalyzer()  # identical canned best move everywhere
    with tempfile.TemporaryDirectory() as tmpdir:
        gen = _card_generator(analyzer, tmpdir)
        html = gen._generate_move_cube_matrix_html(_checker_decision())

    assert html == ""
    assert len(analyzer.seen_ids) == 3  # analysis ran, result was suppressed


def test_card_generator_emits_spoiler_when_best_move_differs():
    analyzer = _CaptureAnalyzer(move_lists=[
        [Move(notation="13/7 13/7", equity=0.1, rank=1, error=0.0)],
        [Move(notation="13/7 13/7", equity=0.1, rank=1, error=0.0)],
        [Move(notation="24/18 18/12", equity=0.1, rank=1, error=0.0)],
    ])
    with tempfile.TemporaryDirectory() as tmpdir:
        gen = _card_generator(analyzer, tmpdir)
        html = gen._generate_move_cube_matrix_html(_checker_decision())

    assert '<details' in html
    assert 'Best move differs for a different cube position' in html


def test_card_generator_records_warning_when_analysis_fails():
    """An analysis failure must not silently masquerade as the meaningful
    'best move is the same at all cube positions' outcome."""

    class _FailingAnalyzer(_CaptureAnalyzer):
        def analyze_positions_parallel(self, position_ids, progress_callback=None,
                                       cancellation_callback=None):
            raise RuntimeError("engine exploded")

    with tempfile.TemporaryDirectory() as tmpdir:
        gen = _card_generator(_FailingAnalyzer(), tmpdir)
        html = gen._generate_move_cube_matrix_html(_checker_decision())

    assert html == ""
    assert len(gen.generation_warnings) == 1
    assert "Cube-position analysis failed" in gen.generation_warnings[0]


def test_card_generator_progress_ticks_once_per_variant():
    """Both engine callback conventions (before-start 0..N-1 plus final N,
    and after-completion 1..N) must yield exactly 3 progress messages."""
    from ankigammon.analysis.move_cube_matrix import generate_move_cube_matrix

    for convention in ("xg", "gnubg"):
        analyzer = _CaptureAnalyzer()
        original = analyzer.analyze_positions_parallel

        def with_callbacks(position_ids, progress_callback=None,
                           cancellation_callback=None, _orig=original,
                           _conv=convention):
            total = len(position_ids)
            if _conv == "xg":  # before each position, plus final (N, N)
                for i in range(total + 1):
                    progress_callback(i, total)
            else:  # after each completion
                for i in range(1, total + 1):
                    progress_callback(i, total)
            return _orig(position_ids)

        analyzer.analyze_positions_parallel = with_callbacks
        messages = []
        generate_move_cube_matrix(
            ISSUE_50_XGID, analyzer, max_moves=3,
            progress_callback=messages.append,
        )
        assert len(messages) == 3, f"{convention}: {messages}"
        assert messages[0].endswith("(1/3)...")
        assert messages[2].endswith("(3/3)...")


def test_card_generator_skips_crawford_without_analyzing():
    analyzer = _CaptureAnalyzer()
    with tempfile.TemporaryDirectory() as tmpdir:
        gen = _card_generator(analyzer, tmpdir)
        decision = _checker_decision(match_length=3, crawford=True, jacoby=False)
        assert gen._generate_move_cube_matrix_html(decision) == ""

    assert analyzer.seen_ids == []


def test_card_generator_skips_one_point_match_without_analyzing():
    analyzer = _CaptureAnalyzer()
    with tempfile.TemporaryDirectory() as tmpdir:
        gen = _card_generator(analyzer, tmpdir)
        decision = _checker_decision(match_length=1, jacoby=False)
        assert gen._generate_move_cube_matrix_html(decision) == ""

    assert analyzer.seen_ids == []
