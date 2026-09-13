"""The unlimited reference on match cube cards, through real GnuBG into real Anki.

Opt-in: ANKIGAMMON_LIVE_ANKI=1 (see tests/conftest.py). Writes to the user's
collection, scoped to a throwaway deck and guarded by anki_collection_guard.

Card A is seeded with its unlimited line. Card B is seeded while the unlimited
analysis fails, so it carries the failure marker instead. The
missing-analysis scope must pick B alone and build its line, and an unlimited
failure forced on A during a regenerate must leave A unwritten.
"""

from contextlib import nullcontext
from unittest import mock

import pytest

import ankigammon.analysis.score_matrix as score_matrix
from ankigammon.anki.optional_analysis import (
    UNLIMITED_REFERENCE_FAILED_MARKER,
    UNLIMITED_REFERENCE_MARKER,
)
from tests.conftest import GNUBG_EXE, anki_call
from tests.test_live_anki_scope_and_safeguard import _analyzed, _back, _regenerate

pytestmark = pytest.mark.live_anki

TEST_DECK = "AnkiGammon E2E Unlimited Temp"
MATCH_XGID_A = "XGID=-b----E-C--AeD---bAdb---A-:0:0:1:00:0:0:0:3:10"
MATCH_XGID_B = "XGID=-b----E-C---eE---c-e----B-:0:0:1:00:0:0:0:3:10"

_real_parse_cell = score_matrix._parse_cell


def _fail_unlimited_only(analyzer, output, player_away, opponent_away, label):
    if label.startswith("unlimited game"):
        raise ValueError("forced unlimited failure")
    return _real_parse_cell(analyzer, output, player_away, opponent_away, label)


def _unlimited_failing():
    return mock.patch.object(score_matrix, "_parse_cell", side_effect=_fail_unlimited_only)


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
    s.score_matrix_max_size = 2  # one grid cell plus the unlimited line
    s.deck_name = TEST_DECK
    return s


@pytest.fixture
def seeded(qapp, matrix_settings, anki_collection_guard, tmp_path):
    """Card A with its unlimited line, card B with the failure marker. Returns {A: id, B: id}."""
    from ankigammon.anki.ankiconnect import AnkiConnect
    from ankigammon.anki.card_generator import CardGenerator

    client = AnkiConnect(deck_name=TEST_DECK)
    client.create_deck(TEST_DECK)
    client.create_model()
    ids = {}
    try:
        for key, xgid, unlimited_fails in (("A", MATCH_XGID_A, False), ("B", MATCH_XGID_B, True)):
            decision = _analyzed(xgid, matrix_settings)
            with mock.patch("ankigammon.anki.card_generator.get_settings",
                            return_value=matrix_settings), \
                 (_unlimited_failing() if unlimited_fails else nullcontext()):
                card = CardGenerator(output_dir=tmp_path / "cards").generate_card(decision)
            assert (UNLIMITED_REFERENCE_MARKER in card["back"]) is not unlimited_fails, (
                f"seed {key} did not come out as intended"
            )
            ids[key] = client.add_note(
                front=card["front"], back=card["back"], tags=card["tags"],
                deck_name=TEST_DECK, xgid=card.get("xgid", ""),
                analysis_data=card.get("analysis_data", ""),
            )
        yield ids
    finally:
        try:
            if ids:
                anki_call("deleteNotes", notes=list(ids.values()))
        finally:
            anki_call("deleteDecks", decks=[TEST_DECK], cardsToo=True)


class TestUnlimitedReferenceInRealAnki:
    def test_the_unlimited_line_is_stored_on_the_card(self, seeded):
        back = _back(seeded["A"])

        assert UNLIMITED_REFERENCE_MARKER in back
        assert "unlimited-jacoby-toggle" in back
        assert "showing-jacoby" in back, "the switch was stored without its script"

    def test_the_failure_marker_survives_storage(self, seeded):
        """Anki must keep the HTML comment, or the scope below has nothing to find."""
        assert UNLIMITED_REFERENCE_FAILED_MARKER in _back(seeded["B"])

    def test_only_the_card_whose_unlimited_line_failed_is_regenerated(self, matrix_settings, seeded):
        from ankigammon.gui.dialogs.regenerate_dialog import MODE_RENDER_ONLY

        outcome, written = _regenerate(
            matrix_settings, seeded.values(), MODE_RENDER_ONLY, only_missing=True
        )

        assert outcome["ok"], outcome["msg"]
        assert written == {seeded["B"]}, "a card that already had its unlimited line was rewritten"
        back = _back(seeded["B"])
        assert UNLIMITED_REFERENCE_MARKER in back, "the missing unlimited line was not built"
        assert UNLIMITED_REFERENCE_FAILED_MARKER not in back

    def test_a_card_whose_unlimited_line_fails_to_rebuild_is_not_written(self, matrix_settings, seeded):
        from ankigammon.gui.dialogs.regenerate_dialog import MODE_RENDER_ONLY

        before = _back(seeded["A"])
        with _unlimited_failing():
            outcome, written = _regenerate(matrix_settings, [seeded["A"]], MODE_RENDER_ONLY)

        assert outcome["ok"], outcome["msg"]
        assert seeded["A"] not in written, "the card's unlimited line was replaced with nothing"
        assert "Kept 1 card" in outcome["msg"]
        assert _back(seeded["A"]) == before
