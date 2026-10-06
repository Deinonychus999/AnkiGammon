"""Opening part of a collection, then exporting it into real Anki.

Opt-in: ANKIGAMMON_LIVE_ANKI=1 (see tests/conftest.py). Writes to the user's
collection under TEST_DECK, guarded by anki_collection_guard; the deck is left
behind for inspection and cleared at the start of the next run.

The collection holds one XG match split over two decks. Open Collection with
one deck unticked, then export: only the ticked deck's positions may reach
Anki, still carrying the analysis stored in the XG file.

Exporting upserts by XGID, so positions that are already cards elsewhere in
the collection would be moved. The test imports every played position and
deletes those before saving, which also checks that deleted positions stay
deleted when the collection is opened again.
"""

import json
import shutil
from pathlib import Path
from unittest import mock

import pytest

from tests.conftest import anki_call

pytestmark = pytest.mark.live_anki

TEST_DECK = "AnkiGammon E2E Deck Picker"
KEPT = f"{TEST_DECK}::Kept"
LEFT_OUT = f"{TEST_DECK}::Left Out"
SAMPLE_XG = Path(__file__).parent / "data" / "sample_match.xg"
PER_DECK = 5


def _deck_query(deck: str) -> str:
    return f'"deck:{deck}" -"deck:{deck}::*"'


@pytest.fixture
def fresh_test_deck(live_anki):
    """Clear this test's own notes from a previous run, before the guard snapshots."""
    stale = anki_call("findNotes", query=f'"deck:{TEST_DECK}"')
    if stale:
        anki_call("deleteNotes", notes=stale)


@pytest.fixture
def window(qapp, tmp_path):
    from ankigammon.gui import main_window as mw
    from ankigammon.settings import Settings

    settings = Settings(config_path=tmp_path / "config.json")
    settings.check_for_updates = False
    settings.export_method = "ankiconnect"
    settings.deck_name = TEST_DECK
    settings.generate_score_matrix = False
    settings.generate_move_score_matrix = False
    settings.generate_move_cube_matrix = False
    w = mw.MainWindow(settings)
    yield w
    w.close()


def _wait_for_imports(window):
    from PySide6.QtTest import QTest

    for _ in range(300):
        QTest.qWait(100)
        if not window._import_queue and not window._import_in_progress:
            QTest.qWait(300)
            return
    pytest.fail("collection import did not finish")


def test_partial_open_exports_only_the_ticked_deck(window, fresh_test_deck, anki_collection_guard, tmp_path):
    from PySide6.QtCore import Qt
    from ankigammon.collection import build_collection, save_collection
    from ankigammon.gui import silent_messagebox
    from ankigammon.gui.dialogs.collection_open_dialog import CollectionOpenDialog
    from ankigammon.gui.dialogs.export_dialog import ExportWorker

    match = tmp_path / "matches" / "sample_match.xg"
    match.parent.mkdir()
    shutil.copy(SAMPLE_XG, match)
    elsewhere_ids = anki_call("findNotes", query=f'tag:ankigammon -"deck:{TEST_DECK}*"')
    in_anki = {
        n["fields"]["XGID"]["value"]
        for n in anki_call("notesInfo", notes=elsewhere_ids)
        if "XGID" in n["fields"]
    }
    quiet = mock.patch.multiple(
        silent_messagebox,
        information=lambda *a, **k: None,
        critical=lambda *a, **k: pytest.fail(f"error dialog: {a[1:]}"),
    )

    # A collection with part of the match split over two decks, the rest deleted
    dm = window.deck_manager
    with quiet:
        window._import_file(str(match), {
            "checker_threshold": 0.0, "cube_threshold": 0.0, "selected_player_names": None,
        })
    imported = dm.get_deck_decisions(dm.default_deck_name)
    fresh, seen = [], set()
    for d in imported:
        if d.xgid not in in_anki and d.xgid not in seen:
            seen.add(d.xgid)
            fresh.append(d)
    if len(fresh) < 2 * PER_DECK:
        pytest.skip(f"only {len(fresh)} sample positions are not cards in your collection yet")
    kept, left_out = fresh[:PER_DECK], fresh[PER_DECK:2 * PER_DECK]
    dm.create_deck(KEPT)
    dm.create_deck(LEFT_OUT)
    dm.move_decisions(kept, KEPT)
    dm.move_decisions(left_out, LEFT_OUT)
    for d in dm.get_deck_decisions(dm.default_deck_name):
        dm.remove_decision(dm.default_deck_name, d)
    kept_xgids = sorted(d.xgid for d in kept)
    collection_file = tmp_path / "collection.json"
    save_collection(str(collection_file), build_collection(dm.get_grouped_decisions(), window._import_filters))

    # Open it again with one deck unticked
    def untick_left_out(dialog):
        dialog._items[LEFT_OUT].setCheckState(0, Qt.Unchecked)
        return True

    with quiet, \
         mock.patch("PySide6.QtWidgets.QFileDialog.getOpenFileName", return_value=(str(collection_file), "")), \
         mock.patch.object(CollectionOpenDialog, "exec", untick_left_out):
        window.on_open_collection_clicked()
        _wait_for_imports(window)

    grouped = dm.get_grouped_decisions()
    assert list(grouped) == [KEPT]
    assert sorted(d.xgid for d in grouped[KEPT]) == kept_xgids
    assert window._partial_collection == (str(collection_file), [LEFT_OUT])

    # Export into real Anki
    worker = ExportWorker(grouped, window.settings, "ankiconnect", import_mode="upsert")
    result = {}
    worker.finished.connect(lambda ok, msg: result.update(ok=ok, msg=msg))
    with mock.patch("ankigammon.anki.card_generator.get_settings", return_value=window.settings):
        worker.run()
    assert result.get("ok"), result

    kept_ids = anki_call("findNotes", query=_deck_query(KEPT))
    assert anki_call("findNotes", query=f'"deck:{LEFT_OUT}"') == [], "an unticked deck reached Anki"
    notes = anki_call("notesInfo", notes=kept_ids)
    assert sorted(n["fields"]["XGID"]["value"] for n in notes) == kept_xgids

    stored = [json.loads(n["fields"]["AnalysisData"]["value"])["decision"] for n in notes]
    levels = {m.get("analysis_level") for d in stored for m in d["candidate_moves"]}
    assert levels - {None}, "the XG file's analysis levels did not reach Anki"
    assert {d["source_file"] for d in stored} == {str(match)}
