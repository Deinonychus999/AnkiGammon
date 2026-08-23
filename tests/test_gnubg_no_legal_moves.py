"""Regression tests for gnubg positions with no legal move.

A user hit "Analysis failed: No moves found in gnubg output for
checker_play" when exporting to Anki. gnubg answers a blocked roll (a
dance, or a roll with no legal play) with "There are no legal moves."
instead of a move list, and the parser turned that into a ValueError that
aborted the whole export batch.

Covers:
  * GNUBGParser produces XG's "Cannot move" for that output
  * AnalysisWorker drops an unparseable position instead of discarding
    every other position analyzed alongside it
"""

from unittest import mock

import pytest
from PySide6.QtWidgets import QApplication

from ankigammon.gui.dialogs.export_dialog import AnalysisWorker, ExportDialog
from ankigammon.models import Decision, DecisionType, Move, Player
from ankigammon.settings import Settings
from ankigammon.parsers.gnubg_parser import GNUBGParser
from ankigammon.utils.xgid import parse_xgid


# X is on the bar against a closed board, so 65 has no legal play.
DANCE_XGID = "XGID=------E-E---Dc-----bbbbbbA:0:0:1:65:0:0:0:0:10"

# Captured from gnubg-cli 1.08.003 for DANCE_XGID.
DANCE_OUTPUT = """ GNU Backgammon  Position ID: sHPwATDgc/ABMA
                 Match ID   : cIkXAAAAAAAE

Analysis chequerplay will use 2 ply evaluation.
Analysis cubedecision will use 2 ply evaluation.
Match winning chances will be shown as probabilities.

There are no legal moves.
"""

NORMAL_OUTPUT = """Match winning chances will be shown as probabilities.
    1. Cubeful 2-ply    8/5 6/5                      Eq.: +0.218
       0.551 0.170 0.008 - 0.449 0.117 0.005
        2-ply cubeful prune [world class]
    2. Cubeful 2-ply    24/23 13/10                  Eq.: -0.010 (-0.229)
       0.496 0.139 0.006 - 0.504 0.138 0.006
        2-ply cubeful prune [world class]
"""

NORMAL_XGID = "XGID=-b----E-C---eE---c-e----B-:0:0:1:31:0:0:0:0:10"


class TestNoLegalMoves:
    def test_blocked_roll_yields_cannot_move(self):
        moves = GNUBGParser._parse_checker_play(DANCE_OUTPUT)

        assert [m.notation for m in moves] == ["Cannot move"]
        assert moves[0].rank == 1
        assert moves[0].error == 0.0

    def test_tutor_phrasing_is_also_recognized(self):
        # gnubg appends "Figure it out yourself." when the tutor is on.
        text = DANCE_OUTPUT.replace(
            "There are no legal moves.",
            "There are no legal moves. Figure it out yourself.",
        )

        assert [m.notation for m in GNUBGParser._parse_checker_play(text)] == [
            "Cannot move"
        ]

    def test_parse_analysis_no_longer_raises(self):
        # The exact failure from the bug report.
        decision = GNUBGParser.parse_analysis(
            DANCE_OUTPUT, DANCE_XGID, DecisionType.CHECKER_PLAY
        )

        assert [m.notation for m in decision.candidate_moves] == ["Cannot move"]
        assert decision.get_best_move().notation == "Cannot move"

    def test_normal_output_still_parses_moves(self):
        moves = GNUBGParser._parse_checker_play(NORMAL_OUTPUT)

        assert [m.notation for m in moves] == ["8/5 6/5", "24/23 13/10"]


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class _Settings:
    analyzer_type = "gnubg"
    gnubg_analysis_ply = 2


def _decision(xgid: str) -> Decision:
    position, metadata = parse_xgid(xgid)
    return Decision(
        position=position,
        xgid=xgid,
        on_roll=metadata.get("on_roll", Player.O),
        dice=metadata.get("dice"),
        decision_type=DecisionType.CHECKER_PLAY,
    )


def _analyzed(xgid: str) -> Decision:
    decision = _decision(xgid)
    decision.candidate_moves = [Move(notation="8/5 6/5", equity=0.2, rank=1)]
    return decision


def _run_worker(decisions, failing_xgids):
    analyzer = mock.Mock()
    analyzer.analyze_positions_parallel.return_value = [
        ("output", DecisionType.CHECKER_PLAY) for _ in decisions
    ]

    def parse_analysis(raw_output, xgid, decision_type):
        if xgid in failing_xgids:
            raise ValueError("No moves found in gnubg output for checker_play")
        return _analyzed(xgid)

    analyzer.parse_analysis.side_effect = parse_analysis

    worker = AnalysisWorker(decisions, _Settings())
    captured = []
    worker.finished.connect(
        lambda ok, message, result: captured.append((ok, message, result))
    )
    with mock.patch(
        "ankigammon.gui.dialogs.export_dialog.create_analyzer", return_value=analyzer
    ):
        worker.run()

    assert len(captured) == 1, captured
    return captured[0]


class TestAnalysisWorkerResilience:
    def test_one_bad_position_does_not_discard_the_batch(self, qapp):
        good_a = _decision(NORMAL_XGID)
        bad = _decision(DANCE_XGID)
        good_b = _decision("XGID=-b----E-C---eE---c-e----B-:0:0:1:52:0:0:0:0:10")

        ok, message, result = _run_worker([good_a, bad, good_b], {DANCE_XGID})

        assert ok is True
        assert "Analyzed 2 position(s)" in message
        assert "1 skipped" in message
        assert [bool(d.candidate_moves) for d in result] == [True, False, True]

    def test_every_position_failing_still_reports_failure(self, qapp):
        bad = _decision(DANCE_XGID)

        ok, message, _ = _run_worker([bad], {DANCE_XGID})

        assert ok is False
        assert "No moves found in gnubg output" in message


class TestExportDialogDropsUnanalyzedPositions:
    def test_move_less_positions_are_not_sent_to_the_exporter(self, qapp, tmp_path):
        deck_a = [_analyzed(NORMAL_XGID), _decision(DANCE_XGID)]
        deck_b = [_analyzed(NORMAL_XGID)]
        grouped = {"Deck A": deck_a, "Deck B": deck_b}
        settings = Settings(config_path=tmp_path / "config.json")

        dialog = ExportDialog(grouped, settings)
        with mock.patch.object(ExportDialog, "_start_export_worker") as start:
            dialog.on_analysis_finished(True, "Analyzed 2 position(s) (1 skipped)",
                                        deck_a + deck_b)

        assert start.called
        assert [len(v) for v in dialog.grouped_decisions.values()] == [1, 1]
        assert len(dialog.all_decisions) == 2
        assert all(d.candidate_moves for d in dialog.all_decisions)

    def test_deck_left_empty_is_removed(self, qapp, tmp_path):
        grouped = {"Deck A": [_decision(DANCE_XGID)], "Deck B": [_analyzed(NORMAL_XGID)]}
        settings = Settings(config_path=tmp_path / "config.json")

        dialog = ExportDialog(grouped, settings)
        with mock.patch.object(ExportDialog, "_start_export_worker"):
            dialog.on_analysis_finished(
                True, "Analyzed 1 position(s) (1 skipped)",
                [_decision(DANCE_XGID), _analyzed(NORMAL_XGID)],
            )

        assert list(dialog.grouped_decisions) == ["Deck B"]
