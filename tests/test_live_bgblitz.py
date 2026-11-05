"""BGBlitz files through the real window, real GnuBG and real Anki.

The window imports run with the normal suite. Analyzing a match saved without
analysis with real GnuBG is opt-in (ANKIGAMMON_LIVE_GNUBG=1), and so is the
export: ANKIGAMMON_LIVE_ANKI=1 (see tests/conftest.py). It writes to the user's
collection under TEST_DECK, guarded by anki_collection_guard; the deck is left
behind for inspection and cleared at the start of the next run.

The .bgf positions keep BGBlitz's analysis all the way into Anki; the .pos
position has none, so the export has GnuBG analyze it.
"""

import json
from pathlib import Path
from unittest import mock

import pytest

from tests.conftest import GNUBG_EXE, _enabled, anki_call

DATA = Path(__file__).parent / "data" / "bgblitz"
MATCH = DATA / "match.bgf"
POSITION = DATA / "positions" / "1.pos"
POSITION_XGID_BOARD = "ab-Aa-DAC--AbE----bdc-----"
TEST_DECK = "AnkiGammon E2E BGBlitz"


@pytest.fixture
def window(qapp, tmp_path):
    from ankigammon.gui import main_window as mw
    from ankigammon.settings import Settings

    settings = Settings(config_path=tmp_path / "config.json")
    settings.check_for_updates = False
    settings.export_method = "ankiconnect"
    settings.deck_name = TEST_DECK
    settings.analyzer_type = "gnubg"
    settings.gnubg_path = GNUBG_EXE
    settings.gnubg_analysis_ply = 0
    settings.generate_score_matrix = False
    settings.generate_move_score_matrix = False
    settings.generate_move_cube_matrix = False
    w = mw.MainWindow(settings)
    yield w
    w.close()


def _import(window, path, options=None):
    from ankigammon.gui import silent_messagebox

    quiet = mock.patch.multiple(
        silent_messagebox,
        information=lambda *a, **k: None,
        warning=lambda *a, **k: pytest.fail(f"warning dialog: {a[1:]}"),
        critical=lambda *a, **k: pytest.fail(f"error dialog: {a[1:]}"),
    )
    with quiet:
        window._import_file(str(path), options)
    dm = window.deck_manager
    return dm.get_deck_decisions(dm.default_deck_name)


def test_window_imports_both_formats(window):
    from ankigammon.models import DecisionType

    imported = _import(window, MATCH, {
        "checker_threshold": 0.08, "cube_threshold": 0.08, "selected_player_names": None,
    })
    assert sorted((d.game_number, d.move_number, d.decision_type.name) for d in imported) == [
        (1, 5, "CHECKER_PLAY"), (2, 8, "CHECKER_PLAY"), (2, 10, "CUBE_ACTION"), (2, 13, "CUBE_ACTION"),
    ]
    assert all(d.source_file == str(MATCH) for d in imported)

    imported = _import(window, POSITION)
    position = imported[-1]
    assert len(imported) == 5
    assert position.candidate_moves == []
    assert position.decision_type == DecisionType.CHECKER_PLAY
    assert POSITION_XGID_BOARD in position.xgid


@pytest.fixture
def unanalyzed_match(tmp_path):
    """The sample match as BGBlitz saves one it has not analyzed: only each
    game's opening record keeps its placeholder evaluation."""
    from ankigammon.parsers.bgf_parser import read_bgf

    match = read_bgf(MATCH.read_bytes())
    for game in match["games"]:
        for index, record in enumerate(game["moves"]):
            record.update(dancingEquity=None, moveAnalysis=[], pr=None, luck=None)
            if index == 0 and record.get("equity"):
                record["equity"]["cubeDecision"] = None
            else:
                record["equity"] = None
    path = tmp_path / "unanalyzed.bgf"
    header = b'{"format":"BGF","version":"1.0","compress":false,"useSmile":false}\n'
    path.write_bytes(header + json.dumps(match).encode())
    return path


def _answer(button):
    from ankigammon.gui import silent_messagebox

    return mock.patch.object(silent_messagebox, "question", return_value=button)


def test_unanalyzed_match_goes_to_the_engine_as_a_mat_file(window, unanalyzed_match):
    from PySide6.QtWidgets import QMessageBox
    from ankigammon.collection import CollectionSource
    from ankigammon.parsers.hedgehog_parser import decision_from_xgid
    from ankigammon.models import DecisionType

    seen = {}

    def analyze(path, options):
        seen.update(path=Path(path), text=Path(path).read_text(encoding="utf-8"))
        analyzed = decision_from_xgid("XGID=-b----E-C---eE---c-e----B-:0:0:1:52:0:0:0:5:8",
                                      DecisionType.CHECKER_PLAY)
        return [analyzed], 40, CollectionSource(path=path)

    with _answer(QMessageBox.StandardButton.Yes), mock.patch.object(window, "_import_match_file", analyze):
        imported = _import(window, unanalyzed_match)

    assert seen["path"].suffix == ".mat"
    assert " 5 point match" in seen["text"] and "20/10 7/2*(2)" in seen["text"]
    assert not seen["path"].exists(), "the temporary .mat file was left behind"
    assert [d.source_file for d in imported] == [str(unanalyzed_match)]


def test_unanalyzed_match_declined(window, unanalyzed_match):
    from PySide6.QtWidgets import QMessageBox

    with _answer(QMessageBox.StandardButton.No), \
         mock.patch.object(window, "_import_match_file", side_effect=AssertionError("analyzed anyway")):
        assert _import(window, unanalyzed_match) == []


def test_unanalyzed_match_without_an_engine_goes_straight_to_the_set_up_offer(window, unanalyzed_match):
    from ankigammon.gui import silent_messagebox

    calls = []
    with mock.patch.object(window.settings, "is_engine_available", return_value=False), \
         mock.patch.object(silent_messagebox, "question", side_effect=AssertionError("asked to analyze")), \
         mock.patch.object(window, "_import_match_file",
                           side_effect=lambda path, options: calls.append(path) or (None, None, None)):
        assert _import(window, unanalyzed_match) == []
    assert len(calls) == 1


def test_declined_match_is_listed_as_skipped_in_a_batch(window, unanalyzed_match):
    from PySide6.QtWidgets import QMessageBox

    window._in_batch_import = True
    window._batch_skipped_files = []
    try:
        with _answer(QMessageBox.StandardButton.No):
            _import(window, unanalyzed_match)
    finally:
        window._in_batch_import = False
    assert [path for path, _ in window._batch_skipped_files] == [str(unanalyzed_match)]


@pytest.mark.skipif(not _enabled("ANKIGAMMON_LIVE_GNUBG") or GNUBG_EXE is None,
                    reason="real GnuBG analysis is opt-in (ANKIGAMMON_LIVE_GNUBG=1)")
def test_unanalyzed_match_analyzed_by_real_gnubg(window, unanalyzed_match):
    """GnuBG finds the same mistakes BGBlitz did in the analyzed copy of the match."""
    from PySide6.QtWidgets import QMessageBox

    with _answer(QMessageBox.StandardButton.Yes):
        imported = _import(window, unanalyzed_match, {
            "checker_threshold": 0.08, "cube_threshold": 0.08, "selected_player_names": None,
        })
    played = {next(m.notation for m in d.candidate_moves if m.was_played) for d in imported}
    assert {"24/20 11/8", "20/10 7/2*(2)"} <= played
    assert all(d.source_file == str(unanalyzed_match) for d in imported)


@pytest.fixture
def fresh_test_deck(live_anki):
    stale = anki_call("findNotes", query=f'"deck:{TEST_DECK}"')
    if stale:
        anki_call("deleteNotes", notes=stale)


@pytest.mark.live_anki
def test_export_reaches_anki_with_bgblitz_and_gnubg_analysis(window, fresh_test_deck, anki_collection_guard):
    from ankigammon.gui.dialogs.export_dialog import AnalysisWorker, ExportWorker

    if GNUBG_EXE is None:
        pytest.skip("needs a GnuBG binary to analyze the .pos position")
    _import(window, MATCH, {
        "checker_threshold": 0.08, "cube_threshold": 0.08, "selected_player_names": None,
    })
    decisions = _import(window, POSITION)
    elsewhere = anki_call("findNotes", query=f'tag:ankigammon -"deck:{TEST_DECK}*"')
    in_anki = {n["fields"]["XGID"]["value"] for n in anki_call("notesInfo", notes=elsewhere)
               if "XGID" in n["fields"]}
    fresh = [d for d in decisions if d.xgid not in in_anki]
    if not any(not d.candidate_moves for d in fresh):
        pytest.skip("the .pos position is already a card in your collection")

    position_xgid = next(d.xgid for d in fresh if not d.candidate_moves)

    # As the Export dialog does: analyze what has no analysis, then export with that engine
    analysis = AnalysisWorker(fresh, window.settings)
    analyzed = {}
    analysis.finished.connect(lambda ok, msg, ds: analyzed.update(ok=ok, msg=msg, decisions=ds))
    analysis.run()
    assert analyzed.get("ok"), analyzed.get("msg")

    worker = ExportWorker({TEST_DECK: analyzed["decisions"]}, window.settings, "ankiconnect",
                          import_mode="upsert", analyzer=analysis.analyzer)
    result = {}
    worker.finished.connect(lambda ok, msg: result.update(ok=ok, msg=msg))
    with mock.patch("ankigammon.anki.card_generator.get_settings", return_value=window.settings):
        worker.run()
    assert result.get("ok"), result

    notes = anki_call("notesInfo", notes=anki_call("findNotes", query=f'"deck:{TEST_DECK}"'))
    stored = {n["fields"]["XGID"]["value"]: json.loads(n["fields"]["AnalysisData"]["value"])["decision"]
              for n in notes}
    assert set(stored) == {d.xgid for d in fresh}
    from_position = stored.pop(position_xgid)
    assert len(from_position["candidate_moves"]) >= 2, "GnuBG did not analyze the .pos position"
    assert from_position["source_description"].endswith("from POS")
    assert all(d["source_description"] == f"BGBlitz file '{MATCH.name}'" for d in stored.values())
    assert all(m.get("analysis_level") == "4-ply" for d in stored.values() for m in d["candidate_moves"]
               if d["decision_type"] == "checker_play")
