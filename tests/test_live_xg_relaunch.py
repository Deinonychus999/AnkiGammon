"""XG killed mid-run against the real application: the analyzer must recover.

Opt-in: ANKIGAMMON_LIVE_XG=1 (see tests/conftest.py).

The diagnostic log in GitHub issue #59 showed XG exiting between two matrix
cells, after which every remaining position failed against the dead handle.
This reproduces the exit for real - one position analyzed, the XG process
killed from outside, another position analyzed - and requires the second one
to succeed through a relaunch, with nothing left running at the end.
"""

import sys
import time

import pytest

from tests.conftest import XG_EXE, force_kill, wait_for_exit, xg_pids

pytestmark = [
    pytest.mark.live_xg,
    pytest.mark.skipif(sys.platform != "win32", reason="XG automation is Windows-only"),
]

XGID_A = "XGID=-b----E-C--AeD---bAdb---A-:0:0:1:52:0:0:3:0:10"
XGID_B = "XGID=-b----E-C---eE---c-e----B-:0:0:1:63:0:0:3:0:10"


@pytest.fixture
def analyzer(live_xg, no_xg_running):
    from ankigammon.utils.xg_analyzer import XGAnalyzer

    a = XGAnalyzer(xg_path=str(live_xg), analysis_level="Very Quick")
    before = no_xg_running
    try:
        yield a, before
    finally:
        try:
            a.terminate()
        except Exception:
            pass
        stragglers = xg_pids() - before
        force_kill(stragglers)
        wait_for_exit(stragglers, timeout=10)


class TestMatchLoadedSignalOnRealXg:
    """The fail-fast rests on Close being greyed with no match and enabled with one."""

    def test_close_menu_tracks_whether_a_match_is_open(self, analyzer):
        a, _ = analyzer
        a._ensure_connected()
        auto = a._automator

        assert auto._match_loaded() is False, "fresh XG should report no match"

        auto.import_xgid_from_file(XGID_A)

        assert auto._match_loaded() is True, "after an import XG should report a match"

        auto.close_match()
        # XG updates the menu and title a beat after the prompt is answered;
        # production never reads the signal this soon after a close, but the
        # probe must not fail on that lag. A bound keeps a stuck match visible.
        deadline = time.time() + 5.0
        while auto._match_loaded() and time.time() < deadline:
            time.sleep(0.25)

        assert auto._match_loaded() is False, "after Close, no match again"


class TestRelaunchAfterXgDies:
    def test_next_position_succeeds_after_xg_is_killed(self, analyzer, caplog):
        a, before = analyzer

        raw_a, _ = a.analyze_position(XGID_A)
        assert "eXtreme Gammon Version" in raw_a
        first_pids = xg_pids() - before
        assert first_pids, "expected a running XG after the first position"

        # The failure the user hit, on demand.
        force_kill(first_pids)
        assert wait_for_exit(first_pids, timeout=10)
        time.sleep(1.0)

        started = time.time()
        with caplog.at_level("WARNING"):
            raw_b, _ = a.analyze_position(XGID_B)
        elapsed = time.time() - started

        assert "eXtreme Gammon Version" in raw_b, "the position after the kill did not get analyzed"
        # A relaunch plus one analysis is well under a minute; anything near
        # the 600s analysis timeout means the wait sat on an empty XG again.
        assert elapsed < 180, f"recovery took {elapsed:.0f}s; the analysis wait is stalling"
        second_pids = xg_pids() - before
        assert second_pids and not (second_pids & first_pids), "expected a fresh XG process"
        assert any("no longer running" in r.message or "relaunching" in r.message
                   for r in caplog.records), "the relaunch should be visible in the log"

    def test_terminate_after_a_relaunch_leaves_nothing_running(self, analyzer):
        a, before = analyzer

        a.analyze_position(XGID_A)
        force_kill(xg_pids() - before)
        wait_for_exit(xg_pids() - before, timeout=10)
        a.analyze_position(XGID_B)

        a.terminate()

        assert wait_for_exit(xg_pids() - before), f"XG left running: {sorted(xg_pids() - before)}"
