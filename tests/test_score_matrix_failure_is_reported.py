"""A score matrix that fails to build must not vanish quietly.

Reported after 1.8.1: "the tables of most cards were updated. I just noticed
that some were deleted instead of updated."

_generate_score_matrix_html catches every exception and returns "", so the
card is written back with no table. On an export that only costs a table that
never existed. On a regenerate it destroys one the card already had, and the
user finds out by noticing, which is how this was found.

The move-cube-matrix path already recorded a warning for exactly this reason.
The score matrix now does too, so the failure reaches the run summary.
"""

from unittest import mock

import pytest

from ankigammon.anki.card_generator import CardGenerator
from ankigammon.models import CubeState, Decision, DecisionType, Move, Player, Position
from ankigammon.settings import Settings
from tests.conftest import GNUBG_EXE

CUBE_XGID = "XGID=-b----E-C--AeD---bAdb---A-:0:0:1:00:0:0:3:0:10"


@pytest.fixture
def matrix_settings(tmp_path):
    if GNUBG_EXE is None:
        pytest.skip("needs an executable to satisfy is_gnubg_available()")
    settings = Settings(config_path=tmp_path / "config.json")
    settings.analyzer_type = "gnubg"
    settings.gnubg_path = GNUBG_EXE
    settings.generate_score_matrix = True
    settings.score_matrix_max_size = 2
    return settings


@pytest.fixture
def card_gen(qapp, matrix_settings, tmp_path):
    with mock.patch(
        "ankigammon.anki.card_generator.get_settings", return_value=matrix_settings
    ):
        yield CardGenerator(output_dir=tmp_path / "cards", analyzer=mock.MagicMock())


def _cube_decision() -> Decision:
    return Decision(
        position=Position(points=[0] * 26),
        xgid=CUBE_XGID,
        on_roll=Player.X,
        dice=None,
        match_length=7,
        cube_value=1,
        cube_owner=CubeState.CENTERED,
        decision_type=DecisionType.CUBE_ACTION,
        candidate_moves=[Move(notation="No double", equity=-0.08, rank=1)],
    )


class TestMatrixFailureIsReported:
    def test_failure_records_a_warning(self, card_gen):
        with mock.patch(
            "ankigammon.analysis.score_matrix.generate_score_matrix",
            side_effect=RuntimeError("engine died mid-matrix"),
        ):
            html = card_gen._generate_score_matrix_html(_cube_decision())

        assert html == ""
        assert card_gen.generation_warnings, "a dropped table was reported nowhere"
        assert CUBE_XGID in card_gen.generation_warnings[0]

    def test_the_warning_says_the_table_is_missing(self, card_gen):
        with mock.patch(
            "ankigammon.analysis.score_matrix.generate_score_matrix",
            side_effect=RuntimeError("boom"),
        ):
            card_gen._generate_score_matrix_html(_cube_decision())

        assert "table" in card_gen.generation_warnings[0].lower()

    def test_cancellation_still_propagates(self, card_gen):
        """Cancelling is not a failure and must not be swallowed or reported."""
        with mock.patch(
            "ankigammon.analysis.score_matrix.generate_score_matrix",
            side_effect=InterruptedError(),
        ):
            with pytest.raises(InterruptedError):
                card_gen._generate_score_matrix_html(_cube_decision())

        assert not card_gen.generation_warnings

    def test_success_records_nothing(self, card_gen):
        with mock.patch(
            "ankigammon.analysis.score_matrix.generate_score_matrix",
            return_value=object(),
        ), mock.patch(
            "ankigammon.analysis.score_matrix.format_matrix_as_html",
            return_value="<table class=score-matrix-table></table>",
        ):
            html = card_gen._generate_score_matrix_html(_cube_decision())

        assert "score-matrix-table" in html
        assert not card_gen.generation_warnings

    def test_an_unavailable_engine_is_not_reported_as_a_failure(
        self, qapp, tmp_path, matrix_settings
    ):
        """No engine configured is a settings state, not a lost table."""
        matrix_settings.gnubg_path = None
        with mock.patch(
            "ankigammon.anki.card_generator.get_settings", return_value=matrix_settings
        ):
            gen = CardGenerator(output_dir=tmp_path / "cards")
            html = gen._generate_score_matrix_html(_cube_decision())

        assert html == ""
        assert not gen.generation_warnings


class TestWarningReachesTheRunSummary:
    def test_regenerate_summary_mentions_the_failure(self, qapp, matrix_settings):
        """generation_warnings is what regenerate reports back to the user."""
        from ankigammon.gui.dialogs.regenerate_dialog import (
            MODE_RENDER_ONLY,
            RegenerateWorker,
        )
        from ankigammon.anki.decision_serialize import decision_to_json

        class FakeAnki:
            def test_connection(self):
                return True

            def create_model(self):
                pass

            def invoke(self, action, **kwargs):
                return [1]

            def notes_info(self, ids):
                return [{
                    "noteId": 1,
                    "fields": {
                        "XGID": {"value": CUBE_XGID},
                        "Front": {"value": ""},
                        "Back": {"value": ""},
                        "AnalysisData": {"value": decision_to_json(_cube_decision())},
                    },
                }]

            def update_note_fields(self, *a, **kw):
                pass

            def update_note_tags(self, *a, **kw):
                pass

        worker = RegenerateWorker(matrix_settings, MODE_RENDER_ONLY)
        outcome = {}
        worker.finished.connect(lambda ok, msg: outcome.update(ok=ok, msg=msg))

        with mock.patch(
            "ankigammon.gui.dialogs.regenerate_dialog.AnkiConnect", return_value=FakeAnki()
        ), mock.patch(
            "ankigammon.anki.card_generator.get_settings", return_value=matrix_settings
        ), mock.patch(
            "ankigammon.utils.analyzer_base.create_analyzer", return_value=mock.MagicMock()
        ), mock.patch(
            "ankigammon.analysis.score_matrix.generate_score_matrix",
            side_effect=RuntimeError("engine died mid-matrix"),
        ):
            worker.run()

        assert outcome["ok"], outcome
        assert "without optional analysis" in outcome["msg"], outcome["msg"]
