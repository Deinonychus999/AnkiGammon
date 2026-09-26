"""Study packs: positions and their analysis in one JSON document.

This is the `ankigammon-position-pack` format that the AnkiGammon trainer
(ankigammon.com/train) studies and the community decks API serves. The
website repo documents it in worker/README.md and builds the same document
from an .apkg in js/apkg-reader.js, so the trainer reads packs from either
source the same way. Each position is its XGID, its tags, and the Decision
as decision_serialize writes it.
"""

import json
from pathlib import Path
from typing import List, Optional, Sequence

from ankigammon.anki.decision_serialize import decision_to_json
from ankigammon.models import Decision

PACK_FORMAT = "ankigammon-position-pack"
PACK_VERSION = 1


def decision_tags(decision: Decision) -> List[str]:
    """Tags for a position, the same on Anki cards and in study packs."""
    tags = ["ankigammon", "backgammon", decision.decision_type.value]
    if decision.match_length > 0:
        tags.append(f"match_{decision.match_length}pt")
    else:
        tags.append("unlimited_game")
    if decision.cube_value > 1:
        tags.append(f"cube_{decision.cube_value}")
    return tags


def build_pack(decisions: Sequence[Decision], title: str,
               extras: Optional[Sequence[Optional[dict]]] = None) -> dict:
    """The pack for `decisions`. Positions without an XGID or without
    analysis are left out: the trainer can neither draw nor grade them.

    `extras`, one per decision, adds the optional analyses a card back would
    show (CardGenerator.study_extras); a position gets them under "extras".
    """
    positions = []
    for i, d in enumerate(decisions):
        if not (d.xgid and d.candidate_moves):
            continue
        position = {
            "xgid": d.xgid,
            "tags": decision_tags(d),
            "analysis": json.loads(decision_to_json(d)),
        }
        if extras is not None and extras[i]:
            position["extras"] = extras[i]
        positions.append(position)
    return {
        "format": PACK_FORMAT,
        "version": PACK_VERSION,
        "deck": {"title": title},
        "positions": positions,
    }


def save_pack(pack: dict, path: Path) -> int:
    """Write a built pack to `path` and return how many positions it holds."""
    Path(path).write_text(json.dumps(pack, separators=(",", ":")), encoding="utf-8")
    return len(pack["positions"])


def write_pack(decisions: Sequence[Decision], path: Path, title: str) -> int:
    """Write the pack to `path` and return how many positions it holds."""
    return save_pack(build_pack(decisions, title), path)
