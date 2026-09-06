"""Cube option order straight out of a real eXtreme Gammon analysis.

Opt-in: ANKIGAMMON_LIVE_XG=1 (see tests/conftest.py).

GitHub issue #59 was reported against XG output, and the mocked tests use a
hand-written export. This runs the real engine so the canonical order is
verified against what XG actually emits, not against a fixture that might
have drifted from it.
"""

import sys

import pytest

pytestmark = [
    pytest.mark.live_xg,
    pytest.mark.skipif(sys.platform != "win32", reason="XG automation is Windows-only"),
]

CUBE_XGID = "XGID=-b----E-C--AeD---bAdb---A-:0:0:1:00:0:0:3:0:10"

CANONICAL = [
    "No Double/Take",
    "Double/Take",
    "Double/Pass",
    "Too good/Take",
    "Too good/Pass",
]


@pytest.fixture(scope="module")
def xg_cube_moves():
    """Analyze one cube position with the real engine, once for this module.

    Module-scoped deliberately: a live XG analysis takes ~15s and the
    automation is occasionally flaky (a headless file-open can time out),
    so running it once per test both slows the suite and multiplies the
    chance of an unrelated failure.
    """
    import os

    from tests.conftest import (
        XG_EXE, force_kill, wait_for_exit, xg_pids,
    )

    if not (os.environ.get("ANKIGAMMON_LIVE") == "1"
            or os.environ.get("ANKIGAMMON_LIVE_XG") == "1"):
        pytest.skip("live XG tests are opt-in (ANKIGAMMON_LIVE_XG=1)")
    if XG_EXE is None:
        pytest.skip("eXtreme Gammon 2 not found")
    pytest.importorskip("psutil")

    before = xg_pids()
    if before:
        pytest.skip(f"XG already running (pids={sorted(before)})")

    from ankigammon.utils.xg_analyzer import XGAnalyzer

    analyzer = XGAnalyzer(xg_path=XG_EXE, analysis_level="Very Quick")
    try:
        raw, decision_type = analyzer.analyze_position(CUBE_XGID)
        yield analyzer.parse_analysis(raw, CUBE_XGID, decision_type)
    finally:
        try:
            analyzer.terminate()
        except Exception:
            pass
        stragglers = xg_pids() - before
        force_kill(stragglers)
        wait_for_exit(stragglers, timeout=10)


class TestRealXgCubeOrder:
    def test_it_is_a_cube_decision_with_five_options(self, xg_cube_moves):
        from ankigammon.models import DecisionType

        assert xg_cube_moves.decision_type == DecisionType.CUBE_ACTION
        assert len(xg_cube_moves.candidate_moves) == 5

    def test_options_come_back_in_canonical_order(self, xg_cube_moves):
        assert [m.notation for m in xg_cube_moves.candidate_moves] == CANONICAL

    def test_the_answer_is_where_the_action_sits_not_always_first(self, xg_cube_moves):
        """The reported symptom: rank 1 pinned to slot A on every card."""
        moves = xg_cube_moves.candidate_moves
        best = next(m for m in moves if m.rank == 1)
        answer_index = moves.index(best)

        assert answer_index == CANONICAL.index(best.notation), (
            "the correct answer is not in its canonical slot"
        )

    def test_exactly_one_rank_one_and_it_has_no_error(self, xg_cube_moves):
        moves = xg_cube_moves.candidate_moves
        best = [m for m in moves if m.rank == 1]

        assert len(best) == 1
        assert best[0].error == 0.0, (
            "the best action must not be charged an error"
        )
