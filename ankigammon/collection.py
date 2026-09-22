"""Collection files: which source files feed which Anki deck, and the import
filters each was read with.

Opening a collection re-imports every file into its deck, so a whole
collection can be rebuilt for new settings or a new version from the original
files, keeping the rollouts stored in them instead of re-analyzing XGIDs.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

FORMAT_NAME = "ankigammon-collection"
FORMAT_VERSION = 1


def same_file(a: str, b: str) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


@dataclass
class CollectionSource:
    """One source file imported into one deck.

    Thresholds of None fall back to the current import settings. players of
    None keeps both players' mistakes; otherwise only the named players'.
    """

    path: str
    checker_threshold: Optional[float] = None
    cube_threshold: Optional[float] = None
    players: Optional[List[str]] = None

    def to_dict(self, base_dir: Optional[Path] = None) -> dict:
        data: dict = {"path": _portable_path(self.path, base_dir)}
        if self.checker_threshold is not None:
            data["checker_threshold"] = self.checker_threshold
        if self.cube_threshold is not None:
            data["cube_threshold"] = self.cube_threshold
        if self.players is not None:
            data["players"] = list(self.players)
        return data

    @classmethod
    def from_dict(cls, data, base_dir: Optional[Path] = None) -> "CollectionSource":
        # A bare string is accepted so a hand-written collection can just list paths.
        if isinstance(data, str):
            data = {"path": data}
        if not isinstance(data, dict) or not isinstance(data.get("path"), str) or not data["path"].strip():
            raise ValueError(f"Each file entry needs a \"path\": {data!r}")

        path = Path(data["path"]).expanduser()
        if not path.is_absolute() and base_dir is not None:
            path = base_dir / path
        players = data.get("players")
        if players is not None and not (
            isinstance(players, list) and all(isinstance(p, str) for p in players)
        ):
            raise ValueError(f"\"players\" must be a list of names: {players!r}")
        return cls(
            path=os.path.normpath(str(path)),
            checker_threshold=_optional_float(data, "checker_threshold"),
            cube_threshold=_optional_float(data, "cube_threshold"),
            players=players,
        )


def _optional_float(data: dict, key: str) -> Optional[float]:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"\"{key}\" must be a number: {value!r}")
    return float(value)


def _portable_path(path: str, base_dir: Optional[Path]) -> str:
    """Files next to or below the collection file are stored relative to it, so
    the collection and its files can be moved together; anything else stays
    absolute rather than becoming a fragile chain of '..'."""
    if base_dir is not None:
        try:
            relative = os.path.relpath(path, base_dir)
        except ValueError:
            relative = None  # Windows: different drive
        if relative is not None and not relative.startswith(os.pardir):
            return Path(relative).as_posix()
    return Path(path).as_posix()


def sources_to_dict(
    sources: Dict[str, List[CollectionSource]], base_dir: Optional[Path] = None
) -> Dict[str, List[dict]]:
    return {deck: [s.to_dict(base_dir) for s in entries] for deck, entries in sources.items()}


def sources_from_dict(
    decks, base_dir: Optional[Path] = None
) -> Dict[str, List[CollectionSource]]:
    if not isinstance(decks, dict):
        raise ValueError("\"decks\" must map deck names to lists of files")
    result: Dict[str, List[CollectionSource]] = {}
    for deck, entries in decks.items():
        if not isinstance(deck, str) or not deck.strip():
            raise ValueError(f"Invalid deck name: {deck!r}")
        if not isinstance(entries, list):
            raise ValueError(f"Deck \"{deck}\" must list its files in [ ]")
        result[deck.strip()] = [CollectionSource.from_dict(e, base_dir) for e in entries]
    return result


def save_collection(path: str, sources: Dict[str, List[CollectionSource]]) -> None:
    target = Path(path)
    payload = {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "decks": sources_to_dict(sources, target.parent.resolve()),
    }
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_collection(path: str) -> Dict[str, List[CollectionSource]]:
    """Read a collection file. Raises ValueError when it is not one."""
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
    return sources_from_dict(payload.get("decks", {}), source.parent.resolve())
