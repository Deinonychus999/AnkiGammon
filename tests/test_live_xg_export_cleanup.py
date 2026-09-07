"""Exporting an already-analyzed card, with a score matrix, against real XG.

Opt-in: ANKIGAMMON_LIVE_XG=1 (see tests/conftest.py).

The flow from #59's follow-up report: the card carries its analysis, so no
AnalysisWorker runs and ExportWorker gets no analyzer; the matrix launches
XG itself. After the export finishes, that XG must be gone.
"""

import sys

import pytest

from tests.conftest import force_kill, read_apkg_notes, wait_for_exit, xg_pids

pytestmark = [
    pytest.mark.live_xg,
    pytest.mark.skipif(sys.platform != "win32", reason="XG automation is Windows-only"),
]

CUBE_XGID = "XGID=-b----E-C--AeD---bAdb---A-:0:0:1:00:0:0:3:0:10"


def test_export_of_an_analyzed_card_leaves_no_xg_running(qapp, live_xg, no_xg_running, tmp_path):
    from unittest import mock

    from ankigammon.gui.dialogs.export_dialog import ExportWorker
    from ankigammon.models import CubeState, Decision, DecisionType, Move, Player, Position
    from ankigammon.settings import Settings

    settings = Settings(config_path=tmp_path / "config.json")
    settings.analyzer_type = "xg"
    settings.xg_exe_path = str(live_xg)
    settings.xg_analysis_level = "Very Quick"
    settings.generate_score_matrix = True
    settings.score_matrix_max_size = 2
    settings.export_method = "apkg"

    analyzed = Decision(
        position=Position(points=[0] * 26), xgid=CUBE_XGID,
        on_roll=Player.X, dice=None, cube_value=1, cube_owner=CubeState.CENTERED,
        decision_type=DecisionType.CUBE_ACTION,
        candidate_moves=[Move(notation="No double", equity=-0.08, rank=1)],
    )
    before = no_xg_running
    out = tmp_path / "deck.apkg"
    worker = ExportWorker({"Deck": [analyzed]}, settings, "apkg", str(out), analyzer=None)
    result = {}
    worker.finished.connect(lambda ok, msg: result.update(ok=ok, msg=msg))
    try:
        with mock.patch("ankigammon.anki.card_generator.get_settings", return_value=settings):
            worker.run()

        assert result["ok"], result
        notes = read_apkg_notes(out)
        assert len(notes) == 1 and "score-matrix-table" in notes[0][2], "matrix was not built"
        assert wait_for_exit(xg_pids() - before), (
            f"XG left running after export: {sorted(xg_pids() - before)}"
        )
    finally:
        stragglers = xg_pids() - before
        force_kill(stragglers)
        wait_for_exit(stragglers, timeout=10)
