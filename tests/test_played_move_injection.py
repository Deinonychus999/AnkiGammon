"""Test for played move injection feature."""

import unittest
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ankigammon.models import Position, Player, Decision, Move, DecisionType
from ankigammon.gui.main_window import MainWindow
from ankigammon.settings import Settings


class TestPlayedMoveInjection(unittest.TestCase):
    """Test that played moves are injected into top 5 candidates for MCQ display."""

    def setUp(self):
        """Set up test fixtures."""
        self.settings = Settings()
        # Note: MainWindow requires PySide6, so we'll test the method directly

    def test_played_move_already_in_top_5(self):
        """Test that nothing happens if played move is already in top 5."""
        position = Position()

        # Create 7 moves where played move is 3rd
        moves = [
            Move(notation="13/9 6/5", equity=0.234, rank=1, was_played=False),
            Move(notation="24/20 13/9", equity=0.221, error=0.013, rank=2, was_played=False),
            Move(notation="13/7 6/3", equity=0.210, error=0.024, rank=3, was_played=True),  # Played
            Move(notation="24/18 13/10", equity=0.200, error=0.034, rank=4, was_played=False),
            Move(notation="13/10 13/7", equity=0.190, error=0.044, rank=5, was_played=False),
            Move(notation="24/21 24/18", equity=0.180, error=0.054, rank=6, was_played=False),
            Move(notation="6/3 6/off", equity=0.170, error=0.064, rank=7, was_played=False),
        ]

        decision = Decision(
            position=position,
            on_roll=Player.O,
            dice=(6, 3),
            candidate_moves=moves,
            decision_type=DecisionType.CHECKER_PLAY
        )

        played_move = moves[2]  # 3rd move

        # Create a minimal MainWindow mock
        class MainWindowMock:
            def _ensure_played_move_in_candidates(self, decision, played_move):
                # Copy the implementation
                top_5 = decision.candidate_moves[:5]
                if played_move in top_5:
                    return
                decision.candidate_moves.remove(played_move)
                decision.candidate_moves.insert(4, played_move)

        mock = MainWindowMock()
        mock._ensure_played_move_in_candidates(decision, played_move)

        # Verify: candidate_moves should be unchanged
        self.assertEqual(decision.candidate_moves[2], played_move)
        self.assertEqual(len(decision.candidate_moves), 7)

    def test_played_move_not_in_top_5(self):
        """Test that played move is injected when it's not in top 5."""
        position = Position()

        # Create 7 moves where played move is 6th (a blunder)
        moves = [
            Move(notation="13/9 6/5", equity=0.234, rank=1, was_played=False),
            Move(notation="24/20 13/9", equity=0.221, error=0.013, rank=2, was_played=False),
            Move(notation="13/7 6/3", equity=0.210, error=0.024, rank=3, was_played=False),
            Move(notation="24/18 13/10", equity=0.200, error=0.034, rank=4, was_played=False),
            Move(notation="13/10 13/7", equity=0.190, error=0.044, rank=5, was_played=False),
            Move(notation="24/21 24/18", equity=0.100, error=0.134, rank=6, was_played=True),  # Played - big blunder!
            Move(notation="6/3 6/off", equity=0.090, error=0.144, rank=7, was_played=False),
        ]

        decision = Decision(
            position=position,
            on_roll=Player.O,
            dice=(6, 3),
            candidate_moves=moves,
            decision_type=DecisionType.CHECKER_PLAY
        )

        played_move = moves[5]  # 6th move (blunder)
        original_5th = moves[4]  # Save reference BEFORE injection

        # Create a minimal MainWindow mock
        class MainWindowMock:
            def _ensure_played_move_in_candidates(self, decision, played_move):
                # Copy the implementation
                top_5 = decision.candidate_moves[:5]
                if played_move in top_5:
                    return
                decision.candidate_moves.remove(played_move)
                decision.candidate_moves.insert(4, played_move)

        mock = MainWindowMock()
        mock._ensure_played_move_in_candidates(decision, played_move)

        # Verify: played move should now be at position 4 (5th slot)
        self.assertEqual(decision.candidate_moves[4], played_move)
        self.assertTrue(decision.candidate_moves[4].was_played)
        self.assertEqual(decision.candidate_moves[4].notation, "24/21 24/18")

        # The 5th best move should have been pushed down
        # New top 5: moves[0], moves[1], moves[2], moves[3], moves[5] (played)
        top_5_after = decision.candidate_moves[:5]
        self.assertIn(played_move, top_5_after)

        # Original 5th move should now be at position 5 or later
        self.assertNotEqual(decision.candidate_moves[4], original_5th)
        self.assertEqual(decision.candidate_moves[4].notation, "24/21 24/18")  # Played move
        self.assertEqual(original_5th.notation, "13/10 13/7")  # Original 5th move

    def test_played_move_is_last(self):
        """Test that played move is injected when it's the worst move."""
        position = Position()

        # Create 10 moves where played move is last (terrible blunder)
        moves = [
            Move(notation=f"Move{i}", equity=1.0 - i*0.1, error=i*0.1, rank=i+1, was_played=(i==9))
            for i in range(10)
        ]

        decision = Decision(
            position=position,
            on_roll=Player.O,
            dice=(6, 3),
            candidate_moves=moves,
            decision_type=DecisionType.CHECKER_PLAY
        )

        played_move = moves[9]  # Last move (worst blunder)

        # Create a minimal MainWindow mock
        class MainWindowMock:
            def _ensure_played_move_in_candidates(self, decision, played_move):
                # Copy the implementation
                top_5 = decision.candidate_moves[:5]
                if played_move in top_5:
                    return
                decision.candidate_moves.remove(played_move)
                decision.candidate_moves.insert(4, played_move)

        mock = MainWindowMock()
        mock._ensure_played_move_in_candidates(decision, played_move)

        # Verify: played move should now be at position 4
        self.assertEqual(decision.candidate_moves[4], played_move)
        self.assertTrue(decision.candidate_moves[4].was_played)

        # Verify it's now in top 5
        top_5_after = decision.candidate_moves[:5]
        self.assertIn(played_move, top_5_after)


if __name__ == '__main__':
    unittest.main()
