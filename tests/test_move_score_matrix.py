"""Tests for move_score_matrix's XGID construction.

The matrix re-encodes the source position at four score contexts (Neutral,
DMP, G-Save, G-Go). Regression guard for issue #48: it must carry the source
position's real cube (value + owner) into every context. Forcing a centered
1-cube collapsed the only column with a live cube (Neutral) to a degenerate
"-1.000 / all moves tied" result whenever the player on roll was past the
opponent's cash point (e.g. a big underdog in a gammonless race).
"""

import re

from ankigammon.analysis.move_score_matrix import (
    format_move_matrix_as_html,
    generate_move_score_matrix,
    MoveAtScore,
    MoveScoreMatrixColumn,
    SCORE_CONFIGS,
)
from ankigammon.anki.card_styles import CARD_CSS, get_error_css_class
from ankigammon.models import CubeState, DecisionType, Move, Player
from ankigammon.utils.xgid import parse_xgid


class _CaptureAnalyzer:
    """Minimal analyzer stub that records the XGIDs it is asked to analyze.

    Returns one dummy ranked move per position so the matrix can be built
    without touching gnubg/XG.
    """

    def __init__(self):
        self.seen_ids = []

    def _fake_result(self, position_id):
        self.seen_ids.append(position_id)
        return (position_id, DecisionType.CHECKER_PLAY)

    def analyze_positions_parallel(self, position_ids, progress_callback=None,
                                   cancellation_callback=None):
        return [self._fake_result(pid) for pid in position_ids]

    def analyze_position(self, position_id):
        return self._fake_result(position_id)

    def parse_checker_play(self, output):
        # `output` is the XGID we returned above; one move is enough.
        return [Move(notation="13/11 2/1", equity=-0.5, rank=1, error=0.0)]


# Issue #48 position: player on roll (O) OWNS a 2-cube, gammonless race,
# O wins ~17.6% (a big underdog, below the take point).
ISSUE_48_XGID = "XGID=--CBCBC------B--b--cabbcb-:1:1:1:21:0:0:0:0:8"


def test_score_contexts_preserve_original_cube():
    """Every score context must reuse the source cube value + owner."""
    analyzer = _CaptureAnalyzer()
    generate_move_score_matrix(ISSUE_48_XGID, analyzer, max_moves=3)

    assert len(analyzer.seen_ids) == len(SCORE_CONFIGS)

    for score_xgid in analyzer.seen_ids:
        _, meta = parse_xgid(score_xgid)
        assert meta["cube_value"] == 2, f"cube value not preserved in {score_xgid}"
        assert meta["cube_owner"] == CubeState.O_OWNS, \
            f"cube owner not preserved in {score_xgid}"


def test_neutral_context_is_not_forced_centered():
    """Regression for #48: the Neutral column must not be re-centered.

    A centered live cube is exactly what made the column collapse.
    """
    analyzer = _CaptureAnalyzer()
    generate_move_score_matrix(ISSUE_48_XGID, analyzer, max_moves=3)

    neutral_idx = next(i for i, c in enumerate(SCORE_CONFIGS)
                       if c["type"] == "Neutral")
    _, meta = parse_xgid(analyzer.seen_ids[neutral_idx])

    assert meta["cube_owner"] != CubeState.CENTERED
    assert meta["cube_value"] == 2
    # Sanity: Neutral keeps its 7-pt / 0-0 / non-Crawford framing.
    assert meta["match_length"] == 7
    assert meta["score_o"] == 0 and meta["score_x"] == 0


def test_centered_source_cube_stays_centered():
    """When the source cube really is centered, contexts stay centered.

    (Accepted limitation of the 'preserve original cube' fix: a centered
    source cube + big underdog can still collapse Neutral — but we must not
    invent ownership that isn't there.)
    """
    centered_xgid = "XGID=--CBCBC------B--b--cabbcb-:0:0:1:21:0:0:0:0:8"
    analyzer = _CaptureAnalyzer()
    generate_move_score_matrix(centered_xgid, analyzer, max_moves=3)

    for score_xgid in analyzer.seen_ids:
        _, meta = parse_xgid(score_xgid)
        assert meta["cube_value"] == 1
        assert meta["cube_owner"] == CubeState.CENTERED


# --- Severity coloring (issue #54): matrix cells share the Top Moves palette ---


def test_error_css_class_boundaries():
    """The shared classifier must match the Top Moves table's thresholds
    exactly (0.080 itself is minor, both boundaries inclusive)."""
    assert get_error_css_class(0.0) == ""
    assert get_error_css_class(0.019) == ""
    assert get_error_css_class(0.020) == "error-minor"
    assert get_error_css_class(0.080) == "error-minor"
    assert get_error_css_class(0.081) == "error-blunder"


def _matrix_columns():
    """Two columns exercising all severity buckets, no analyzer needed.

    The same notation lands in different buckets per column, proving
    classification is per-score-context.
    """
    return [
        MoveScoreMatrixColumn(score_type="Neutral", top_moves=[
            MoveAtScore(notation="13/11 2/1", equity=0.1, error=0.0, rank=1),
            MoveAtScore(notation="13/10", equity=0.09, error=0.010, rank=2),
            MoveAtScore(notation="24/21", equity=-0.05, error=0.150, rank=3),
        ]),
        MoveScoreMatrixColumn(score_type="DMP", top_moves=[
            MoveAtScore(notation="13/10", equity=0.2, error=0.0, rank=1),
            MoveAtScore(notation="13/11 2/1", equity=0.175, error=0.025, rank=2),
        ]),
    ]


def test_matrix_cells_carry_severity_classes():
    html = format_move_matrix_as_html(_matrix_columns())

    rows = re.findall(r'<tr class="rank-(\d)">\n(.*?)</tr>', html, re.S)
    assert [rank for rank, _ in rows] == ["1", "2", "3"]

    rank1_row, rank2_row, rank3_row = (body for _, body in rows)

    # Rank 1 cells are classless (styled by tr.rank-1).
    assert "error-minor" not in rank1_row and "error-blunder" not in rank1_row

    # Rank 2: Neutral 0.010 -> classless, DMP 0.025 -> minor.
    rank2_cells = [c for c in rank2_row.split("</td>") if c.strip()]
    assert rank2_cells[0].strip().startswith("<td><div")
    assert rank2_cells[1].strip().startswith('<td class="error-minor">')

    # Rank 3: Neutral 0.150 -> blunder, DMP has no move at this rank.
    assert '<td class="error-blunder">' in rank3_row
    assert '<span class="no-move">' in rank3_row


def test_card_css_styles_matrix_severity_classes():
    """The stylesheet and markup must not drift apart."""
    assert ".move-score-matrix-table td.error-minor" in CARD_CSS
    assert ".move-score-matrix-table td.error-blunder" in CARD_CSS
    # The old uniform-gray span rule is gone; spans inherit the td color.
    assert ".move-score-matrix-table .error {" not in CARD_CSS
