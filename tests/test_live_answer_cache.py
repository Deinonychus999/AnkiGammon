"""Regenerating HedgeHog cards must not ask HedgeHog again, against the real
service and a running Anki.

Opt-in: ANKIGAMMON_LIVE_HEDGEHOG=1 and ANKIGAMMON_LIVE_ANKI=1, with a HedgeHog
account connected in AnkiGammon's Settings. Spends about 15 position analyses
from that account's plan (one cube card, one checker card, small matrices),
then the same again for the control run. The cards are added to the
"AnkiGammon Answer Cache E2E" deck and deleted afterwards.

Regenerate is scoped to the seeded notes, so the user's own cards are never
read or rewritten; anki_collection_guard checks that.
"""

import re
from unittest import mock

import pytest

from ankigammon.analysis.answer_cache import AnswerCache
from ankigammon.models import DecisionType
from ankigammon.utils.hedgehog_client import HedgehogClient
from tests.conftest import anki_call

pytestmark = [pytest.mark.live_hedgehog, pytest.mark.live_anki]

TEST_DECK = "AnkiGammon Answer Cache E2E"
CUBE_7PT = "XGID=-BBB--CC----eA--bc-e-B----:0:0:1:00:2:1:0:7:10"
CHECKER_7PT = "XGID=-b----E-C---eE---c-e----B-:0:0:1:31:0:0:0:7:10"
TABLE = re.compile(r"<table class=\"(?:score-matrix-table|move-score-matrix-table)[^\"]*\">.*?</table>", re.S)


@pytest.fixture
def settings(live_hedgehog, tmp_path, monkeypatch):
    from ankigammon.anki import card_generator
    from ankigammon.settings import Settings

    s = Settings(config_path=tmp_path / "config.json")
    s.analyzer_type = "hedgehog"
    s.hedgehog_preset = "2ply"
    s.set_hedgehog_account("live-test", None)
    s.generate_score_matrix = True
    s.generate_move_score_matrix = True
    s.generate_move_cube_matrix = True
    s.score_matrix_max_size = 3
    s.deck_name = TEST_DECK
    monkeypatch.setattr(card_generator, "get_settings", lambda: s)
    return s


@pytest.fixture
def hedgehog_requests():
    """Every batch actually sent to hedgehog-bg.com, as its OGIDs."""
    sent = []
    real = HedgehogClient.analyze_positions

    def counting(self, ogids, *args, **kwargs):
        sent.append(list(ogids))
        return real(self, ogids, *args, **kwargs)

    with mock.patch.object(HedgehogClient, "analyze_positions", counting):
        yield sent


@pytest.fixture
def exported_notes(qapp, settings, hedgehog_requests, anki_collection_guard, tmp_path):
    """Export one cube and one checker card through the cache, as Send to Anki does."""
    from ankigammon.anki.ankiconnect import AnkiConnect
    from ankigammon.anki.card_generator import CardGenerator
    from ankigammon.utils.hedgehog_analyzer import HedgehogAnalyzer

    analyzer = HedgehogAnalyzer(preset="2ply", preset_label=settings.hedgehog_preset_label())
    generator = CardGenerator(tmp_path / "cards", analyzer=analyzer, answer_cache=AnswerCache.default())
    client = AnkiConnect(deck_name=TEST_DECK)
    client.create_deck(TEST_DECK)
    client.create_model()
    note_ids = []
    for xgid, decision_type in ((CUBE_7PT, DecisionType.CUBE_ACTION), (CHECKER_7PT, DecisionType.CHECKER_PLAY)):
        raw, _ = analyzer.analyze_position(xgid)
        card = generator.generate_card(analyzer.parse_analysis(raw, xgid, decision_type))
        # add_note, not upsert_note: upsert matches by XGID across the whole
        # collection, and test_live_hedgehog left a card at CUBE_7PT.
        note_ids.append(client.add_note(
            front=card["front"], back=card["back"], tags=card["tags"], deck_name=TEST_DECK,
            xgid=card.get("xgid", ""), analysis_data=card.get("analysis_data", ""),
        ))
    try:
        assert not generator.generation_warnings, generator.generation_warnings
        yield note_ids
    finally:
        # Deleted rather than kept: a stray copy of these XGIDs would be what
        # the next upsert-based live test updates instead of its own card.
        anki_call("deleteNotes", notes=note_ids)


def _backs(note_ids):
    return [n["fields"]["Back"]["value"] for n in anki_call("notesInfo", notes=note_ids)]


def _regenerate_scoped(settings, note_ids):
    from ankigammon.anki.ankiconnect import AnkiConnect
    from ankigammon.gui.dialogs.regenerate_dialog import MODE_RENDER_ONLY, RegenerateWorker

    class ScopedAnkiConnect(AnkiConnect):
        def invoke(self, action, **params):
            if action == "findNotes":
                return list(note_ids)
            return super().invoke(action, **params)

    worker = RegenerateWorker(settings, MODE_RENDER_ONLY)
    outcome = {}
    worker.finished.connect(lambda ok, msg: outcome.update(ok=ok, msg=msg))
    with mock.patch(
        "ankigammon.gui.dialogs.regenerate_dialog.AnkiConnect",
        side_effect=lambda **kw: ScopedAnkiConnect(**kw),
    ):
        worker.run()
    return outcome


def test_regenerate_asks_hedgehog_for_nothing(settings, exported_notes, hedgehog_requests):
    before = _backs(exported_notes)
    assert TABLE.search(before[0]), "the cube card has no score matrix"
    assert "move-score-matrix-table" in before[1], "the checker card has no move score matrix"
    hedgehog_requests.clear()

    outcome = _regenerate_scoped(settings, exported_notes)

    assert outcome["ok"], outcome["msg"]
    assert "Successfully re-rendered 2" in outcome["msg"], outcome["msg"]
    assert hedgehog_requests == [], f"regenerate sent {len(hedgehog_requests)} batch(es) to HedgeHog"
    after = _backs(exported_notes)
    for old, new in zip(before, after):
        assert TABLE.findall(new) == TABLE.findall(old)
        assert ("cube-matrix-details" in new) == ("cube-matrix-details" in old)


def test_without_saved_answers_regenerate_does_ask(settings, exported_notes, hedgehog_requests):
    """Control: the counter sees real requests, so the zero above means something."""
    AnswerCache.default().clear()
    hedgehog_requests.clear()

    outcome = _regenerate_scoped(settings, exported_notes)

    assert outcome["ok"], outcome["msg"]
    assert hedgehog_requests, "nothing was sent even with the cache cleared"
