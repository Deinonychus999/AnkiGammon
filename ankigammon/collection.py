"""Collection files: a snapshot of the positions loaded in AnkiGammon.

Positions imported from a file are saved as a reference to that file, with
the import filters used and which deck each of its positions sits in. Opening
the collection re-imports the file, so analysis added to it since (such as
new rollouts) is picked up instead of re-analyzing XGIDs. Positions that came
from no file (pasted analysis or position IDs) are saved whole.
"""

import json
import os
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ankigammon.anki.decision_serialize import decision_from_json, decision_to_json
from ankigammon.models import Decision

FORMAT_NAME = "ankigammon-collection"
FORMAT_VERSION = 1


def file_key(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


@dataclass
class CollectionSource:
    """A source file and the import filters it was read with.

    Thresholds of None fall back to the current import settings. players of
    None keeps both players' mistakes; otherwise only the named players'.
    placement maps each deck to the XGIDs of this file's positions in it.
    """

    path: str
    checker_threshold: Optional[float] = None
    cube_threshold: Optional[float] = None
    players: Optional[List[str]] = None
    placement: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class Collection:
    files: List[CollectionSource] = field(default_factory=list)
    positions: Dict[str, List[Decision]] = field(default_factory=dict)

    def deck_names(self) -> List[str]:
        names = [deck for source in self.files for deck in source.placement]
        names += list(self.positions)
        return list(dict.fromkeys(names))

    @property
    def position_count(self) -> int:
        return sum(len(xgids) for s in self.files for xgids in s.placement.values()) + sum(
            len(decisions) for decisions in self.positions.values()
        )


def build_collection(
    grouped: Dict[str, List[Decision]], import_filters: Dict[str, CollectionSource]
) -> Collection:
    """Snapshot the loaded positions, given each imported file's filters keyed by file_key."""
    files: Dict[str, CollectionSource] = {}
    positions: Dict[str, List[Decision]] = {}
    for deck, decisions in grouped.items():
        for decision in decisions:
            key = file_key(decision.source_file) if decision.source_file else None
            imported = import_filters.get(key) if key else None
            if imported is None or not decision.xgid:
                positions.setdefault(deck, []).append(decision)
                continue
            if key not in files:
                files[key] = CollectionSource(
                    imported.path, imported.checker_threshold, imported.cube_threshold, imported.players
                )
            files[key].placement.setdefault(deck, []).append(decision.xgid)
    return Collection(list(files.values()), positions)


def place_decisions(
    decisions: List[Decision], placement: Dict[str, List[str]]
) -> Tuple[Dict[str, List[Decision]], int, int]:
    """Put a re-imported file's positions back into their saved decks.

    Returns (decisions by deck, positions not in the snapshot, saved positions
    not found). Positions not in the snapshot were deleted by the user, or are
    new because the file's analysis changed; they are left out either way.
    """
    wanted: Dict[str, Counter] = {deck: Counter(xgids) for deck, xgids in placement.items()}
    placed: Dict[str, List[Decision]] = {}
    unplaced = 0
    for decision in decisions:
        deck = next((d for d, counts in wanted.items() if counts[decision.xgid] > 0), None)
        if deck is None:
            unplaced += 1
            continue
        wanted[deck][decision.xgid] -= 1
        placed.setdefault(deck, []).append(decision)
    missing = sum(sum(counts.values()) for counts in wanted.values())
    return placed, unplaced, missing


def _portable_path(path: str, base_dir: Path) -> str:
    """Files next to or below the collection file are stored relative to it, so
    the collection and its files can be moved together; anything else stays
    absolute rather than becoming a fragile chain of '..'."""
    try:
        relative = os.path.relpath(path, base_dir)
    except ValueError:
        relative = None  # Windows: different drive
    if relative is not None and not relative.startswith(os.pardir):
        return Path(relative).as_posix()
    return Path(path).as_posix()


def save_collection(path: str, collection: Collection) -> None:
    target = Path(path)
    base_dir = target.parent.resolve()
    files = []
    for source in collection.files:
        entry: dict = {"path": _portable_path(source.path, base_dir)}
        if source.checker_threshold is not None:
            entry["checker_threshold"] = source.checker_threshold
        if source.cube_threshold is not None:
            entry["cube_threshold"] = source.cube_threshold
        if source.players is not None:
            entry["players"] = list(source.players)
        entry["decks"] = source.placement
        files.append(entry)
    payload = {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "files": files,
        "positions": {
            deck: [json.loads(decision_to_json(d)) for d in decisions]
            for deck, decisions in collection.positions.items()
        },
    }
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_collection(path: str) -> Collection:
    """Read a collection file. Raises ValueError when it is not a valid one."""
    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        raise ValueError(f"Not valid JSON: {e}") from e
    if not isinstance(payload, dict) or payload.get("format") != FORMAT_NAME:
        raise ValueError("Not an AnkiGammon collection file")
    version = payload.get("version")
    if not isinstance(version, int) or version > FORMAT_VERSION:
        raise ValueError(
            f"Collection file version {version!r} is newer than this AnkiGammon "
            f"supports ({FORMAT_VERSION}); please update AnkiGammon"
        )

    base_dir = source.parent.resolve()
    files = payload.get("files", [])
    positions = payload.get("positions", {})
    if not isinstance(files, list) or not isinstance(positions, dict):
        raise ValueError("\"files\" must be a list and \"positions\" must map decks to lists")
    try:
        return Collection(
            files=[_load_source(entry, base_dir) for entry in files],
            positions={
                deck: [decision_from_json(json.dumps(blob)) for blob in blobs]
                for deck, blobs in positions.items()
            },
        )
    except (KeyError, TypeError, AttributeError) as e:
        raise ValueError(f"Malformed collection entry: {e!r}") from e


def _load_source(entry, base_dir: Path) -> CollectionSource:
    if not isinstance(entry, dict) or not isinstance(entry.get("path"), str) or not entry["path"].strip():
        raise ValueError(f"Each file entry needs a \"path\": {entry!r}")
    path = Path(entry["path"]).expanduser()
    if not path.is_absolute():
        path = base_dir / path

    players = entry.get("players")
    if players is not None and not (
        isinstance(players, list) and all(isinstance(p, str) for p in players)
    ):
        raise ValueError(f"\"players\" must be a list of names: {players!r}")

    placement = entry.get("decks")
    if not isinstance(placement, dict) or not all(
        isinstance(xgids, list) and all(isinstance(x, str) for x in xgids)
        for xgids in placement.values()
    ):
        raise ValueError(f"\"decks\" of {entry['path']} must map deck names to lists of XGIDs")

    return CollectionSource(
        path=os.path.normpath(str(path)),
        checker_threshold=_optional_float(entry, "checker_threshold"),
        cube_threshold=_optional_float(entry, "cube_threshold"),
        players=players,
        placement={deck.strip(): list(xgids) for deck, xgids in placement.items()},
    )


def _optional_float(data: dict, key: str) -> Optional[float]:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"\"{key}\" must be a number: {value!r}")
    return float(value)
