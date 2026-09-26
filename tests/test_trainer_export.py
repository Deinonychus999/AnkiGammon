"""Send to Trainer, the export method that hands a study pack to the browser
trainer instead of writing Anki cards.

It runs the same optional analyses as an Anki export (score matrix, move
score matrix, cube-position comparison) and stores them as data under each
position's "extras", since the trainer has no engine of its own.
"""

import json
from unittest import mock

import pytest

from ankigammon.analysis.move_cube_matrix import CubeMatrixColumn, MoveAtCubeState
from ankigammon.analysis.move_score_matrix import MoveAtScore, MoveScoreMatrixColumn
from ankigammon.analysis.score_matrix import ScoreMatrixCell, UnlimitedReference
from ankigammon.anki.card_generator import CardGenerator
from ankigammon.models import CubeState, Decision, DecisionType, Move, Player, Position
from ankigammon.settings import Settings
from ankigammon.study_pack import build_pack, save_pack

CUBE_XGID = "XGID=-b----E-C--AeD---bAdb---A-:0:0:1:00:0:0:3:0:10"
CHECKER_XGID = "XGID=-b----E-C--AeD---bAdb---A-:0:0:1:52:0:0:3:0:10"


def _cell(pa, oa, action="D/T"):
    return ScoreMatrixCell(player_away=pa, opponent_away=oa, best_action=action,
                           error_no_double=0.05, error_double=0.0, error_pass=0.3,
                           equity_no_double=0.4, equity_double_take=0.45, equity_double_pass=1.0)


def _cube_decision():
    return Decision(
        position=Position(points=[0] * 26), xgid=CUBE_XGID, on_roll=Player.O, dice=None,
        match_length=3, score_o=0, score_x=0, cube_value=1, cube_owner=CubeState.CENTERED,
        decision_type=DecisionType.CUBE_ACTION,
        candidate_moves=[Move(notation="Double/Take", equity=0.45, rank=1)],
    )


def _checker_decision():
    return Decision(
        position=Position(points=[0] * 26), xgid=CHECKER_XGID, on_roll=Player.O, dice=(5, 2),
        match_length=0, cube_value=1, cube_owner=CubeState.CENTERED,
        decision_type=DecisionType.CHECKER_PLAY,
        candidate_moves=[Move(notation="18/11", equity=0.0, rank=1)],
    )


@pytest.fixture
def settings(tmp_path):
    s = Settings(config_path=tmp_path / "config.json")
    s.generate_score_matrix = True
    s.generate_move_score_matrix = True
    s.generate_move_cube_matrix = True
    return s


@pytest.fixture
def card_gen(qapp, settings, tmp_path):
    with mock.patch("ankigammon.anki.card_generator.get_settings", return_value=settings), \
            mock.patch.object(CardGenerator, "_engine_available", return_value=True):
        yield CardGenerator(output_dir=tmp_path / "cards", analyzer=mock.MagicMock())


MATRIX = [[_cell(2, 2), _cell(2, 3, "N/T")], [_cell(3, 2, "D/P"), _cell(3, 3)]]
UNLIMITED = UnlimitedReference(no_jacoby=_cell(0, 0), jacoby=None)
MOVE_COLUMNS = [MoveScoreMatrixColumn("Neutral", [MoveAtScore("18/11", 0.1, 0.0, 1)]),
                MoveScoreMatrixColumn("DMP", [MoveAtScore("24/22 18/13", 0.2, 0.0, 1)])]
CUBE_COLUMNS = [CubeMatrixColumn("Neutral", [MoveAtCubeState("18/11", 0.1, 0.0, 1)]),
                CubeMatrixColumn("Player", [MoveAtCubeState("24/22 18/13", 0.2, 0.0, 1)])]


class TestStudyExtras:
    def test_a_cube_decision_carries_its_score_matrix_as_data(self, card_gen):
        with mock.patch("ankigammon.analysis.score_matrix.generate_score_matrix", return_value=(MATRIX, UNLIMITED)):
            extras = card_gen.study_extras(_cube_decision())

        matrix = extras["score_matrix"]
        assert [[c["best_action"] for c in row] for row in matrix["cells"]] == [["D/T", "N/T"], ["D/P", "D/T"]]
        assert matrix["current"] == {"player_away": 3, "opponent_away": 3}
        assert matrix["unlimited"]["no_jacoby"]["best_action"] == "D/T"
        assert matrix["projection"] is False
        assert json.loads(json.dumps(extras)) == extras

    def test_a_checker_play_carries_both_move_tables(self, card_gen):
        with mock.patch("ankigammon.analysis.move_score_matrix.generate_move_score_matrix", return_value=MOVE_COLUMNS), \
                mock.patch("ankigammon.analysis.move_cube_matrix.generate_move_cube_matrix", return_value=CUBE_COLUMNS):
            extras = card_gen.study_extras(_checker_decision())

        assert [c["score_type"] for c in extras["move_score_matrix"]["columns"]] == ["Neutral", "DMP"]
        assert extras["cube_matrix"]["best_move_differs"] is True
        assert extras["cube_matrix"]["columns"][1]["top_moves"][0]["notation"] == "24/22 18/13"

    def test_only_the_analyses_the_settings_ask_for_are_run(self, card_gen, settings):
        settings.generate_move_score_matrix = False
        settings.generate_move_cube_matrix = False
        with mock.patch("ankigammon.analysis.move_score_matrix.generate_move_score_matrix") as move, \
                mock.patch("ankigammon.analysis.move_cube_matrix.generate_move_cube_matrix") as cube:
            assert card_gen.study_extras(_checker_decision()) == {}
        move.assert_not_called()
        cube.assert_not_called()

    def test_a_failed_analysis_is_left_out_and_reported(self, card_gen):
        with mock.patch("ankigammon.analysis.score_matrix.generate_score_matrix", side_effect=RuntimeError("engine died")):
            extras = card_gen.study_extras(_cube_decision())
        assert extras == {}
        assert any(CUBE_XGID in w for w in card_gen.generation_warnings)

    def test_cancelling_stops_the_export(self, card_gen):
        with mock.patch("ankigammon.analysis.score_matrix.generate_score_matrix", side_effect=InterruptedError):
            with pytest.raises(InterruptedError):
                card_gen.study_extras(_cube_decision())

    def test_the_card_back_still_gets_the_same_table(self, card_gen):
        with mock.patch("ankigammon.analysis.score_matrix.generate_score_matrix", return_value=(MATRIX, UNLIMITED)):
            html = card_gen._generate_score_matrix_html(_cube_decision())
        assert "score-matrix" in html and "D/P" in html


class TestPackExtras:
    def test_extras_go_with_their_position(self):
        unanalyzed = _checker_decision()
        unanalyzed.candidate_moves = []
        pack = build_pack([unanalyzed, _cube_decision(), _checker_decision()], "Club",
                          extras=[{"x": 1}, {"score_matrix": {"cells": []}}, {}])
        assert [p["xgid"] for p in pack["positions"]] == [CUBE_XGID, CHECKER_XGID]
        assert pack["positions"][0]["extras"] == {"score_matrix": {"cells": []}}
        assert "extras" not in pack["positions"][1]

    def test_save_pack_writes_the_document(self, tmp_path):
        pack = build_pack([_cube_decision()], "Club")
        assert save_pack(pack, tmp_path / "club.json") == 1
        assert json.loads((tmp_path / "club.json").read_text(encoding="utf-8")) == pack


class TestExportWorker:
    def _run(self, qapp, settings, decisions, extras):
        from ankigammon.gui.dialogs.export_dialog import ExportWorker
        settings.deck_name = "AnkiGammon::Club night"
        worker = ExportWorker({"AnkiGammon": decisions}, settings, "trainer", analyzer=mock.MagicMock())
        results = []
        worker.finished.connect(lambda ok, msg: results.append((ok, msg)))
        with mock.patch("ankigammon.anki.card_generator.get_settings", return_value=settings), \
                mock.patch.object(CardGenerator, "study_extras", side_effect=extras):
            worker.run()
        return worker, results

    def test_builds_one_pack_named_after_the_deck(self, qapp, settings):
        worker, results = self._run(qapp, settings, [_cube_decision(), _checker_decision()],
                                    [{"score_matrix": {"cells": []}}, {}])
        assert results[0][0] is True
        assert worker.pack["deck"]["title"] == "Club night"
        assert [p["xgid"] for p in worker.pack["positions"]] == [CUBE_XGID, CHECKER_XGID]
        assert worker.pack["positions"][0]["extras"] == {"score_matrix": {"cells": []}}

    def test_nothing_analyzed_is_a_failure(self, qapp, settings):
        empty = _checker_decision()
        empty.candidate_moves = []
        worker, results = self._run(qapp, settings, [empty], [{}])
        assert results[0][0] is False
        assert worker.pack is None

    def test_cancelling_during_an_analysis_stops_it(self, qapp, settings):
        worker, results = self._run(qapp, settings, [_cube_decision()], InterruptedError)
        assert results == [(False, "Export cancelled by user")]


class TestExportDialog:
    def _dialog(self, qapp, settings):
        from ankigammon.gui.dialogs.export_dialog import ExportDialog
        settings.export_method = "trainer"
        settings.deck_name = "Club night"
        dialog = ExportDialog({"Club night": [_cube_decision()]}, settings)
        dialog.worker = mock.MagicMock(pack=build_pack([_cube_decision()], "Club night"))
        return dialog

    def test_names_itself_after_the_trainer(self, qapp, settings):
        dialog = self._dialog(qapp, settings)
        assert dialog.windowTitle() == "Send to Trainer"
        assert dialog.btn_export.text() == "Send"

    @pytest.mark.parametrize("outcome, success, words", [
        ("sent", True, "Sent 1 position(s) to the trainer"),
        ("cancelled", False, "Not sent"),
    ])
    def test_handoff_outcomes(self, qapp, settings, outcome, success, words):
        dialog = self._dialog(qapp, settings)
        handoff = mock.MagicMock(outcome=outcome)
        with mock.patch("ankigammon.gui.dialogs.trainer_handoff_dialog.TrainerHandoffDialog", return_value=handoff):
            ok, message = dialog._hand_to_trainer("Prepared 1 position(s) for the trainer\nWarning(s):\n  - x")
        assert ok is success
        assert words in message
        if success:
            assert "Warning(s)" in message

    def test_save_file_instead_writes_the_same_pack(self, qapp, settings, tmp_path):
        dialog = self._dialog(qapp, settings)
        target = tmp_path / "Club night.json"
        with mock.patch("ankigammon.gui.dialogs.trainer_handoff_dialog.TrainerHandoffDialog",
                        return_value=mock.MagicMock(outcome="save_file")), \
                mock.patch("ankigammon.gui.dialogs.export_dialog.QFileDialog.getSaveFileName",
                           return_value=(str(target), "")):
            ok, message = dialog._hand_to_trainer("Prepared 1 position(s) for the trainer")
        assert ok is True and str(target) in message
        assert json.loads(target.read_text(encoding="utf-8")) == dialog.worker.pack


def test_settings_offer_the_trainer_as_an_export_method():
    from ankigammon.gui.dialogs.settings_dialog import EXPORT_METHODS
    assert [value for value, _ in EXPORT_METHODS] == ["ankiconnect", "apkg", "trainer"]
