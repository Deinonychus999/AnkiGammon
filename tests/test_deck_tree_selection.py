"""Tests for deck tree position selection (auto-display of imported positions)."""

import tempfile
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from ankigammon.models import Decision, DecisionType, Position, Player
from ankigammon.settings import Settings
from ankigammon.gui.deck_manager import DeckManager
from ankigammon.gui.widgets.deck_tree import DeckTreeWidget, DeckTreeItem


@pytest.fixture(scope="module")
def qapp():
    """Create QApplication instance for GUI tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def make_decision() -> Decision:
    """Create a minimal decision for tree tests."""
    return Decision(
        position=Position(),
        on_roll=Player.X,
        decision_type=DecisionType.CUBE_ACTION,
        candidate_moves=[]
    )


class TestDeckTreeSelection:
    """Test DeckTreeWidget.select_decision and the import selection behavior."""

    def setup_method(self):
        """Create a temporary config file and deck manager for testing."""
        self.temp_dir = tempfile.mkdtemp()
        self.config_path = Path(self.temp_dir) / "config.json"
        self.settings = Settings(config_path=self.config_path)
        self.deck_manager = DeckManager("Test")

    def _make_tree(self) -> DeckTreeWidget:
        return DeckTreeWidget(self.deck_manager, self.settings)

    def test_import_scenario_bug_precondition(self, qapp):
        """After an import-style add + rebuild, the deck (not the position) is selected.

        Documents the precondition of issue #53: rebuild_tree() re-selects the
        previously selected deck item, so no position_selected is emitted and
        the preview keeps showing the welcome screen.
        """
        tree = self._make_tree()

        # Startup state: the empty default deck is selected
        assert isinstance(tree.currentItem(), DeckTreeItem)

        decision = make_decision()
        self.deck_manager.add_decisions([decision])
        tree.rebuild_tree()

        # The deck is re-selected, so no position is considered selected
        assert tree.get_selected_decision() is None

    def test_select_decision_selects_item(self, qapp):
        """select_decision finds the position item by identity and selects it."""
        tree = self._make_tree()
        decision = make_decision()
        self.deck_manager.add_decisions([decision])
        tree.rebuild_tree()

        assert tree.select_decision(decision) is True
        assert tree.get_selected_decision() is decision

    def test_select_decision_emits_position_selected(self, qapp):
        """select_decision emits position_selected (drives show_decision in the app)."""
        tree = self._make_tree()
        decision = make_decision()
        self.deck_manager.add_decisions([decision])
        tree.rebuild_tree()

        emitted = []
        tree.position_selected.connect(emitted.append)

        assert tree.select_decision(decision) is True
        assert emitted == [decision]

    def test_select_decision_expands_nested_deck(self, qapp):
        """select_decision expands all ancestor decks of a nested position."""
        self.deck_manager.create_deck("Test::Sub")
        decision = make_decision()
        self.deck_manager.add_decisions([decision], "Test::Sub")

        tree = self._make_tree()
        tree.rebuild_tree()
        tree.collapseAll()

        assert tree.select_decision(decision) is True
        assert tree.get_selected_decision() is decision

        # All ancestor deck items must be expanded so the item is visible
        parent = tree.currentItem().parent()
        assert parent is not None
        while parent:
            assert parent.isExpanded()
            parent = parent.parent()

    def test_select_decision_unknown_returns_false(self, qapp):
        """select_decision returns False and leaves selection unchanged for unknown decisions."""
        tree = self._make_tree()
        decision = make_decision()
        self.deck_manager.add_decisions([decision])
        tree.rebuild_tree()

        before = tree.currentItem()
        unknown = make_decision()

        assert tree.select_decision(unknown) is False
        assert tree.currentItem() is before
