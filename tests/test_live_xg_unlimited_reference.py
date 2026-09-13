"""The unlimited reference on a match cube card, against a real eXtreme Gammon 2.

Opt-in: ANKIGAMMON_LIVE_XG=1 (see tests/conftest.py).

Two things only a real XG can answer: that it accepts a match position
re-encoded as an unlimited game, and that it reads the Jacoby bit from the
XGID, which is what separates the row's two analyses. Real GnuBG was probed
for the same with this position: too good without Jacoby, double/pass with it.

XG automation drives the clipboard, so running this clobbers it.
"""

import sys

import pytest

from ankigammon.analysis.score_matrix import generate_score_matrix

pytestmark = [
    pytest.mark.live_xg,
    pytest.mark.skipif(sys.platform != "win32", reason="XG automation is Windows-only"),
]

POSITION = "--BBbBB-----a-----Be-c-bbE"
MATCH_XGID = f"XGID={POSITION}:0:0:-1:00:0:0:0:3:8"


@pytest.fixture
def xg(qapp, live_xg, no_xg_running, tmp_path):
    from ankigammon.settings import Settings
    from ankigammon.utils.analyzer_base import create_analyzer

    settings = Settings(config_path=tmp_path / "config.json")
    settings.analyzer_type = "xg"
    settings.xg_exe_path = str(live_xg)
    settings.xg_analysis_level = "Very Quick"
    analyzer = create_analyzer(settings)
    try:
        yield analyzer
    finally:
        analyzer.terminate()


class TestRealXgUnlimitedReference:
    def test_matrix_carries_both_unlimited_cells(self, xg):
        grid, unlimited = generate_score_matrix(MATCH_XGID, 2, xg, unlimited_reference=True)

        assert grid[0][0].equity_no_double is not None
        assert unlimited is not None, "XG's analysis of an unlimited position did not parse"
        assert unlimited.no_jacoby.best_action.startswith("TG"), (
            "without Jacoby a gammonish too-good position should stay too good"
        )
        assert unlimited.jacoby is not None
        assert unlimited.jacoby.best_action == "D/P", (
            "XG ignored the Jacoby bit: an undoubled game cannot win a gammon under Jacoby"
        )
