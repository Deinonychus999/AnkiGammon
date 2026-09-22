"""Collection files: saving which source file went into which deck, and
rebuilding the decks from them with the same import filters."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from ankigammon.collection import (
    FORMAT_NAME,
    FORMAT_VERSION,
    CollectionSource,
    load_collection,
    save_collection,
    sources_from_dict,
    sources_to_dict,
)
from ankigammon.gui.deck_manager import DeckManager
from ankigammon.settings import Settings

SAMPLE_XG = Path(__file__).parent / "data" / "sample_match.xg"


def _write(path: Path, payload) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class TestCollectionFile:
    def test_roundtrip_keeps_decks_files_and_filters(self, tmp_path):
        inside = tmp_path / "matches" / "a.xg"
        sources = {
            "AnkiGammon::Openings": [
                CollectionSource(str(inside), 0.05, 0.1, ["Frank"]),
                CollectionSource(str(tmp_path / "b.xgp")),
            ],
            "AnkiGammon::Cube": [CollectionSource(str(inside), players=None)],
        }
        target = tmp_path / "collection.json"
        save_collection(str(target), sources)

        assert load_collection(str(target)) == {
            deck: [
                CollectionSource(os.path.normpath(s.path), s.checker_threshold, s.cube_threshold, s.players)
                for s in entries
            ]
            for deck, entries in sources.items()
        }

    def test_files_below_the_collection_are_stored_relative(self, tmp_path):
        target = tmp_path / "collection.json"
        save_collection(str(target), {"D": [CollectionSource(str(tmp_path / "matches" / "a.xg"))]})
        assert json.loads(target.read_text())["decks"]["D"][0]["path"] == "matches/a.xg"

    def test_files_elsewhere_stay_absolute(self, tmp_path):
        target = tmp_path / "sub" / "collection.json"
        target.parent.mkdir()
        outside = tmp_path / "other" / "a.xg"
        save_collection(str(target), {"D": [CollectionSource(str(outside))]})
        stored = json.loads(target.read_text())["decks"]["D"][0]["path"]
        assert Path(stored).is_absolute()
        assert load_collection(str(target))["D"][0].path == os.path.normpath(str(outside))

    def test_moving_collection_with_its_files_keeps_working(self, tmp_path):
        first = tmp_path / "one"
        first.mkdir()
        save_collection(str(first / "c.json"), {"D": [CollectionSource(str(first / "a.xg"))]})
        moved = tmp_path / "two"
        first.rename(moved)
        assert load_collection(str(moved / "c.json"))["D"][0].path == str(moved / "a.xg")

    def test_hand_written_bare_paths_are_accepted(self, tmp_path):
        target = _write(tmp_path / "c.json", {
            "format": FORMAT_NAME, "version": 1,
            "decks": {"AnkiGammon::Mine": ["a.xg", {"path": "b.mat", "players": ["Me"]}]},
        })
        loaded = load_collection(str(target))["AnkiGammon::Mine"]
        assert loaded == [
            CollectionSource(str(tmp_path / "a.xg")),
            CollectionSource(str(tmp_path / "b.mat"), players=["Me"]),
        ]

    @pytest.mark.parametrize("payload, message", [
        ({"decks": {}}, "Not an AnkiGammon collection"),
        ({"format": FORMAT_NAME, "version": FORMAT_VERSION + 1, "decks": {}}, "newer"),
        ({"format": FORMAT_NAME, "version": 1, "decks": []}, "must map"),
        ({"format": FORMAT_NAME, "version": 1, "decks": {"D": "a.xg"}}, "must list"),
        ({"format": FORMAT_NAME, "version": 1, "decks": {"D": [{"file": "a.xg"}]}}, "path"),
        ({"format": FORMAT_NAME, "version": 1, "decks": {"D": [{"path": "a", "players": "Me"}]}}, "players"),
        ({"format": FORMAT_NAME, "version": 1, "decks": {"D": [{"path": "a", "cube_threshold": "x"}]}}, "number"),
    ])
    def test_invalid_files_are_rejected(self, tmp_path, payload, message):
        with pytest.raises(ValueError, match=message):
            load_collection(str(_write(tmp_path / "c.json", payload)))

    def test_not_json_is_rejected(self, tmp_path):
        bad = tmp_path / "c.json"
        bad.write_text("{nope", encoding="utf-8")
        with pytest.raises(ValueError, match="JSON"):
            load_collection(str(bad))

    def test_settings_form_roundtrips_with_absolute_paths(self, tmp_path):
        sources = {"D": [CollectionSource(str(tmp_path / "a.xg"), 0.08, None, ["X"])]}
        assert sources_from_dict(json.loads(json.dumps(sources_to_dict(sources)))) == sources


class TestDeckManagerSources:
    def test_reimporting_a_file_replaces_its_entry(self):
        dm = DeckManager("A")
        dm.record_source("A", CollectionSource("/m/a.xg", 0.1))
        dm.record_source("A", CollectionSource("/m/a.xg", 0.05))
        assert dm.get_sources() == {"A": [CollectionSource("/m/a.xg", 0.05)]}

    def test_same_file_in_two_decks_is_kept_in_both(self):
        dm = DeckManager("A")
        dm.create_deck("B")
        dm.record_source("A", CollectionSource("/m/a.xg"))
        dm.record_source("B", CollectionSource("/m/a.xg"))
        assert list(dm.get_sources()) == ["A", "B"]

    def test_rename_carries_sources(self):
        dm = DeckManager("A")
        dm.create_deck("B")
        dm.record_source("B", CollectionSource("/m/a.xg"))
        dm.rename_deck("B", "C")
        assert dm.get_sources() == {"C": [CollectionSource("/m/a.xg")]}

    def test_delete_moving_positions_moves_sources(self):
        dm = DeckManager("A")
        dm.create_deck("B")
        dm.record_source("B", CollectionSource("/m/a.xg"))
        dm.delete_deck("B", move_to="A")
        assert dm.get_sources() == {"A": [CollectionSource("/m/a.xg")]}

    def test_delete_discarding_positions_forgets_sources(self):
        dm = DeckManager("A")
        dm.create_deck("B")
        dm.record_source("B", CollectionSource("/m/a.xg"))
        dm.delete_deck("B")
        assert dm.get_sources() == {}

    def test_clearing_positions_keeps_sources(self):
        """Positions are cleared after every export by default; the collection
        has to survive that or it could never be saved."""
        dm = DeckManager("A")
        dm.record_source("A", CollectionSource("/m/a.xg"))
        dm.clear_all()
        assert dm.get_sources() == {"A": [CollectionSource("/m/a.xg")]}

    def test_set_sources_creates_missing_decks(self):
        dm = DeckManager("A")
        dm.record_source("A", CollectionSource("/m/old.xg"))
        dm.set_sources({"A::New": [CollectionSource("/m/a.xg")]})
        assert dm.has_deck("A::New")
        assert dm.get_sources() == {"A::New": [CollectionSource("/m/a.xg")]}


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

    def _persist_collection_sources(self):
        pass


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


class TestImportFromCollection:
    def test_entry_imports_into_its_deck_with_its_filter(self, harness):
        harness.deck_manager.create_deck("AnkiGammon::Two")
        harness._import_file(str(SAMPLE_XG), "AnkiGammon::Two", _options(0.08, 0.08, ["Player Two"]))

        decisions = harness.deck_manager.get_deck_decisions("AnkiGammon::Two")
        assert decisions
        assert harness.deck_manager.get_deck_decisions("AnkiGammon") == []
        # Player Two is the file's player 2, i.e. Player.X
        from ankigammon.models import DecisionType, Player
        assert all(
            d.on_roll == Player.X for d in decisions if d.decision_type == DecisionType.CHECKER_PLAY
        )
        assert {d.source_file for d in decisions} == {os.path.abspath(SAMPLE_XG)}
        assert harness.deck_manager.get_sources() == {
            "AnkiGammon::Two": [CollectionSource(os.path.abspath(SAMPLE_XG), 0.08, 0.08, ["Player Two"])]
        }

    def test_both_players_when_players_is_omitted(self, harness):
        harness._import_file(str(SAMPLE_XG), "AnkiGammon", _options(0.08, 0.08, None))
        from ankigammon.models import Player
        on_roll = {d.on_roll for d in harness.deck_manager.get_deck_decisions("AnkiGammon")}
        assert on_roll == {Player.X, Player.O}
        assert harness.deck_manager.get_sources()["AnkiGammon"][0].players is None

    def test_entry_with_unknown_player_is_skipped_with_reason(self, harness):
        harness._import_file(str(SAMPLE_XG), "AnkiGammon", _options(0.08, 0.08, ["Nobody"]))
        assert harness.deck_manager.is_empty
        assert harness.deck_manager.get_sources() == {}
        assert harness._batch_skipped_files == [(str(SAMPLE_XG), "not listed")]

    def test_saved_collection_rebuilds_the_same_positions(self, harness, tmp_path):
        harness.deck_manager.create_deck("AnkiGammon::Mine")
        harness._import_file(str(SAMPLE_XG), "AnkiGammon::Mine", _options(0.05, 0.1, ["Player One"]))
        first = [d.xgid for d in harness.deck_manager.get_deck_decisions("AnkiGammon::Mine")]

        target = tmp_path / "c.json"
        save_collection(str(target), harness.deck_manager.get_sources())

        rebuilt = _ImportHarness(harness.settings)
        for deck, entries in load_collection(str(target)).items():
            rebuilt.deck_manager.create_deck(deck)
            for s in entries:
                rebuilt._import_file(s.path, deck, _options(s.checker_threshold, s.cube_threshold, s.players))

        assert [d.xgid for d in rebuilt.deck_manager.get_deck_decisions("AnkiGammon::Mine")] == first
