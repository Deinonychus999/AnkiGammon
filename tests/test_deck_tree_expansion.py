"""Tests for deck tree expand/collapse state across rebuilds, and stylesheet image paths."""

import re
import tempfile
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from ankigammon.models import Decision, DecisionType, Position, Player
from ankigammon.settings import Settings
from ankigammon.gui.deck_manager import DeckManager
from ankigammon.gui.resources import load_stylesheet
from ankigammon.gui.widgets.deck_tree import DeckTreeWidget, DeckTreeItem


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def make_decision() -> Decision:
    return Decision(
        position=Position(),
        on_roll=Player.X,
        decision_type=DecisionType.CUBE_ACTION,
        candidate_moves=[]
    )


class TestDeckTreeExpansion:

    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.settings = Settings(config_path=Path(self.temp_dir) / "config.json")
        self.deck_manager = DeckManager("Root")

    def _add(self, deck_name: str, decision: Decision = None) -> Decision:
        decision = decision or make_decision()
        self.deck_manager.create_deck(deck_name)
        self.deck_manager.add_decisions([decision], deck_name)
        return decision

    def _make_tree(self) -> DeckTreeWidget:
        tree = DeckTreeWidget(self.deck_manager, self.settings)
        # Must be visible: setCurrentItem() only auto-scrolls (and expands) when shown
        tree.show()
        return tree

    def _deck(self, tree: DeckTreeWidget, name: str) -> DeckTreeItem:
        return next(d for d in tree._iter_deck_items() if d.deck_name == name)

    def test_collapsed_subdeck_stays_collapsed_after_import_elsewhere(self, qapp):
        self._add("Root::A")
        tree = self._make_tree()
        self._deck(tree, "Root::A").setExpanded(False)

        self._add("Root::B")
        tree.rebuild_tree()

        assert not self._deck(tree, "Root::A").isExpanded()
        assert self._deck(tree, "Root::B").isExpanded()

    def test_collapsed_deck_holding_selection_stays_collapsed(self, qapp):
        decision = make_decision()
        self._add("Root::A", decision)
        tree = self._make_tree()
        tree.select_decision(decision)
        self._deck(tree, "Root::A").setExpanded(False)

        self._add("Root::B")
        tree.rebuild_tree()

        assert not self._deck(tree, "Root::A").isExpanded()
        assert tree.get_selected_decision() is decision

    def test_empty_deck_opens_on_first_import(self, qapp):
        self.deck_manager.create_deck("Root::A")
        tree = self._make_tree()
        assert not self._deck(tree, "Root::A").isExpanded()

        self._add("Root::A")
        tree.rebuild_tree()

        assert self._deck(tree, "Root::A").isExpanded()

    def test_collapse_all_survives_rebuild(self, qapp):
        self._add("Root::A")
        self._add("Root::B")
        tree = self._make_tree()
        tree.collapseAll()

        tree.rebuild_tree()

        assert not any(d.isExpanded() for d in tree._iter_deck_items())

    def test_set_expanded_recursive(self, qapp):
        self._add("Root::A::X")
        tree = self._make_tree()
        tree.collapseAll()

        tree.set_expanded_recursive(self._deck(tree, "Root"), True)

        assert all(d.isExpanded() for d in tree._iter_deck_items())


def test_stylesheet_image_urls_are_absolute_and_exist():
    urls = re.findall(r"url\(([^)]+)\)", load_stylesheet())
    assert urls
    for url in urls:
        path = Path(url)
        assert path.is_absolute(), url
        assert path.exists(), url
