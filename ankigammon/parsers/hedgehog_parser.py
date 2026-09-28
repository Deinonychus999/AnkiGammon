"""Turns HedgeHog's position analysis (JSON, section 9.5 of its partner API)
into Decisions, and holds the probability helpers the OGXM parser shares.

HedgeHog probabilities are cumulative (gammons include backgammons) and from
the point of view of the player to act.
"""

import json
from typing import List, Optional, Tuple

from ankigammon.models import Decision, DecisionType, Move, Player
from ankigammon.utils.ogid import encode_ogid
from ankigammon.utils.xgid import parse_xgid

# A batch counts as one analysis only when the whole of it takes under a second
# of engine time. About 12 positions fit at 2ply; deeper presets are counted per
# position however they are sent, so they only need fewer requests.
BATCH_SIZES = {"1ply": 64, "2ply": 12, "3ply": 64, "+": 8, "++": 8}

PCT_ATTRS = (
    "player_win_pct", "player_gammon_pct", "player_backgammon_pct",
    "opponent_win_pct", "opponent_gammon_pct", "opponent_backgammon_pct",
)


def set_probabilities(target, probs: Optional[dict]) -> None:
    """Copy HedgeHog's five probabilities onto a Move or Decision as percentages."""
    if not probs:
        return
    target.player_win_pct = probs["win"] * 100
    target.player_gammon_pct = probs["gammon_win"] * 100
    target.player_backgammon_pct = probs["bg_win"] * 100
    target.opponent_win_pct = (1 - probs["win"]) * 100
    target.opponent_gammon_pct = probs["gammon_loss"] * 100
    target.opponent_backgammon_pct = probs["bg_loss"] * 100


def swap_sides(probs: Optional[dict]) -> Optional[dict]:
    """The same probabilities seen by the other player."""
    if not probs:
        return probs
    return {
        "win": 1 - probs["win"], "gammon_win": probs["gammon_loss"], "bg_win": probs["bg_loss"],
        "gammon_loss": probs["gammon_win"], "bg_loss": probs["bg_win"],
    }


def aways(decision: Decision) -> Tuple[int, int]:
    """(player on roll's away, opponent's away); (0, 0) in unlimited games."""
    if decision.match_length <= 0:
        return 0, 0
    if decision.on_roll == Player.O:
        return decision.match_length - decision.score_o, decision.match_length - decision.score_x
    return decision.match_length - decision.score_x, decision.match_length - decision.score_o


def is_post_crawford(decision: Decision) -> bool:
    player_away, opponent_away = aways(decision)
    return decision.match_length > 0 and not decision.crawford and 1 in (player_away, opponent_away)


def cubeless_equity(target, decision: Decision, cube_value: Optional[int] = None) -> Optional[float]:
    """Cubeless equity of a Move or Decision's probabilities: money points, or
    normalized match equity at the decision's score."""
    if target.player_win_pct is None:
        return None
    player_away, opponent_away = aways(decision)
    probe = Move(notation="", equity=0.0)
    for attr in PCT_ATTRS:
        setattr(probe, attr, getattr(target, attr))
    return probe.calculate_cubeless_equity(
        cumulative=True, match_length=decision.match_length, player_away=player_away,
        opponent_away=opponent_away, cube_value=cube_value or decision.cube_value,
        crawford=decision.crawford, post_crawford=is_post_crawford(decision),
    )


def decision_from_xgid(xgid: str, decision_type: DecisionType) -> Decision:
    position, metadata = parse_xgid(xgid)
    match_length = metadata.get("match_length", 0)
    crawford_jacoby = metadata.get("crawford_jacoby", 0)
    return Decision(
        position=position,
        xgid=xgid,
        on_roll=metadata.get("on_roll", Player.O),
        dice=metadata.get("dice") if decision_type == DecisionType.CHECKER_PLAY else None,
        score_x=metadata.get("score_x", 0),
        score_o=metadata.get("score_o", 0),
        match_length=match_length,
        crawford=bool(match_length > 0 and crawford_jacoby & 1),
        cube_value=metadata.get("cube_value", 1),
        cube_owner=metadata.get("cube_owner"),
        decision_type=decision_type,
        beavers_allowed=bool(metadata.get("beavers_allowed", False)),
        jacoby=bool(metadata.get("jacoby", False)),
    )


def xgid_to_ogid(xgid: str) -> Tuple[str, DecisionType, bool]:
    """The OGID HedgeHog analyses for an XGID, its decision type (dice mean a
    checker play) and whether the Jacoby rule applies."""
    position, metadata = parse_xgid(xgid)
    dice = metadata.get("dice")
    match_length = metadata.get("match_length", 0)
    crawford = match_length > 0 and bool(metadata.get("crawford_jacoby", 0) & 1)
    ogid = encode_ogid(
        position,
        cube_value=metadata.get("cube_value", 1),
        cube_owner=metadata.get("cube_owner"),
        cube_action="N",
        dice=dice,
        on_roll=metadata.get("on_roll", Player.O),
        game_state="R" if dice else "C",
        score_x=metadata.get("score_x", 0),
        score_o=metadata.get("score_o", 0),
        match_length=match_length,
        match_modifier="C" if crawford else "",
    )
    decision_type = DecisionType.CHECKER_PLAY if dice else DecisionType.CUBE_ACTION
    return ogid, decision_type, bool(metadata.get("jacoby", False)) and match_length == 0


def plan_batches(xgids: List[str], preset: str) -> Tuple[List[dict], List[DecisionType]]:
    """The batch requests that analyse `xgids` at `preset`, and each position's
    decision type. A batch is {"ogids", "jacoby", "indices"}: `jacoby` applies
    to a whole batch, so the two rules go in separate batches, and `indices`
    say which input each answer belongs to."""
    prepared = [xgid_to_ogid(xgid) for xgid in xgids]
    groups: dict = {}
    for index, (_, _, jacoby) in enumerate(prepared):
        groups.setdefault(jacoby, []).append(index)
    size = BATCH_SIZES.get(preset, 8)
    batches = []
    for jacoby, indices in groups.items():
        for start in range(0, len(indices), size):
            chunk = indices[start:start + size]
            batches.append({"ogids": [prepared[i][0] for i in chunk], "jacoby": jacoby, "indices": chunk})
    return batches, [decision_type for _, decision_type, _ in prepared]


def estimated_cost(batches: List[dict], preset: str) -> int:
    """How many position analyses `batches` should count against a HedgeHog
    allowance. A batch that finishes in under a second of engine time counts
    once; the batch sizes keep 1ply and 2ply batches there, and deeper
    presets count per position."""
    if preset in ("1ply", "2ply"):
        return len(batches)
    return sum(len(batch["indices"]) for batch in batches)


class PositionResultParsing:
    """The BackgammonAnalyzer parse methods for analyzers whose raw output is
    one HedgeHog position result (JSON). Needs `preset_label`."""

    preset_label = "HedgeHog"

    def parse_analysis(self, raw_output: str, xgid: str, decision_type: DecisionType) -> Decision:
        return parse_position_result(raw_output, xgid, decision_type, self.preset_label)

    def parse_checker_play(self, raw_output: str) -> List[Move]:
        result = json.loads(raw_output)
        return checker_moves(result, self._decision_for(result), self.preset_label)

    def parse_cube_decision(self, raw_output: str, cube_value: int = 1) -> List[Move]:
        result = json.loads(raw_output)
        try:
            return cube_decision_moves(result, self._decision_for(result))
        except ValueError:
            return []

    @staticmethod
    def _decision_for(result: dict) -> Decision:
        """The game context of a bare result, read from the OGID HedgeHog analysed."""
        from ankigammon.utils.ogid import parse_ogid
        from ankigammon.utils.xgid import encode_xgid
        position, metadata = parse_ogid(result["ogid"])
        xgid = encode_xgid(
            position, cube_value=metadata.get("cube_value", 1), cube_owner=metadata.get("cube_owner"),
            dice=metadata.get("dice"), on_roll=metadata["on_roll"],
            score_x=metadata.get("score_x", 0), score_o=metadata.get("score_o", 0),
            match_length=metadata.get("match_length", 0),
            crawford_jacoby=1 if metadata.get("match_modifier") == "C" else 0,
        )
        decision_type = (
            DecisionType.CHECKER_PLAY if result.get("decision_type") == "checker" else DecisionType.CUBE_ACTION
        )
        return decision_from_xgid(xgid, decision_type)


def checker_moves(result: dict, decision: Decision, level: str) -> List[Move]:
    alternatives = result.get("alternatives") or []
    if not alternatives:
        raise ValueError("HedgeHog returned no moves for this position")
    best = alternatives[0]["equity"]
    moves = []
    for rank, alternative in enumerate(alternatives, 1):
        move = Move(
            notation=alternative["move_notation"],
            equity=alternative["equity"],
            error=abs(best - alternative["equity"]),
            rank=rank,
            xg_rank=rank,
            xg_error=alternative["equity"] - best,
            xg_notation=alternative["move_notation"],
            analysis_level=level,
        )
        set_probabilities(move, alternative.get("eval"))
        move.cubeless_equity = cubeless_equity(move, decision)
        moves.append(move)
    return moves


def cube_moves(cube_value: int, no_double: float, double_take: float, double_pass: float,
               best: str) -> List[Move]:
    """The five cube options AnkiGammon's cards use, best first by `best`,
    which is one of "no_double", "double_take", "double_pass", "too_good"."""
    double = "Redouble" if cube_value > 1 else "Double"
    equities = {
        f"No {double}/Take": no_double,
        f"{double}/Take": double_take,
        f"{double}/Pass": double_pass,
        "Too good/Take": no_double,
        "Too good/Pass": no_double,
    }
    short = {
        f"No {double}/Take": f"No {double.lower()}",
        f"{double}/Take": f"{double}/Take",
        f"{double}/Pass": f"{double}/Pass",
    }
    if best == "too_good":
        best_notation = "Too good/Pass" if double_take >= double_pass else "Too good/Take"
    else:
        best_notation = {
            "no_double": f"No {double}/Take",
            "double_take": f"{double}/Take",
            "double_pass": f"{double}/Pass",
        }[best]
    moves = [
        Move(
            notation=notation,
            equity=equity,
            xg_notation=short.get(notation),
            from_xg_analysis=not notation.startswith("Too good"),
        )
        for notation, equity in equities.items()
    ]
    best_move = next(m for m in moves if m.notation == best_notation)
    best_move.rank = 1
    others = sorted((m for m in moves if m is not best_move), key=lambda m: m.equity, reverse=True)
    for rank, move in enumerate(others, 2):
        move.rank = rank
    for move in moves:
        move.error = abs(best_move.equity - move.equity)
    return moves


def _best_from_action(action: str) -> str:
    action = action.lower()
    if "too good" in action:
        return "too_good"
    if action.startswith("no "):
        return "no_double"
    return "double_pass" if action.endswith("pass") else "double_take"


def cube_decision_moves(result: dict, decision: Decision) -> List[Move]:
    cube = result.get("cube_decision")
    if not cube:
        raise ValueError(
            "HedgeHog has no cube decision here: the cube is dead (Crawford, or it "
            "can no longer be turned) or the engine does not decide cubes."
        )
    if decision.match_length > 0 and "no_double_norm_eq" in cube:
        triple = (cube["no_double_norm_eq"], cube["double_take_norm_eq"], cube["double_pass_norm_eq"])
    else:
        triple = (cube["no_double_equity"], cube["double_take_equity"], cube["double_pass_equity"])
    return cube_moves(decision.cube_value, *triple, _best_from_action(cube["action"]))


def parse_position_result(raw_output: str, xgid: str, decision_type: DecisionType,
                          level: str) -> Decision:
    """A Decision from one HedgeHog position result (the analyzer's raw output)."""
    result = json.loads(raw_output)
    if result.get("success") is False:
        error = result.get("error") or {}
        raise ValueError(error.get("message") or "HedgeHog could not analyze this position")
    decision = decision_from_xgid(xgid, decision_type)
    if decision_type == DecisionType.CHECKER_PLAY:
        decision.candidate_moves = checker_moves(result, decision, level)
    else:
        decision.candidate_moves = cube_decision_moves(result, decision)
        set_probabilities(decision, result.get("eval"))
        decision.cubeless_equity = cubeless_equity(decision, decision)
        if decision.match_length > 0:
            decision.double_cubeless_equity = cubeless_equity(decision, decision, decision.cube_value * 2)
        elif decision.cubeless_equity is not None:
            decision.double_cubeless_equity = decision.cubeless_equity * 2
    return decision
