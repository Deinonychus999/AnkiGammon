"""Parse and apply backgammon move notation."""

import re
from typing import List, Tuple

from ankigammon.models import Position, Player


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
            Point 0 = X bar, Point 25 = O bar, Point 26 = bearing off

        Examples:
            "13/9 6/5" -> [(13, 9), (6, 5)]
            "bar/22" -> [(0, 22)]
            "6/off" -> [(6, 26)]
            "6/4(4)" -> [(6, 4), (6, 4), (6, 4), (6, 4)]
        """
        notation = notation.strip().lower()

        if notation in ['double', 'take', 'drop', 'pass', 'accept', 'decline']:
            return []

        moves = []

        # Split by spaces or commas
        parts = re.split(r'[\s,]+', notation)

        for part in parts:
            if not part or '/' not in part:
                continue

            # Check for repetition notation like "6/4(4)"
            repetition_count = 1
            repetition_match = re.search(r'\((\d+)\)$', part)
            if repetition_match:
                repetition_count = int(repetition_match.group(1))
                part = re.sub(r'\(\d+\)$', '', part)

            # Handle compound notation like "6/5*/3" or "24/23/22"
            segments = part.split('/')
            segments = [seg.rstrip('*') for seg in segments]

            # Convert compound notation to consecutive moves: "6/5/3" -> [(6,5), (5,3)]
            if len(segments) > 2:
                for i in range(len(segments) - 1):
                    from_str = segments[i]
                    to_str = segments[i + 1]

                    if 'bar' in from_str:
                        from_point = 0
                    else:
                        try:
                            from_point = int(from_str)
                        except ValueError:
                            continue

                    if 'off' in to_str:
                        to_point = 26
                    elif 'bar' in to_str:
                        to_point = 0
                    else:
                        try:
                            to_point = int(to_str)
                        except ValueError:
                            continue

                    for _ in range(repetition_count):
                        moves.append((from_point, to_point))
            else:
                # Simple notation like "6/5" or "bar/22"
                from_str = segments[0]
                to_str = segments[1] if len(segments) > 1 else ''

                if not to_str:
                    continue

                if 'bar' in from_str:
                    from_point = 0
                else:
                    try:
                        from_point = int(from_str)
                    except ValueError:
                        continue

                if 'off' in to_str:
                    to_point = 26
                elif 'bar' in to_str:
                    to_point = 0
                else:
                    try:
                        to_point = int(to_str)
                    except ValueError:
                        continue

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
            # Adjust bar points for player perspective
            if from_point == 0 and player == Player.O:
                from_point = 25
            if to_point == 0 and player == Player.X:
                to_point = 25

            if from_point == 26:
                continue

            if new_pos.points[from_point] == 0:
                continue

            if player == Player.X:
                if new_pos.points[from_point] > 0:
                    new_pos.points[from_point] -= 1
                else:
                    continue
            else:
                if new_pos.points[from_point] < 0:
                    new_pos.points[from_point] += 1
                else:
                    continue

            if to_point == 26:
                if player == Player.X:
                    new_pos.x_off += 1
                else:
                    new_pos.o_off += 1
            else:
                target_count = new_pos.points[to_point]

                if player == Player.X:
                    if target_count == -1:
                        new_pos.points[25] -= 1
                        new_pos.points[to_point] = 1
                    else:
                        new_pos.points[to_point] += 1
                else:
                    if target_count == 1:
                        new_pos.points[0] += 1
                        new_pos.points[to_point] = -1
                    else:
                        new_pos.points[to_point] -= 1

        return new_pos

    @staticmethod
    def format_move(from_point: int, to_point: int, player: Player) -> str:
        """
        Format a single move as notation.

        Args:
            from_point: Source point
            to_point: Destination point
            player: Player making the move

        Returns:
            Move notation string (e.g., "13/9", "bar/22", "6/off")
        """
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
