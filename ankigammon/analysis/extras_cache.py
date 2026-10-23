"""On-disk cache of the optional analysis tables behind a card.

The score matrix, move score matrix and cube-position comparison cost one
engine request per cell or column, and a HedgeHog request spends allowance. A
card made again from the same position (a regenerate after a theme change, a
re-export, a collection opened afresh) finds them here instead of asking the
engine. One small JSON file per table, named by a hash of everything the table
depends on, so a different engine, depth or matrix size never shares an entry.
"""

import hashlib
import json
import logging
import os
from dataclasses import asdict
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from ankigammon.analysis.move_cube_matrix import CubeMatrixColumn, MoveAtCubeState
from ankigammon.analysis.move_score_matrix import MoveAtScore, MoveScoreMatrixColumn
from ankigammon.analysis.score_matrix import ScoreMatrixCell, UnlimitedReference

logger = logging.getLogger(__name__)

CACHE_VERSION = 1

KIND_SCORE_MATRIX = "score_matrix"
KIND_MOVE_SCORE_MATRIX = "move_score_matrix"
KIND_MOVE_CUBE_MATRIX = "move_cube_matrix"


def _entry_name(kind: str, key: dict) -> str:
    canonical = json.dumps([CACHE_VERSION, kind, key], sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:40] + ".json"


class ExtrasCache:
    def __init__(self, directory: Path):
        self.directory = Path(directory)

    @classmethod
    def default(cls) -> "ExtrasCache":
        return cls(Path.home() / ".ankigammon" / "analysis_cache")

    def get(self, kind: str, key: dict) -> Optional[dict]:
        path = self.directory / _entry_name(kind, key)
        try:
            entry = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(entry, dict) or entry.get("kind") != kind or entry.get("key") != key:
            return None
        data = entry.get("data")
        return data if isinstance(data, dict) else None

    def put(self, kind: str, key: dict, data: dict) -> None:
        """Best effort: a cache that cannot be written only costs a later request."""
        path = self.directory / _entry_name(kind, key)
        temp = path.with_suffix(".tmp")
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            temp.write_text(
                json.dumps({"kind": kind, "key": key, "data": data}, ensure_ascii=False),
                encoding="utf-8",
            )
            os.replace(temp, path)
        except (OSError, TypeError, ValueError):
            logger.warning("Could not write analysis cache entry %s", path, exc_info=True)
            try:
                temp.unlink()
            except OSError:
                pass

    def stats(self) -> Tuple[int, int]:
        """(entries, bytes) currently stored."""
        count = size = 0
        try:
            for path in self.directory.glob("*.json"):
                count += 1
                size += path.stat().st_size
        except OSError:
            pass
        return count, size

    def clear(self) -> int:
        """Delete every entry; returns how many were removed."""
        removed = 0
        try:
            for path in self.directory.glob("*.json"):
                try:
                    path.unlink()
                    removed += 1
                except OSError:
                    pass
        except OSError:
            pass
        return removed


def _cell(data: dict) -> ScoreMatrixCell:
    return ScoreMatrixCell(**data)


def encode_score_matrix(matrix: List[List[ScoreMatrixCell]], unlimited: Optional[UnlimitedReference]) -> dict:
    return {
        "matrix": [[asdict(cell) for cell in row] for row in matrix],
        "unlimited": asdict(unlimited) if unlimited is not None else None,
    }


def decode_score_matrix(data: dict) -> Tuple[List[List[ScoreMatrixCell]], Optional[UnlimitedReference]]:
    matrix = [[_cell(cell) for cell in row] for row in data["matrix"]]
    raw = data["unlimited"]
    unlimited = None
    if raw is not None:
        jacoby = raw.get("jacoby")
        unlimited = UnlimitedReference(
            no_jacoby=_cell(raw["no_jacoby"]),
            jacoby=_cell(jacoby) if jacoby is not None else None,
        )
    return matrix, unlimited


def encode_columns(columns: list) -> dict:
    return {"columns": [asdict(column) for column in columns]}


def decode_move_score_columns(data: dict) -> List[MoveScoreMatrixColumn]:
    return [
        MoveScoreMatrixColumn(
            score_type=column["score_type"],
            top_moves=[MoveAtScore(**move) for move in column["top_moves"]],
        )
        for column in data["columns"]
    ]


def decode_move_cube_columns(data: dict) -> List[CubeMatrixColumn]:
    return [
        CubeMatrixColumn(
            cube_type=column["cube_type"],
            top_moves=[MoveAtCubeState(**move) for move in column["top_moves"]],
        )
        for column in data["columns"]
    ]


def cached_or_compute(
    cache: Optional[ExtrasCache],
    kind: str,
    key: Callable[[], dict],
    compute: Callable[[], object],
    encode: Callable[[object], dict],
    decode: Callable[[dict], object],
    is_complete: Callable[[object], bool] = lambda result: True,
):
    """The stored table for `key`, else `compute()`'s result, stored when complete.

    A stored entry that no longer reads back is treated as absent and replaced.
    `key` is a callable so a run without a cache never builds it.
    """
    if cache is None:
        return compute()
    key = key()
    hit = cache.get(kind, key)
    if hit is not None:
        try:
            return decode(hit)
        except (KeyError, TypeError, ValueError, AttributeError):
            logger.warning("Ignoring unreadable analysis cache entry for %s", kind, exc_info=True)
    result = compute()
    if result is not None and is_complete(result):
        try:
            data = encode(result)
        except (TypeError, AttributeError, ValueError):
            logger.warning("Could not store %s in the analysis cache", kind, exc_info=True)
        else:
            cache.put(kind, key, data)
    return result
