"""JSON serialization for Decision objects so cards can be re-rendered
without re-running analysis.

The serialized blob is stored in the Anki note's AnalysisData field. Round-trip
preserves every field of Decision, Position, and Move — including rollout
results — so cosmetic settings (colors, pip counter, board orientation) can
be changed and cards re-rendered using only the persisted data.
"""

import dataclasses
import json
from enum import Enum
from typing import Any

from ankigammon.models import (
    CubeState,
    Decision,
    DecisionType,
    Move,
    Player,
    Position,
)


SCHEMA_VERSION = 1


def _to_jsonable(value: Any) -> Any:
    """Recursively convert asdict() output to JSON-safe primitives.

    asdict() leaves enums and tuples in place; json.dumps can't handle either.
    """
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    return value


def decision_to_json(decision: Decision) -> str:
    """Serialize a Decision to a JSON string for storage in an Anki note."""
    payload = {
        "version": SCHEMA_VERSION,
        "decision": _to_jsonable(dataclasses.asdict(decision)),
    }
    return json.dumps(payload, separators=(",", ":"))


def _build_position(data: dict) -> Position:
    return Position(
        points=list(data["points"]),
        x_off=data.get("x_off", 0),
        o_off=data.get("o_off", 0),
    )


def _build_move(data: dict) -> Move:
    rp = data.get("resulting_position")
    return Move(
        notation=data["notation"],
        equity=data["equity"],
        error=data.get("error", 0.0),
        rank=data.get("rank", 1),
        xg_rank=data.get("xg_rank"),
        xg_error=data.get("xg_error"),
        xg_notation=data.get("xg_notation"),
        resulting_position=_build_position(rp) if rp else None,
        from_xg_analysis=data.get("from_xg_analysis", True),
        was_played=data.get("was_played", False),
        player_win_pct=data.get("player_win_pct"),
        player_gammon_pct=data.get("player_gammon_pct"),
        player_backgammon_pct=data.get("player_backgammon_pct"),
        opponent_win_pct=data.get("opponent_win_pct"),
        opponent_gammon_pct=data.get("opponent_gammon_pct"),
        opponent_backgammon_pct=data.get("opponent_backgammon_pct"),
        cubeless_equity=data.get("cubeless_equity"),
    )


def decision_from_json(blob: str) -> Decision:
    """Deserialize a Decision from a JSON string written by decision_to_json."""
    payload = json.loads(blob)
    version = payload.get("version")
    if version != SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported AnalysisData schema version: {version!r} "
            f"(expected {SCHEMA_VERSION})"
        )
    data = payload["decision"]

    dice = data.get("dice")
    return Decision(
        position=_build_position(data["position"]),
        position_image_path=data.get("position_image_path"),
        xgid=data.get("xgid"),
        on_roll=Player(data["on_roll"]),
        dice=tuple(dice) if dice is not None else None,
        score_x=data.get("score_x", 0),
        score_o=data.get("score_o", 0),
        match_length=data.get("match_length", 0),
        crawford=data.get("crawford", False),
        cube_value=data.get("cube_value", 1),
        cube_owner=CubeState(data["cube_owner"]),
        decision_type=DecisionType(data["decision_type"]),
        candidate_moves=[_build_move(m) for m in data.get("candidate_moves", [])],
        cube_error=data.get("cube_error"),
        take_error=data.get("take_error"),
        cubeless_equity=data.get("cubeless_equity"),
        double_cubeless_equity=data.get("double_cubeless_equity"),
        xg_error_move=data.get("xg_error_move"),
        player_win_pct=data.get("player_win_pct"),
        player_gammon_pct=data.get("player_gammon_pct"),
        player_backgammon_pct=data.get("player_backgammon_pct"),
        opponent_win_pct=data.get("opponent_win_pct"),
        opponent_gammon_pct=data.get("opponent_gammon_pct"),
        opponent_backgammon_pct=data.get("opponent_backgammon_pct"),
        source_file=data.get("source_file"),
        source_description=data.get("source_description"),
        original_position_format=data.get("original_position_format"),
        game_number=data.get("game_number"),
        move_number=data.get("move_number"),
        note=data.get("note"),
    )
