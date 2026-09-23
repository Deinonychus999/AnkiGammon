"""Collection files: a snapshot of the loaded positions that re-imports source
files (keeping their newest analysis) and restores every position's deck."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ankigammon.anki.decision_serialize import decision_to_json
from ankigammon.collection import (
    FORMAT_NAME,
    FORMAT_VERSION,
    Collection,
    CollectionSource,
    build_collection,
    file_key,
    load_collection,
    place_decisions,
    save_collection,
)
from ankigammon.gui.deck_manager import DeckManager
from ankigammon.models import Decision, DecisionType, Move, Player, Position
from ankigammon.settings import Settings

SAMPLE_XG = Path(__file__).parent / "data" / "sample_match.xg"


def _decision(xgid, source_file=None):
    return Decision(
        position=Position(),
        on_roll=Player.O,
        dice=(3, 1),
        xgid=xgid,
        decision_type=DecisionType.CHECKER_PLAY,
        candidate_moves=[Move(notation="8/5 6/5", equity=0.1, analysis_level="Rollout")],
        source_file=source_file,
    )


def _write(path: Path, payload) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class TestBuildCollection:
    def test_file_positions_become_one_entry_placed_by_deck(self):
        a = "/m/a.xg"
        filters = {file_key(a): CollectionSource(a, 0.05, 0.1, ["Frank"])}
        grouped = {
            "D1": [_decision("X1", a), _decision("X2", a)],
            "D2": [_decision("X3", a)],
        }
        collection = build_collection(grouped, filters)
        assert collection.files == [
            CollectionSource(a, 0.05, 0.1, ["Frank"], {"D1": ["X1", "X2"], "D2": ["X3"]})
        ]
        assert collection.positions == {}
        assert filters[file_key(a)].placement == {}, "the import record must not be mutated"

    def test_positions_without_an_imported_file_are_kept_whole(self):
        pasted = _decision("P1")
        unknown_file = _decision("P2", "/m/never-imported.xg")
        no_xgid = _decision(None, "/m/a.xg")
        collection = build_collection(
            {"D": [pasted, unknown_file, no_xgid]},
            {file_key("/m/a.xg"): CollectionSource("/m/a.xg")},
        )
        assert collection.files == []
        assert collection.positions == {"D": [pasted, unknown_file, no_xgid]}
        assert collection.position_count == 3
        assert collection.deck_names() == ["D"]


class TestPlaceDecisions:
    def test_positions_return_to_saved_decks_and_extras_are_left_out(self):
        decisions = [_decision("X1"), _decision("X2"), _decision("X3"), _decision("NEW")]
        placed, unplaced, missing = place_decisions(
            decisions, {"D1": ["X1", "X3"], "D2": ["X2", "GONE"]}
        )
        assert {d: [x.xgid for x in v] for d, v in placed.items()} == {"D1": ["X1", "X3"], "D2": ["X2"]}
        assert (unplaced, missing) == (1, 1)

    def test_duplicate_xgids_are_matched_one_to_one(self):
        placed, unplaced, missing = place_decisions(
            [_decision("X"), _decision("X"), _decision("X")], {"D1": ["X"], "D2": ["X"]}
        )
        assert {d: len(v) for d, v in placed.items()} == {"D1": 1, "D2": 1}
        assert (unplaced, missing) == (1, 0)


class TestCollectionFile:
    def test_roundtrip(self, tmp_path):
        pasted = _decision("P1")
        collection = Collection(
            files=[CollectionSource(str(tmp_path / "m" / "a.xg"), 0.05, None, ["Frank"], {"D1": ["X1"]})],
            positions={"D2": [pasted]},
        )
        target = tmp_path / "c.json"
        save_collection(str(target), collection)

        loaded = load_collection(str(target))
        assert loaded.files == collection.files
        assert [decision_to_json(d) for d in loaded.positions["D2"]] == [decision_to_json(pasted)]
        assert loaded.positions["D2"][0].candidate_moves[0].analysis_level == "Rollout"

    def test_files_below_the_collection_are_stored_relative(self, tmp_path):
        target = tmp_path / "c.json"
        save_collection(str(target), Collection([CollectionSource(str(tmp_path / "m" / "a.xg"))]))
        assert json.loads(target.read_text())["files"][0]["path"] == "m/a.xg"

    def test_files_elsewhere_stay_absolute(self, tmp_path):
        target = tmp_path / "sub" / "c.json"
        target.parent.mkdir()
        outside = str(tmp_path / "other" / "a.xg")
        save_collection(str(target), Collection([CollectionSource(outside)]))
        assert Path(json.loads(target.read_text())["files"][0]["path"]).is_absolute()
        assert load_collection(str(target)).files[0].path == outside

    def test_moving_collection_with_its_files_keeps_working(self, tmp_path):
        first = tmp_path / "one"
        first.mkdir()
        save_collection(str(first / "c.json"), Collection([CollectionSource(str(first / "a.xg"))]))
        first.rename(tmp_path / "two")
        assert load_collection(str(tmp_path / "two" / "c.json")).files[0].path == str(tmp_path / "two" / "a.xg")

    @pytest.mark.parametrize("payload, message", [
        ({"files": []}, "Not an AnkiGammon collection"),
        ({"format": FORMAT_NAME, "version": FORMAT_VERSION + 1}, "newer"),
        ({"format": FORMAT_NAME, "version": 1, "files": {}}, "must be a list"),
        ({"format": FORMAT_NAME, "version": 1, "files": [{"decks": {}}]}, "path"),
        ({"format": FORMAT_NAME, "version": 1, "files": [{"path": "a"}]}, "XGIDs"),
        ({"format": FORMAT_NAME, "version": 1, "files": [{"path": "a", "decks": {}, "players": "Me"}]}, "players"),
        ({"format": FORMAT_NAME, "version": 1, "files": [{"path": "a", "decks": {}, "cube_threshold": "x"}]}, "number"),
        ({"format": FORMAT_NAME, "version": 1, "positions": {"D": [{"version": 1, "decision": {}}]}}, "Malformed"),
    ])
    def test_invalid_files_are_rejected(self, tmp_path, payload, message):
        with pytest.raises(ValueError, match=message):
            load_collection(str(_write(tmp_path / "c.json", payload)))

    def test_not_json_is_rejected(self, tmp_path):
        bad = tmp_path / "c.json"
        bad.write_text("{nope", encoding="utf-8")
        with pytest.raises(ValueError, match="JSON"):
            load_collection(str(bad))


class _ImportHarness:
    """MainWindow's import path without building the window (and its web view)."""

    from ankigammon.gui.main_window import MainWindow as _MW

    _import_file = _MW._import_file
    _filter_from_options = _MW._filter_from_options
    _source_for = staticmethod(_MW._source_for)
    _resolve_player_flags = staticmethod(_MW._resolve_player_flags)
    _filter_decisions_by_import_options = _MW._filter_decisions_by_import_options
    _ensure_played_move_in_candidates = _MW._ensure_played_move_in_candidates

    def __init__(self, settings: Settings):
        self.settings = settings
        self.deck_manager = DeckManager("AnkiGammon")
        self.deck_tree = MagicMock()
        self.deck_tree.get_active_deck_name.return_value = "AnkiGammon"
        self.deck_tree.get_selected_decision.return_value = object()
        self.btn_export = MagicMock()
        self._batch_import_options = None
        self._import_target_deck = None
        self._in_batch_import = True
        self._batch_import_results = []
        self._batch_skipped_files = []
        self._batch_notes = []
        self._import_filters = {}

    def open_collection(self, collection: Collection):
        """The part of on_open_collection_clicked after the dialogs."""
        self.deck_manager.merge_deck_names(collection.deck_names())
        for deck, decisions in collection.positions.items():
            self.deck_manager.add_decisions(decisions, deck)
        for s in collection.files:
            self._import_file(s.path, _options(s.checker_threshold, s.cube_threshold, s.players), s.placement)


@pytest.fixture
def harness(tmp_path):
    settings = Settings(config_path=tmp_path / "config.json")
    settings.max_moves = 5
    return _ImportHarness(settings)


def _options(checker, cube, players, reason="not listed"):
    return {
        "checker_threshold": checker,
        "cube_threshold": cube,
        "selected_player_names": players,
        "unselected_reason": reason,
    }


def _xgids_by_deck(dm: DeckManager):
    return {name: sorted(d.xgid for d in dm.get_deck_decisions(name)) for name in dm.get_deck_names()}


class TestImportAndReopen:
    def test_import_records_its_filter_and_source_file(self, harness):
        harness._import_file(str(SAMPLE_XG), _options(0.08, 0.08, ["Player Two"]))

        decisions = harness.deck_manager.get_deck_decisions("AnkiGammon")
        assert decisions
        # Player Two is the file's player 2, i.e. Player.X
        assert all(
            d.on_roll == Player.X for d in decisions if d.decision_type == DecisionType.CHECKER_PLAY
        )
        assert {d.source_file for d in decisions} == {os.path.abspath(SAMPLE_XG)}
        assert harness._import_filters == {
            file_key(str(SAMPLE_XG)): CollectionSource(os.path.abspath(SAMPLE_XG), 0.08, 0.08, ["Player Two"])
        }

    def test_both_players_when_players_is_omitted(self, harness):
        harness._import_file(str(SAMPLE_XG), _options(0.08, 0.08, None))
        on_roll = {d.on_roll for d in harness.deck_manager.get_deck_decisions("AnkiGammon")}
        assert on_roll == {Player.X, Player.O}

    def test_unknown_player_is_skipped_with_reason(self, harness):
        harness._import_file(str(SAMPLE_XG), _options(0.08, 0.08, ["Nobody"]))
        assert harness.deck_manager.is_empty
        assert harness._batch_skipped_files == [(str(SAMPLE_XG), "not listed")]

    def test_reopening_restores_moves_deletions_and_pasted_positions(self, harness, tmp_path):
        dm = harness.deck_manager
        harness._import_file(str(SAMPLE_XG), _options(0.05, 0.1, ["Player One"]))
        imported = dm.get_deck_decisions("AnkiGammon")
        assert len(imported) >= 3

        dm.create_deck("AnkiGammon::Moved")
        dm.move_decisions(imported[:2], "AnkiGammon::Moved")
        dm.remove_decision("AnkiGammon", imported[2])
        dm.add_decisions([_decision("XGID=pasted")], "AnkiGammon::Moved")
        before = _xgids_by_deck(dm)

        target = tmp_path / "c.json"
        save_collection(str(target), build_collection(dm.get_grouped_decisions(), harness._import_filters))

        reopened = _ImportHarness(harness.settings)
        reopened.open_collection(load_collection(str(target)))

        assert _xgids_by_deck(reopened.deck_manager) == before
        assert reopened._batch_notes == []
        assert {d.source_file for d in reopened.deck_manager.get_deck_decisions("AnkiGammon")} == {
            os.path.abspath(SAMPLE_XG)
        }

    def test_saved_positions_missing_from_the_file_are_reported(self, harness):
        harness.open_collection(Collection([CollectionSource(
            os.path.abspath(SAMPLE_XG), 0.05, 0.1, ["Player One"], {"AnkiGammon": ["XGID=not-in-file"]}
        )]))
        assert harness.deck_manager.is_empty
        assert harness._batch_notes == [
            "sample_match.xg: 1 saved position(s) no longer found (the file or its analysis may have changed)"
        ]
