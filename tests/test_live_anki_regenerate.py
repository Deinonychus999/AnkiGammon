"""GitHub issue #58 against a running Anki: regenerate must not eat comments.

Opt-in: ANKIGAMMON_LIVE_ANKI=1 (see tests/conftest.py). This one WRITES to
the user's real collection.

Safety, in layers:
  * the card is seeded into a throwaway deck and deleted afterwards;
  * findNotes is scoped to that one note id, so RegenerateWorker's
    `tag:ankigammon` query can never reach the user's own cards;
  * the anki_collection_guard fixture fails the test if any pre-existing
    AnkiGammon note's mod time changes.

Reproduced here before the fix: regenerate reported "Successfully
regenerated 1 card(s)" while the comment was gone from both the rendered
Back field and the AnalysisData blob - which is why the report looked like
a success to everyone except the user who lost the note.
"""

import json

import pytest

from tests.conftest import GNUBG_EXE, anki_call

pytestmark = pytest.mark.live_anki

TEST_DECK = "AnkiGammon E2E Temp"
XGID = "XGID=-b----E-C--AeD---bAdb---A-:0:0:1:52:0:0:3:0:10"
COMMENT = "Race lead = 4 pips, so run."


@pytest.fixture
def gnubg_settings(tmp_path):
    """GnuBG keeps the live Anki round-trip to a few seconds."""
    if GNUBG_EXE is None:
        pytest.skip("needs a GnuBG binary to re-analyze")
    from ankigammon.settings import Settings

    settings = Settings(config_path=tmp_path / "config.json")
    settings.analyzer_type = "gnubg"
    settings.gnubg_path = GNUBG_EXE
    settings.gnubg_analysis_ply = 0
    settings.deck_name = TEST_DECK
    return settings


@pytest.fixture
def seeded_note(qapp, gnubg_settings, anki_collection_guard, tmp_path):
    """Put one real, commented AnkiGammon card into a throwaway deck."""
    from ankigammon.anki.ankiconnect import AnkiConnect
    from ankigammon.anki.card_generator import CardGenerator
    from ankigammon.gui.dialogs.export_dialog import AnalysisWorker
    from ankigammon.gui.dialogs.input_dialog import InputDialog
    from ankigammon.gui.format_detector import InputFormat

    dialog = InputDialog(gnubg_settings)
    decisions = dialog._parse_input(f"{XGID}\n{COMMENT}", InputFormat.POSITION_IDS)

    worker = AnalysisWorker(decisions, gnubg_settings)
    captured = {}
    worker.finished.connect(
        lambda ok, msg, decs: captured.update(ok=ok, msg=msg, decisions=decs)
    )
    worker.run()
    assert captured["ok"], captured["msg"]

    card = CardGenerator(output_dir=tmp_path / "cards").generate_card(
        captured["decisions"][0]
    )

    client = AnkiConnect(deck_name=TEST_DECK)
    client.create_deck(TEST_DECK)
    client.create_model()
    note_id = client.add_note(
        front=card["front"], back=card["back"], tags=card["tags"],
        deck_name=TEST_DECK, xgid=card.get("xgid", ""),
        analysis_data=card.get("analysis_data", ""),
    )
    try:
        yield note_id
    finally:
        try:
            anki_call("deleteNotes", notes=[note_id])
        finally:
            anki_call("deleteDecks", decks=[TEST_DECK], cardsToo=True)


def _regenerate_scoped(settings, note_id):
    """Run the real worker against real Anki, scoped to one note."""
    from unittest import mock

    from ankigammon.anki.ankiconnect import AnkiConnect
    from ankigammon.gui.dialogs.regenerate_dialog import (
        MODE_REANALYZE,
        RegenerateWorker,
    )

    class ScopedAnkiConnect(AnkiConnect):
        """Real client, except findNotes only ever sees the seeded note."""

        def invoke(self, action, **params):
            if action == "findNotes":
                return [note_id]
            return super().invoke(action, **params)

    worker = RegenerateWorker(settings, MODE_REANALYZE)
    outcome = {}
    worker.finished.connect(lambda ok, msg: outcome.update(ok=ok, msg=msg))
    with mock.patch(
        "ankigammon.gui.dialogs.regenerate_dialog.AnkiConnect",
        side_effect=lambda **kw: ScopedAnkiConnect(**kw),
    ):
        worker.run()
    return outcome


class TestRegenerateAgainstRealAnki:
    def test_seeded_card_starts_with_the_comment(self, seeded_note):
        note = anki_call("notesInfo", notes=[seeded_note])[0]

        assert COMMENT in note["fields"]["Back"]["value"]

    def test_comment_survives_regenerate_in_anki(self, gnubg_settings, seeded_note):
        before = anki_call("notesInfo", notes=[seeded_note])[0]

        outcome = _regenerate_scoped(gnubg_settings, seeded_note)
        assert outcome["ok"], outcome["msg"]

        after = anki_call("notesInfo", notes=[seeded_note])[0]
        assert COMMENT in after["fields"]["Back"]["value"], "regenerate ate the comment"
        assert after["mod"] >= before["mod"], "the note was never rewritten"

    def test_comment_survives_in_the_stored_blob(self, gnubg_settings, seeded_note):
        from ankigammon.anki.decision_serialize import decision_from_json

        outcome = _regenerate_scoped(gnubg_settings, seeded_note)
        assert outcome["ok"], outcome["msg"]

        blob = anki_call("notesInfo", notes=[seeded_note])[0]["fields"]["AnalysisData"]["value"]
        assert blob, "regenerate must still write a refreshed blob"
        assert decision_from_json(blob).note == COMMENT

    def test_the_card_really_was_reanalyzed(self, gnubg_settings, seeded_note):
        """Preserving the comment must not mean skipping the analysis."""
        outcome = _regenerate_scoped(gnubg_settings, seeded_note)
        assert outcome["ok"], outcome["msg"]

        note = anki_call("notesInfo", notes=[seeded_note])[0]
        blob = json.loads(note["fields"]["AnalysisData"]["value"])
        assert blob["decision"]["candidate_moves"]
        assert "Regenerated with" in (blob["decision"]["source_description"] or "")

    def test_pre_fix_behaviour_would_have_lost_the_comment(
        self, gnubg_settings, seeded_note, monkeypatch
    ):
        """Pin the bug itself, so a regression cannot pass this file silently."""
        from ankigammon.gui.dialogs.regenerate_dialog import RegenerateWorker

        monkeypatch.setattr(
            RegenerateWorker, "_restore_user_metadata",
            lambda self, decision, blob, note_id: None,
        )

        outcome = _regenerate_scoped(gnubg_settings, seeded_note)
        assert outcome["ok"], outcome["msg"]

        note = anki_call("notesInfo", notes=[seeded_note])[0]
        assert COMMENT not in note["fields"]["Back"]["value"]
