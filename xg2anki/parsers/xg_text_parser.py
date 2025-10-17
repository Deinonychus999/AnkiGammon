"""Parser for XG text exports with ASCII board diagrams.

This parser handles the text format that XG exports with:
- XGID line
- ASCII board diagram
- Move analysis with equities and rollout data
"""

import re
from typing import List, Optional, Tuple

from xg2anki.models import Decision, Move, Position, Player, CubeState, DecisionType
from xg2anki.utils.xgid import parse_xgid


class XGTextParser:
    """Parse XG text export format."""

    @staticmethod
    def parse_file(file_path: str) -> List[Decision]:
        """
        Parse an XG text export file.

        Args:
            file_path: Path to XG text file

        Returns:
            List of Decision objects
        """
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        return XGTextParser.parse_string(content)

    @staticmethod
    def parse_string(content: str) -> List[Decision]:
        """
        Parse XG text export from string.

        Args:
            content: Full text content

        Returns:
            List of Decision objects
        """
        decisions = []

        # Split into sections by XGID
        sections = re.split(r'(XGID=[^\n]+)', content)

        for i in range(1, len(sections), 2):
            if i + 1 >= len(sections):
                break

            xgid_line = sections[i].strip()
            analysis_section = sections[i + 1]

            decision = XGTextParser._parse_decision_section(xgid_line, analysis_section)
            if decision:
                decisions.append(decision)

        return decisions

    @staticmethod
    def _parse_decision_section(xgid_line: str, analysis_section: str) -> Optional[Decision]:
        """Parse a single decision section."""
        # Parse XGID
        try:
            position, metadata = parse_xgid(xgid_line)
        except Exception as e:
            print(f"Error parsing XGID '{xgid_line}': {e}")
            return None

        # Parse game info (players, score, cube, etc.)
        game_info = XGTextParser._parse_game_info(analysis_section)
        if game_info:
            # Update metadata with parsed info
            metadata.update(game_info)

        # Parse move analysis
        moves = XGTextParser._parse_moves(analysis_section)
        if not moves:
            return None

        # Create decision
        decision = Decision(
            position=position,
            xgid=xgid_line,
            on_roll=metadata.get('on_roll', Player.O),
            dice=metadata.get('dice'),
            score_x=metadata.get('score_x', 0),
            score_o=metadata.get('score_o', 0),
            match_length=metadata.get('match_length', 0),
            cube_value=metadata.get('cube_value', 1),
            cube_owner=metadata.get('cube_owner', CubeState.CENTERED),
            decision_type=metadata.get('decision_type', DecisionType.CHECKER_PLAY),
            candidate_moves=moves
        )

        return decision

    @staticmethod
    def _parse_game_info(text: str) -> dict:
        """
        Parse game information from text section.

        Extracts:
        - Players (X:Player 2   O:Player 1)
        - Score (Score is X:3 O:4 5 pt.(s) match.)
        - Cube info (Cube: 2, O own cube)
        - Turn info (X to play 63)
        """
        info = {}

        # First, parse the player designation to build mapping
        # "X:Player 1   O:Player 2" means X is Player 1, O is Player 2
        # Player 1 = BOTTOM player = Player.O in our internal model
        # Player 2 = TOP player = Player.X in our internal model
        xo_to_player = {}
        player_designation = re.search(
            r'([XO]):Player\s+(\d+)',
            text,
            re.IGNORECASE
        )
        if player_designation:
            label = player_designation.group(1).upper()  # 'X' or 'O'
            player_num = int(player_designation.group(2))  # 1 or 2

            # Map: Player 1 = BOTTOM = Player.O, Player 2 = TOP = Player.X
            if player_num == 1:
                xo_to_player[label] = Player.O
            else:
                xo_to_player[label] = Player.X

            # Also get the other player
            other_label = 'O' if label == 'X' else 'X'
            other_player_designation = re.search(
                rf'{other_label}:Player\s+(\d+)',
                text,
                re.IGNORECASE
            )
            if other_player_designation:
                other_num = int(other_player_designation.group(1))
                if other_num == 1:
                    xo_to_player[other_label] = Player.O
                else:
                    xo_to_player[other_label] = Player.X

        # Parse score and match length
        # "Score is X:3 O:4 5 pt.(s) match."
        score_match = re.search(
            r'Score is X:(\d+)\s+O:(\d+)\s+(\d+)\s+pt',
            text,
            re.IGNORECASE
        )
        if score_match:
            info['score_x'] = int(score_match.group(1))
            info['score_o'] = int(score_match.group(2))
            info['match_length'] = int(score_match.group(3))

        # Check for money game
        if 'money game' in text.lower():
            info['match_length'] = 0

        # Parse cube info
        # "Cube: 2, O own cube" or "Cube: 4, X own cube" or "Cube: 1"
        cube_match = re.search(
            r'Cube:\s*(\d+)(?:,\s*([XO])\s+own\s+cube)?',
            text,
            re.IGNORECASE
        )
        if cube_match:
            info['cube_value'] = int(cube_match.group(1))
            owner_label = cube_match.group(2)
            if owner_label:
                owner_label = owner_label.upper()
                # Use mapping if available
                if owner_label in xo_to_player:
                    owner_player = xo_to_player[owner_label]
                    if owner_player == Player.X:
                        info['cube_owner'] = CubeState.X_OWNS
                    else:
                        info['cube_owner'] = CubeState.O_OWNS
                else:
                    # Fallback: old behavior
                    if owner_label == 'X':
                        info['cube_owner'] = CubeState.X_OWNS
                    elif owner_label == 'O':
                        info['cube_owner'] = CubeState.O_OWNS
            else:
                info['cube_owner'] = CubeState.CENTERED

        # Parse turn info
        # "X to play 63" or "O to play 52" or "X to roll" or "O on roll"
        turn_match = re.search(
            r'([XO])\s+(?:to\s+play|to\s+roll|on\s+roll)(?:\s+(\d)(\d))?',
            text,
            re.IGNORECASE
        )
        if turn_match:
            player_label = turn_match.group(1).upper()  # 'X' or 'O' from text

            # Use the mapping if available, otherwise fall back to simple mapping
            if player_label in xo_to_player:
                info['on_roll'] = xo_to_player[player_label]
            else:
                # Fallback: assume X=Player.X, O=Player.O (old behavior)
                info['on_roll'] = Player.X if player_label == 'X' else Player.O

            dice1 = turn_match.group(2)
            dice2 = turn_match.group(3)
            if dice1 and dice2:
                info['dice'] = (int(dice1), int(dice2))

        # Check for cube actions
        if any(word in text.lower() for word in ['double', 'take', 'drop', 'pass', 'beaver']):
            # Look for cube decision indicators
            if 'double' in text.lower() and 'to play' not in text.lower():
                info['decision_type'] = DecisionType.CUBE_ACTION

        return info

    @staticmethod
    def _parse_moves(text: str) -> List[Move]:
        """
        Parse move analysis from text.

        Format:
            1. XG Roller+  11/8 11/5                    eq:+0.589
              Player:   79.46% (G:17.05% B:0.67%)
              Opponent: 20.54% (G:2.22% B:0.06%)

            2. XG Roller+  9/3* 6/3                     eq:+0.529 (-0.061)
              Player:   76.43% (G:24.10% B:1.77%)
              Opponent: 23.57% (G:3.32% B:0.12%)

        Or for cube decisions:
            1. XG Roller+  Double, take                 eq:+0.678
            2. XG Roller+  Double, drop                 eq:+0.645 (-0.033)
            3. XG Roller+  No double                    eq:+0.623 (-0.055)
        """
        moves = []

        # Find all move entries
        # Pattern: rank. [engine] notation eq:[equity] [(error)]
        move_pattern = re.compile(
            r'^\s*(\d+)\.\s+(?:[\w\s+-]+?)\s+(.*?)\s+eq:\s*([+-]?\d+\.\d+)(?:\s*\(([+-]\d+\.\d+)\))?',
            re.MULTILINE | re.IGNORECASE
        )

        for match in move_pattern.finditer(text):
            rank = int(match.group(1))
            notation = match.group(2).strip()
            equity = float(match.group(3))
            error_str = match.group(4)

            # Parse error (if present in parentheses)
            if error_str:
                error = abs(float(error_str))
            else:
                # First move has no error
                error = 0.0 if rank == 1 else 0.0

            # Clean up notation
            notation = XGTextParser._clean_move_notation(notation)

            moves.append(Move(
                notation=notation,
                equity=equity,
                error=error,
                rank=rank
            ))

        # If we didn't find moves with the standard pattern, try alternative patterns
        if not moves:
            moves = XGTextParser._parse_moves_fallback(text)

        # Calculate errors if not already set
        if moves and len(moves) > 1:
            best_equity = moves[0].equity
            for move in moves[1:]:
                if move.error == 0.0:
                    move.error = abs(best_equity - move.equity)

        return moves

    @staticmethod
    def _parse_moves_fallback(text: str) -> List[Move]:
        """Fallback parser for alternative move formats."""
        moves = []

        # Try simpler pattern without engine name
        # "1. 11/8 11/5   eq:+0.589"
        pattern = re.compile(
            r'^\s*(\d+)\.\s+(.*?)\s+eq:\s*([+-]?\d+\.\d+)',
            re.MULTILINE | re.IGNORECASE
        )

        for match in pattern.finditer(text):
            rank = int(match.group(1))
            notation = match.group(2).strip()
            equity = float(match.group(3))

            notation = XGTextParser._clean_move_notation(notation)

            moves.append(Move(
                notation=notation,
                equity=equity,
                error=0.0,
                rank=rank
            ))

        return moves

    @staticmethod
    def _clean_move_notation(notation: str) -> str:
        """Clean up move notation."""
        # Remove engine names like "XG Roller+", "Roller++", "3-ply", etc.
        # These appear at the start of the notation
        notation = re.sub(r'^(XG\s+)?(?:Roller\+*|rollout|\d+-ply)\s+', '', notation, flags=re.IGNORECASE)

        # Remove extra whitespace
        notation = re.sub(r'\s+', ' ', notation)
        notation = notation.strip()

        # Handle cube actions
        notation_lower = notation.lower()
        if 'double' in notation_lower and 'take' in notation_lower:
            return "Double/Take"
        elif 'double' in notation_lower and 'drop' in notation_lower:
            return "Double/Drop"
        elif 'double' in notation_lower and 'pass' in notation_lower:
            return "Double/Pass"
        elif 'no double' in notation_lower or 'no redouble' in notation_lower:
            return "No Double"
        elif 'take' in notation_lower:
            return "Take"
        elif 'drop' in notation_lower or 'pass' in notation_lower:
            return "Drop"

        return notation
