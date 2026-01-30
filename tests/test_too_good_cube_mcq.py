"""
Tests for 'Too good to double' cube decision MCQ behavior.

These tests verify that:
1. "Too good/Pass" is the correct MCQ answer when it's the best cube action
2. ALL wrong cube answers are marked as INCORRECT (not close)
3. The analysis table correctly highlights "No Double" for display purposes
4. Cube decisions use binary error (0/1) because each option represents a distinct strategic concept

Key concept: For cube decisions to be "CLOSE", an answer must match BOTH dimensions:
- Action dimension: double vs no double
- Response dimension: take vs pass
Since no wrong answer matches both, all wrong answers are INCORRECT.
"""

import json
import tempfile
from pathlib import Path

import pytest

from ankigammon.models import Decision, DecisionType, Move, Player, Position
from ankigammon.anki.card_generator import CardGenerator


# Threshold used by JavaScript feedback for determining CLOSE vs INCORRECT
CLOSE_THRESHOLD = 0.020


class TestTooGoodCubeMCQ:
    """Test MCQ behavior for 'too good to double' positions."""

    @pytest.fixture
    def too_good_decision(self) -> Decision:
        """Create a 'too good to double' cube decision with realistic equities.

        This simulates a position where:
        - Best action is "Too good/Pass" (rank 1)
        - No Double has higher equity (1.145) because you keep gammon chances
        - Double/Take has highest equity (1.796) but opponent should pass
        - Double/Pass has equity 1.000 (normalized)

        The "Too good" options have NO DOUBLE equity (1.145) because you DON'T
        double - the Take/Pass suffix indicates opponent's hypothetical response.
        """
        position = Position()

        # Create moves in the order they appear in the MCQ
        moves = [
            Move(
                notation="No Double/Take",
                equity=1.145,
                rank=3,  # Not the best - different strategic concept
                error=0.145,
                from_xg_analysis=True,
                xg_notation="No double",
                xg_rank=1,
                xg_error=0.0,
            ),
            Move(
                notation="Double/Take",
                equity=1.796,
                rank=2,
                error=0.796,
                from_xg_analysis=True,
                xg_notation="Double/Take",
                xg_rank=2,
                xg_error=0.651,
            ),
            Move(
                notation="Double/Pass",
                equity=1.000,
                rank=4,
                error=0.0,
                from_xg_analysis=True,
                xg_notation="Double/Pass",
                xg_rank=3,
                xg_error=-0.145,
            ),
            Move(
                notation="Too good/Take",
                equity=1.145,  # Same as No Double (you don't double)
                rank=5,
                error=0.0,
                from_xg_analysis=False,  # Synthetic option
            ),
            Move(
                notation="Too good/Pass",
                equity=1.145,  # Same as No Double (you don't double) - BEST action
                rank=1,  # BEST - "too good to double, opponent should pass"
                error=0.0,
                from_xg_analysis=False,  # Synthetic option
            ),
        ]

        return Decision(
            position=position,
            on_roll=Player.X,
            decision_type=DecisionType.CUBE_ACTION,
            candidate_moves=moves,
            dice=None,
            cube_value=1,
            match_length=0,
        )

    @pytest.fixture
    def normal_no_double_decision(self) -> Decision:
        """Create a normal 'No Double/Take' cube decision (not too good).

        This simulates a position where:
        - Best action is "No Double/Take" (rank 1)
        - Position isn't strong enough to double yet
        """
        position = Position()

        moves = [
            Move(
                notation="No Double/Take",
                equity=0.500,
                rank=1,  # BEST - normal no double situation
                error=0.0,
                from_xg_analysis=True,
                xg_notation="No double",
                xg_rank=1,
                xg_error=0.0,
            ),
            Move(
                notation="Double/Take",
                equity=0.450,
                rank=2,
                error=0.050,
                from_xg_analysis=True,
                xg_notation="Double/Take",
                xg_rank=2,
                xg_error=-0.050,
            ),
            Move(
                notation="Double/Pass",
                equity=1.000,
                rank=3,
                error=0.500,
                from_xg_analysis=True,
                xg_notation="Double/Pass",
                xg_rank=3,
                xg_error=0.500,
            ),
            Move(
                notation="Too good/Take",
                equity=0.500,  # Same as No Double (you don't double)
                rank=4,
                error=0.0,  # Same equity as best move
                from_xg_analysis=False,
            ),
            Move(
                notation="Too good/Pass",
                equity=0.500,  # Same as No Double (you don't double)
                rank=5,
                error=0.0,  # Same equity as best move
                from_xg_analysis=False,
            ),
        ]

        return Decision(
            position=position,
            on_roll=Player.X,
            decision_type=DecisionType.CUBE_ACTION,
            candidate_moves=moves,
            dice=None,
            cube_value=1,
            match_length=0,
        )

    def test_too_good_correct_answer_is_too_good_pass(self, too_good_decision):
        """When 'Too good/Pass' is best, it should be the MCQ correct answer."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = CardGenerator(Path(tmpdir), show_options=True)
            card = gen.generate_card(too_good_decision)

            back_html = card['back']

            # The correct answer should be E (Too good/Pass is at index 4)
            assert 'data-correct-answer="E"' in back_html

            # The best move notation should show "Too good/Pass"
            assert 'Too good/Pass' in back_html

    def test_too_good_correct_answer_has_zero_error(self, too_good_decision):
        """The correct answer should have zero error in the error map."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = CardGenerator(Path(tmpdir), show_options=True)
            card = gen.generate_card(too_good_decision)

            back_html = card['back']

            import re
            error_map_match = re.search(r"data-error-map='(\{[^']+\})'", back_html)
            assert error_map_match, "Error map not found in HTML"

            error_map = json.loads(error_map_match.group(1))

            # E = Too good/Pass should have error 0.0 (it's the correct answer)
            assert error_map['E'] == pytest.approx(0.0, abs=0.001)

    def test_too_good_no_double_is_incorrect(self, too_good_decision):
        """'No Double/Take' should be INCORRECT when 'Too good/Pass' is correct.

        These represent fundamentally different strategic concepts:
        - 'No Double/Take': Position isn't strong enough, opponent would TAKE
        - 'Too good/Pass': Position is SO strong, opponent would PASS

        They differ on the RESPONSE dimension (take vs pass), so not CLOSE.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = CardGenerator(Path(tmpdir), show_options=True)
            card = gen.generate_card(too_good_decision)

            back_html = card['back']

            import re
            error_map_match = re.search(r"data-error-map='(\{[^']+\})'", back_html)
            error_map = json.loads(error_map_match.group(1))

            # No Double (A) error should be ABOVE the close threshold
            no_double_error = error_map['A']
            assert no_double_error > CLOSE_THRESHOLD, (
                f"No Double error ({no_double_error}) should be > {CLOSE_THRESHOLD} "
                "to be marked INCORRECT, not CLOSE"
            )

    def test_too_good_double_pass_is_incorrect(self, too_good_decision):
        """'Double/Pass' should be INCORRECT when 'Too good/Pass' is correct.

        Even though both have the same equity (1.000), they represent different concepts:
        - 'Double/Pass': You DOUBLE, opponent passes
        - 'Too good/Pass': You DON'T double (want gammons), opponent would pass if you did

        They differ on the ACTION dimension (double vs no double), so not CLOSE.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = CardGenerator(Path(tmpdir), show_options=True)
            card = gen.generate_card(too_good_decision)

            back_html = card['back']

            import re
            error_map_match = re.search(r"data-error-map='(\{[^']+\})'", back_html)
            error_map = json.loads(error_map_match.group(1))

            # C = Double/Pass should be INCORRECT (different action concept)
            double_pass_error = error_map['C']
            assert double_pass_error > CLOSE_THRESHOLD, (
                f"Double/Pass error ({double_pass_error}) should be > {CLOSE_THRESHOLD} "
                "because it differs from Too good/Pass on ACTION dimension"
            )

    def test_too_good_double_take_is_incorrect(self, too_good_decision):
        """'Double/Take' should be INCORRECT - differs on both dimensions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = CardGenerator(Path(tmpdir), show_options=True)
            card = gen.generate_card(too_good_decision)

            back_html = card['back']

            import re
            error_map_match = re.search(r"data-error-map='(\{[^']+\})'", back_html)
            error_map = json.loads(error_map_match.group(1))

            # B = Double/Take should have high error (wrong action AND wrong response)
            double_take_error = error_map['B']
            assert double_take_error > CLOSE_THRESHOLD, (
                f"Double/Take error ({double_take_error}) should be > {CLOSE_THRESHOLD} "
                "because opponent should pass, not take"
            )

    def test_too_good_take_is_incorrect(self, too_good_decision):
        """'Too good/Take' should be INCORRECT when 'Too good/Pass' is correct.

        Even though both recognize the position is "too good":
        - 'Too good/Take': Opponent would TAKE if you doubled
        - 'Too good/Pass': Opponent would PASS if you doubled

        They differ on the RESPONSE dimension (take vs pass), so not CLOSE.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = CardGenerator(Path(tmpdir), show_options=True)
            card = gen.generate_card(too_good_decision)

            back_html = card['back']

            import re
            error_map_match = re.search(r"data-error-map='(\{[^']+\})'", back_html)
            error_map = json.loads(error_map_match.group(1))

            # D = Too good/Take should be INCORRECT (different response concept)
            too_good_take_error = error_map['D']
            assert too_good_take_error > CLOSE_THRESHOLD, (
                f"Too good/Take error ({too_good_take_error}) should be > {CLOSE_THRESHOLD} "
                "because it differs from Too good/Pass on RESPONSE dimension"
            )

    def test_too_good_analysis_table_highlights_no_double(self, too_good_decision):
        """The analysis table should still highlight 'No Double' as best for display.

        Even though 'Too good/Pass' is the MCQ answer, the analysis table
        shows the 3 real options (No Double, Double/Take, Double/Pass) and
        'No Double' should be highlighted because it's the practical action.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = CardGenerator(Path(tmpdir), show_options=True)
            card = gen.generate_card(too_good_decision)

            back_html = card['back']

            # The No Double row should have the 'best-move' class
            # Look for a table row with both 'best-move' and 'No double' text
            assert 'class="best-move' in back_html

            # The row with 'No double' notation should be marked as best
            import re
            # Find the row containing "No double" and verify it has best-move class
            no_double_row_pattern = r'<tr class="best-move[^"]*"[^>]*>.*?No double.*?</tr>'
            match = re.search(no_double_row_pattern, back_html, re.DOTALL)
            assert match, "No Double row should have 'best-move' class in analysis table"

    def test_normal_no_double_is_correct_answer(self, normal_no_double_decision):
        """When 'No Double/Take' is genuinely best, it should be the correct answer."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = CardGenerator(Path(tmpdir), show_options=True)
            card = gen.generate_card(normal_no_double_decision)

            back_html = card['back']

            # The correct answer should be A (No Double/Take is at index 0)
            assert 'data-correct-answer="A"' in back_html

    def test_normal_no_double_has_zero_error(self, normal_no_double_decision):
        """When 'No Double/Take' is best, it should have zero error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = CardGenerator(Path(tmpdir), show_options=True)
            card = gen.generate_card(normal_no_double_decision)

            back_html = card['back']

            import re
            error_map_match = re.search(r"data-error-map='(\{[^']+\})'", back_html)
            error_map = json.loads(error_map_match.group(1))

            # A = No Double/Take should have error 0.0 (it's the correct answer)
            assert error_map['A'] == pytest.approx(0.0, abs=0.001)

    def test_normal_all_wrong_answers_are_incorrect(self, normal_no_double_decision):
        """When 'No Double/Take' is best, all other options should be INCORRECT."""
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = CardGenerator(Path(tmpdir), show_options=True)
            card = gen.generate_card(normal_no_double_decision)

            back_html = card['back']

            import re
            error_map_match = re.search(r"data-error-map='(\{[^']+\})'", back_html)
            error_map = json.loads(error_map_match.group(1))

            # All non-A options should be INCORRECT
            for letter in ['B', 'C', 'D', 'E']:
                assert error_map[letter] > CLOSE_THRESHOLD, (
                    f"Option {letter} should be INCORRECT (error > {CLOSE_THRESHOLD})"
                )


class TestTooGoodCubeEdgeCases:
    """Edge case tests for 'too good' cube decision handling."""

    def test_all_cube_errors_are_binary(self):
        """For cube decisions, all non-correct answers should have high error (binary system).

        This ensures JavaScript feedback shows INCORRECT for all wrong answers,
        not CLOSE based on equity similarity.
        """
        position = Position()

        moves = [
            Move(notation="No Double/Take", equity=1.145, rank=3, error=0.145, from_xg_analysis=True),
            Move(notation="Double/Take", equity=1.796, rank=2, error=0.796, from_xg_analysis=True),
            Move(notation="Double/Pass", equity=1.000, rank=4, error=0.0, from_xg_analysis=True),
            Move(notation="Too good/Take", equity=1.145, rank=5, error=0.0, from_xg_analysis=False),  # No Double equity
            Move(notation="Too good/Pass", equity=1.145, rank=1, error=0.0, from_xg_analysis=False),  # No Double equity
        ]

        decision = Decision(
            position=position,
            on_roll=Player.X,
            decision_type=DecisionType.CUBE_ACTION,
            candidate_moves=moves,
            dice=None,
            cube_value=1,
            match_length=0,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            gen = CardGenerator(Path(tmpdir), show_options=True)
            card = gen.generate_card(decision)

            import re
            error_map_match = re.search(r"data-error-map='(\{[^']+\})'", card['back'])
            error_map = json.loads(error_map_match.group(1))

            # E = Too good/Pass is correct (error 0.0)
            assert error_map['E'] == pytest.approx(0.0, abs=0.001)

            # All others should be INCORRECT (error >> 0.020)
            for letter in ['A', 'B', 'C', 'D']:
                assert error_map[letter] > CLOSE_THRESHOLD, (
                    f"Option {letter} should be INCORRECT with error > {CLOSE_THRESHOLD}, "
                    f"got {error_map[letter]}"
                )

    def test_redouble_too_good_decision(self):
        """Test 'too good' scenario with redouble (cube > 1)."""
        position = Position()

        # With cube at 2, terminology changes to "Redouble"
        moves = [
            Move(notation="No Redouble/Take", equity=1.761, rank=3, error=0.761, from_xg_analysis=True),
            Move(notation="Redouble/Take", equity=3.332, rank=2, error=2.332, from_xg_analysis=True),
            Move(notation="Redouble/Pass", equity=1.000, rank=4, error=0.0, from_xg_analysis=True),
            Move(notation="Too good/Take", equity=1.761, rank=5, error=0.0, from_xg_analysis=False),  # No Redouble equity
            Move(notation="Too good/Pass", equity=1.761, rank=1, error=0.0, from_xg_analysis=False),  # No Redouble equity
        ]

        decision = Decision(
            position=position,
            on_roll=Player.X,
            decision_type=DecisionType.CUBE_ACTION,
            candidate_moves=moves,
            dice=None,
            cube_value=2,
            match_length=0,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            gen = CardGenerator(Path(tmpdir), show_options=True)
            card = gen.generate_card(decision)

            back_html = card['back']

            # Correct answer should still be E (Too good/Pass)
            assert 'data-correct-answer="E"' in back_html

            import re
            error_map_match = re.search(r"data-error-map='(\{[^']+\})'", back_html)
            error_map = json.loads(error_map_match.group(1))

            # E = correct, all others INCORRECT
            assert error_map['E'] == pytest.approx(0.0, abs=0.001)
            assert error_map['A'] > CLOSE_THRESHOLD, "No Redouble should be INCORRECT"
            assert error_map['B'] > CLOSE_THRESHOLD, "Redouble/Take should be INCORRECT"
            assert error_map['C'] > CLOSE_THRESHOLD, "Redouble/Pass should be INCORRECT"
            assert error_map['D'] > CLOSE_THRESHOLD, "Too good/Take should be INCORRECT"

    def test_double_take_correct_all_others_incorrect(self):
        """When 'Double/Take' is correct, all other options should be INCORRECT."""
        position = Position()

        moves = [
            Move(notation="No Double/Take", equity=0.800, rank=2, error=0.050, from_xg_analysis=True),
            Move(notation="Double/Take", equity=0.850, rank=1, error=0.0, from_xg_analysis=True),
            Move(notation="Double/Pass", equity=1.000, rank=3, error=0.150, from_xg_analysis=True),
            Move(notation="Too good/Take", equity=0.800, rank=4, error=0.050, from_xg_analysis=False),  # No Double equity
            Move(notation="Too good/Pass", equity=0.800, rank=5, error=0.050, from_xg_analysis=False),  # No Double equity
        ]

        decision = Decision(
            position=position,
            on_roll=Player.X,
            decision_type=DecisionType.CUBE_ACTION,
            candidate_moves=moves,
            dice=None,
            cube_value=1,
            match_length=0,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            gen = CardGenerator(Path(tmpdir), show_options=True)
            card = gen.generate_card(decision)

            back_html = card['back']

            # Correct answer should be B (Double/Take)
            assert 'data-correct-answer="B"' in back_html

            import re
            error_map_match = re.search(r"data-error-map='(\{[^']+\})'", back_html)
            error_map = json.loads(error_map_match.group(1))

            # B = correct, all others INCORRECT
            assert error_map['B'] == pytest.approx(0.0, abs=0.001)
            for letter in ['A', 'C', 'D', 'E']:
                assert error_map[letter] > CLOSE_THRESHOLD, (
                    f"Option {letter} should be INCORRECT"
                )

    def test_double_pass_correct_all_others_incorrect(self):
        """When 'Double/Pass' is correct, all other options should be INCORRECT."""
        position = Position()

        moves = [
            Move(notation="No Double/Take", equity=0.950, rank=2, error=0.050, from_xg_analysis=True),
            Move(notation="Double/Take", equity=1.500, rank=3, error=0.500, from_xg_analysis=True),
            Move(notation="Double/Pass", equity=1.000, rank=1, error=0.0, from_xg_analysis=True),
            Move(notation="Too good/Take", equity=0.950, rank=4, error=0.050, from_xg_analysis=False),  # No Double equity
            Move(notation="Too good/Pass", equity=0.950, rank=5, error=0.050, from_xg_analysis=False),  # No Double equity
        ]

        decision = Decision(
            position=position,
            on_roll=Player.X,
            decision_type=DecisionType.CUBE_ACTION,
            candidate_moves=moves,
            dice=None,
            cube_value=1,
            match_length=0,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            gen = CardGenerator(Path(tmpdir), show_options=True)
            card = gen.generate_card(decision)

            back_html = card['back']

            # Correct answer should be C (Double/Pass)
            assert 'data-correct-answer="C"' in back_html

            import re
            error_map_match = re.search(r"data-error-map='(\{[^']+\})'", back_html)
            error_map = json.loads(error_map_match.group(1))

            # C = correct, all others INCORRECT
            assert error_map['C'] == pytest.approx(0.0, abs=0.001)
            for letter in ['A', 'B', 'D', 'E']:
                assert error_map[letter] > CLOSE_THRESHOLD, (
                    f"Option {letter} should be INCORRECT"
                )
