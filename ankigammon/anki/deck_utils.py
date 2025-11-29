"""Utility functions for deck management and naming."""

from typing import Dict, List, Set
from ankigammon.models import Decision, DecisionType


def get_deck_name_for_decision(
    base_deck_name: str,
    decision: Decision,
    use_subdecks: bool
) -> str:
    """
    Get the appropriate deck name for a decision.

    When use_subdecks is True, returns deck name with subdeck notation
    (e.g., "My Deck::Checker Play" or "My Deck::Cube Decisions").
    When use_subdecks is False, returns the base deck name unchanged.

    Args:
        base_deck_name: The base deck name
        decision: The decision to get the deck name for
        use_subdecks: Whether to use subdeck notation

    Returns:
        The deck name to use for this decision
    """
    if not use_subdecks:
        return base_deck_name

    # Determine subdeck name based on decision type
    if decision.decision_type == DecisionType.CHECKER_PLAY:
        subdeck = "Checker Play"
    else:  # DecisionType.CUBE_ACTION
        subdeck = "Cube Decisions"

    return f"{base_deck_name}::{subdeck}"


def get_required_deck_names(
    decisions: List[Decision],
    base_deck_name: str,
    use_subdecks: bool
) -> Set[str]:
    """
    Get unique deck names needed for a set of decisions.

    Args:
        decisions: List of decisions to process
        base_deck_name: The base deck name
        use_subdecks: Whether to use subdeck notation

    Returns:
        Set of unique deck names required
    """
    return {
        get_deck_name_for_decision(base_deck_name, decision, use_subdecks)
        for decision in decisions
    }


def group_decisions_by_deck(
    decisions: List[Decision],
    base_deck_name: str,
    use_subdecks: bool
) -> Dict[str, List[Decision]]:
    """
    Group decisions by their target deck.

    Args:
        decisions: List of decisions to group
        base_deck_name: The base deck name
        use_subdecks: Whether to use subdeck notation

    Returns:
        Dictionary mapping deck names to lists of decisions
    """
    if not use_subdecks:
        # All decisions go to the same deck
        return {base_deck_name: decisions}

    # Group by decision type
    grouped: Dict[str, List[Decision]] = {}

    for decision in decisions:
        deck_name = get_deck_name_for_decision(base_deck_name, decision, use_subdecks)
        if deck_name not in grouped:
            grouped[deck_name] = []
        grouped[deck_name].append(decision)

    return grouped
