"""Pasted position IDs (XGID, GNU BG ID, OGID) as unanalyzed Decisions.

Qt-free, so the desktop's paste dialog and the browser version read a paste
the same way.
"""

from typing import List, Optional, Tuple

from ankigammon.models import CubeState, Decision, DecisionType, Player, Position
from ankigammon.utils.gnuid import parse_gnuid
from ankigammon.utils.ogid import parse_ogid
from ankigammon.utils.xgid import encode_xgid, parse_xgid

# A GNU BG Position ID is always exactly this long; a truncated Match ID
# after it is the common paste error worth naming.
GNUID_POSITION_ID_LEN = 14


def parse_position_id_lines(text: str) -> Tuple[List[Decision], List[str]]:
    """Parse pasted position IDs, keeping any prose pasted with them.

    A bare ID has none of the structure XGTextParser reads a note out of,
    so free-text lines are attached to the position they sit with: prose
    follows its position, except before the first ID where it leads one.

    Returns the decisions and the lines that looked like IDs but did not parse.
    """
    decisions: List[Decision] = []
    rejected: List[str] = []
    pending: List[str] = []
    current: Optional[Decision] = None

    def attach(target: Optional[Decision]) -> None:
        note = '\n'.join(pending).strip()
        pending.clear()
        if note and target is not None:
            target.note = f"{target.note}\n{note}" if target.note else note

    for line in (raw.strip() for raw in text.split('\n')):
        if not line:
            continue

        decision = parse_position_id(line)
        if decision is not None:
            attach(current if current is not None else decision)
            decisions.append(decision)
            current = decision
        elif looks_like_position_id(line):
            rejected.append(line)
        else:
            pending.append(line)

    attach(current)
    return decisions, rejected


def looks_like_position_id(line: str) -> bool:
    """Tell a mistyped ID from a note, so prose isn't reported as an error.

    Deliberately narrow: a line misread as an ID is only reported, but a
    line misread as prose would hide a real paste error.
    """
    if line.upper().startswith('XGID='):
        return True
    if any(ch.isspace() for ch in line):
        return False
    parts = line.split(':')
    # An OGID carries three or more fields; a GNU BG ID has one colon after
    # a fixed-length half. Short prose like "ND:+0.05" matches neither.
    return len(parts) > 2 or (len(parts) == 2 and len(parts[0]) == GNUID_POSITION_ID_LEN)


def describe_rejected_id(position_id: str) -> str:
    """Say why a position ID was rejected, not just that it was."""
    shown = position_id if len(position_id) <= 60 else position_id[:57] + "..."
    parts = position_id.split(':')
    # A 14-character Position ID means the user meant a GNU BG ID, so the
    # Match ID half is what to point at.
    if len(parts) == 2 and len(parts[0]) == 14 and len(parts[1]) != 12:
        return (
            f"{shown}\nGNU BG IDs need a 12-character Match ID; "
            f"this one has {len(parts[1])}. Copy it again from GnuBG "
            f"(Edit > Copy ID to Clipboard > GNU Backgammon ID)."
        )
    return f"{shown}\nNot a valid XGID, GNU BG ID, or OGID."


def parse_position_id(position_id: str) -> Optional[Decision]:
    """Parse a single position ID (XGID, GNUID, or OGID) into a Decision."""
    if 'XGID=' in position_id or ':' in position_id:
        try:
            position, metadata = parse_xgid(position_id)
            return decision_from_metadata(position, metadata, original_xgid=position_id)
        except Exception:
            pass

    if ':' in position_id:
        parts = position_id.split(':')
        if len(parts) >= 2 and len(parts[0]) == 14 and len(parts[1]) == 12:
            try:
                position, metadata = parse_gnuid(position_id)
                return decision_from_metadata(position, metadata, original_format="GNUID")
            except Exception:
                pass

    if ':' in position_id:
        try:
            position, metadata = parse_ogid(position_id)
            return decision_from_metadata(position, metadata, original_format="OGID")
        except Exception:
            pass

    return None


def decision_from_metadata(
    position: Position,
    metadata: dict,
    original_format: str = "XGID",
    original_xgid: Optional[str] = None,
) -> Decision:
    """Create an unanalyzed Decision from a parsed position and its metadata.

    When ``original_xgid`` is provided, it is stored verbatim as
    ``Decision.xgid`` to avoid lossy round-tripping through ``encode_xgid``
    (which would normalize away the cube-action flag and the max-cube
    field, causing GUID collisions in Anki for distinct user inputs).
    """
    # Crawford only exists in match play
    match_length = metadata.get('match_length', 0)
    crawford = False

    if match_length > 0:
        if 'crawford' in metadata and metadata['crawford']:
            crawford = True
        elif 'crawford_jacoby' in metadata and metadata['crawford_jacoby'] > 0:
            crawford = True
        elif 'match_modifier' in metadata and metadata['match_modifier'] == 'C':
            crawford = True

    if original_xgid is not None:
        xgid = original_xgid
    else:
        # Re-encode for OGID/GNUID inputs (analyzers consume XGID).
        # Pass max_cube through so it survives the round-trip.
        xgid = encode_xgid(
            position=position,
            cube_value=metadata.get('cube_value', 1),
            cube_owner=metadata.get('cube_owner', CubeState.CENTERED),
            dice=metadata.get('dice'),
            on_roll=metadata.get('on_roll', Player.X),
            score_x=metadata.get('score_x', 0),
            score_o=metadata.get('score_o', 0),
            match_length=metadata.get('match_length', 0),
            crawford_jacoby=metadata.get('crawford_jacoby', 1 if crawford else 0),
            max_cube=metadata.get('max_cube', 256),
        )

    return Decision(
        position=position,
        xgid=xgid,
        on_roll=metadata.get('on_roll', Player.X),
        dice=metadata.get('dice'),
        score_x=metadata.get('score_x', 0),
        score_o=metadata.get('score_o', 0),
        match_length=metadata.get('match_length', 0),
        crawford=crawford,
        cube_value=metadata.get('cube_value', 1),
        cube_owner=metadata.get('cube_owner', CubeState.CENTERED),
        decision_type=DecisionType.CUBE_ACTION if not metadata.get('dice') else DecisionType.CHECKER_PLAY,
        candidate_moves=[],
        original_position_format=original_format
    )
