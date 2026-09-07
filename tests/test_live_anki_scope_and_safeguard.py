"""The missing-analysis scope and the keep-the-card safeguard, against real Anki.

Opt-in: ANKIGAMMON_LIVE_ANKI=1 (see tests/conftest.py). Writes to the user's
collection, scoped to a throwaway deck and guarded by anki_collection_guard.

Two cube cards are seeded through the real pipeline, one with its score
matrix and one deliberately without. The scope must regenerate only the
second. Then a matrix failure is forced on the first and the safeguard must
leave that card unwritten. Writes are recorded at the AnkiConnect boundary,
which is the only way to prove a card was *not* touched.
"""

from unittest import mock

import pytest

from tests.conftest import GNUBG_EXE, anki_call

pytestmark = pytest.mark.live_anki

TEST_DECK = "AnkiGammon E2E Temp"
CUBE_XGID_A = "XGID=-b----E-C--AeD---bAdb---A-:0:0:1:00:0:0:3:0:10"
CUBE_XGID_B = "XGID=-b----E-C---eE---c-e----B-:0:0:1:00:0:0:3:0:10"
TABLE = "score-matrix-table"


@pytest.fixture
def matrix_settings(tmp_path):
    if GNUBG_EXE is None:
        pytest.skip("needs a GnuBG binary to build a matrix")
    from ankigammon.settings import Settings

    s = Settings(config_path=tmp_path / "config.json")
    s.analyzer_type = "gnubg"
    s.gnubg_path = GNUBG_EXE
    s.gnubg_analysis_ply = 0
    s.generate_score_matrix = True
    s.score_matrix_max_size = 2  # a handful of cells; seconds at ply 0
    s.deck_name = TEST_DECK
    return s


def _analyzed(xgid, settings):
    from ankigammon.gui.dialogs.export_dialog import AnalysisWorker
    from ankigammon.gui.dialogs.input_dialog import InputDialog
    from ankigammon.gui.format_detector import InputFormat

    decisions = InputDialog(settings)._parse_input(xgid, InputFormat.POSITION_IDS)
    worker = AnalysisWorker(decisions, settings)
    out = {}
    worker.finished.connect(lambda ok, msg, decs: out.update(ok=ok, msg=msg, decs=decs))
    worker.run()
    assert out["ok"], out["msg"]
    return out["decs"][0]


@pytest.fixture
def seeded(qapp, matrix_settings, anki_collection_guard, tmp_path):
    """Card A with its table, card B without. Returns {A: id, B: id}."""
    from ankigammon.anki.ankiconnect import AnkiConnect
    from ankigammon.anki.card_generator import CardGenerator

    client = AnkiConnect(deck_name=TEST_DECK)
    client.create_deck(TEST_DECK)
    client.create_model()
    ids = {}
    try:
        for key, xgid, with_table in (("A", CUBE_XGID_A, True), ("B", CUBE_XGID_B, False)):
            matrix_settings.generate_score_matrix = with_table
            decision = _analyzed(xgid, matrix_settings)
            with mock.patch("ankigammon.anki.card_generator.get_settings",
                            return_value=matrix_settings):
                card = CardGenerator(output_dir=tmp_path / "cards").generate_card(decision)
            assert (TABLE in card["back"]) is with_table, f"seed {key} did not come out as intended"
            ids[key] = client.add_note(
                front=card["front"], back=card["back"], tags=card["tags"],
                deck_name=TEST_DECK, xgid=card.get("xgid", ""),
                analysis_data=card.get("analysis_data", ""),
            )
        matrix_settings.generate_score_matrix = True
        yield ids
    finally:
        try:
            if ids:
                anki_call("deleteNotes", notes=list(ids.values()))
        finally:
            anki_call("deleteDecks", decks=[TEST_DECK], cardsToo=True)


def _regenerate(settings, note_ids, mode, only_missing=False):
    """Real worker, real AnkiConnect; findNotes scoped, writes recorded."""
    from ankigammon.anki.ankiconnect import AnkiConnect
    from ankigammon.gui.dialogs.regenerate_dialog import RegenerateWorker

    written = set()

    class ScopedAnkiConnect(AnkiConnect):
        def invoke(self, action, **params):
            if action == "findNotes":
                return list(note_ids)
            return super().invoke(action, **params)

        def update_note_fields(self, note_id, *a, **kw):
            written.add(note_id)
            return super().update_note_fields(note_id, *a, **kw)

    worker = RegenerateWorker(settings, mode, only_missing=only_missing)
    outcome = {}
    worker.finished.connect(lambda ok, msg: outcome.update(ok=ok, msg=msg))
    with mock.patch("ankigammon.gui.dialogs.regenerate_dialog.AnkiConnect",
                    side_effect=lambda **kw: ScopedAnkiConnect(**kw)), \
         mock.patch("ankigammon.anki.card_generator.get_settings", return_value=settings):
        worker.run()
    return outcome, written


def _back(note_id):
    return anki_call("notesInfo", notes=[note_id])[0]["fields"]["Back"]["value"]


class TestScopeAgainstRealAnki:
    def test_only_the_card_without_a_table_is_regenerated(self, matrix_settings, seeded):
        from ankigammon.gui.dialogs.regenerate_dialog import MODE_RENDER_ONLY

        outcome, written = _regenerate(
            matrix_settings, seeded.values(), MODE_RENDER_ONLY, only_missing=True
        )

        assert outcome["ok"], outcome["msg"]
        assert written == {seeded["B"]}, "the card that already had its table was rewritten"
        assert TABLE in _back(seeded["B"]), "the missing table was not built"

    def test_nothing_to_do_when_every_card_has_its_table(self, matrix_settings, seeded):
        from ankigammon.gui.dialogs.regenerate_dialog import MODE_RENDER_ONLY

        _regenerate(matrix_settings, seeded.values(), MODE_RENDER_ONLY, only_missing=True)
        outcome, written = _regenerate(
            matrix_settings, seeded.values(), MODE_RENDER_ONLY, only_missing=True
        )

        assert outcome["ok"]
        assert "No cards are missing" in outcome["msg"]
        assert written == set()


class TestSafeguardAgainstRealAnki:
    def test_a_card_whose_table_fails_to_rebuild_is_not_written(self, matrix_settings, seeded):
        from ankigammon.gui.dialogs.regenerate_dialog import MODE_REANALYZE

        before = _back(seeded["A"])
        with mock.patch("ankigammon.analysis.score_matrix.generate_score_matrix",
                        side_effect=RuntimeError("engine died mid-matrix")):
            outcome, written = _regenerate(matrix_settings, [seeded["A"]], MODE_REANALYZE)

        assert outcome["ok"], outcome["msg"]
        assert seeded["A"] not in written, "the card's table was replaced with nothing"
        assert "Kept 1 card" in outcome["msg"]
        assert _back(seeded["A"]) == before

    def test_the_same_failure_on_a_card_without_a_table_still_writes(self, matrix_settings, seeded):
        """Nothing to protect, so the user gets the fresh render plus the warning."""
        from ankigammon.gui.dialogs.regenerate_dialog import MODE_REANALYZE

        with mock.patch("ankigammon.analysis.score_matrix.generate_score_matrix",
                        side_effect=RuntimeError("engine died mid-matrix")):
            outcome, written = _regenerate(matrix_settings, [seeded["B"]], MODE_REANALYZE)

        assert outcome["ok"], outcome["msg"]
        assert written == {seeded["B"]}
        assert "without optional analysis" in outcome["msg"]
