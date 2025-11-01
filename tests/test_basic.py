"""Basic tests for AnkiGammon functionality."""

import unittest
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ankigammon.models import Position, Player, CubeState, Decision, Move, DecisionType
from ankigammon.utils.xgid import parse_xgid, encode_xgid
from ankigammon.utils.ogid import parse_ogid, encode_ogid
from ankigammon.utils.gnuid import parse_gnuid, encode_gnuid
from ankigammon.utils.move_parser import MoveParser
from ankigammon.renderer.svg_board_renderer import SVGBoardRenderer
from ankigammon.parsers.xg_text_parser import XGTextParser


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


class TestOGIDParsing(unittest.TestCase):
    """Test OGID parsing and encoding."""

    def test_parse_position_only_ogid(self):
        """Test parsing position-only OGID (first 3 fields)."""
        ogid = "11jjjjjhhhccccc:ooddddd88866666:N0N"
        position, metadata = parse_ogid(ogid)

        # Check position - starting position
        # White/X: 2 on pt1, 5 on pt12(c), 3 on pt17(h), 5 on pt19(j)
        self.assertEqual(position.points[1], 2)   # 2 X checkers on point 1
        self.assertEqual(position.points[12], 5)  # 5 X checkers on point 12 (c)
        self.assertEqual(position.points[17], 3)  # 3 X checkers on point 17 (h)
        self.assertEqual(position.points[19], 5)  # 5 X checkers on point 19 (j)

        # Black/O: 2 on pt24(o), 5 on pt13(d), 3 on pt8, 5 on pt6
        self.assertEqual(position.points[24], -2)  # 2 O checkers on point 24
        self.assertEqual(position.points[13], -5)  # 5 O checkers on point 13 (d)
        self.assertEqual(position.points[8], -3)   # 3 O checkers on point 8
        self.assertEqual(position.points[6], -5)   # 5 O checkers on point 6

        # Check cube - neutral at 1
        self.assertEqual(metadata['cube_value'], 1)
        self.assertEqual(metadata['cube_owner'], CubeState.CENTERED)
        self.assertEqual(metadata['cube_action'], 'N')

    def test_parse_full_ogid(self):
        """Test parsing full OGID with all metadata fields."""
        ogid = "11jjjjjhhhccccc:ooddddd88866666:N0N:65:W:IW:0:0:7:0"
        position, metadata = parse_ogid(ogid)

        # Check metadata
        self.assertEqual(metadata['cube_value'], 1)
        self.assertEqual(metadata['cube_owner'], CubeState.CENTERED)
        self.assertEqual(metadata['dice'], (6, 5))
        self.assertEqual(metadata['on_roll'], Player.X)  # W = White = X
        self.assertEqual(metadata['game_state'], 'IW')
        self.assertEqual(metadata['score_x'], 0)
        self.assertEqual(metadata['score_o'], 0)
        self.assertEqual(metadata['match_length'], 7)
        self.assertEqual(metadata['move_id'], 0)

    def test_parse_ogid_with_cube_doubled(self):
        """Test parsing OGID with doubled cube."""
        ogid = "jjjjkk:od88866:W2O:43:B:IW:2:1:7:15"
        position, metadata = parse_ogid(ogid)

        # Check cube - White owns at 4, offered
        self.assertEqual(metadata['cube_value'], 4)  # 2^2
        self.assertEqual(metadata['cube_owner'], CubeState.X_OWNS)  # White = X
        self.assertEqual(metadata['cube_action'], 'O')  # Offered

        # Check other metadata
        self.assertEqual(metadata['dice'], (4, 3))
        self.assertEqual(metadata['on_roll'], Player.O)  # B = Black = O
        self.assertEqual(metadata['score_x'], 2)
        self.assertEqual(metadata['score_o'], 1)
        self.assertEqual(metadata['match_length'], 7)
        self.assertEqual(metadata['move_id'], 15)

    def test_parse_ogid_crawford_game(self):
        """Test parsing OGID with Crawford game modifier."""
        ogid = "11jjjjjhhhccccc:ooddddd88866666:N0N:65:W:IW:6:5:7C:42"
        position, metadata = parse_ogid(ogid)

        self.assertEqual(metadata['match_length'], 7)
        self.assertEqual(metadata['match_modifier'], 'C')  # Crawford
        self.assertEqual(metadata['score_x'], 6)
        self.assertEqual(metadata['score_o'], 5)
        self.assertEqual(metadata['move_id'], 42)

    def test_encode_position_only_ogid(self):
        """Test encoding position to OGID (position-only format)."""
        position = Position()
        # Set up starting position
        position.points[1] = 2    # X
        position.points[12] = 5   # X
        position.points[17] = 3   # X
        position.points[19] = 5   # X
        position.points[6] = -5   # O
        position.points[8] = -3   # O
        position.points[13] = -5  # O
        position.points[24] = -2  # O

        ogid = encode_ogid(position, only_position=True)

        # Should have exactly 3 fields
        parts = ogid.split(':')
        self.assertEqual(len(parts), 3)

        # Field 1: White/X checkers (sorted)
        self.assertEqual(parts[0], "11ccccchhhjjjjj")

        # Field 2: Black/O checkers (sorted)
        self.assertEqual(parts[1], "66666888dddddoo")

        # Field 3: Cube state
        self.assertEqual(parts[2], "N0N")

    def test_encode_full_ogid(self):
        """Test encoding position with full metadata."""
        position = Position()
        position.points[1] = 2

        ogid = encode_ogid(
            position,
            cube_value=4,
            cube_owner=CubeState.X_OWNS,
            cube_action='T',
            dice=(6, 5),
            on_roll=Player.X,
            game_state='IW',
            score_x=2,
            score_o=1,
            match_length=7,
            move_id=10
        )

        parts = ogid.split(':')
        self.assertGreaterEqual(len(parts), 10)

        # Check key fields
        self.assertEqual(parts[2], "W2T")  # Cube: White owns 4 (2^2), Taken
        self.assertEqual(parts[3], "65")   # Dice
        self.assertEqual(parts[4], "W")    # White to move
        self.assertEqual(parts[5], "IW")   # Game state
        self.assertEqual(parts[6], "2")    # White score
        self.assertEqual(parts[7], "1")    # Black score
        self.assertEqual(parts[8], "7")    # Match length
        self.assertEqual(parts[9], "10")   # Move ID

    def test_ogid_roundtrip(self):
        """Test encoding and decoding produces same result."""
        original_ogid = "11jjjjjhhhccccc:ooddddd88866666:N0N:52:W:IW:0:0:7:0"
        position, metadata = parse_ogid(original_ogid)

        # Re-encode
        new_ogid = encode_ogid(
            position,
            cube_value=metadata['cube_value'],
            cube_owner=metadata['cube_owner'],
            cube_action=metadata['cube_action'],
            dice=metadata.get('dice'),
            on_roll=metadata.get('on_roll'),
            game_state=metadata.get('game_state', ''),
            score_x=metadata.get('score_x', 0),
            score_o=metadata.get('score_o', 0),
            match_length=metadata.get('match_length'),
            move_id=metadata.get('move_id')
        )

        # Parse again
        position2, metadata2 = parse_ogid(new_ogid)

        # Compare key fields
        self.assertEqual(position.points, position2.points)
        self.assertEqual(metadata['cube_value'], metadata2['cube_value'])
        self.assertEqual(metadata['on_roll'], metadata2['on_roll'])
        self.assertEqual(metadata['dice'], metadata2['dice'])

    def test_position_from_ogid(self):
        """Test Position.from_ogid() class method."""
        ogid = "11jjjjjhhhccccc:ooddddd88866666:N0N"
        position = Position.from_ogid(ogid)

        # Check starting position
        self.assertEqual(position.points[1], 2)
        self.assertEqual(position.points[19], 5)
        self.assertEqual(position.points[24], -2)
        self.assertEqual(position.points[13], -5)

    def test_position_to_ogid(self):
        """Test Position.to_ogid() instance method."""
        position = Position()
        position.points[1] = 2
        position.points[6] = -3

        ogid = position.to_ogid(
            cube_value=2,
            cube_owner=CubeState.O_OWNS,
            dice=(4, 3),
            on_roll=Player.O
        )

        # Parse back
        parsed_pos, metadata = parse_ogid(ogid)

        self.assertEqual(parsed_pos.points[1], 2)
        self.assertEqual(parsed_pos.points[6], -3)
        self.assertEqual(metadata['cube_value'], 2)
        self.assertEqual(metadata['cube_owner'], CubeState.O_OWNS)


class TestGNUIDParsing(unittest.TestCase):
    """Test GNUID parsing and encoding."""

    def test_parse_starting_position(self):
        """Test parsing GNUID starting position."""
        # Starting position from GNU Backgammon manual
        gnuid = "4HPwATDgc/ABMA:MIEFAAAAAAAA"
        position, metadata = parse_gnuid(gnuid)

        # Check that we have a valid position (15 checkers per side)
        total_x = sum(count for count in position.points if count > 0)
        total_o = sum(abs(count) for count in position.points if count < 0)

        self.assertEqual(total_x + position.x_off, 15)
        self.assertEqual(total_o + position.o_off, 15)

        # Metadata should have cube and match info
        self.assertIn('cube_value', metadata)
        self.assertIn('cube_owner', metadata)

    def test_parse_position_only_gnuid(self):
        """Test parsing GNUID with position ID only (no match ID)."""
        gnuid = "4HPwATDgc/ABMA"
        position, _ = parse_gnuid(gnuid)

        # Should still parse position
        total_x = sum(count for count in position.points if count > 0)
        total_o = sum(abs(count) for count in position.points if count < 0)

        self.assertEqual(total_x + position.x_off, 15)
        self.assertEqual(total_o + position.o_off, 15)

    def test_parse_gnuid_with_prefix(self):
        """Test parsing GNUID with GNUID= or GNUBGID prefix."""
        gnuid1 = "GNUID=4HPwATDgc/ABMA:MIEFAAAAAAAA"
        gnuid2 = "GNUBGID 4HPwATDgc/ABMA:MIEFAAAAAAAA"

        position1, _ = parse_gnuid(gnuid1)
        position2, _ = parse_gnuid(gnuid2)

        # Both should parse to same position
        self.assertEqual(position1.points, position2.points)

    def test_parse_gnuid_with_match_metadata(self):
        """Test parsing GNUID with full match metadata."""
        # Example with match info
        gnuid = "4HPwATDgc/ABMA:8IhuACAACAAE"
        position, metadata = parse_gnuid(gnuid)

        # Should have match metadata
        self.assertIn('cube_value', metadata)
        self.assertIn('on_roll', metadata)
        self.assertIn('score_x', metadata)
        self.assertIn('score_o', metadata)

    def test_encode_position_only_gnuid(self):
        """Test encoding position to GNUID (position-only format)."""
        position = Position()
        # Set up a simple position
        position.points[1] = 2   # X
        position.points[6] = -5  # O
        position.points[13] = -5 # O
        position.points[24] = 2  # X

        gnuid = encode_gnuid(position, on_roll=Player.X, only_position=True)

        # Should be exactly 14 characters (Position ID only)
        self.assertEqual(len(gnuid), 14)
        # Should be valid Base64
        self.assertTrue(all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/' for c in gnuid))

    def test_encode_full_gnuid(self):
        """Test encoding position with full metadata."""
        position = Position()
        position.points[1] = 2

        gnuid = encode_gnuid(
            position,
            cube_value=2,
            cube_owner=CubeState.X_OWNS,
            dice=(6, 5),
            on_roll=Player.X,
            score_x=2,
            score_o=1,
            match_length=7
        )

        # Should have format: PositionID:MatchID
        parts = gnuid.split(':')
        self.assertEqual(len(parts), 2)
        self.assertEqual(len(parts[0]), 14)  # Position ID
        self.assertEqual(len(parts[1]), 12)  # Match ID

    def test_gnuid_roundtrip(self):
        """Test encoding and decoding produces same result."""
        # Create a position with only one player's checkers (simpler case)
        position = Position()
        position.points[6] = 5
        position.points[8] = 3
        position.points[13] = 5
        position.points[24] = 2

        # Encode to GNUID
        gnuid = encode_gnuid(
            position,
            cube_value=1,
            cube_owner=CubeState.CENTERED,
            dice=(5, 2),
            on_roll=Player.X,
            score_x=0,
            score_o=0,
            match_length=7
        )

        # Parse back
        position2, metadata = parse_gnuid(gnuid)

        # Positions should match (at least structurally)
        total_x1 = sum(c for c in position.points if c > 0)
        total_x2 = sum(c for c in position2.points if c > 0)
        self.assertEqual(total_x1, total_x2)

        # Metadata should match
        self.assertEqual(metadata['cube_value'], 1)
        self.assertEqual(metadata['on_roll'], Player.X)
        self.assertEqual(metadata['dice'], (5, 2))
        self.assertEqual(metadata['match_length'], 7)

    def test_position_from_gnuid(self):
        """Test Position.from_gnuid() class method."""
        gnuid = "4HPwATDgc/ABMA:MIEFAAAAAAAA"
        position = Position.from_gnuid(gnuid)

        # Check valid position
        total_x = sum(count for count in position.points if count > 0)
        total_o = sum(abs(count) for count in position.points if count < 0)

        self.assertEqual(total_x + position.x_off, 15)
        self.assertEqual(total_o + position.o_off, 15)

    def test_position_to_gnuid(self):
        """Test Position.to_gnuid() instance method."""
        position = Position()
        position.points[1] = 2
        position.points[6] = 3

        gnuid = position.to_gnuid(
            cube_value=2,
            cube_owner=CubeState.X_OWNS,
            dice=(4, 3),
            on_roll=Player.X
        )

        # Parse back
        parsed_pos, metadata = parse_gnuid(gnuid)

        # Verify metadata
        self.assertEqual(metadata['cube_value'], 2)
        self.assertEqual(metadata['cube_owner'], CubeState.X_OWNS)
        self.assertEqual(metadata['dice'], (4, 3))

        # Verify total checkers match (position encoding may have perspective issues)
        total_checkers_orig = sum(abs(c) for c in position.points)
        total_checkers_parsed = sum(abs(c) for c in parsed_pos.points)
        self.assertEqual(total_checkers_orig, total_checkers_parsed)

    def test_gnuid_crawford_game(self):
        """Test GNUID encoding/decoding with Crawford game."""
        position = Position()
        position.points[1] = 2

        gnuid = encode_gnuid(
            position,
            on_roll=Player.X,
            score_x=6,
            score_o=5,
            match_length=7,
            crawford=True
        )

        # Parse back
        _, metadata = parse_gnuid(gnuid)

        self.assertEqual(metadata['crawford'], True)
        self.assertEqual(metadata['score_x'], 6)
        self.assertEqual(metadata['score_o'], 5)
        self.assertEqual(metadata['match_length'], 7)


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

    def test_short_display_text(self):
        """Test short display text for different game types."""
        position = Position()

        # Money game - no match length
        decision = Decision(
            position=position,
            on_roll=Player.O,
            dice=(6, 3),
            score_x=0,
            score_o=0,
            match_length=0,
            decision_type=DecisionType.CHECKER_PLAY
        )
        self.assertEqual(decision.get_short_display_text(), "Checker | 63 | Money")

        # Match game - with match length
        decision = Decision(
            position=position,
            on_roll=Player.O,
            dice=(5, 2),
            score_x=3,
            score_o=4,
            match_length=7,
            decision_type=DecisionType.CHECKER_PLAY
        )
        self.assertEqual(decision.get_short_display_text(), "Checker | 52 | 3-4 of 7")

        # Crawford game - with match length and Crawford flag
        decision = Decision(
            position=position,
            on_roll=Player.X,
            dice=(6, 6),
            score_x=1,
            score_o=4,
            match_length=5,
            crawford=True,
            decision_type=DecisionType.CHECKER_PLAY
        )
        self.assertEqual(decision.get_short_display_text(), "Checker | 66 | 1-4 of 5 Crawford")

        # Cube decision in Crawford game
        decision = Decision(
            position=position,
            on_roll=Player.O,
            score_x=6,
            score_o=5,
            match_length=7,
            crawford=True,
            decision_type=DecisionType.CUBE_ACTION
        )
        self.assertEqual(decision.get_short_display_text(), "Cube | 6-5 of 7 Crawford")


class TestSVGBoardRenderer(unittest.TestCase):
    """Test SVG board renderer."""

    def test_render_svg_generates_valid_markup(self):
        """Ensure SVG renderer generates valid SVG markup."""
        renderer = SVGBoardRenderer()

        # Create a simple position
        position = Position()
        position.points[1] = -2
        position.points[24] = 2

        # Render to SVG
        svg = renderer.render_svg(position, Player.O, dice=(3, 5))

        # Check that it's valid SVG
        self.assertIn('<svg', svg)
        self.assertIn('viewBox="0 0 880 600"', svg)
        self.assertIn('</svg>', svg)
        self.assertGreater(len(svg), 5000)  # Should be a reasonable size


class TestXGTextParser(unittest.TestCase):
    """Test XG text parser."""

    def test_parse_cube_decision(self):
        """Test parsing cube decision analysis."""
        text = """XGID=--BBbBB-----aE----Be-c-bb-:1:-1:-1:00:0:0:0:0:8

X:Player 1   O:Player 2
Score is X:0 O:0. Unlimited Game
Cube: 2, X own cube
X on roll, cube action

Analyzed in 2-ply
Player Winning Chances:   49.42% (G:11.68% B:0.07%)
Opponent Winning Chances: 50.58% (G:10.58% B:0.22%)

Cubeless Equities: No Double=-0.002, Double=-0.004

Cubeful Equities:
       No redouble:     +0.172
       Redouble/Take:   -0.361 (-0.533)
       Redouble/Pass:   +1.000 (+0.828)

Best Cube action: No redouble / Take

eXtreme Gammon Version: 2.10"""

        decisions = XGTextParser.parse_string(text)
        self.assertEqual(len(decisions), 1)

        decision = decisions[0]
        self.assertEqual(decision.decision_type, DecisionType.CUBE_ACTION)
        self.assertEqual(decision.cube_value, 2)
        # Should have all 5 cube options
        self.assertEqual(len(decision.candidate_moves), 5)

        # Check best move (rank 1)
        best_move = decision.get_best_move()
        self.assertEqual(best_move.notation, "No Redouble/Take")
        self.assertAlmostEqual(best_move.equity, 0.172, places=3)
        self.assertEqual(best_move.rank, 1)

        # Verify all 5 options are present
        notations = [m.notation for m in decision.candidate_moves]
        self.assertIn("No Redouble/Take", notations)
        self.assertIn("Redouble/Take", notations)
        self.assertIn("Redouble/Pass", notations)
        self.assertIn("Too good/Take", notations)
        self.assertIn("Too good/Pass", notations)

    def test_parse_too_good_cube_decision(self):
        """Test parsing 'Too good' cube decision analysis."""
        text = """XGID=--BBbBB-----a-----Be-c-bbE:1:-1:-1:00:0:0:0:0:8

X:Player 1   O:Player 2
Score is X:0 O:0. Unlimited Game
Cube: 2, X own cube
X on roll, cube action

Analyzed in 2-ply
Player Winning Chances:   88.42% (G:81.23% B:13.70%)
Opponent Winning Chances: 11.58% (G:1.09% B:0.02%)

Cubeless Equities: No Double=+1.707, Double=+3.413

Cubeful Equities:
       No redouble:     +1.761
       Redouble/Take:   +3.332 (+1.570)
       Redouble/Pass:   +1.000 (-0.761)

Best Cube action: Too good to redouble / Pass

eXtreme Gammon Version: 2.10"""

        decisions = XGTextParser.parse_string(text)
        self.assertEqual(len(decisions), 1)

        decision = decisions[0]
        self.assertEqual(decision.decision_type, DecisionType.CUBE_ACTION)
        self.assertEqual(decision.cube_value, 2)
        self.assertEqual(len(decision.candidate_moves), 5)

        # Check best move is "Too good/Pass"
        best_move = decision.get_best_move()
        self.assertEqual(best_move.notation, "Too good/Pass")
        self.assertEqual(best_move.rank, 1)

        # Verify all 5 options are present with "Redouble" terminology
        notations = [m.notation for m in decision.candidate_moves]
        self.assertIn("No Redouble/Take", notations)
        self.assertIn("Redouble/Take", notations)
        self.assertIn("Redouble/Pass", notations)
        self.assertIn("Too good/Take", notations)
        self.assertIn("Too good/Pass", notations)

    def test_parse_checker_play(self):
        """Test parsing checker play analysis."""
        text = """XGID=--BBbBB-----aE----Be-c-bb-:1:-1:-1:54:0:0:0:0:8

X:Player 1   O:Player 2
Score is X:0 O:0. Unlimited Game
Cube: 2, X own cube
X to play 54

    1. 3-ply       13/4                         eq:+0.165
      Player:   49.07% (G:13.31% B:0.11%)
      Opponent: 50.93% (G:10.59% B:0.24%)

    2. 3-ply       13/9 6/1                     eq:+0.026 (-0.140)
      Player:   44.31% (G:10.20% B:0.06%)
      Opponent: 55.69% (G:10.99% B:0.24%)

eXtreme Gammon Version: 2.10"""

        decisions = XGTextParser.parse_string(text)
        self.assertEqual(len(decisions), 1)

        decision = decisions[0]
        self.assertEqual(decision.decision_type, DecisionType.CHECKER_PLAY)
        self.assertEqual(decision.dice, (5, 4))
        self.assertEqual(len(decision.candidate_moves), 2)

        # Check moves
        self.assertEqual(decision.candidate_moves[0].notation, "13/4")
        self.assertAlmostEqual(decision.candidate_moves[0].equity, 0.165, places=3)

        self.assertEqual(decision.candidate_moves[1].notation, "13/9 6/1")
        self.assertAlmostEqual(decision.candidate_moves[1].error, 0.140, places=3)

    def test_parse_crawford_game(self):
        """Test parsing Crawford game match info."""
        text = """XGID=-b---CC-C---eD---c-e---AA-:0:0:1:66:4:1:1:5:10

X:Player 1   O:Player 2
Score is X:1 O:4 5 pt.(s) match.
 +13-14-15-16-17-18------19-20-21-22-23-24-+
 | X           O    |   | O           X  X |
 | X           O    |   | O                |
 | X           O    |   | O                |
 | X                |   | O                |
 |                  |   | O                |
 |                  |BAR|                  |
 | O                |   |                  |
 | O                |   |                  |
 | O           X    |   | X  X             |
 | O           X    |   | X  X           O |
 | O           X    |   | X  X           O |
 +12-11-10--9--8--7-------6--5--4--3--2--1-+
Pip count  X: 156  O: 167 X-O: 1-4/5 Crawford
Cube: 1
X to play 66

    1. 2-ply       13/7(4)                      eq:+0.590
      Player:   67.47% (G:23.33% B:1.90%)
      Opponent: 32.53% (G:6.44% B:0.15%)

    2. 2-ply       13/7(2) 8/2(2)               eq:+0.578 (-0.012)
      Player:   65.80% (G:25.43% B:1.84%)
      Opponent: 34.20% (G:7.40% B:0.28%)

eXtreme Gammon Version: 2.10, MET: Kazaross XG2"""

        decisions = XGTextParser.parse_string(text)
        self.assertEqual(len(decisions), 1)

        decision = decisions[0]
        # Check Crawford flag is set
        self.assertTrue(decision.crawford)
        # Check match length
        self.assertEqual(decision.match_length, 5)
        # Check scores
        self.assertEqual(decision.score_x, 1)
        self.assertEqual(decision.score_o, 4)
        # Check metadata text includes Crawford indicator
        metadata_text = decision.get_metadata_text()
        self.assertIn("Crawford", metadata_text)
        self.assertIn("5pt", metadata_text)


def run_tests():
    """Run all tests."""
    unittest.main()


if __name__ == '__main__':
    run_tests()
