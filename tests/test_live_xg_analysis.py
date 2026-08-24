"""A user's comment through a real eXtreme Gammon 2 analysis and out to a deck.

Opt-in: ANKIGAMMON_LIVE_XG=1 (see tests/conftest.py).

This is the flow the bug reports came from: paste a bare XGID with a typed
comment, let XG analyze it, export. Everything here is real - XG really runs,
the .apkg is really written and read back - so it also re-checks that the
analyzer does not strand an XG process.

XG automation drives the clipboard, so running this clobbers it.
"""

import sys

import pytest

from tests.conftest import force_kill, read_apkg_notes, wait_for_exit, xg_pids

pytestmark = [
    pytest.mark.live_xg,
    pytest.mark.skipif(sys.platform != "win32", reason="XG automation is Windows-only"),
]

XGID = "XGID=-b----E-C--AeD---bAdb---A-:0:0:1:52:0:0:3:0:10"
COMMENT = "Race lead = 4 pips, so run."


@pytest.fixture
def xg_settings(live_xg, tmp_path):
    from ankigammon.settings import Settings

    settings = Settings(config_path=tmp_path / "config.json")
    settings.analyzer_type = "xg"
    settings.xg_exe_path = str(live_xg)
    settings.xg_analysis_level = "Very Quick"  # keeps a live run to ~15s
    return settings


@pytest.fixture
def analyzed(qapp, xg_settings, no_xg_running):
    """Paste a commented XGID and analyze it with the real engine."""
    from ankigammon.gui.dialogs.export_dialog import AnalysisWorker
    from ankigammon.gui.dialogs.input_dialog import InputDialog
    from ankigammon.gui.format_detector import InputFormat

    before = no_xg_running
    dialog = InputDialog(xg_settings)
    decisions = dialog._parse_input(f"{XGID}\n{COMMENT}", InputFormat.POSITION_IDS)
    assert decisions[0].note == COMMENT, "the paste itself dropped the comment"

    worker = AnalysisWorker(decisions, xg_settings)
    captured = {}
    worker.finished.connect(
        lambda ok, msg, decs: captured.update(ok=ok, msg=msg, decisions=decs)
    )
    ours = set()
    try:
        worker.run()
        ours = xg_pids() - before
        assert captured["ok"], captured["msg"]
        yield captured["decisions"], worker, ours
    finally:
        if worker.analyzer is not None:
            try:
                worker.analyzer.terminate()
            except Exception:
                pass
        force_kill(ours)
        wait_for_exit(ours, timeout=10)


class TestRealXgAnalysis:
    def test_xg_actually_analyzed_the_position(self, analyzed):
        decisions, _, _ = analyzed

        assert decisions[0].candidate_moves, "XG returned no candidate moves"
        assert decisions[0].candidate_moves[0].notation

    def test_comment_survives_a_real_xg_analysis(self, analyzed):
        decisions, _, _ = analyzed

        assert decisions[0].note == COMMENT

    def test_comment_reaches_a_real_apkg(self, analyzed, tmp_path):
        from ankigammon.anki.apkg_exporter import ApkgExporter
        from ankigammon.anki.decision_serialize import decision_from_json

        decisions, _, _ = analyzed
        out = tmp_path / "live.apkg"
        ApkgExporter(output_dir=tmp_path / "cards", deck_name="Live XG").export(
            decisions, output_file=str(out)
        )

        notes = read_apkg_notes(out)
        assert len(notes) == 1
        _, _, back, blob = notes[0]
        assert COMMENT in back
        assert decision_from_json(blob).note == COMMENT

    def test_terminate_leaves_no_xg_process(self, analyzed):
        """The reported symptom: xg2 still in the process table afterwards."""
        _, worker, ours = analyzed

        worker.analyzer.terminate()

        assert wait_for_exit(ours), (
            f"XG left running after terminate(): {sorted(ours & xg_pids())}"
        )
