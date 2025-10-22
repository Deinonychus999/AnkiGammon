"""XGID format parsing and encoding.

XGID (eXtreme Gammon ID) is a compact text representation of a backgammon position.

Format: XGID=PPPPPPPPPPPPPPPPPPPPPPPPPP:CV:CP:T:D:S1:S2:CJ:ML:MC

Fields:
1. Position (26 chars):
   - Char 0: bar for TOP player
   - Chars 1-24: points 1-24 (from BOTTOM player's perspective)
   - Char 25: bar for BOTTOM player
   - 'A'-'P': BOTTOM player's checkers (1-16)
   - 'a'-'p': TOP player's checkers (1-16)
   - '-': empty point

2. Cube Value (CV): 2^CV (0=1, 1=2, 2=4, etc.)

3. Cube Position (CP):
   - 1: owned by BOTTOM player
   - 0: centered
   - -1: owned by TOP player

4. Turn (T):
   - 1: BOTTOM player's turn
   - -1: TOP player's turn

5. Dice (D):
   - 00: player to roll or double
   - D: player doubled, opponent must take/drop
   - B: player doubled, opponent beavered
   - R: doubled, beavered, and raccooned
   - xx: rolled dice (e.g., 63, 35, 11)

6. Score 1 (S1): BOTTOM player's score
7. Score 2 (S2): TOP player's score
8. Crawford/Jacoby (CJ): Crawford rule (match) or Jacoby rule (money)
9. Match Length (ML): 0 for money games
10. Max Cube (MC): Maximum cube value (2^MC)

Note: In our internal model, we use O for BOTTOM player and X for TOP player.
"""

import re
from typing import Optional, Tuple

from ankigammon.models import Position, Player, CubeState


def parse_xgid(xgid: str) -> Tuple[Position, dict]:
    """
    Parse an XGID string into a Position and metadata.

    Args:
        xgid: XGID string (e.g., "XGID=-a-B--C-dE---eE---c-e----B-:1:0:1:63:0:0:0:0:10")

    Returns:
        Tuple of (Position, metadata_dict)
    """
    # Remove "XGID=" prefix if present
    if xgid.startswith("XGID="):
        xgid = xgid[5:]

    # Split into components
    parts = xgid.split(':')
    if len(parts) < 9:
        raise ValueError(f"Invalid XGID format: expected 9+ parts, got {len(parts)}")

    position_str = parts[0]
    cube_value_log = int(parts[1])
    cube_position = int(parts[2])
    turn = int(parts[3])
    dice_str = parts[4]
    score_bottom = int(parts[5])
    score_top = int(parts[6])
    crawford_jacoby = int(parts[7]) if len(parts) > 7 else 0
    match_length = int(parts[8]) if len(parts) > 8 else 0
    max_cube = int(parts[9]) if len(parts) > 9 else 8

    # Parse position
    # CRITICAL: The position encoding depends on whose turn it is!
    # When turn=1 (BOTTOM/O on roll), the encoding is from O's perspective
    # When turn=-1 (TOP/X on roll), the encoding is from X's perspective
    # We need to pass the turn to correctly interpret the position
    position = _parse_position_string(position_str, turn)

    # Parse metadata
    metadata = {}

    # Cube value (2^cube_value_log)
    cube_value = 2 ** cube_value_log if cube_value_log >= 0 else 1
    metadata['cube_value'] = cube_value

    # Cube owner
    # CRITICAL: Like the position encoding, cube ownership is relative to perspective!
    # -1 = TOP player, 0 = centered, 1 = BOTTOM player
    # When turn=1 (O on roll): TOP=X, BOTTOM=O
    # When turn=-1 (X on roll): TOP=O, BOTTOM=X (SWAPPED!)
    if cube_position == 0:
        cube_state = CubeState.CENTERED
    elif turn == 1:
        # O's perspective (standard)
        if cube_position == -1:
            cube_state = CubeState.X_OWNS  # TOP = X
        else:  # cube_position == 1
            cube_state = CubeState.O_OWNS  # BOTTOM = O
    else:  # turn == -1
        # X's perspective (SWAPPED!)
        if cube_position == -1:
            cube_state = CubeState.O_OWNS  # TOP = O (in X's perspective)
        else:  # cube_position == 1
            cube_state = CubeState.X_OWNS  # BOTTOM = X (in X's perspective)
    metadata['cube_owner'] = cube_state

    # Turn: 1 = BOTTOM player (O), -1 = TOP player (X)
    on_roll = Player.O if turn == 1 else Player.X
    metadata['on_roll'] = on_roll

    # Dice
    dice_str = dice_str.upper().strip()
    if dice_str == '00':
        # Player to roll or double (no dice shown)
        pass
    elif dice_str in ['D', 'B', 'R']:
        # Cube action pending
        metadata['decision_type'] = 'cube_action'
    elif len(dice_str) == 2 and dice_str.isdigit():
        # Rolled dice
        d1 = int(dice_str[0])
        d2 = int(dice_str[1])
        if 1 <= d1 <= 6 and 1 <= d2 <= 6:
            metadata['dice'] = (d1, d2)

    # Score: in XGID, field 5 is bottom player, field 6 is top player
    # We map bottom=O, top=X
    metadata['score_o'] = score_bottom
    metadata['score_x'] = score_top

    # Match length
    metadata['match_length'] = match_length

    # Crawford/Jacoby
    metadata['crawford_jacoby'] = crawford_jacoby

    # Max cube
    metadata['max_cube'] = 2 ** max_cube if max_cube >= 0 else 256

    return position, metadata


def _parse_position_string(pos_str: str, turn: int) -> Position:
    """
    Parse the position encoding part of XGID.

    Format: 26 characters
    - Char 0: X's bar (TOP player) - ALWAYS, regardless of turn
    - Chars 1-24: points 1-24 (perspective depends on turn)
    - Char 25: O's bar (BOTTOM player) - ALWAYS, regardless of turn

    CRITICAL: The encoding perspective for BOARD POINTS depends on whose turn it is!
    - When turn=1 (O on roll): lowercase='X', uppercase='O', points in standard order
    - When turn=-1 (X on roll): lowercase='X', uppercase='O', points in REVERSED order

    Bar positions are always the same:
    - Char 0 is always X's bar
    - Char 25 is always O's bar

    In our internal model, we always use:
    - points[0] = X's bar (TOP player in standard orientation)
    - points[1-24] = board points (point 1 = O's home, point 24 = X's home)
    - points[25] = O's bar (BOTTOM player in standard orientation)
    """
    if len(pos_str) != 26:
        raise ValueError(f"Position string must be 26 characters, got {len(pos_str)}")

    position = Position()

    # Bar positions are ALWAYS the same regardless of turn
    # Char 0: X's bar
    # Char 25: O's bar
    position.points[0] = _decode_checker_count(pos_str[0], turn)
    position.points[25] = _decode_checker_count(pos_str[25], turn)

    if turn == 1:
        # O is on roll - encoding is from O's perspective (standard)
        # Chars 1-24: points 1-24
        for i in range(1, 25):
            position.points[i] = _decode_checker_count(pos_str[i], turn)
    else:
        # X is on roll - encoding is from X's perspective (FLIPPED!)
        # We need to flip the board to get to our internal model
        # Chars 1-24: points from X's perspective -> need to reverse

        # Board points - reverse the numbering and swap players
        for i in range(1, 25):
            # Point i in our model comes from point (25-i) in the XGID
            position.points[i] = _decode_checker_count(pos_str[25 - i], turn)

    # Calculate borne-off checkers (each player starts with 15)
    total_x = sum(count for count in position.points if count > 0)
    total_o = sum(abs(count) for count in position.points if count < 0)

    position.x_off = 15 - total_x
    position.o_off = 15 - total_o

    return position


def _decode_checker_count(char: str, turn: int) -> int:
    """
    Decode a single character to checker count.

    The interpretation depends on whose turn it is:
    - When turn=1 (O on roll): lowercase='X' (positive), uppercase='O' (negative)
    - When turn=-1 (X on roll): lowercase='X' (positive), uppercase='O' (negative) - SAME!

    CRITICAL: The uppercase/lowercase mapping to players does NOT change based on turn!
    What changes is the POINT NUMBERING (handled in _parse_position_string).

    Args:
        char: The character to decode
        turn: 1 if O on roll, -1 if X on roll

    Returns:
        Checker count (positive for X, negative for O, 0 for empty)
    """
    if char == '-':
        return 0
    elif 'a' <= char <= 'p':
        count = ord(char) - ord('a') + 1
        # lowercase ALWAYS = X (positive), regardless of turn
        return count  # X checkers (positive)
    elif 'A' <= char <= 'P':
        count = ord(char) - ord('A') + 1
        # uppercase ALWAYS = O (negative), regardless of turn
        return -count  # O checkers (negative)
    else:
        raise ValueError(f"Invalid position character: {char}")


def encode_xgid(
    position: Position,
    cube_value: int = 1,
    cube_owner: CubeState = CubeState.CENTERED,
    dice: Optional[Tuple[int, int]] = None,
    on_roll: Player = Player.O,
    score_x: int = 0,
    score_o: int = 0,
    match_length: int = 0,
    crawford_jacoby: int = 0,
    max_cube: int = 256,
) -> str:
    """
    Encode a position and metadata as an XGID string.

    Args:
        position: The position to encode
        cube_value: Doubling cube value
        cube_owner: Who owns the cube
        dice: Dice values (if any)
        on_roll: Player on roll
        score_x: TOP player's score
        score_o: BOTTOM player's score
        match_length: Match length (0 for money)
        crawford_jacoby: Crawford/Jacoby setting
        max_cube: Maximum cube value

    Returns:
        XGID string
    """
    # Encode position
    pos_str = _encode_position_string(position)

    # Cube value as log2
    cube_value_log = 0
    temp_cube = cube_value
    while temp_cube > 1:
        temp_cube //= 2
        cube_value_log += 1

    # Cube position: -1 = TOP (X), 0 = centered, 1 = BOTTOM (O)
    if cube_owner == CubeState.X_OWNS:
        cube_position = -1
    elif cube_owner == CubeState.O_OWNS:
        cube_position = 1
    else:
        cube_position = 0

    # Turn: 1 = BOTTOM (O), -1 = TOP (X)
    turn = 1 if on_roll == Player.O else -1

    # Dice
    if dice:
        dice_str = f"{dice[0]}{dice[1]}"
    else:
        dice_str = "00"

    # Max cube as log2
    max_cube_log = 0
    temp = max_cube
    while temp > 1:
        temp //= 2
        max_cube_log += 1

    # Build XGID
    xgid = (
        f"XGID={pos_str}:"
        f"{cube_value_log}:{cube_position}:{turn}:{dice_str}:"
        f"{score_o}:{score_x}:"
        f"{crawford_jacoby}:{match_length}:{max_cube_log}"
    )

    return xgid


def _encode_position_string(position: Position) -> str:
    """
    Encode a position to the 26-character XGID format.

    Format:
    - Char 0: TOP player's bar (our points[0])
    - Chars 1-24: board points
    - Char 25: BOTTOM player's bar (our points[25])
    """
    chars = []

    # Char 0: X's bar (TOP)
    chars.append(_encode_checker_count(position.points[0]))

    # Chars 1-24: board
    for i in range(1, 25):
        chars.append(_encode_checker_count(position.points[i]))

    # Char 25: O's bar (BOTTOM)
    chars.append(_encode_checker_count(position.points[25]))

    return ''.join(chars)


def _encode_checker_count(count: int) -> str:
    """
    Encode checker count to a single character.

    0 = '-'
    1 to 16 (positive, X/TOP) = 'a' to 'p'
    -1 to -16 (negative, O/BOTTOM) = 'A' to 'P'
    """
    if count == 0:
        return '-'
    elif count > 0:
        # TOP player (X) - positive -> 'a' to 'p'
        if count > 16:
            count = 16
        return chr(ord('a') + count - 1)
    else:
        # BOTTOM player (O) - negative -> 'A' to 'P'
        abs_count = abs(count)
        if abs_count > 16:
            abs_count = 16
        return chr(ord('A') + abs_count - 1)
