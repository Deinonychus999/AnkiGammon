"""Basic tests for XG2Anki functionality."""

import unittest
from pathlib import Path
from unittest.mock import patch
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from xg2anki.models import Position, Player, CubeState, Decision, Move, DecisionType
from xg2anki.utils.xgid import parse_xgid, encode_xgid
from xg2anki.utils.move_parser import MoveParser
from xg2anki.renderer.board_renderer import BoardRenderer
from xg2anki.interactive import InteractiveSession


class TestXGIDParsing(unittest.TestCase):
    """Test XGID parsing and encoding."""

    def test_parse_basic_xgid(self):
        """Test parsing a basic XGID."""
        xgid = "XGID=---BBBBAAA---Ac-bbccbAA-A-:1:1:-1:63:4:3:0:5:8"
        position, metadata = parse_xgid(xgid)

        # Check cube
        self.assertEqual(metadata['cube_value'], 2)  # 2^1
        self.assertEqual(metadata['cube_owner'], CubeState.O_OWNS)  # 1 = O owns

        # Check turn
        self.assertEqual(metadata['on_roll'], Player.X)  # -1 = X's turn

        # Check dice
        self.assertEqual(metadata['dice'], (6, 3))

        # Check match
        self.assertEqual(metadata['match_length'], 5)

    def test_encode_xgid(self):
        """Test encoding a position to XGID."""
        position = Position()
        position.points[1] = -2  # 2 O checkers on point 1

        xgid = encode_xgid(
            position,
            cube_value=2,
            dice=(6, 3),
            match_length=7
        )

        self.assertIn("XGID=", xgid)
        self.assertIn(":1:", xgid)  # Cube value 2^1

    def test_xgid_roundtrip(self):
        """Test encoding and decoding produces same result."""
        original_xgid = "XGID=--------------------c-e-B-:0:0:1:52:0:0:0:0:0"
        position, metadata = parse_xgid(original_xgid)

        # Re-encode
        new_xgid = encode_xgid(
            position,
            cube_value=metadata['cube_value'],
            cube_owner=metadata['cube_owner'],
            dice=metadata.get('dice'),
            on_roll=metadata['on_roll'],
            score_x=metadata['score_x'],
            score_o=metadata['score_o'],
            match_length=metadata['match_length']
        )

        # Parse again
        position2, metadata2 = parse_xgid(new_xgid)

        # Compare key fields
        self.assertEqual(position.points, position2.points)
        self.assertEqual(metadata['cube_value'], metadata2['cube_value'])
        self.assertEqual(metadata['on_roll'], metadata2['on_roll'])


class TestMoveParser(unittest.TestCase):
    """Test move notation parsing."""

    def test_parse_simple_move(self):
        """Test parsing simple move notation."""
        moves = MoveParser.parse_move_notation("13/9 6/5")
        self.assertEqual(len(moves), 2)
        self.assertEqual(moves[0], (13, 9))
        self.assertEqual(moves[1], (6, 5))

    def test_parse_bar_move(self):
        """Test parsing bar entry."""
        moves = MoveParser.parse_move_notation("bar/22")
        self.assertEqual(len(moves), 1)
        self.assertEqual(moves[0], (0, 22))

    def test_parse_bearoff(self):
        """Test parsing bear-off move."""
        moves = MoveParser.parse_move_notation("6/off")
        self.assertEqual(len(moves), 1)
        self.assertEqual(moves[0], (6, 26))


class TestPosition(unittest.TestCase):
    """Test Position model."""

    def test_position_creation(self):
        """Test creating a position."""
        position = Position()
        self.assertEqual(len(position.points), 26)
        self.assertEqual(position.x_off, 0)
        self.assertEqual(position.o_off, 0)

    def test_position_copy(self):
        """Test copying a position."""
        position = Position()
        position.points[1] = 5
        position.x_off = 2

        copy = position.copy()
        copy.points[1] = 3
        copy.x_off = 1

        # Original should be unchanged
        self.assertEqual(position.points[1], 5)
        self.assertEqual(position.x_off, 2)

    def test_from_xgid(self):
        """Test creating position from XGID."""
        xgid = "XGID=---BBBBAAA---Ac-bbccbAA-A-:1:1:-1:63:4:3:0:5:8"
        position = Position.from_xgid(xgid)

        self.assertEqual(len(position.points), 26)


class TestDecision(unittest.TestCase):
    """Test Decision model."""

    def test_decision_creation(self):
        """Test creating a decision."""
        position = Position()
        moves = [
            Move(notation="13/9 6/5", equity=0.234, rank=1),
            Move(notation="24/20 13/9", equity=0.221, error=0.013, rank=2),
        ]

        decision = Decision(
            position=position,
            on_roll=Player.O,
            dice=(6, 3),
            candidate_moves=moves
        )

        self.assertEqual(decision.on_roll, Player.O)
        self.assertEqual(len(decision.candidate_moves), 2)

    def test_get_best_move(self):
        """Test getting best move."""
        position = Position()
        moves = [
            Move(notation="13/9 6/5", equity=0.234, rank=1),
            Move(notation="24/20 13/9", equity=0.221, error=0.013, rank=2),
        ]

        decision = Decision(
            position=position,
            candidate_moves=moves
        )

        best = decision.get_best_move()
        self.assertIsNotNone(best)
        self.assertEqual(best.rank, 1)
        self.assertEqual(best.notation, "13/9 6/5")

    def test_metadata_text(self):
        """Test metadata text generation."""
        position = Position()
        decision = Decision(
            position=position,
            on_roll=Player.O,
            dice=(6, 3),
            score_x=2,
            score_o=3,
            match_length=7,
            cube_value=2
        )

        text = decision.get_metadata_text()
        self.assertIn("O", text)
        self.assertIn("6-3", text)
        self.assertIn("2-3", text)
        self.assertIn("7pt", text)
        self.assertIn("2", text)


class TestBoardRenderer(unittest.TestCase):
    """Test basic board renderer orientation helpers."""

    def test_map_point_index_flip(self):
        """Ensure point mapping rotates board by half when flipped."""
        renderer = BoardRenderer()

        # No flip keeps indices unchanged
        self.assertEqual(renderer._map_point_index(1, False), 1)
        self.assertEqual(renderer._map_point_index(24, False), 24)

        # Flip rotates indices by 12 points (half board)
        self.assertEqual(renderer._map_point_index(1, True), 13)
        self.assertEqual(renderer._map_point_index(6, True), 18)
        self.assertEqual(renderer._map_point_index(13, True), 1)
        self.assertEqual(renderer._map_point_index(24, True), 12)


class TestInteractiveSession(unittest.TestCase):
    """Test interactive session helpers."""

    def test_collect_position_includes_footer_after_blank_break(self):
        """Ensure footer lines following blank separators stay with the position."""
        session = InteractiveSession()
        sample_lines = [
            "XGID=-aA--BD-C---eA--ac-c--b-B-:0:0:1:61:0:0:3:0:10",
            "",
            "X:Player 1   O:Player 2",
            "Score is X:0 O:0. Unlimited Game, Jacoby Beaver",
            " +13-14-15-16-17-18------19-20-21-22-23-24-+",
            " | X        O  O    |   | O        O     X |",
            " |             O    |   | O        O     X |",
            " |             O    |   | O                |",
            " |                  |   |                  |",
            " |                  |   |                  |",
            " |                  |BAR|                  |",
            " | O                |   |                  |",
            " | O                |   | X                |",
            " | O           X    |   | X                |",
            " | O           X    |   | X  X             |",
            " | O           X    |   | X  X        X  O |",
            " +12-11-10--9--8--7-------6--5--4--3--2--1-+",
            "Pip count  X: 121  O: 146 X-O: 0-0",
            "Cube: 1",
            "X to play 61",
            "",
            "    1. 2-ply       13/7 8/7                     eq:+0.100",
            "      Player:   47.72% (G:16.27% B:0.55%)",
            "      Opponent: 52.28% (G:0.00% B:0.00%)",
            "",
            "    2. 2-ply       24/18 2/1*                   eq:-0.029 (-0.129)",
            "      Player:   43.43% (G:15.51% B:0.47%)",
            "      Opponent: 56.57% (G:0.00% B:0.00%)",
            "",
            "    3. 2-ply       8/2 6/5                      eq:-0.053 (-0.153)",
            "      Player:   42.67% (G:16.57% B:0.49%)",
            "      Opponent: 57.33% (G:0.00% B:0.00%)",
            "",
            "    4. 2-ply       24/23 8/2                    eq:-0.064 (-0.164)",
            "      Player:   42.45% (G:16.29% B:0.45%)",
            "      Opponent: 57.55% (G:0.00% B:0.00%)",
            "",
            "    5. 2-ply       13/7 2/1*                    eq:-0.106 (-0.206)",
            "      Player:   41.35% (G:14.66% B:0.36%)",
            "      Opponent: 58.65% (G:0.00% B:0.00%)",
            "eXtreme Gammon Version: 2.10",
            "done",
        ]

        input_sequence = iter(sample_lines)

        with patch('builtins.input', side_effect=lambda: next(input_sequence)):
            positions = session.collect_positions()

        self.assertEqual(len(positions), 1)
        self.assertIn("eXtreme Gammon Version: 2.10", positions[0])


def run_tests():
    """Run all tests."""
    unittest.main()


if __name__ == '__main__':
    run_tests()
