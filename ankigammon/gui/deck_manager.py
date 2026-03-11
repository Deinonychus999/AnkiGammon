"""Data model for organizing decisions into named decks."""

from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

from ankigammon.models import Decision


class DeckManager:
    """Manages decisions organized into named decks.

    Replaces the flat List[Decision] as the single source of truth for
    position organization. Each deck maps to an Anki deck using the ::
    subdeck separator convention.

    Uses object identity (not equality) for decision operations to avoid
    expensive __eq__ on deeply nested dataclass objects.
    """

    def __init__(self, default_deck_name: str):
        self.default_deck_name = default_deck_name
        self._decks: OrderedDict[str, List[Decision]] = OrderedDict()
        self._decks[default_deck_name] = []

    # -- Deck operations --

    def create_deck(self, name: str) -> bool:
        """Create a new empty deck. Returns False if name already exists."""
        name = name.strip()
        if not name or name in self._decks:
            return False
        self._decks[name] = []
        return True

    def rename_deck(self, old_name: str, new_name: str) -> bool:
        """Rename a deck. Returns False if old doesn't exist or new already taken."""
        new_name = new_name.strip()
        if not new_name or old_name not in self._decks or new_name in self._decks:
            return False
        if old_name == new_name:
            return True

        # Rebuild OrderedDict preserving order with new key
        new_decks: OrderedDict[str, List[Decision]] = OrderedDict()
        for key, value in self._decks.items():
            if key == old_name:
                new_decks[new_name] = value
            else:
                new_decks[key] = value
        self._decks = new_decks

        # Update default name if it was the default deck
        if self.default_deck_name == old_name:
            self.default_deck_name = new_name

        return True

    def delete_deck(self, name: str, move_to: Optional[str] = None) -> bool:
        """Delete a deck. Optionally moves its positions to another deck.

        Returns False if deck doesn't exist or is the last remaining deck.
        """
        if name not in self._decks or len(self._decks) <= 1:
            return False

        decisions = self._decks[name]
        if move_to and move_to in self._decks and move_to != name:
            self._decks[move_to].extend(decisions)

        del self._decks[name]

        # If we deleted the default deck, reassign default to the first deck
        if self.default_deck_name == name:
            self.default_deck_name = next(iter(self._decks))

        return True

    def create_subdeck(self, parent_name: str, child_name: str) -> Optional[str]:
        """Create a subdeck under a parent. Returns full name or None if failed."""
        child_name = child_name.strip()
        if not child_name:
            return None
        full_name = f"{parent_name}::{child_name}"
        if self.create_deck(full_name):
            return full_name
        return None

    def get_deck_names(self) -> List[str]:
        """Return list of deck names in creation order."""
        return list(self._decks.keys())

    def has_deck(self, name: str) -> bool:
        """Check if a deck with the given name exists."""
        return name in self._decks

    # -- Decision operations --

    def add_decisions(self, decisions: List[Decision], deck_name: Optional[str] = None) -> None:
        """Add decisions to a deck. Uses default deck if name is None or not found."""
        target = deck_name if deck_name and deck_name in self._decks else self.default_deck_name
        self._decks[target].extend(decisions)

    def move_decisions(self, decisions: List[Decision], to_deck: str) -> None:
        """Move decisions to a target deck. Removes from their current decks by identity."""
        if to_deck not in self._decks:
            return

        decisions_set = set(id(d) for d in decisions)

        # Remove from all source decks
        for deck_name in self._decks:
            if deck_name == to_deck:
                continue
            self._decks[deck_name] = [
                d for d in self._decks[deck_name] if id(d) not in decisions_set
            ]

        # Add to target (avoid duplicates by identity)
        existing_ids = set(id(d) for d in self._decks[to_deck])
        for d in decisions:
            if id(d) not in existing_ids:
                self._decks[to_deck].append(d)

    def remove_decision(self, deck_name: str, decision: Decision) -> None:
        """Remove a single decision from a specific deck by identity."""
        if deck_name in self._decks:
            self._decks[deck_name] = [
                d for d in self._decks[deck_name] if d is not decision
            ]

    def remove_decisions_by_identity(self, removals: List[Tuple[str, Decision]]) -> None:
        """Remove multiple decisions, each identified by (deck_name, decision) pair."""
        # Group removals by deck for efficiency
        by_deck: Dict[str, set] = {}
        for deck_name, decision in removals:
            if deck_name not in by_deck:
                by_deck[deck_name] = set()
            by_deck[deck_name].add(id(decision))

        for deck_name, ids_to_remove in by_deck.items():
            if deck_name in self._decks:
                self._decks[deck_name] = [
                    d for d in self._decks[deck_name] if id(d) not in ids_to_remove
                ]

    # -- Query operations --

    def get_all_decisions(self) -> List[Decision]:
        """Return a flat list of all decisions across all decks."""
        result = []
        for decisions in self._decks.values():
            result.extend(decisions)
        return result

    def get_grouped_decisions(self) -> Dict[str, List[Decision]]:
        """Return a copy of the deck-to-decisions mapping (skipping empty decks)."""
        return {
            name: list(decisions)
            for name, decisions in self._decks.items()
            if decisions
        }

    def get_deck_decisions(self, deck_name: str) -> List[Decision]:
        """Return decisions for a specific deck, or empty list."""
        return list(self._decks.get(deck_name, []))

    @property
    def total_count(self) -> int:
        """Total number of decisions across all decks."""
        return sum(len(v) for v in self._decks.values())

    @property
    def is_empty(self) -> bool:
        """True if no decisions exist in any deck."""
        return self.total_count == 0

    # -- Bulk operations --

    def merge_deck_names(self, names: List[str]) -> int:
        """Merge external deck names into existing structure (additive only).

        Creates any decks that don't already exist. Never deletes existing decks.

        Args:
            names: List of deck names to merge.

        Returns:
            Number of new decks created.
        """
        created = 0
        for name in names:
            name = name.strip()
            if name and name not in self._decks:
                self._decks[name] = []
                created += 1
        return created

    def clear_all(self) -> None:
        """Remove all decisions but preserve deck structure."""
        for deck_name in self._decks:
            self._decks[deck_name] = []

    def clear_all_and_reset(self) -> None:
        """Remove all decisions and all decks except the default."""
        self._decks.clear()
        self._decks[self.default_deck_name] = []
