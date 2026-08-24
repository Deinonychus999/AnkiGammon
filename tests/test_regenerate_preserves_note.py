"""Regression tests for GitHub issue #58: Regenerate deleted user comments.

The re-analyze path rebuilds each Decision from fresh engine output, which
carries no user annotations. Before the fix it wrote that annotation-free
Decision back over both the rendered Back field and the AnalysisData blob,
destroying the user's note with no way to recover it.

The re-render path never had the bug (it deserializes FROM AnalysisData), so
it is pinned here too as the contrast case.
"""

from unittest import mock

import pytest
from PySide6.QtWidgets import QApplication

from ankigammon.anki.decision_serialize import decision_to_json, decision_from_json
from ankigammon.gui.dialogs.regenerate_dialog import (
    MODE_REANALYZE,
    MODE_RENDER_ONLY,
    RegenerateWorker,
)
from ankigammon.models import Decision, DecisionType, Player, Position
from ankigammon.settings import Settings


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


XGID_A = "XGID=-b----E-C--AeD---bAdb---A-:0:0:1:52:0:0:3:0:10"
XGID_B = "XGID=-b----E-C--AeD---bAdb---A-:0:0:1:31:0:0:3:0:10"


def _decision(xgid: str, note=None, **kwargs) -> Decision:
    return Decision(
        position=Position(points=[0] * 26),
        xgid=xgid,
        on_roll=Player.X,
        dice=(5, 2),
        decision_type=DecisionType.CHECKER_PLAY,
        note=note,
        **kwargs,
    )


class FakeCardGenerator:
    """Stands in for CardGenerator, recording what each card was built from."""

    generation_warnings = []

    def __init__(self):
        self.seen = []

    def generate_card(self, decision):
        self.seen.append(decision)
        note_html = ""
        if decision.note:
            note_html = "<div class=note>" + decision.note + "</div>"
        return {
            "front": "<div>front</div>",
            "back": "<div>back</div>" + note_html,
            "xgid": decision.xgid or "",
            "analysis_data": decision_to_json(decision),
            "tags": ["ankigammon"],
        }


class FakeAnkiConnect:
    """In-memory stand-in for a live Anki collection."""

    def __init__(self, notes):
        self._notes = {n["noteId"]: n for n in notes}
        self.writes = {}

    def test_connection(self):
        return True

    def create_model(self):
        pass

    def invoke(self, action, **kwargs):
        if action == "findNotes":
            return list(self._notes)
        raise AssertionError("unexpected invoke: " + action)

    def notes_info(self, note_ids):
        return [self._notes[i] for i in note_ids]

    def update_note_fields(self, note_id, front, back, xgid="", analysis_data=None):
        self.writes[note_id] = {
            "front": front,
            "back": back,
            "xgid": xgid,
            "analysis_data": analysis_data,
        }

    def update_note_tags(self, note_id, tags):
        pass


class FakeAnalyzer:
    """Returns fresh, annotation-free analysis - exactly what a real engine does."""

    def __init__(self):
        self.terminated = False

    def analyze_positions_parallel(self, xgids, progress_callback=None, **kwargs):
        return [("<raw>", DecisionType.CHECKER_PLAY) for _ in xgids]

    def parse_analysis(self, raw_output, xgid, decision_type):
        return _decision(xgid)

    def terminate(self):
        self.terminated = True


def _anki_note(note_id, xgid, note_text):
    """An Anki note as notesInfo returns it, carrying a user note."""
    stored = _decision(xgid, note=note_text)
    return {
        "noteId": note_id,
        "fields": {
            "XGID": {"value": xgid},
            "Front": {"value": "<div>front</div>"},
            "Back": {"value": "<div>back</div><div class=note>" + note_text + "</div>"},
            "AnalysisData": {"value": decision_to_json(stored)},
        },
    }


def _run(mode, notes, analyzer=None):
    """Drive RegenerateWorker synchronously against fakes."""
    client = FakeAnkiConnect(notes)
    card_gen = FakeCardGenerator()
    analyzer = analyzer or FakeAnalyzer()
    result = {}

    worker = RegenerateWorker(Settings(), mode)
    worker.finished.connect(lambda ok, msg: result.update(ok=ok, msg=msg))

    with mock.patch(
        "ankigammon.gui.dialogs.regenerate_dialog.AnkiConnect", return_value=client
    ), mock.patch(
        "ankigammon.utils.analyzer_base.create_analyzer", return_value=analyzer
    ), mock.patch.object(
        RegenerateWorker, "_build_card_generator", return_value=card_gen
    ):
        worker.run()

    return client, card_gen, result


class TestReanalyzePreservesNote:
    def test_note_survives_reanalyze_in_rendered_back(self, qapp):
        notes = [_anki_note(1, XGID_A, "Race lead = 4 pips, so run.")]
        _, card_gen, result = _run(MODE_REANALYZE, notes)

        assert result["ok"], result
        assert len(card_gen.seen) == 1
        assert card_gen.seen[0].note == "Race lead = 4 pips, so run."

    def test_note_survives_reanalyze_in_analysis_data(self, qapp):
        """The blob is the only durable home for the note - losing it is unrecoverable."""
        notes = [_anki_note(1, XGID_A, "When ahead in the race, race!")]
        client, _, result = _run(MODE_REANALYZE, notes)

        assert result["ok"], result
        blob = client.writes[1]["analysis_data"]
        assert blob, "re-analyze must still write a refreshed AnalysisData blob"
        assert decision_from_json(blob).note == "When ahead in the race, race!"

    def test_two_notes_sharing_one_xgid_keep_their_own_notes(self, qapp):
        """Decisions are deduped by XGID for analysis; annotations are per-note."""
        notes = [
            _anki_note(1, XGID_A, "first card comment"),
            _anki_note(2, XGID_A, "second card comment"),
        ]
        client, _, result = _run(MODE_REANALYZE, notes)

        assert result["ok"], result
        assert decision_from_json(client.writes[1]["analysis_data"]).note == "first card comment"
        assert decision_from_json(client.writes[2]["analysis_data"]).note == "second card comment"

    def test_other_user_metadata_survives_reanalyze(self, qapp):
        """Mirrors the preservation the export path already does."""
        stored = _decision(
            XGID_A,
            note="keep me",
            source_file="match.xg",
            game_number=3,
            move_number=17,
            original_position_format="OGID",
        )
        notes = [{
            "noteId": 1,
            "fields": {
                "XGID": {"value": XGID_A},
                "Front": {"value": ""},
                "Back": {"value": ""},
                "AnalysisData": {"value": decision_to_json(stored)},
            },
        }]
        _, card_gen, result = _run(MODE_REANALYZE, notes)

        assert result["ok"], result
        seen = card_gen.seen[0]
        assert seen.note == "keep me"
        assert seen.source_file == "match.xg"
        assert seen.game_number == 3
        assert seen.move_number == 17
        assert seen.original_position_format == "OGID"

    def test_reanalyze_still_refreshes_source_description(self, qapp):
        """Preserving annotations must not preserve the stale engine label."""
        notes = [_anki_note(1, XGID_A, "note")]
        _, card_gen, result = _run(MODE_REANALYZE, notes)

        assert result["ok"], result
        assert card_gen.seen[0].source_description.startswith("Regenerated with")

    def test_legacy_note_without_analysis_data_still_regenerates(self, qapp):
        """Pre-AnalysisData cards have no note to restore; they must not crash."""
        notes = [{
            "noteId": 1,
            "fields": {
                "XGID": {"value": XGID_A},
                "Front": {"value": ""},
                "Back": {"value": ""},
                "AnalysisData": {"value": ""},
            },
        }]
        client, card_gen, result = _run(MODE_REANALYZE, notes)

        assert result["ok"], result
        assert card_gen.seen[0].note is None
        assert client.writes[1]["analysis_data"]

    def test_corrupt_analysis_data_does_not_abort_the_batch(self, qapp):
        notes = [
            {
                "noteId": 1,
                "fields": {
                    "XGID": {"value": XGID_A},
                    "Front": {"value": ""},
                    "Back": {"value": ""},
                    "AnalysisData": {"value": "{not json"},
                },
            },
            _anki_note(2, XGID_B, "still here"),
        ]
        client, _, result = _run(MODE_REANALYZE, notes)

        assert result["ok"], result
        assert decision_from_json(client.writes[2]["analysis_data"]).note == "still here"


class TestRenderOnlyKeepsWorking:
    def test_render_only_preserves_note_and_leaves_blob_untouched(self, qapp):
        notes = [_anki_note(1, XGID_A, "cosmetic pass must not touch this")]
        client, card_gen, result = _run(MODE_RENDER_ONLY, notes)

        assert result["ok"], result
        assert card_gen.seen[0].note == "cosmetic pass must not touch this"
        assert client.writes[1]["analysis_data"] is None
