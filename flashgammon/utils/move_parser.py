"""Parse and apply backgammon move notation."""

import re
from typing import List, Tuple

from flashgammon.models import Position, Player


class MoveParser:
    """Parse and apply backgammon move notation."""

    @staticmethod
    def parse_move_notation(notation: str) -> List[Tuple[int, int]]:
        """
        Parse move notation into list of (from, to) tuples.

        Args:
            notation: Move notation (e.g., "13/9 6/5", "bar/22", "6/off")

        Returns:
            List of (from_point, to_point) tuples
            Use 0 for X bar, 25 for O bar, 26 for bearing off

        Examples:
            "13/9 6/5" -> [(13, 9), (6, 5)]
            "bar/22" -> [(0, 22)]  # X entering from bar
            "6/off" -> [(6, 26)]  # Bearing off
            "6/4(4)" -> [(6, 4), (6, 4), (6, 4), (6, 4)]  # Repetition notation
        """
        notation = notation.strip().lower()

        # Handle special cases
        if notation in ['double', 'take', 'drop', 'pass', 'accept', 'decline']:
            return []  # Cube actions have no checker movement

        moves = []

        # Split by spaces or commas
        parts = re.split(r'[\s,]+', notation)

        for part in parts:
            if not part or '/' not in part:
                continue

            # Check for repetition notation like "6/4(4)" meaning "move 4 checkers from 6 to 4"
            repetition_count = 1
            repetition_match = re.search(r'\((\d+)\)$', part)
            if repetition_match:
                repetition_count = int(repetition_match.group(1))
                # Remove the repetition notation from the part
                part = re.sub(r'\(\d+\)$', '', part)

            # Parse from/to
            from_str, to_str = part.split('/', 1)

            # Remove asterisk (hit indicator) from notation
            from_str = from_str.rstrip('*')
            to_str = to_str.rstrip('*')

            # Parse 'from' point
            if 'bar' in from_str:
                from_point = 0  # X bar (we'll adjust for O later)
            else:
                try:
                    from_point = int(from_str)
                except ValueError:
                    continue

            # Parse 'to' point
            if 'off' in to_str:
                to_point = 26  # Bearing off
            elif 'bar' in to_str:
                # Hit - destination is the bar (rare in notation)
                to_point = 0  # Will be adjusted based on context
            else:
                try:
                    to_point = int(to_str)
                except ValueError:
                    continue

            # Add the move repetition_count times (handles notation like "6/4(4)")
            for _ in range(repetition_count):
                moves.append((from_point, to_point))

        return moves

    @staticmethod
    def apply_move(position: Position, notation: str, player: Player) -> Position:
        """
        Apply a move to a position and return the resulting position.

        Args:
            position: Initial position
            notation: Move notation
            player: Player making the move

        Returns:
            New position after the move
        """
        new_pos = position.copy()
        moves = MoveParser.parse_move_notation(notation)

        for from_point, to_point in moves:
            # In backgammon notation, both players use the SAME numbering (1-24)
            # The position array also uses this same numbering:
            #   - points[1] = point 1 (O's 1-point)
            #   - points[24] = point 24 (X's 1-point, O's 24-point)
            #
            # X moves from high numbers to low (24->1), O moves from low to high (1->24)
            # No coordinate conversion is needed - notation matches position indices directly!

            # The only special handling needed is for bar points:
            # - X's bar is at position[0]
            # - O's bar is at position[25]
            # parse_move_notation() returns 0 for "bar", so correct it for O
            if from_point == 0 and player == Player.O:
                from_point = 25
            if to_point == 0 and player == Player.X:
                to_point = 25  # When X hits, opponent goes to bar 25

            # Move checker
            if from_point == 26:  # Bearing off (from)
                # This shouldn't happen in normal notation
                continue

            # Remove from source
            if new_pos.points[from_point] == 0:
                # Invalid move - no checker to move
                continue

            if player == Player.X:
                if new_pos.points[from_point] > 0:
                    new_pos.points[from_point] -= 1
                else:
                    # Wrong player's checker
                    continue
            else:  # Player.O
                if new_pos.points[from_point] < 0:
                    new_pos.points[from_point] += 1
                else:
                    # Wrong player's checker
                    continue

            # Add to destination
            if to_point == 26:  # Bearing off
                if player == Player.X:
                    new_pos.x_off += 1
                else:
                    new_pos.o_off += 1
            else:
                # Check for hitting
                target_count = new_pos.points[to_point]

                if player == Player.X:
                    if target_count == -1:
                        # Hit O's blot
                        new_pos.points[25] -= 1  # Send to O's bar
                        new_pos.points[to_point] = 1
                    else:
                        new_pos.points[to_point] += 1
                else:  # Player.O
                    if target_count == 1:
                        # Hit X's blot
                        new_pos.points[0] += 1  # Send to X's bar
                        new_pos.points[to_point] = -1
                    else:
                        new_pos.points[to_point] -= 1

        return new_pos

    @staticmethod
    def format_move(from_point: int, to_point: int, player: Player) -> str:
        """
        Format a single move as notation.

        Args:
            from_point: Source point (0-25, or 26 for bearing off)
            to_point: Destination point
            player: Player making the move

        Returns:
            Move notation string (e.g., "13/9", "bar/22", "6/off")
        """
        # Handle special points
        if from_point == 0 and player == Player.X:
            from_str = "bar"
        elif from_point == 25 and player == Player.O:
            from_str = "bar"
        else:
            from_str = str(from_point)

        if to_point == 26:
            to_str = "off"
        elif to_point == 0 and player == Player.O:
            to_str = "bar"
        elif to_point == 25 and player == Player.X:
            to_str = "bar"
        else:
            to_str = str(to_point)

        return f"{from_str}/{to_str}"
