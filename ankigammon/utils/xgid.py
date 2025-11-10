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

    # Parse position (encoding is perspective-dependent based on turn)
    position = _parse_position_string(position_str, turn)

    # Parse metadata
    metadata = {}

    # Cube value (2^cube_value_log)
    cube_value = 2 ** cube_value_log if cube_value_log >= 0 else 1
    metadata['cube_value'] = cube_value

    # Cube owner is perspective-dependent (flipped when X is on roll)
    if cube_position == 0:
        cube_state = CubeState.CENTERED
    elif cube_position == -1:
        cube_state = CubeState.X_OWNS if turn == 1 else CubeState.O_OWNS
    else:  # cube_position == 1
        cube_state = CubeState.O_OWNS if turn == 1 else CubeState.X_OWNS
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

    The 26-character position string is encoded from the perspective of the player on roll:

    When turn=1 (O on roll):
    - Char 0: X's bar, Chars 1-24: points 1-24, Char 25: O's bar
    - lowercase = X checkers, uppercase = O checkers

    When turn=-1 (X on roll):
    - Char 0: O's bar, Chars 1-24: points in reverse (24-1), Char 25: X's bar
    - lowercase = X checkers, uppercase = O checkers

    Internal model (always consistent):
    - points[0] = X's bar (TOP player)
    - points[1-24] = board points (1 = O's home, 24 = X's home)
    - points[25] = O's bar (BOTTOM player)
    """
    if len(pos_str) != 26:
        raise ValueError(f"Position string must be 26 characters, got {len(pos_str)}")

    position = Position()

    if turn == 1:
        # O on roll: standard perspective
        position.points[0] = _decode_checker_count(pos_str[0], turn)
        position.points[25] = _decode_checker_count(pos_str[25], turn)

        for i in range(1, 25):
            position.points[i] = _decode_checker_count(pos_str[i], turn)
    else:
        # X on roll: flipped perspective - bars and points are reversed
        position.points[0] = _decode_checker_count(pos_str[25], turn)  # X's bar
        position.points[25] = _decode_checker_count(pos_str[0], turn)  # O's bar

        # Board points: reverse mapping
        for i in range(1, 25):
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

    The uppercase/lowercase mapping depends on whose turn it is:

    When turn=1 (O on roll):
    - lowercase = X checkers (positive)
    - uppercase = O checkers (negative)

    When turn=-1 (X on roll):
    - lowercase = O checkers (negative)
    - uppercase = X checkers (positive)

    Args:
        char: The character to decode
        turn: 1 if O on roll, -1 if X on roll

    Returns:
        Checker count (positive for X, negative for O, 0 for empty)
    """
    if char == '-':
        return 0

    count = 0
    if 'a' <= char <= 'p':
        count = ord(char) - ord('a') + 1
        is_lowercase = True
    elif 'A' <= char <= 'P':
        count = ord(char) - ord('A') + 1
        is_lowercase = False
    else:
        raise ValueError(f"Invalid position character: {char}")

    if turn == 1:
        # O's perspective: lowercase=X, uppercase=O
        return count if is_lowercase else -count
    else:
        # X's perspective: lowercase=O, uppercase=X
        return -count if is_lowercase else count


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
    # Turn: 1 = BOTTOM (O), -1 = TOP (X)
    turn = 1 if on_roll == Player.O else -1

    # Encode position (turn-dependent)
    pos_str = _encode_position_string(position, turn)

    # Cube value as log2
    cube_value_log = 0
    temp_cube = cube_value
    while temp_cube > 1:
        temp_cube //= 2
        cube_value_log += 1

    # Cube position is perspective-dependent (flipped when X is on roll)
    if cube_owner == CubeState.CENTERED:
        cube_position = 0
    elif turn == 1:
        cube_position = -1 if cube_owner == CubeState.X_OWNS else 1
    else:
        cube_position = 1 if cube_owner == CubeState.X_OWNS else -1

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


def _encode_position_string(position: Position, turn: int) -> str:
    """
    Encode a position to the 26-character XGID format.

    The encoding depends on whose turn it is:

    When turn=1 (O on roll):
    - Char 0: X's bar (points[0])
    - Chars 1-24: points in standard order (points[1-24])
    - Char 25: O's bar (points[25])

    When turn=-1 (X on roll):
    - Char 0: O's bar (points[25])
    - Chars 1-24: points in reversed order
    - Char 25: X's bar (points[0])

    Args:
        position: The position to encode
        turn: 1 if O on roll, -1 if X on roll

    Returns:
        26-character position string
    """
    chars = [''] * 26

    if turn == 1:
        # O on roll: standard perspective
        chars[0] = _encode_checker_count(position.points[0], turn)
        chars[25] = _encode_checker_count(position.points[25], turn)

        for i in range(1, 25):
            chars[i] = _encode_checker_count(position.points[i], turn)
    else:
        # X on roll: flipped perspective - bars and points are reversed
        chars[0] = _encode_checker_count(position.points[25], turn)  # O's bar
        chars[25] = _encode_checker_count(position.points[0], turn)  # X's bar

        # Board points: reverse mapping
        for i in range(1, 25):
            chars[25 - i] = _encode_checker_count(position.points[i], turn)

    return ''.join(chars)


def _encode_checker_count(count: int, turn: int) -> str:
    """
    Encode checker count to a single character.

    The uppercase/lowercase mapping depends on whose turn it is:

    When turn=1 (O on roll):
    - 0 = '-'
    - positive (X) = lowercase 'a' to 'p'
    - negative (O) = uppercase 'A' to 'P'

    When turn=-1 (X on roll):
    - 0 = '-'
    - positive (X) = uppercase 'A' to 'P'
    - negative (O) = lowercase 'a' to 'p'

    Args:
        count: Checker count (positive for X, negative for O, 0 for empty)
        turn: 1 if O on roll, -1 if X on roll

    Returns:
        Single character encoding
    """
    if count == 0:
        return '-'

    abs_count = abs(count)
    if abs_count > 16:
        abs_count = 16

    if turn == 1:
        # O's perspective: lowercase=X, uppercase=O
        if count > 0:
            return chr(ord('a') + abs_count - 1)
        else:
            return chr(ord('A') + abs_count - 1)
    else:
        # X's perspective: uppercase=X, lowercase=O
        if count > 0:
            return chr(ord('A') + abs_count - 1)
        else:
            return chr(ord('a') + abs_count - 1)
