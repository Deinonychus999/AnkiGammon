"""Every analyzer a worker creates must be terminated when the worker ends.

XGAnalyzer.terminate() is what closes the XG2 process AnkiGammon launched.
Workers that created an analyzer and simply returned left that process
running - the "background process of xg2 is left after everything is
shutdown" report. GnuBG analyzers are cheap to terminate, so the rule is
uniform rather than engine-specific.
"""

from unittest import mock

import pytest
from PySide6.QtWidgets import QApplication

from ankigammon.gui.dialogs.regenerate_dialog import MODE_REANALYZE, RegenerateWorker
from ankigammon.gui.main_window import MatchAnalysisWorker
from ankigammon.models import DecisionType
from ankigammon.settings import Settings


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class SpyAnalyzer:
    def __init__(self, match_result=None, boom=None):
        self.terminated = False
        self._match_result = match_result if match_result is not None else []
        self._boom = boom

    def analyze_match_file(self, *a, **kw):
        if self._boom:
            raise self._boom
        return self._match_result

    def analyze_positions_parallel(self, xgids, progress_callback=None, **kw):
        if self._boom:
            raise self._boom
        return [("<raw>", DecisionType.CHECKER_PLAY) for _ in xgids]

    def parse_analysis(self, raw_output, xgid, decision_type):
        raise AssertionError("not used in these tests")

    def terminate(self):
        self.terminated = True


def _run_match_worker(analyzer, cancelled=False):
    worker = MatchAnalysisWorker(
        file_path="match.mat",
        settings=Settings(),
        checker_threshold=0.0,
        cube_threshold=0.0,
        include_player_x=True,
        include_player_o=True,
        filter_func=lambda decisions, *a: list(decisions),
        max_moves=8,
    )
    worker._cancelled = cancelled
    with mock.patch(
        "ankigammon.utils.analyzer_base.create_analyzer", return_value=analyzer
    ):
        worker.run()
    return worker


class TestMatchAnalysisWorker:
    def test_analyzer_is_terminated_after_a_successful_run(self, qapp):
        analyzer = SpyAnalyzer()
        _run_match_worker(analyzer)

        assert analyzer.terminated, "a completed match import must not leak XG"

    def test_analyzer_is_terminated_when_analysis_raises(self, qapp):
        analyzer = SpyAnalyzer(boom=RuntimeError("engine died"))
        _run_match_worker(analyzer)

        assert analyzer.terminated

    def test_successful_run_still_reports_success(self, qapp):
        """Cleanup must not change what the worker emits."""
        analyzer = SpyAnalyzer()
        worker = MatchAnalysisWorker(
            file_path="match.mat",
            settings=Settings(),
            checker_threshold=0.0,
            cube_threshold=0.0,
            include_player_x=True,
            include_player_o=True,
            filter_func=lambda decisions, *a: list(decisions),
            max_moves=8,
        )
        seen = {}
        worker.finished.connect(
            lambda ok, msg, decs, total: seen.update(ok=ok, msg=msg, total=total)
        )
        with mock.patch(
            "ankigammon.utils.analyzer_base.create_analyzer", return_value=analyzer
        ):
            worker.run()

        assert seen["ok"] is True
        assert seen["msg"] == "Success"


class TestRegenerateWorker:
    def _run(self, analyzer, notes_data):
        client = mock.MagicMock()
        client.test_connection.return_value = True
        client.invoke.return_value = [1]
        client.notes_info.return_value = notes_data

        worker = RegenerateWorker(Settings(), MODE_REANALYZE)
        with mock.patch(
            "ankigammon.gui.dialogs.regenerate_dialog.AnkiConnect", return_value=client
        ), mock.patch(
            "ankigammon.utils.analyzer_base.create_analyzer", return_value=analyzer
        ), mock.patch.object(
            RegenerateWorker, "_build_card_generator", return_value=mock.MagicMock()
        ):
            worker.run()

    def test_analyzer_is_terminated_after_reanalyze(self, qapp):
        analyzer = SpyAnalyzer()
        notes = [{
            "noteId": 1,
            "fields": {
                "XGID": {"value": "XGID=-b----E-C--AeD---bAdb---A-:0:0:1:52:0:0:3:0:10"},
                "AnalysisData": {"value": ""},
            },
        }]
        self._run(analyzer, notes)

        assert analyzer.terminated, "regenerate must not leak an XG process"

    def test_analyzer_is_terminated_when_analysis_raises(self, qapp):
        analyzer = SpyAnalyzer(boom=RuntimeError("engine died"))
        notes = [{
            "noteId": 1,
            "fields": {
                "XGID": {"value": "XGID=-b----E-C--AeD---bAdb---A-:0:0:1:52:0:0:3:0:10"},
                "AnalysisData": {"value": ""},
            },
        }]
        self._run(analyzer, notes)

        assert analyzer.terminated

    def test_no_analyzer_created_when_there_is_nothing_to_do(self, qapp):
        """No notes carry an XGID, so no engine should be started at all."""
        analyzer = SpyAnalyzer()
        self._run(analyzer, [{"noteId": 1, "fields": {"XGID": {"value": ""}}}])

        assert not analyzer.terminated
