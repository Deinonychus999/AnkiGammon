"""Which optional analysis blocks a card should carry, and whether it does.

Three blocks are rendered only when a setting asks for them, and each is
omitted when it cannot be built. A card therefore cannot say on its own
whether a block is absent by choice or by failure. The two matrices are
identified by their table class. The cube-position comparison is omitted by
design when the best move is the same at every cube position, so it carries
a marker for that case and another for failure; a card with neither predates
the markers and is left alone.
"""

from typing import List, Optional

CUBE_MATRIX_MARKER = "score-matrix-table"
MOVE_MATRIX_MARKER = "move-score-matrix-table"
CUBE_COMPARISON_MARKER = "cube-matrix-details"
CUBE_COMPARISON_SAME_MARKER = "<!-- cube-comparison: same -->"
CUBE_COMPARISON_FAILED_MARKER = "<!-- cube-comparison: failed -->"

OPTIONAL_BLOCK_MARKERS = {
    CUBE_MATRIX_MARKER: "score matrix",
    MOVE_MATRIX_MARKER: "move score matrix",
    CUBE_COMPARISON_MARKER: "cube-position comparison",
}


def is_cube_xgid(xgid: str) -> Optional[bool]:
    """True for a cube action, False for a checker play, None if unreadable."""
    parts = xgid.split("=", 1)[-1].split(":")
    if len(parts) < 5 or len(parts[4]) != 2:
        return None
    return parts[4] == "00"


def missing_optional_blocks(
    back_html: str,
    is_cube: bool,
    settings,
    match_length: Optional[int] = None,
) -> List[str]:
    """Blocks the settings call for that the card does not have.

    A 1-point match has a dead cube, so nothing can be built for it and it is
    never reported. The cube-position comparison is reported only when the
    card itself says it failed.
    """
    if match_length == 1:
        return []
    missing: List[str] = []
    if is_cube:
        if settings.generate_score_matrix and CUBE_MATRIX_MARKER not in back_html:
            missing.append(OPTIONAL_BLOCK_MARKERS[CUBE_MATRIX_MARKER])
        return missing
    if settings.generate_move_score_matrix and MOVE_MATRIX_MARKER not in back_html:
        missing.append(OPTIONAL_BLOCK_MARKERS[MOVE_MATRIX_MARKER])
    if settings.generate_move_cube_matrix and CUBE_COMPARISON_FAILED_MARKER in back_html:
        missing.append(OPTIONAL_BLOCK_MARKERS[CUBE_COMPARISON_MARKER])
    return missing


def lost_optional_blocks(old_back: str, new_back: str) -> List[str]:
    """Blocks the old card had that the new rendering lacks."""
    return [
        name for marker, name in OPTIONAL_BLOCK_MARKERS.items()
        if marker in old_back and marker not in new_back
    ]
