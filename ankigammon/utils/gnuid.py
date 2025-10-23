"""GNUID format parsing and encoding.

GNUID (GNU Backgammon ID) is GNU Backgammon's position identification format.

Format: PositionID:MatchID

Position ID:
- 14-character Base64 string
- Encodes 10 bytes (80 bits)
- Variable-length bit encoding of checker positions
- Format per point: [player 1-bits][0][opponent 1-bits][0]

Match ID:
- 12-character Base64 string
- Encodes 9 bytes (72 bits)
- Contains cube value, owner, scores, dice, match length, etc.

Example: 4HPwATDgc/ABMA:8IhuACAACAAE
- Position: 4HPwATDgc/ABMA (starting position)
- Match: 8IhuACAACAAE (match state)

Encoding Algorithm (Position ID):
1. Start with empty bit string
2. For each point (from player on roll's perspective):
   - Append N ones (N = player on roll's checkers)
   - Append M ones (M = opponent's checkers)
   - Append one zero (separator)
3. Pad to 80 bits with zeros
4. Pack into 10 bytes (little-endian)
5. Base64 encode (without padding)

Note: In our internal model:
- Player.X = TOP player (positive values)
- Player.O = BOTTOM player (negative values)
"""

import base64
from typing import Dict, Optional, Tuple

from ankigammon.models import Position, Player, CubeState


def parse_gnuid(gnuid: str) -> Tuple[Position, Dict]:
    """
    Parse a GNUID string into a Position and metadata.

    Args:
        gnuid: GNUID string (e.g., "4HPwATDgc/ABMA:8IhuACAACAAE")

    Returns:
        Tuple of (Position, metadata_dict)
    """
    # Remove "GNUID=" or "GNUBGID=" prefix if present
    gnuid = gnuid.strip()
    if gnuid.upper().startswith("GNUID="):
        gnuid = gnuid[6:]
    elif gnuid.upper().startswith("GNUBGID="):
        gnuid = gnuid[8:]
    elif gnuid.upper().startswith("GNUBGID "):
        gnuid = gnuid[8:]

    # Split into Position ID and Match ID
    parts = gnuid.split(':')
    if len(parts) < 1:
        raise ValueError("Invalid GNUID format: no colon separator found")

    position_id = parts[0].strip()
    match_id = parts[1].strip() if len(parts) > 1 else None

    # Parse position ID
    if len(position_id) != 14:
        raise ValueError(f"Invalid Position ID length: expected 14 chars, got {len(position_id)}")

    # Decode position (GNUID Position ID always uses Player 1/X's perspective)
    position = _decode_position_id(position_id)

    # Parse metadata from match ID
    metadata = {}
    if match_id:
        metadata = _decode_match_id(match_id)

    return position, metadata


def _decode_position_id(position_id: str) -> Position:
    """
    Decode a 14-character Position ID into a Position object.

    GNUID Position IDs always encode from Player 1 (X/top player)'s perspective,
    regardless of who is on roll.

    Args:
        position_id: 14-character Base64 string

    Returns:
        Position object
    """
    # Base64 decode to 10 bytes (no padding)
    try:
        # Add padding if needed for decoding
        position_bytes = base64.b64decode(position_id + "==")
    except Exception as e:
        raise ValueError(f"Invalid Position ID Base64: {e}")

    if len(position_bytes) != 10:
        raise ValueError(f"Invalid Position ID: expected 10 bytes, got {len(position_bytes)}")

    # Convert bytes to bit string (80 bits, little-endian)
    bits = []
    for byte in position_bytes:
        for i in range(8):
            bits.append((byte >> i) & 1)

    # Decode bit string into TanBoard structure
    # Format: [player0-25points][player1-25points]
    # Each point: [N consecutive 1s][separator 0]
    # This matches GNU Backgammon's oldPositionFromKey() function
    anBoard = [[0] * 25 for _ in range(2)]  # [2 players][25 points]

    bit_idx = 0
    player = 0  # Start with player 0 (X)
    point = 0   # Start with point 0

    while bit_idx < len(bits) and player < 2:
        # Count consecutive 1s (checkers on this point)
        checker_count = 0
        while bit_idx < len(bits) and bits[bit_idx] == 1:
            checker_count += 1
            bit_idx += 1

        # Store checker count
        if point < 25:
            anBoard[player][point] = checker_count

        # Skip separator (0-bit)
        if bit_idx < len(bits) and bits[bit_idx] == 0:
            bit_idx += 1

        # Move to next point
        point += 1
        if point >= 25:
            # Move to next player
            player += 1
            point = 0

    # Convert TanBoard to our Position model
    position = _convert_tanboard_to_position(anBoard)

    return position


def _convert_tanboard_to_position(anBoard: list) -> Position:
    """
    Convert TanBoard structure to our internal Position model.

    TanBoard structure (from GNU Backgammon):
    - anBoard[0][0-23] = Player 0 (X/top) checkers on points 0-23
    - anBoard[0][24] = Player 0 (X) bar
    - anBoard[1][0-23] = Player 1 (O/bottom) checkers on points 0-23
    - anBoard[1][24] = Player 1 (O) bar

    Point numbering in TanBoard (player-relative):
    - Player 0 (X): anBoard[0][0] = point 24, anBoard[0][23] = point 1 (reverse mapping)
    - Player 1 (O): anBoard[1][0] = point 1, anBoard[1][23] = point 24 (direct mapping)

    Our internal model:
    - points[0] = X's bar
    - points[1-24] = board points (1 = O's ace, 24 = X's ace)
    - points[25] = O's bar
    - Positive values = X checkers, Negative values = O checkers

    Args:
        anBoard: TanBoard structure [2 players][25 points]

    Returns:
        Position object
    """
    position = Position()

    # Player 0 (X) - reverse numbering, positive values
    for i in range(24):
        our_point = 24 - i  # anBoard[0][0] → point 24, anBoard[0][23] → point 1
        position.points[our_point] += anBoard[0][i]  # Positive for X
    position.points[0] = anBoard[0][24]  # X's bar

    # Player 1 (O) - direct numbering, negative values
    for i in range(24):
        our_point = i + 1  # anBoard[1][0] → point 1, anBoard[1][23] → point 24
        position.points[our_point] -= anBoard[1][i]  # Negative for O
    position.points[25] = -anBoard[1][24]  # O's bar

    # Calculate borne-off checkers
    total_x = sum(count for count in position.points if count > 0)
    total_o = sum(abs(count) for count in position.points if count < 0)

    position.x_off = 15 - total_x
    position.o_off = 15 - total_o

    return position


def _convert_position_to_tanboard(position: Position) -> list:
    """
    Convert our internal Position model to TanBoard structure.

    This is the inverse of _convert_tanboard_to_position.

    Args:
        position: Our internal position

    Returns:
        TanBoard structure [2 players][25 points]
    """
    anBoard = [[0] * 25 for _ in range(2)]

    # Player 0 (X) - reverse mapping: point p → anBoard[0][24-p]
    for our_point in range(1, 25):
        if position.points[our_point] > 0:
            anBoard[0][24 - our_point] = position.points[our_point]
    anBoard[0][24] = position.points[0]  # X's bar

    # Player 1 (O) - direct mapping: point p → anBoard[1][p-1]
    for our_point in range(1, 25):
        if position.points[our_point] < 0:
            anBoard[1][our_point - 1] = -position.points[our_point]
    anBoard[1][24] = -position.points[25] if position.points[25] < 0 else 0  # O's bar

    return anBoard


def _convert_gnuid_to_position(
    player_checkers: list,
    opponent_checkers: list,
    on_roll: Player
) -> Position:
    """
    Convert GNUID perspective arrays to our internal Position model.

    Args:
        player_checkers: Checkers from player on roll's perspective [0-25]
        opponent_checkers: Opponent's checkers from same perspective [0-25]
        on_roll: Player who is on roll

    Returns:
        Position object
    """
    position = Position()

    # GNUID point mapping from player on roll's perspective:
    # Points 0-23 are board points from player's ace point (1) through opponent's ace (24)
    # Point 24 is player's bar
    # Point 25 is opponent's bar

    if on_roll == Player.X:
        # X is on roll, so player = X, opponent = O
        # GNUID point 0 = X's point 24 (X's ace, looking from X's perspective)
        # GNUID point 23 = X's point 1 (O's ace, looking from X's perspective)
        # GNUID point 24 = X's bar (our point 0)
        # GNUID point 25 = O's bar (our point 25)

        # Map board points (reverse numbering for X's perspective)
        for gnuid_pt in range(24):
            our_pt = 24 - gnuid_pt
            position.points[our_pt] = player_checkers[gnuid_pt]  # X checkers (positive)
            position.points[our_pt] -= opponent_checkers[gnuid_pt]  # O checkers (negative)

        # Map bars
        position.points[0] = player_checkers[24]  # X's bar
        position.points[25] = -opponent_checkers[25]  # O's bar

    else:
        # O is on roll, so player = O, opponent = X
        # GNUID point 0 = O's point 1 (O's ace)
        # GNUID point 23 = O's point 24 (X's ace)
        # GNUID point 24 = O's bar (our point 25)
        # GNUID point 25 = X's bar (our point 0)

        # Map board points (direct mapping)
        for gnuid_pt in range(24):
            our_pt = gnuid_pt + 1
            position.points[our_pt] = -player_checkers[gnuid_pt]  # O checkers (negative)
            position.points[our_pt] += opponent_checkers[gnuid_pt]  # X checkers (positive)

        # Map bars
        position.points[25] = -player_checkers[24]  # O's bar
        position.points[0] = opponent_checkers[25]  # X's bar

    # Calculate borne-off checkers
    total_x = sum(count for count in position.points if count > 0)
    total_o = sum(abs(count) for count in position.points if count < 0)

    position.x_off = 15 - total_x
    position.o_off = 15 - total_o

    return position


def _decode_match_id(match_id: str) -> Dict:
    """
    Decode a 12-character Match ID into metadata.

    Args:
        match_id: 12-character Base64 string

    Returns:
        Dictionary with metadata fields
    """
    if len(match_id) != 12:
        raise ValueError(f"Invalid Match ID length: expected 12 chars, got {len(match_id)}")

    try:
        # Base64 decode to 9 bytes
        match_bytes = base64.b64decode(match_id + "=")
    except Exception as e:
        raise ValueError(f"Invalid Match ID Base64: {e}")

    if len(match_bytes) != 9:
        raise ValueError(f"Invalid Match ID: expected 9 bytes, got {len(match_bytes)}")

    # Convert to bit array
    bits = []
    for byte in match_bytes:
        for i in range(8):
            bits.append((byte >> i) & 1)

    # Extract fields (total 72 bits)
    metadata = {}

    # Bits 0-3: Cube value (log2)
    cube_log = _extract_bits(bits, 0, 4)
    metadata['cube_value'] = 2 ** cube_log if cube_log < 15 else 1

    # Bits 4-5: Cube owner (00=player0, 01=player1, 11=centered)
    cube_owner_bits = _extract_bits(bits, 4, 2)
    if cube_owner_bits == 3:
        metadata['cube_owner'] = CubeState.CENTERED
    elif cube_owner_bits == 0:
        metadata['cube_owner'] = CubeState.X_OWNS  # Player 0 = X
    else:
        metadata['cube_owner'] = CubeState.O_OWNS  # Player 1 = O

    # Bit 6: Move (who rolled)
    # Bit 7: Crawford
    metadata['crawford'] = bits[7] == 1

    # Bits 8-10: Game state
    game_state = _extract_bits(bits, 8, 3)
    metadata['game_state'] = game_state

    # Bit 11: Turn (0=player0/X, 1=player1/O)
    turn_bit = bits[11]
    metadata['on_roll'] = Player.O if turn_bit == 1 else Player.X

    # Bit 12: Doubled
    metadata['doubled'] = bits[12] == 1

    # Bits 13-14: Resigned
    resign_bits = _extract_bits(bits, 13, 2)
    metadata['resigned'] = resign_bits

    # Bits 15-17: Die 0
    die0 = _extract_bits(bits, 15, 3)
    # Bits 18-20: Die 1
    die1 = _extract_bits(bits, 18, 3)

    if die0 > 0 and die1 > 0:
        metadata['dice'] = (die0, die1)

    # Bits 21-35: Match length (15 bits)
    match_length = _extract_bits(bits, 21, 15)
    metadata['match_length'] = match_length

    # Bits 36-50: Player 0 score (15 bits)
    score_0 = _extract_bits(bits, 36, 15)
    metadata['score_x'] = score_0  # Player 0 = X

    # Bits 51-65: Player 1 score (15 bits)
    score_1 = _extract_bits(bits, 51, 15)
    metadata['score_o'] = score_1  # Player 1 = O

    return metadata


def _extract_bits(bits: list, start: int, count: int) -> int:
    """Extract an integer from a bit array."""
    value = 0
    for i in range(count):
        if start + i < len(bits):
            value |= (bits[start + i] << i)
    return value


def encode_gnuid(
    position: Position,
    cube_value: int = 1,
    cube_owner: CubeState = CubeState.CENTERED,
    dice: Optional[Tuple[int, int]] = None,
    on_roll: Player = Player.X,
    score_x: int = 0,
    score_o: int = 0,
    match_length: int = 0,
    crawford: bool = False,
    only_position: bool = False,
) -> str:
    """
    Encode a position and metadata as a GNUID string.

    Args:
        position: The position to encode
        cube_value: Doubling cube value
        cube_owner: Who owns the cube
        dice: Dice values (if any)
        on_roll: Player on roll
        score_x: Player X's (player 0) score
        score_o: Player O's (player 1) score
        match_length: Match length (0 for money)
        crawford: Crawford game flag
        only_position: If True, only return Position ID (no Match ID)

    Returns:
        GNUID string (PositionID:MatchID or just PositionID)
    """
    # Encode position ID (always from Player X's perspective)
    position_id = _encode_position_id(position)

    if only_position:
        return position_id

    # Encode match ID
    match_id = _encode_match_id(
        cube_value=cube_value,
        cube_owner=cube_owner,
        dice=dice,
        on_roll=on_roll,
        score_x=score_x,
        score_o=score_o,
        match_length=match_length,
        crawford=crawford,
    )

    return f"{position_id}:{match_id}"


def _encode_position_id(position: Position) -> str:
    """
    Encode a Position into a 14-character Position ID.

    Args:
        position: The position to encode

    Returns:
        14-character Base64 Position ID
    """
    # Convert our position to TanBoard structure
    anBoard = _convert_position_to_tanboard(position)

    # Build bit string - ALL player 0 points, then ALL player 1 points
    bits = []

    for player in range(2):
        for point in range(25):
            # Add checkers as 1s
            for _ in range(anBoard[player][point]):
                bits.append(1)
            # Add separator 0
            bits.append(0)

    # Pad to 80 bits
    while len(bits) < 80:
        bits.append(0)

    # Pack into 10 bytes (little-endian)
    position_bytes = bytearray(10)
    for i, bit in enumerate(bits[:80]):
        byte_idx = i // 8
        bit_idx = i % 8
        position_bytes[byte_idx] |= (bit << bit_idx)

    # Base64 encode (remove padding)
    position_id = base64.b64encode(bytes(position_bytes)).decode('ascii').rstrip('=')

    return position_id


def _convert_position_to_gnuid(position: Position, on_roll: Player) -> Tuple[list, list]:
    """
    Convert our internal Position to GNUID perspective arrays.

    Args:
        position: Our internal position
        on_roll: Player on roll

    Returns:
        Tuple of (player_checkers[26], opponent_checkers[26])
    """
    player_checkers = [0] * 26
    opponent_checkers = [0] * 26

    if on_roll == Player.X:
        # X is on roll
        # GNUID point 0 = our point 24 (X's ace)
        # GNUID point 23 = our point 1 (O's ace)
        # GNUID point 24 = our point 0 (X's bar)
        # GNUID point 25 = our point 25 (O's bar)

        # Map board points (reverse)
        for our_pt in range(1, 25):
            gnuid_pt = 24 - our_pt
            count = position.points[our_pt]
            if count > 0:
                player_checkers[gnuid_pt] = count  # X checkers
            elif count < 0:
                opponent_checkers[gnuid_pt] = -count  # O checkers

        # Map bars
        player_checkers[24] = position.points[0]  # X's bar
        opponent_checkers[25] = -position.points[25]  # O's bar

    else:
        # O is on roll
        # GNUID point 0 = our point 1 (O's ace)
        # GNUID point 23 = our point 24 (X's ace)
        # GNUID point 24 = our point 25 (O's bar)
        # GNUID point 25 = our point 0 (X's bar)

        # Map board points (direct)
        for our_pt in range(1, 25):
            gnuid_pt = our_pt - 1
            count = position.points[our_pt]
            if count < 0:
                player_checkers[gnuid_pt] = -count  # O checkers
            elif count > 0:
                opponent_checkers[gnuid_pt] = count  # X checkers

        # Map bars
        player_checkers[24] = -position.points[25]  # O's bar
        opponent_checkers[25] = position.points[0]  # X's bar

    return player_checkers, opponent_checkers


def _encode_match_id(
    cube_value: int,
    cube_owner: CubeState,
    dice: Optional[Tuple[int, int]],
    on_roll: Player,
    score_x: int,
    score_o: int,
    match_length: int,
    crawford: bool,
) -> str:
    """
    Encode match metadata into a 12-character Match ID.

    Returns:
        12-character Base64 Match ID
    """
    # Build 72-bit array
    bits = [0] * 72

    # Bits 0-3: Cube value (log2)
    cube_log = 0
    temp = cube_value
    while temp > 1:
        temp //= 2
        cube_log += 1
    _set_bits(bits, 0, 4, cube_log)

    # Bits 4-5: Cube owner
    if cube_owner == CubeState.CENTERED:
        cube_owner_val = 3
    elif cube_owner == CubeState.X_OWNS:
        cube_owner_val = 0  # Player 0
    else:
        cube_owner_val = 1  # Player 1
    _set_bits(bits, 4, 2, cube_owner_val)

    # Bit 6: Move (0 for now)
    # Bit 7: Crawford
    bits[7] = 1 if crawford else 0

    # Bits 8-10: Game state (1 = playing)
    _set_bits(bits, 8, 3, 1)

    # Bit 11: Turn
    bits[11] = 1 if on_roll == Player.O else 0

    # Bit 12: Doubled (0 for now)
    # Bits 13-14: Resigned (0 for now)

    # Bits 15-17: Die 0
    # Bits 18-20: Die 1
    if dice:
        _set_bits(bits, 15, 3, dice[0])
        _set_bits(bits, 18, 3, dice[1])

    # Bits 21-35: Match length
    _set_bits(bits, 21, 15, match_length)

    # Bits 36-50: Player 0 score
    _set_bits(bits, 36, 15, score_x)

    # Bits 51-65: Player 1 score
    _set_bits(bits, 51, 15, score_o)

    # Pack into 9 bytes
    match_bytes = bytearray(9)
    for i in range(72):
        byte_idx = i // 8
        bit_idx = i % 8
        match_bytes[byte_idx] |= (bits[i] << bit_idx)

    # Base64 encode (remove padding)
    match_id = base64.b64encode(bytes(match_bytes)).decode('ascii').rstrip('=')

    return match_id


def _set_bits(bits: list, start: int, count: int, value: int):
    """Set bits in a bit array from an integer value."""
    for i in range(count):
        bits[start + i] = (value >> i) & 1
