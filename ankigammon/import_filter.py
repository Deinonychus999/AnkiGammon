"""Reduce an analyzed match to the decisions worth studying.

Kept free of Qt so the desktop import and the browser version share it.
"""

import logging
from typing import List

from ankigammon.models import Decision, DecisionType, Move, Player

logger = logging.getLogger(__name__)


def ensure_played_move_in_candidates(decision: Decision, played_move: Move, max_options: int) -> None:
    """Move the played move into the last of the first `max_options` slots if it ranks lower,
    so the card offers the move the player actually chose."""
    if played_move in decision.candidate_moves[:max_options]:
        return
    decision.candidate_moves.remove(played_move)
    decision.candidate_moves.insert(max_options - 1, played_move)


def filter_decisions(
    decisions: List[Decision],
    checker_threshold: float,
    cube_threshold: float,
    include_player_x: bool,
    include_player_o: bool,
    max_options: int,
) -> List[Decision]:
    """Keep the decisions where an included player erred by at least the threshold.

    Thresholds are positive equity losses (e.g. 0.080). Kept decisions are
    modified in place: the played move is guaranteed a multiple-choice slot, and
    with a single player included, cube decisions record that player in
    `user_player`.
    """
    filtered = []

    cube_found = sum(1 for d in decisions if d.decision_type == DecisionType.CUBE_ACTION)
    logger.debug(f"Filtering {len(decisions)} total decisions ({cube_found} cube decisions)")

    for decision in decisions:
        if not decision.candidate_moves:
            continue

        played_move = next((m for m in decision.candidate_moves if m.was_played), None)
        if not played_move:
            continue

        if decision.decision_type == DecisionType.CUBE_ACTION:
            attr = decision.get_cube_error_attribution()
            doubler = attr['doubler']
            responder = attr['responder']
            doubler_error = attr['doubler_error']
            responder_error = attr['responder_error']

            doubler_made_error = doubler_error is not None and abs(doubler_error) >= cube_threshold
            responder_made_error = responder_error is not None and abs(responder_error) >= cube_threshold

            logger.debug(
                f"Cube decision - doubler={doubler}, doubler_error={doubler_error}, "
                f"responder={responder}, responder_error={responder_error}, cube_threshold={cube_threshold}"
            )

            if not doubler_made_error and not responder_made_error:
                continue

            include_decision = (
                (doubler == Player.X and doubler_made_error and include_player_x)
                or (doubler == Player.O and doubler_made_error and include_player_o)
                or (responder == Player.X and responder_made_error and include_player_x)
                or (responder == Player.O and responder_made_error and include_player_o)
            )
            if not include_decision:
                continue

            ensure_played_move_in_candidates(decision, played_move, max_options)

            # user_player drives the split-cube card variants (doubler-only /
            # receiver-only) in card_generator; with both players included it
            # stays None so the full card is generated.
            only_x = include_player_x and not include_player_o
            only_o = include_player_o and not include_player_x
            if only_x:
                if (doubler == Player.X and doubler_made_error) or (responder == Player.X and responder_made_error):
                    decision.user_player = Player.X
            elif only_o:
                if (doubler == Player.O and doubler_made_error) or (responder == Player.O and responder_made_error):
                    decision.user_player = Player.O

            filtered.append(decision)
        else:
            # XG's ErrMove is authoritative for XG binary files; text imports
            # carry xg_error, and other sources only the recalculated error.
            if decision.xg_error_move is not None:
                error_magnitude = decision.xg_error_move
            elif played_move.xg_error is not None:
                error_magnitude = abs(played_move.xg_error)
            else:
                error_magnitude = played_move.error

            if error_magnitude < checker_threshold:
                continue

            if decision.on_roll == Player.X and not include_player_x:
                continue
            if decision.on_roll == Player.O and not include_player_o:
                continue

            ensure_played_move_in_candidates(decision, played_move, max_options)
            filtered.append(decision)

    cube_kept = sum(1 for d in filtered if d.decision_type == DecisionType.CUBE_ACTION)
    logger.debug(f"After filtering: {len(filtered)} decisions ({cube_kept} cube decisions)")

    return filtered
