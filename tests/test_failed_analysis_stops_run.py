"""A failed optional analysis stops the run instead of writing a bare card.

User report: when the connection to HedgeHog dropped while making cards, the
run went on and wrote cards without the score matrices or cube comparison the
settings ask for, and those cards are then hard to find among the rest. Any
engine's failure on an analysis the settings ask for now stops the desktop
export or regenerate before that card. A failure that repeats on one position
would then block every retry, so the dialog offers to go on without the
missing tables, and Send to Anki resumes at the card that stopped it.

An exhausted HedgeHog allowance still finishes without the tables, since the
export asked about exactly that before it started. The browser version keeps
writing cards without what failed: it reports misses instead of stopping.
"""

from unittest import mock

import pytest

from ankigammon.anki.card_generator import CardGenerator
from ankigammon.anki.decision_serialize import decision_to_json
from ankigammon.models import DecisionType, Move
from ankigammon.settings import Settings
from ankigammon.utils.analyzer_base import OptionalAnalysisFailed
from tests.test_hedgehog_rate_limit import (  # noqa: F401  (settings is a fixture)
    MATRIX, XGIDS, _allowance_exhausted, _cube_decision, _export, settings,
)

LOST = "Could not reach HedgeHog (The handshake operation timed out)."


def _lost_at_second(xgid, analyzer, **kwargs):
    if xgid == XGIDS[1]:
        raise RuntimeError(LOST)
    return MATRIX


def _allowance_at_second(xgid, analyzer, **kwargs):
    if xgid == XGIDS[1]:
        raise _allowance_exhausted()
    return MATRIX


class TestExportStops:
    def test_send_to_anki_stops_before_the_card_whose_matrix_failed(self, qapp, settings):
        sent, [(ok, message)], worker = _export(qapp, settings, mock.MagicMock(), _lost_at_second)

        assert sent == XGIDS[:1]
        assert not ok
        assert LOST in message and XGIDS[1] in message
        assert "Stopped after sending 1 of 3 card(s)" in message
        assert isinstance(worker.stopped_by, OptionalAnalysisFailed)
        assert worker.sent == 1

    def test_an_apkg_is_not_written(self, qapp, settings, tmp_path):
        target = tmp_path / "deck.apkg"
        _, [(ok, message)], _ = _export(qapp, settings, mock.MagicMock(), _lost_at_second, "apkg", str(target))

        assert not ok and LOST in message
        assert not target.exists()

    def test_nothing_goes_to_the_trainer(self, qapp, settings):
        _, [(ok, message)], worker = _export(qapp, settings, mock.MagicMock(), _lost_at_second, "trainer")

        assert not ok and LOST in message
        assert worker.pack is None

    def test_a_missing_unlimited_reference_stops_it_too(self, qapp, settings):
        def without_reference(xgid, analyzer, **kwargs):
            return [], (None if xgid == XGIDS[1] else MATRIX[1])

        sent, [(ok, message)], _ = _export(qapp, settings, mock.MagicMock(), without_reference)

        assert sent == XGIDS[:1]
        assert not ok and "unlimited reference" in message

    def test_an_exhausted_allowance_still_finishes_without_the_tables(self, qapp, settings):
        sent, [(ok, message)], _ = _export(qapp, settings, mock.MagicMock(), _allowance_at_second)

        assert sent == XGIDS
        assert ok


class TestGoingOn:
    def test_without_missing_tables_writes_every_card_and_reports_the_miss(self, qapp, settings):
        sent, [(ok, message)], _ = _export(
            qapp, settings, mock.MagicMock(), _lost_at_second, require_optional_analysis=False,
        )

        assert sent == XGIDS
        assert ok
        assert f"Score matrix failed for {XGIDS[1]}" in message

    def test_send_to_anki_resumes_at_the_card_that_stopped_it(self, qapp, settings):
        sent, [(ok, message)], _ = _export(qapp, settings, mock.MagicMock(), _lost_at_second, already_sent=1,
                                           require_optional_analysis=False)

        assert sent == XGIDS[1:]
        assert ok
        assert "3 card(s)" in message


def _checker_decision():
    return mock.MagicMock(
        xgid=XGIDS[0], decision_type=DecisionType.CHECKER_PLAY, dice=(5, 2),
        crawford=False, match_length=7, candidate_moves=[Move(notation="13/8 13/11", equity=0.1, rank=1)],
    )


@pytest.fixture
def generator(settings, tmp_path):
    def make(**options):
        with mock.patch("ankigammon.anki.card_generator.get_settings", return_value=settings):
            return CardGenerator(output_dir=tmp_path, analyzer=mock.MagicMock(), **options)
    return make


class TestEachOptionalAnalysis:
    @pytest.mark.parametrize("target, render", [
        ("ankigammon.analysis.move_score_matrix.generate_move_score_matrix", "_generate_move_score_matrix_html"),
        ("ankigammon.analysis.move_cube_matrix.generate_move_cube_matrix", "_generate_move_cube_matrix_html"),
    ])
    def test_a_checker_play_table_stops_the_run(self, generator, target, render):
        gen = generator(require_optional_analysis=True)
        with mock.patch(target, side_effect=RuntimeError(LOST)):
            with pytest.raises(OptionalAnalysisFailed, match="could not be made"):
                getattr(gen, render)(_checker_decision())

    @pytest.mark.parametrize("target, render, warning", [
        ("ankigammon.analysis.move_score_matrix.generate_move_score_matrix",
         "_generate_move_score_matrix_html", "Move score matrix failed"),
        ("ankigammon.analysis.move_cube_matrix.generate_move_cube_matrix",
         "_generate_move_cube_matrix_html", "Cube-position analysis failed"),
    ])
    def test_the_browser_version_writes_the_card_and_reports_the_miss(self, generator, target, render, warning):
        gen = generator()
        with mock.patch(target, side_effect=RuntimeError(LOST)):
            getattr(gen, render)(_checker_decision())
        assert any(warning in w for w in gen.generation_warnings), gen.generation_warnings


class TestRegenerate:
    def _run(self, qapp, settings, **options):
        from ankigammon.gui.dialogs.regenerate_dialog import MODE_RENDER_ONLY, RegenerateWorker

        updated = []

        class Anki:
            def test_connection(self):
                return True

            def create_model(self):
                pass

            def invoke(self, action, **kwargs):
                return [0, 1]

            def notes_info(self, ids):
                return [{
                    "noteId": i,
                    "fields": {
                        "XGID": {"value": XGIDS[i]},
                        "Front": {"value": ""},
                        "Back": {"value": "<table class=score-matrix-table></table>"},
                        "AnalysisData": {"value": decision_to_json(_cube_decision(XGIDS[i]))},
                    },
                } for i in ids]

            def update_note_fields(self, note_id, *args, **kwargs):
                updated.append(note_id)

            def update_note_tags(self, *args, **kwargs):
                pass

        worker = RegenerateWorker(settings, MODE_RENDER_ONLY, **options)
        results = []
        worker.finished.connect(lambda ok, msg: results.append((ok, msg)))
        with mock.patch("ankigammon.gui.dialogs.regenerate_dialog.AnkiConnect", return_value=Anki()), \
                mock.patch("ankigammon.anki.card_generator.get_settings", return_value=settings), \
                mock.patch.object(Settings, "is_engine_available", return_value=True), \
                mock.patch("ankigammon.utils.analyzer_base.create_analyzer", return_value=mock.MagicMock()), \
                mock.patch("ankigammon.analysis.score_matrix.generate_score_matrix", side_effect=_lost_at_second):
            worker.run()
        return updated, results, worker

    def test_it_stops_at_the_card_whose_matrix_failed(self, qapp, settings):
        updated, [(ok, message)], worker = self._run(qapp, settings)

        assert updated == [0]
        assert not ok and LOST in message
        assert "Stopped at card 2 of 2" in message
        assert isinstance(worker.stopped_by, OptionalAnalysisFailed)

    def test_without_missing_tables_it_keeps_the_card_that_failed(self, qapp, settings):
        updated, [(ok, message)], _ = self._run(qapp, settings, require_optional_analysis=False)

        assert updated == [0]
        assert ok and "Kept 1 card(s) unchanged" in message


class TestExportDialog:
    def _stopped_dialog(self, qapp, settings, stopped_by, sent=1):
        from ankigammon.gui.dialogs import export_dialog

        started = []

        class Worker:
            def __init__(self, *args, **kwargs):
                started.append(kwargs)
                self.progress = self.status_message = self.finished = mock.MagicMock()

            def start(self):
                pass

        settings.export_method = "ankiconnect"
        dialog = export_dialog.ExportDialog({settings.deck_name: [_cube_decision(x) for x in XGIDS]}, settings)
        dialog.output_path = None
        dialog.worker = mock.MagicMock(stopped_by=stopped_by, sent=sent)
        dialog.on_finished(False, "stopped")
        return dialog, started, mock.patch.object(export_dialog, "ExportWorker", Worker)

    def test_after_a_failed_table_it_offers_to_go_on_without_it(self, qapp, settings):
        dialog, started, worker_class = self._stopped_dialog(qapp, settings, OptionalAnalysisFailed(LOST))
        assert not dialog.btn_without.isHidden()

        with worker_class:
            dialog.btn_without.click()

        [options] = started
        assert options["require_optional_analysis"] is False
        assert options["already_sent"] == 1
        assert dialog.btn_without.isHidden()

    def test_a_retry_still_requires_the_tables_and_resumes(self, qapp, settings):
        dialog, started, worker_class = self._stopped_dialog(qapp, settings, OptionalAnalysisFailed(LOST))
        with worker_class:
            dialog._start_export_worker()
        [options] = started
        assert options["require_optional_analysis"] is True
        assert options["already_sent"] == 1

    def test_a_rate_limit_offers_no_way_around_it(self, qapp, settings):
        from tests.test_hedgehog_rate_limit import _rate_limited
        dialog, _, _ = self._stopped_dialog(qapp, settings, _rate_limited())
        assert dialog.btn_without.isHidden()


def test_regenerate_offers_to_go_on_without_the_failed_tables(qapp, settings):
    from ankigammon.gui.dialogs import regenerate_dialog

    started = []

    class Worker:
        def __init__(self, *args, **kwargs):
            started.append(kwargs)
            self.progress = self.status_message = self.finished = mock.MagicMock()

        def start(self):
            pass

    dialog = regenerate_dialog.RegenerateDialog(settings)
    assert dialog.btn_without.isHidden()
    dialog.worker = mock.MagicMock(stopped_by=OptionalAnalysisFailed(LOST))
    dialog.on_finished(False, "stopped")
    assert not dialog.btn_without.isHidden()

    with mock.patch.object(regenerate_dialog, "RegenerateWorker", Worker):
        dialog.btn_without.click()
    [options] = started
    assert options["require_optional_analysis"] is False
