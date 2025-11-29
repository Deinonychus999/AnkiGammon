"""Tests for subdeck organization feature."""

import pytest
from ankigammon.models import Decision, DecisionType, Position, Player
from ankigammon.anki.deck_utils import get_deck_name_for_decision, group_decisions_by_deck


class TestSubdeckUtils:
    """Test deck name utilities for subdeck feature."""

    def test_get_deck_name_without_subdecks(self):
        """Test that deck name is unchanged when subdecks are disabled."""
        position = Position()
        decision = Decision(
            position=position,
            on_roll=Player.X,
            decision_type=DecisionType.CHECKER_PLAY,
            candidate_moves=[]
        )

        deck_name = get_deck_name_for_decision("My Deck", decision, use_subdecks=False)
        assert deck_name == "My Deck"

    def test_get_deck_name_checker_play(self):
        """Test that checker play decisions go to Checker Play subdeck."""
        position = Position()
        decision = Decision(
            position=position,
            on_roll=Player.X,
            decision_type=DecisionType.CHECKER_PLAY,
            candidate_moves=[]
        )

        deck_name = get_deck_name_for_decision("My Deck", decision, use_subdecks=True)
        assert deck_name == "My Deck::Checker Play"

    def test_get_deck_name_cube_action(self):
        """Test that cube decisions go to Cube Decisions subdeck."""
        position = Position()
        decision = Decision(
            position=position,
            on_roll=Player.X,
            decision_type=DecisionType.CUBE_ACTION,
            candidate_moves=[]
        )

        deck_name = get_deck_name_for_decision("My Deck", decision, use_subdecks=True)
        assert deck_name == "My Deck::Cube Decisions"

    def test_group_decisions_without_subdecks(self):
        """Test that all decisions are grouped into a single deck when subdecks are disabled."""
        position = Position()
        decisions = [
            Decision(
                position=position,
                on_roll=Player.X,
                decision_type=DecisionType.CHECKER_PLAY,
                candidate_moves=[]
            ),
            Decision(
                position=position,
                on_roll=Player.O,
                decision_type=DecisionType.CUBE_ACTION,
                candidate_moves=[]
            ),
            Decision(
                position=position,
                on_roll=Player.X,
                decision_type=DecisionType.CHECKER_PLAY,
                candidate_moves=[]
            ),
        ]

        grouped = group_decisions_by_deck(decisions, "My Deck", use_subdecks=False)

        assert len(grouped) == 1
        assert "My Deck" in grouped
        assert len(grouped["My Deck"]) == 3

    def test_group_decisions_with_subdecks(self):
        """Test that decisions are grouped by type when subdecks are enabled."""
        position = Position()
        decisions = [
            Decision(
                position=position,
                on_roll=Player.X,
                decision_type=DecisionType.CHECKER_PLAY,
                candidate_moves=[]
            ),
            Decision(
                position=position,
                on_roll=Player.O,
                decision_type=DecisionType.CUBE_ACTION,
                candidate_moves=[]
            ),
            Decision(
                position=position,
                on_roll=Player.X,
                decision_type=DecisionType.CHECKER_PLAY,
                candidate_moves=[]
            ),
            Decision(
                position=position,
                on_roll=Player.O,
                decision_type=DecisionType.CUBE_ACTION,
                candidate_moves=[]
            ),
        ]

        grouped = group_decisions_by_deck(decisions, "My Deck", use_subdecks=True)

        assert len(grouped) == 2
        assert "My Deck::Checker Play" in grouped
        assert "My Deck::Cube Decisions" in grouped
        assert len(grouped["My Deck::Checker Play"]) == 2
        assert len(grouped["My Deck::Cube Decisions"]) == 2

    def test_group_decisions_only_checker_play(self):
        """Test grouping when only checker play decisions are present."""
        position = Position()
        decisions = [
            Decision(
                position=position,
                on_roll=Player.X,
                decision_type=DecisionType.CHECKER_PLAY,
                candidate_moves=[]
            ),
            Decision(
                position=position,
                on_roll=Player.O,
                decision_type=DecisionType.CHECKER_PLAY,
                candidate_moves=[]
            ),
        ]

        grouped = group_decisions_by_deck(decisions, "My Deck", use_subdecks=True)

        assert len(grouped) == 1
        assert "My Deck::Checker Play" in grouped
        assert len(grouped["My Deck::Checker Play"]) == 2

    def test_group_decisions_only_cube_decisions(self):
        """Test grouping when only cube decisions are present."""
        position = Position()
        decisions = [
            Decision(
                position=position,
                on_roll=Player.X,
                decision_type=DecisionType.CUBE_ACTION,
                candidate_moves=[]
            ),
            Decision(
                position=position,
                on_roll=Player.O,
                decision_type=DecisionType.CUBE_ACTION,
                candidate_moves=[]
            ),
        ]

        grouped = group_decisions_by_deck(decisions, "My Deck", use_subdecks=True)

        assert len(grouped) == 1
        assert "My Deck::Cube Decisions" in grouped
        assert len(grouped["My Deck::Cube Decisions"]) == 2

    def test_deck_name_with_special_characters(self):
        """Test that deck names with special characters work correctly."""
        position = Position()
        decision = Decision(
            position=position,
            on_roll=Player.X,
            decision_type=DecisionType.CHECKER_PLAY,
            candidate_moves=[]
        )

        deck_name = get_deck_name_for_decision(
            "My Awesome Deck (2024)",
            decision,
            use_subdecks=True
        )
        assert deck_name == "My Awesome Deck (2024)::Checker Play"
