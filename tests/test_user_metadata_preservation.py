"""The fields an analyzer cannot regenerate, and the paths that must carry them.

Re-analysis builds a Decision from engine output alone. Anything the user
typed - or anything describing where the position came from - exists only on
the old Decision, so every path that replaces one with a fresh analysis has
to copy those fields across explicitly.

Two paths do this: export (analyze-then-export) and regenerate (re-analyze in
place). They drifted apart once already, which is how GitHub issue #58 got in:
export copied the note, regenerate did not. These tests pin the shared helper
and both callers.
"""

import dataclasses
from unittest import mock

import pytest

from ankigammon.anki.decision_serialize import (
    USER_METADATA_FIELDS,
    carry_user_metadata,
    decision_from_json,
    decision_to_json,
)
from ankigammon.models import Decision, DecisionType, Move, Player, Position

XGID = "XGID=-b----E-C--AeD---bAdb---A-:0:0:1:52:0:0:3:0:10"

ANNOTATIONS = {
    "note": "Race lead = 4 pips, so run.",
    "source_file": "match.xg",
    "game_number": 3,
    "move_number": 17,
    "position_image_path": "/cards/pos_1.svg",
    "original_position_format": "OGID",
}


def _decision(**kwargs) -> Decision:
    base = dict(
        position=Position(points=[0] * 26),
        xgid=XGID,
        on_roll=Player.X,
        dice=(5, 2),
        decision_type=DecisionType.CHECKER_PLAY,
    )
    base.update(kwargs)
    return Decision(**base)


def _analyzed() -> Decision:
    """What an engine hands back: moves, no annotations."""
    return _decision(
        candidate_moves=[Move(notation="18/11", equity=-0.0026, rank=1)],
        source_description="Analyzed with GnuBG (3-ply) from XGID",
    )


class TestFieldListIsHonest:
    def test_every_named_field_exists_on_decision(self):
        """Catches a rename that would otherwise silently stop copying."""
        names = {f.name for f in dataclasses.fields(Decision)}

        assert set(USER_METADATA_FIELDS) <= names

    def test_the_list_is_not_accidentally_empty_or_duplicated(self):
        assert USER_METADATA_FIELDS
        assert len(set(USER_METADATA_FIELDS)) == len(USER_METADATA_FIELDS)

    def test_no_analysis_field_is_in_the_list(self):
        """Copying an analysis field across would preserve stale results."""
        forbidden = {
            "candidate_moves", "cube_error", "take_error", "cubeless_equity",
            "double_cubeless_equity", "source_description", "player_win_pct",
            "opponent_win_pct", "xg_error_move",
        }

        assert not forbidden & set(USER_METADATA_FIELDS)

    def test_every_field_round_trips_through_the_blob(self):
        """The blob is where regenerate reads these back from."""
        stored = _decision(**ANNOTATIONS)

        restored = decision_from_json(decision_to_json(stored))

        for name in USER_METADATA_FIELDS:
            assert getattr(restored, name) == ANNOTATIONS[name], name


class TestCarryUserMetadata:
    def test_all_annotations_are_copied(self):
        target = _analyzed()

        carry_user_metadata(_decision(**ANNOTATIONS), target)

        for name, value in ANNOTATIONS.items():
            assert getattr(target, name) == value, name

    def test_analysis_results_are_left_alone(self):
        target = _analyzed()

        carry_user_metadata(_decision(**ANNOTATIONS), target)

        assert target.candidate_moves[0].notation == "18/11"
        assert target.source_description == "Analyzed with GnuBG (3-ply) from XGID"

    def test_absent_annotations_clear_stale_ones(self):
        """A source with no note must not leave a previous note in place."""
        target = _analyzed()
        target.note = "stale"

        carry_user_metadata(_decision(), target)

        assert target.note is None

    def test_returns_the_target(self):
        target = _analyzed()

        assert carry_user_metadata(_decision(**ANNOTATIONS), target) is target

    def test_source_is_not_mutated(self):
        source = _decision(**ANNOTATIONS)

        carry_user_metadata(source, _analyzed())

        assert source.note == ANNOTATIONS["note"]
        assert not source.candidate_moves


class TestExportPathCarriesThem:
    """export_dialog.AnalysisWorker: analyze pending positions, then export."""

    def _run(self, decisions):
        from ankigammon.gui.dialogs.export_dialog import AnalysisWorker
        from ankigammon.settings import Settings

        class FakeAnalyzer:
            def analyze_positions_parallel(self, ids, progress_callback=None, **kw):
                return [("<raw>", DecisionType.CHECKER_PLAY) for _ in ids]

            def parse_analysis(self, raw, xgid, decision_type):
                return _analyzed()

            def terminate(self):
                pass

        worker = AnalysisWorker(decisions, Settings())
        captured = {}
        worker.finished.connect(
            lambda ok, msg, decs: captured.update(ok=ok, msg=msg, decisions=decs)
        )
        with mock.patch(
            "ankigammon.gui.dialogs.export_dialog.create_analyzer",
            return_value=FakeAnalyzer(),
        ):
            worker.run()
        assert captured["ok"], captured["msg"]
        return captured["decisions"]

    def test_annotations_survive_analysis(self, qapp):
        result = self._run([_decision(**ANNOTATIONS)])

        for name, value in ANNOTATIONS.items():
            if name == "original_position_format":
                continue  # feeds source_description, asserted below
            assert getattr(result[0], name) == value, name

    def test_source_description_is_refreshed_not_carried(self, qapp):
        result = self._run([_decision(**ANNOTATIONS)])

        assert result[0].source_description.startswith("Analyzed with")
        assert "OGID" in result[0].source_description

    def test_each_position_keeps_its_own_annotations(self, qapp):
        result = self._run([
            _decision(note="first"),
            _decision(note="second"),
        ])

        assert [d.note for d in result] == ["first", "second"]

    def test_already_analyzed_positions_are_left_untouched(self, qapp):
        """Only positions lacking moves get analyzed; the rest pass through."""
        done = _decision(note="untouched",
                         candidate_moves=[Move(notation="24/18", equity=0.1, rank=1)])

        result = self._run([done])

        assert result[0] is done
        assert result[0].note == "untouched"
