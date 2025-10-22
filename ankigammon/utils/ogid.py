"""OGID format parsing and encoding.

OGID (OpenGammon Position ID) is a colon-separated format for representing
complete backgammon board states.

Format: P1:P2:CUBE[:DICE[:TURN[:STATE[:S1[:S2[:ML[:MID[:NCHECKERS]]]]]]]]

Fields:
1. P1 (White/X checkers): Base-26 encoded positions with repeated characters
2. P2 (Black/O checkers): Base-26 encoded positions with repeated characters
3. CUBE: Three-character cube state (owner, value, action)
4. DICE: Two-character dice roll (optional)
5. TURN: Player to move - W or B (optional)
6. STATE: Two-character game state (optional)
7. S1: White/X score (optional)
8. S2: Black/O score (optional)
9. ML: Match length with modifiers (optional)
10. MID: Move ID (optional)
11. NCHECKERS: Number of checkers per side (optional, default 15)

Position encoding uses base-26:
- Characters '0'-'9' = points 0-9
- Characters 'a'-'p' = points 10-25
- Point 0 = White's bar (X in our model)
- Points 1-24 = board points
- Point 25 = Black's bar (O in our model)
- Repeated characters = multiple checkers on same point

Example starting position:
  White: 11jjjjjhhhccccc (2 on pt1, 5 on pt9, 3 on pt17, 5 on pt12)
  Black: ooddddd88866666 (2 on pt24, 5 on pt13, 3 on pt8, 5 on pt6)
  Full: 11jjjjjhhhccccc:ooddddd88866666:N0N::W:IW:0:0:1:0

Note: In our internal model:
  - White = Player.X (TOP player)
  - Black = Player.O (BOTTOM player)
  - Positive values = X checkers
  - Negative values = O checkers
"""

import re
from typing import Optional, Tuple, Dict

from ankigammon.models import Position, Player, CubeState


# Character to point mapping for base-26 encoding
def _char_to_point(char: str) -> int:
    """Convert a character to a point number (0-25)."""
    if '0' <= char <= '9':
        return ord(char) - ord('0')
    elif 'a' <= char <= 'p':
        return ord(char) - ord('a') + 10
    else:
        raise ValueError(f"Invalid position character: {char}")


def _point_to_char(point: int) -> str:
    """Convert a point number (0-25) to a character."""
    if 0 <= point <= 9:
        return chr(ord('0') + point)
    elif 10 <= point <= 25:
        return chr(ord('a') + point - 10)
    else:
        raise ValueError(f"Invalid point number: {point}")


def parse_ogid(ogid: str) -> Tuple[Position, Dict]:
    """
    Parse an OGID string into a Position and metadata.

    Args:
        ogid: OGID string (e.g., "11jjjjjhhhccccc:ooddddd88866666:N0N::W:IW:0:0:1:0")

    Returns:
        Tuple of (Position, metadata_dict)
    """
    # Remove "OGID=" prefix if present
    if ogid.upper().startswith("OGID="):
        ogid = ogid[5:]

    # Split into components
    parts = ogid.split(':')
    if len(parts) < 3:
        raise ValueError(f"Invalid OGID format: expected at least 3 parts, got {len(parts)}")

    white_pos = parts[0]  # White/X checkers
    black_pos = parts[1]  # Black/O checkers
    cube_str = parts[2]   # Cube state

    # Parse position
    position = _parse_ogid_position(white_pos, black_pos)

    # Parse metadata
    metadata = {}

    # Parse cube state (3 characters: owner, value, action)
    if len(cube_str) == 3:
        cube_owner_char = cube_str[0]
        cube_value_char = cube_str[1]
        cube_action_char = cube_str[2]

        # Cube value: 0->1, 1->2, 2->4, etc.
        cube_value_log = int(cube_value_char)
        metadata['cube_value'] = 2 ** cube_value_log

        # Cube owner: W=White/X, B=Black/O, N=Neutral, D=Dead
        if cube_owner_char == 'W':
            metadata['cube_owner'] = CubeState.X_OWNS  # White = X in our model
        elif cube_owner_char == 'B':
            metadata['cube_owner'] = CubeState.O_OWNS  # Black = O in our model
        elif cube_owner_char == 'N':
            metadata['cube_owner'] = CubeState.CENTERED
        else:  # D or ?
            metadata['cube_owner'] = CubeState.CENTERED  # Default to centered

        # Cube action (O=Offered, T=Taken, P=Passed, N=Normal)
        metadata['cube_action'] = cube_action_char

    # Parse optional fields
    if len(parts) > 3 and parts[3]:
        # Field 4: Dice
        dice_str = parts[3]
        if len(dice_str) == 2 and dice_str.isdigit():
            d1 = int(dice_str[0])
            d2 = int(dice_str[1])
            if 1 <= d1 <= 6 and 1 <= d2 <= 6:
                metadata['dice'] = (d1, d2)

    if len(parts) > 4 and parts[4]:
        # Field 5: Color (W or B) - represents who SENT the position
        # In OGID protocol, this is the player who supplied the position,
        # which is the OPPOSITE of who's on roll (except for cube decisions)
        # We invert the color to get the actual player on roll
        turn_str = parts[4].upper()
        if turn_str == 'W':
            # W sent position → B is on roll
            metadata['on_roll'] = Player.O  # Black = O
        elif turn_str == 'B':
            # B sent position → W is on roll
            metadata['on_roll'] = Player.X  # White = X

    if len(parts) > 5 and parts[5]:
        # Field 6: Game state (e.g., IW, FB)
        metadata['game_state'] = parts[5]

    if len(parts) > 6 and parts[6]:
        # Field 7: White/X score
        metadata['score_x'] = int(parts[6])

    if len(parts) > 7 and parts[7]:
        # Field 8: Black/O score
        metadata['score_o'] = int(parts[7])

    if len(parts) > 8 and parts[8]:
        # Field 9: Match length (e.g., "7", "5C", "9G15")
        match_str = parts[8]
        match_regex = re.compile(r'(\d+)([LCG]?)(\d*)')
        match = match_regex.match(match_str)
        if match:
            metadata['match_length'] = int(match.group(1))
            if match.group(2):
                metadata['match_modifier'] = match.group(2)  # L, C, or G
            if match.group(3):
                metadata['match_max_games'] = int(match.group(3))

    if len(parts) > 9 and parts[9]:
        # Field 10: Move ID
        metadata['move_id'] = int(parts[9])

    if len(parts) > 10 and parts[10]:
        # Field 11: Number of checkers per side (default 15)
        metadata['num_checkers'] = int(parts[10])

    return position, metadata


def _parse_ogid_position(white_str: str, black_str: str) -> Position:
    """
    Parse OGID position strings into a Position object.

    Args:
        white_str: White/X checker positions (e.g., "11jjjjjhhhccccc")
        black_str: Black/O checker positions (e.g., "ooddddd88866666")

    Returns:
        Position object with checkers placed
    """
    position = Position()

    # Parse White/X checkers (positive in our model)
    for char in white_str:
        point = _char_to_point(char)
        position.points[point] += 1  # Positive for X

    # Parse Black/O checkers (negative in our model)
    for char in black_str:
        point = _char_to_point(char)
        position.points[point] -= 1  # Negative for O

    # Calculate borne-off checkers (each player starts with 15)
    total_x = sum(count for count in position.points if count > 0)
    total_o = sum(abs(count) for count in position.points if count < 0)

    position.x_off = 15 - total_x
    position.o_off = 15 - total_o

    return position


def encode_ogid(
    position: Position,
    cube_value: int = 1,
    cube_owner: CubeState = CubeState.CENTERED,
    cube_action: str = 'N',
    dice: Optional[Tuple[int, int]] = None,
    on_roll: Optional[Player] = None,
    game_state: str = '',
    score_x: int = 0,
    score_o: int = 0,
    match_length: Optional[int] = None,
    match_modifier: str = '',
    match_max_games: Optional[int] = None,
    move_id: Optional[int] = None,
    num_checkers: Optional[int] = None,
    only_position: bool = False,
) -> str:
    """
    Encode a position and metadata as an OGID string.

    Args:
        position: The position to encode
        cube_value: Doubling cube value
        cube_owner: Who owns the cube
        cube_action: Cube action (N=Normal, O=Offered, T=Taken, P=Passed)
        dice: Dice values (if any)
        on_roll: Player on roll
        game_state: Game state code (e.g., "IW", "FB")
        score_x: White/X player's score
        score_o: Black/O player's score
        match_length: Match length (points to win)
        match_modifier: Match modifier (L, C, or G)
        match_max_games: Max games for Galaxie format
        move_id: Move sequence number
        num_checkers: Number of checkers per side (only include if not 15)
        only_position: If True, only encode position fields (1-3)

    Returns:
        OGID string
    """
    # Encode position strings
    white_chars = []  # X/White checkers
    black_chars = []  # O/Black checkers

    for point_idx in range(26):
        count = position.points[point_idx]
        if count > 0:
            # X/White checkers (positive)
            white_chars.extend([_point_to_char(point_idx)] * count)
        elif count < 0:
            # O/Black checkers (negative)
            black_chars.extend([_point_to_char(point_idx)] * abs(count))

    # Sort characters (OGID format convention)
    white_str = ''.join(sorted(white_chars))
    black_str = ''.join(sorted(black_chars))

    # Encode cube state (3 characters)
    # Owner
    if cube_owner == CubeState.X_OWNS:
        cube_owner_char = 'W'  # White = X
    elif cube_owner == CubeState.O_OWNS:
        cube_owner_char = 'B'  # Black = O
    else:
        cube_owner_char = 'N'  # Neutral

    # Value as log2
    cube_value_log = 0
    temp = cube_value
    while temp > 1:
        temp //= 2
        cube_value_log += 1
    cube_value_char = str(cube_value_log)

    # Action
    cube_action_char = cube_action

    cube_str = f"{cube_owner_char}{cube_value_char}{cube_action_char}"

    # Build OGID string
    ogid_parts = [white_str, black_str, cube_str]

    # If only_position is True, return just the first 3 fields
    if only_position:
        return ':'.join(ogid_parts)

    # Add optional fields
    # Field 4: Dice
    if dice:
        ogid_parts.append(f"{dice[0]}{dice[1]}")
    else:
        ogid_parts.append('')

    # Field 5: Turn
    if on_roll:
        turn_char = 'W' if on_roll == Player.X else 'B'
        ogid_parts.append(turn_char)
    else:
        ogid_parts.append('')

    # Field 6: Game state
    ogid_parts.append(game_state)

    # Field 7-8: Scores
    ogid_parts.append(str(score_x))
    ogid_parts.append(str(score_o))

    # Field 9: Match length
    if match_length is not None:
        match_str = str(match_length)
        if match_modifier:
            match_str += match_modifier
        if match_max_games is not None:
            match_str += str(match_max_games)
        ogid_parts.append(match_str)
    else:
        ogid_parts.append('')

    # Field 10: Move ID
    if move_id is not None:
        ogid_parts.append(str(move_id))
    else:
        ogid_parts.append('')

    # Field 11: Number of checkers (only if not 15)
    if num_checkers is not None and num_checkers != 15:
        ogid_parts.append(str(num_checkers))

    return ':'.join(ogid_parts)
