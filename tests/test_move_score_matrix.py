"""Tests for move_score_matrix's XGID construction.

The matrix re-encodes the source position at four score contexts (Neutral,
DMP, G-Save, G-Go). Regression guard for issue #48: it must carry the source
position's real cube (value + owner) into every context. Forcing a centered
1-cube collapsed the only column with a live cube (Neutral) to a degenerate
"-1.000 / all moves tied" result whenever the player on roll was past the
opponent's cash point (e.g. a big underdog in a gammonless race).
"""

from ankigammon.analysis.move_score_matrix import (
    generate_move_score_matrix,
    SCORE_CONFIGS,
)
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
