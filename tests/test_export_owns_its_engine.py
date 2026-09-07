"""An export must shut down any engine its card generator started.

Reported on GitHub issue #59 after the 1.8.3 fixes: adding one card left an
eXtreme Gammon process running. The card was already analyzed, so no
AnalysisWorker ran and ExportWorker received no analyzer; the score matrix
then lazily launched its own XG, and the dialog's cleanup - which only knows
the analysis worker's engine - never touched it. The same defect regenerate
had, one dialog over.

An engine handed in by the dialog stays the dialog's to close.
"""

from unittest import mock

import pytest

from ankigammon.gui.dialogs.export_dialog import ExportWorker
from ankigammon.models import CubeState, Decision, DecisionType, Move, Player, Position
from ankigammon.settings import Settings
from tests.conftest import GNUBG_EXE

CUBE_XGID = "XGID=-b----E-C--AeD---bAdb---A-:0:0:1:00:0:0:0:7:10"


class SpyAnalyzer:
    def __init__(self):
        self.terminated = False

    def terminate(self):
        self.terminated = True


def _analyzed_cube() -> Decision:
    """A card that already carries its analysis, so no AnalysisWorker runs."""
    return Decision(
        position=Position(points=[0] * 26), xgid=CUBE_XGID,
        on_roll=Player.X, dice=None, match_length=7,
        cube_value=1, cube_owner=CubeState.CENTERED,
        decision_type=DecisionType.CUBE_ACTION,
        candidate_moves=[Move(notation="No double", equity=-0.08, rank=1)],
    )


@pytest.fixture
def matrix_settings(tmp_path):
    if GNUBG_EXE is None:
        pytest.skip("needs an executable to satisfy is_gnubg_available()")
    s = Settings(config_path=tmp_path / "config.json")
    s.analyzer_type = "gnubg"
    s.gnubg_path = GNUBG_EXE
    s.generate_score_matrix = True
    s.export_method = "apkg"
    return s


def _run_export(settings, output, analyzer=None):
    """Real ExportWorker over the APKG path; only the engine is faked."""
    created = []

    def factory(_settings):
        spy = SpyAnalyzer()
        created.append(spy)
        return spy

    worker = ExportWorker({"Deck": [_analyzed_cube()]}, settings, "apkg", str(output), analyzer=analyzer)
    result = {}
    worker.finished.connect(lambda ok, msg: result.update(ok=ok, msg=msg))
    with mock.patch("ankigammon.utils.analyzer_base.create_analyzer", side_effect=factory), \
         mock.patch("ankigammon.anki.card_generator.get_settings", return_value=settings), \
         mock.patch("ankigammon.analysis.score_matrix.generate_score_matrix", return_value=object()), \
         mock.patch("ankigammon.analysis.score_matrix.format_matrix_as_html",
                    return_value='<table class="score-matrix-table"></table>'):
        worker.run()
    return created, result


class TestExportWithNoAnalyzerHandedIn:
    def test_the_engine_it_started_is_terminated(self, qapp, matrix_settings, tmp_path):
        created, result = _run_export(matrix_settings, tmp_path / "deck.apkg")

        assert result["ok"], result
        assert len(created) == 1, "the score matrix should have started exactly one engine"
        assert created[0].terminated, "the engine the export started was left running"

    def test_the_export_itself_still_succeeds(self, qapp, matrix_settings, tmp_path):
        _, result = _run_export(matrix_settings, tmp_path / "deck.apkg")

        assert result["ok"], result
        assert (tmp_path / "deck.apkg").exists()

    def test_a_failed_export_still_terminates_it(self, qapp, matrix_settings, tmp_path):
        """Writing the package into a directory path fails after the matrix ran."""
        created, result = _run_export(matrix_settings, tmp_path)

        assert not result["ok"]
        assert created and created[0].terminated


class TestEngineHandedInByTheDialog:
    def test_is_not_terminated_by_the_worker(self, qapp, matrix_settings, tmp_path):
        """The dialog closes what it started, after the worker is done."""
        shared = SpyAnalyzer()
        created, result = _run_export(matrix_settings, tmp_path / "deck.apkg", analyzer=shared)

        assert result["ok"], result
        assert created == [], "a second engine was started despite one being handed in"
        assert not shared.terminated

    def test_no_matrix_means_no_engine_at_all(self, qapp, matrix_settings, tmp_path):
        matrix_settings.generate_score_matrix = False
        created, result = _run_export(matrix_settings, tmp_path / "deck.apkg")

        assert result["ok"], result
        assert created == []
