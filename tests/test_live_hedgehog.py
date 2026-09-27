"""HedgeHog end to end, against hedgehog-bg.com and (for the last test) Anki.

Opt-in: ANKIGAMMON_LIVE_HEDGEHOG=1, with a HedgeHog account connected in
AnkiGammon's Settings; the Anki test also needs ANKIGAMMON_LIVE_ANKI=1 and
leaves its card in the "AnkiGammon HedgeHog E2E" deck. Every analysis counts
toward the connected account's HedgeHog plan.
"""

from pathlib import Path

import pytest

from ankigammon.import_filter import filter_decisions
from ankigammon.models import DecisionType, Player
from ankigammon.utils.hedgehog_analyzer import HedgehogAnalyzer
from ankigammon.utils.hedgehog_client import HedgehogClient
from tests.conftest import anki_call

pytestmark = pytest.mark.live_hedgehog

MATCH = Path(__file__).parent.parent / "match_files" / "rchoicebug.mat"
CUBE_7PT = "XGID=-BBB--CC----eA--bc-e-B----:0:0:1:00:2:1:0:7:10"
OPENING_X = "XGID=-b----E-C---eE---c-e----B-:0:0:-1:43:0:0:0:7:8"
TEST_DECK = "AnkiGammon HedgeHog E2E"


@pytest.fixture
def analyzer(live_hedgehog):
    return HedgehogAnalyzer(preset="2ply", preset_label="3-ply")


def test_account_answers(live_hedgehog):
    me = HedgehogClient().me()
    assert me["user_id"]
    assert "2ply" in me["presets"]["position"]


def test_positions_from_both_sides(analyzer):
    results = analyzer.analyze_positions_parallel([CUBE_7PT, OPENING_X])
    cube = analyzer.parse_analysis(results[0][0], CUBE_7PT, results[0][1])
    opening = analyzer.parse_analysis(results[1][0], OPENING_X, results[1][1])
    assert cube.decision_type == DecisionType.CUBE_ACTION
    assert {m.notation for m in cube.candidate_moves} >= {"No Double/Take", "Double/Take", "Double/Pass"}
    assert opening.on_roll == Player.X
    # X's 4-3 opening, read in X's own numbering: every candidate moves from X's side
    assert all(m.notation.split()[0].split("/")[0] in {"24", "13", "8", "6"} for m in opening.candidate_moves)


def test_match_file(analyzer):
    decisions = analyzer.analyze_match_file(str(MATCH))
    assert len(decisions) > 100
    assert all(any(m.was_played for m in d.candidate_moves)
               for d in decisions if d.decision_type == DecisionType.CHECKER_PLAY)
    assert filter_decisions(decisions, 0.080, 0.080, True, True, 5)
    assert decisions[0].source_description.startswith("HedgeHog analysis")


def test_card_with_score_matrix_reaches_anki(analyzer, anki_collection_guard, tmp_path, monkeypatch):
    from ankigammon.anki import card_generator
    from ankigammon.anki.ankiconnect import AnkiConnect
    from ankigammon.settings import Settings

    settings = Settings(config_path=tmp_path / "config.json")
    settings.analyzer_type = "hedgehog"
    settings.set_hedgehog_account("live-test", None)
    settings.set("generate_score_matrix", True)
    monkeypatch.setattr(card_generator, "get_settings", lambda: settings)

    raw, decision_type = analyzer.analyze_position(CUBE_7PT)
    decision = analyzer.parse_analysis(raw, CUBE_7PT, decision_type)
    generator = card_generator.CardGenerator(tmp_path / "cards", analyzer=analyzer)
    card = generator.generate_card(decision)
    assert not generator.generation_warnings
    assert "score-matrix" in card["back"]

    client = AnkiConnect(deck_name=TEST_DECK)
    client.create_deck(TEST_DECK)
    client.create_model()
    note_id = client.upsert_note(
        front=card["front"], back=card["back"], tags=card["tags"], deck_name=TEST_DECK,
        xgid=card.get("xgid", ""), analysis_data=card.get("analysis_data", ""),
    )
    # The deck is left in Anki on purpose, to look at the card afterwards.
    back = anki_call("notesInfo", notes=[note_id])[0]["fields"]["Back"]["value"]
    assert "score-matrix" in back
