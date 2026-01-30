"""
GNU Backgammon text output parser.

Parses analysis output from gnubg-cli.exe into Decision objects.
"""

import re
from typing import List, Optional

from ankigammon.models import Decision, DecisionType, Move, Player, Position
from ankigammon.utils.xgid import parse_xgid


class GNUBGParser:
    """Parse GNU Backgammon analysis output."""

    @staticmethod
    def _parse_locale_float(s: str) -> float:
        """Parse a float string that may use comma or period as decimal separator."""
        return float(s.replace(',', '.'))

    @staticmethod
    def parse_analysis(
        gnubg_output: str,
        xgid: str,
        decision_type: DecisionType
    ) -> Decision:
        """
        Parse gnubg output into Decision object.

        Args:
            gnubg_output: Raw text output from gnubg-cli.exe
            xgid: Original XGID for position reconstruction
            decision_type: CHECKER_PLAY or CUBE_ACTION

        Returns:
            Decision object with populated candidate_moves

        Raises:
            ValueError: If parsing fails
        """
        # Parse XGID to get position and metadata
        position, metadata = parse_xgid(xgid)

        # Parse moves based on decision type
        if decision_type == DecisionType.CHECKER_PLAY:
            moves = GNUBGParser._parse_checker_play(gnubg_output)
        else:
            cube_value = metadata.get('cube_value', 1)
            moves = GNUBGParser._parse_cube_decision(gnubg_output, cube_value)

        if not moves:
            raise ValueError(f"No moves found in gnubg output for {decision_type.value}")

        # Extract winning chances from metadata or output
        winning_chances = GNUBGParser._parse_winning_chances(gnubg_output)

        # Build Decision object
        decision = Decision(
            position=position,
            on_roll=metadata.get('on_roll', Player.O),
            decision_type=decision_type,
            candidate_moves=moves,
            dice=metadata.get('dice'),
            xgid=xgid,
            score_x=metadata.get('score_x', 0),
            score_o=metadata.get('score_o', 0),
            match_length=metadata.get('match_length', 0),
            cube_value=metadata.get('cube_value', 1),
            cube_owner=metadata.get('cube_owner'),
        )

        # Add winning chances to decision if found
        if winning_chances:
            decision.player_win_pct = winning_chances.get('player_win_pct')
            decision.player_gammon_pct = winning_chances.get('player_gammon_pct')
            decision.player_backgammon_pct = winning_chances.get('player_backgammon_pct')
            decision.opponent_win_pct = winning_chances.get('opponent_win_pct')
            decision.opponent_gammon_pct = winning_chances.get('opponent_gammon_pct')
            decision.opponent_backgammon_pct = winning_chances.get('opponent_backgammon_pct')

        return decision

    @staticmethod
    def _parse_checker_play(text: str) -> List[Move]:
        """
        Parse checker play analysis from gnubg output.

        Expected format:
            1. Cubeful 4-ply    21/16 21/15                  Eq.:  -0.411
               0.266 0.021 0.001 - 0.734 0.048 0.001
                4-ply cubeful prune [4ply]
            2. Cubeful 4-ply    9/4 9/3                      Eq.:  -0.437 ( -0.025)
               0.249 0.004 0.000 - 0.751 0.021 0.000
                4-ply cubeful prune [4ply]

        Args:
            text: gnubg output text

        Returns:
            List of Move objects sorted by rank
        """
        moves = []
        lines = text.split('\n')

        # Pattern for gnubg move lines (supports European locale with comma decimal separator)
        # Matches: "    1. Cubeful 4-ply    21/16 21/15                  Eq.:  -0.411"
        #          "    2. Cubeful 4-ply    9/4 9/3                      Eq.:  -0.437 ( -0.025)"
        move_pattern = re.compile(
            r'^\s*(\d+)\.\s+(?:Cubeful\s+\d+-ply\s+)?(.*?)\s+Eq\.?:\s*([+-]?\d+[.,]\d+)(?:\s*\(\s*([+-]?\d+[.,]\d+)\))?',
            re.IGNORECASE
        )

        # Pattern for probability line (supports European locale with comma decimal separator)
        # Matches: "       0.266 0.021 0.001 - 0.734 0.048 0.001" or "       0,266 0,021 0,001 - 0,734 0,048 0,001"
        prob_pattern = re.compile(
            r'^\s*(\d[.,]\d+)\s+(\d[.,]\d+)\s+(\d[.,]\d+)\s*-\s*(\d[.,]\d+)\s+(\d[.,]\d+)\s+(\d[.,]\d+)'
        )

        for i, line in enumerate(lines):
            match = move_pattern.match(line)
            if match:
                rank = int(match.group(1))
                notation = match.group(2).strip()
                equity = GNUBGParser._parse_locale_float(match.group(3))
                error_str = match.group(4)

                error = GNUBGParser._parse_locale_float(error_str) if error_str else 0.0
                abs_error = abs(error)

                # Look for probability line on next line
                player_win = None
                player_gammon = None
                player_backgammon = None
                opponent_win = None
                opponent_gammon = None
                opponent_backgammon = None

                if i + 1 < len(lines):
                    prob_match = prob_pattern.match(lines[i + 1])
                    if prob_match:
                        player_win = GNUBGParser._parse_locale_float(prob_match.group(1)) * 100
                        player_gammon = GNUBGParser._parse_locale_float(prob_match.group(2)) * 100
                        player_backgammon = GNUBGParser._parse_locale_float(prob_match.group(3)) * 100
                        opponent_win = GNUBGParser._parse_locale_float(prob_match.group(4)) * 100
                        opponent_gammon = GNUBGParser._parse_locale_float(prob_match.group(5)) * 100
                        opponent_backgammon = GNUBGParser._parse_locale_float(prob_match.group(6)) * 100

                moves.append(Move(
                    notation=notation,
                    equity=equity,
                    rank=rank,
                    error=abs_error,
                    xg_error=error,
                    xg_notation=notation,
                    xg_rank=rank,
                    from_xg_analysis=True,
                    player_win_pct=player_win,
                    player_gammon_pct=player_gammon,
                    player_backgammon_pct=player_backgammon,
                    opponent_win_pct=opponent_win,
                    opponent_gammon_pct=opponent_gammon,
                    opponent_backgammon_pct=opponent_backgammon
                ))

        # If no moves found, try alternative pattern
        if not moves:
            # Try simpler pattern without rank numbers (supports European locale)
            alt_pattern = re.compile(
                r'^\s*([0-9/\s*bar]+?)\s+Eq:\s*([+-]?\d+[.,]\d+)',
                re.MULTILINE
            )
            for i, match in enumerate(alt_pattern.finditer(text), 1):
                notation = match.group(1).strip()
                equity = GNUBGParser._parse_locale_float(match.group(2))

                moves.append(Move(
                    notation=notation,
                    equity=equity,
                    rank=i,
                    error=0.0,
                    from_xg_analysis=True
                ))

        # Sort by equity (highest first) and recalculate errors
        if moves:
            moves.sort(key=lambda m: m.equity, reverse=True)
            best_equity = moves[0].equity

            for i, move in enumerate(moves, 1):
                move.rank = i
                move.error = abs(best_equity - move.equity)

        return moves

    @staticmethod
    def _parse_cube_decision(text: str, cube_value: int = 1) -> List[Move]:
        """
        Parse cube decision analysis from gnubg output.

        Expected format:
            Cubeful equities:
            1. No double           +0.172
            2. Double, take        -0.361  (-0.533)
            3. Double, pass        +1.000  (+0.828)

            Proper cube action: No double

        Note: Score matrix generation always uses initial double (cube=1), so
        "You cannot double" should not occur. This handler is for edge cases
        and non-matrix analysis. Returns move that displays as "—" in matrix.

        Generates all 5 cube options (like XG parser):
        - No double/Take
        - Double/Take
        - Double/Pass
        - Too good/Take (synthetic)
        - Too good/Pass (synthetic)

        Args:
            text: gnubg output text

        Returns:
            List of Move objects with all 5 cube options
        """
        moves = []

        # Handle "You cannot double" (restricted doubling at certain match scores)
        if 'You cannot double' in text or 'you cannot double' in text:
            moves.append(Move(
                notation="No Double/Take",
                equity=0.0,  # No equity info available
                error=0.0,
                rank=1,
                xg_error=0.0,
                xg_notation="No Double/Take",
                xg_rank=1,
                from_xg_analysis=True
            ))
            return moves

        # Look for "Cubeful equities:" section
        if 'Cubeful equities' not in text and 'cubeful equities' not in text:
            return moves

        # Parse the 3 equity values from gnubg (supports European locale with comma)
        # Pattern to match cube decision lines:
        # "1. No double           +0.172" or "1. No double           +0,172"
        # "2. Double, take        -0.361  (-0.533)"
        # "3. Double, pass        +1.000  (+0.828)"
        pattern = re.compile(
            r'^\s*\d+\.\s*(No (?:re)?double|(?:Re)?[Dd]ouble,?\s*(?:take|pass|drop))\s*([+-]?\d+[.,]\d+)(?:\s*\(([+-]\d+[.,]\d+)\))?',
            re.MULTILINE | re.IGNORECASE
        )

        # Store parsed equities in order they appear
        gnubg_moves_data = []  # List of (normalized_notation, equity, gnubg_error)
        for match in pattern.finditer(text):
            notation = match.group(1).strip()
            equity = GNUBGParser._parse_locale_float(match.group(2))
            error_str = match.group(3)

            gnubg_error = GNUBGParser._parse_locale_float(error_str) if error_str else 0.0

            normalized = notation.replace(', ', '/').replace(',', '/')
            normalized = GNUBGParser._normalize_cube_notation(normalized)

            gnubg_moves_data.append((normalized, equity, gnubg_error))

        if not gnubg_moves_data:
            return moves

        # Build equity map for easy lookup
        equity_map = {data[0]: data[1] for data in gnubg_moves_data}

        # Parse "Proper cube action:" to determine best move
        best_action_match = re.search(
            r'Proper cube action:\s*(.+?)(?:\n|$)',
            text,
            re.IGNORECASE
        )

        best_action_text = None
        if best_action_match:
            best_action_text = best_action_match.group(1).strip()

        double_term = "Redouble" if cube_value > 1 else "Double"

        all_options = [
            f"No {double_term}/Take",
            f"{double_term}/Take",
            f"{double_term}/Pass",
            f"Too good/Take",
            f"Too good/Pass"
        ]

        no_double_eq = equity_map.get("No Double", None)
        double_take_eq = equity_map.get("Double/Take", None)
        double_pass_eq = equity_map.get("Double/Pass", None)

        option_equities = {}
        if no_double_eq is not None:
            option_equities[f"No {double_term}/Take"] = no_double_eq
        if double_take_eq is not None:
            option_equities[f"{double_term}/Take"] = double_take_eq
        if double_pass_eq is not None:
            option_equities[f"{double_term}/Pass"] = double_pass_eq

        # "Too good" options have No Double equity because you DON'T double
        # The Take/Pass suffix indicates opponent's hypothetical response if you did
        if no_double_eq is not None:
            option_equities["Too good/Take"] = no_double_eq
            option_equities["Too good/Pass"] = no_double_eq

        best_notation = GNUBGParser._parse_best_cube_action(best_action_text, double_term)

        # Map full notation to short XG-style notation for analysis table
        xg_notation_map = {
            f"No {double_term}/Take": f"No {double_term.lower()}",
            f"{double_term}/Take": f"{double_term}/Take",
            f"{double_term}/Pass": f"{double_term}/Pass",
        }

        for option in all_options:
            equity = option_equities.get(option, 0.0)
            is_from_gnubg = not option.startswith("Too good")

            moves.append(Move(
                notation=option,
                equity=equity,
                error=0.0,  # Will calculate below
                rank=0,  # Will assign below
                xg_error=None,
                xg_notation=xg_notation_map.get(option) if is_from_gnubg else None,
                xg_rank=None,
                from_xg_analysis=is_from_gnubg
            ))

        # Preserve canonical order for cube decisions (don't sort by equity)
        if best_notation:
            for move in moves:
                if move.notation == best_notation:
                    move.rank = 1
                    break

            remaining_moves = [m for m in moves if m.rank != 1]
            remaining_moves.sort(key=lambda m: m.equity, reverse=True)

            for i, move in enumerate(remaining_moves, 2):
                move.rank = i
        else:
            moves_by_equity = sorted(moves, key=lambda m: m.equity, reverse=True)
            for i, move_sorted in enumerate(moves_by_equity, 1):
                for move in moves:
                    if move.notation == move_sorted.notation:
                        move.rank = i
                        break

        if moves:
            best_move = next((m for m in moves if m.rank == 1), moves[0])
            for move in moves:
                move.error = abs(best_move.equity - move.equity)

        return moves

    @staticmethod
    def _normalize_cube_notation(notation: str) -> str:
        """
        Normalize cube notation to standard format.

        Args:
            notation: Raw notation (e.g., "Double, take", "No redouble")

        Returns:
            Normalized notation (e.g., "Double/Take", "No Double")
        """
        # Standardize case
        parts = notation.split('/')
        result_parts = []

        for part in parts:
            part = part.strip().lower()

            # Normalize terms
            if 'no' in part and ('double' in part or 'redouble' in part):
                result_parts.append("No Double")
            elif 'double' in part or 'redouble' in part:
                result_parts.append("Double")
            elif 'take' in part:
                result_parts.append("Take")
            elif 'pass' in part or 'drop' in part:
                result_parts.append("Pass")
            elif 'too good' in part:
                result_parts.append("Too good")
            else:
                result_parts.append(part.capitalize())

        return '/'.join(result_parts)

    @staticmethod
    def _parse_best_cube_action(best_text: Optional[str], double_term: str) -> Optional[str]:
        """
        Parse "Proper cube action:" text to determine best move notation.

        Args:
            best_text: Text from "Proper cube action:" line
            double_term: "Double" or "Redouble"

        Returns:
            Standardized notation matching all_options format
        """
        if not best_text:
            return None

        text_lower = best_text.lower()

        if 'too good' in text_lower:
            if 'take' in text_lower:
                return "Too good/Take"
            elif 'pass' in text_lower or 'drop' in text_lower:
                return "Too good/Pass"
        elif 'no double' in text_lower or 'no redouble' in text_lower:
            return f"No {double_term}/Take"
        elif 'double' in text_lower or 'redouble' in text_lower:
            if 'take' in text_lower:
                return f"{double_term}/Take"
            elif 'pass' in text_lower or 'drop' in text_lower:
                return f"{double_term}/Pass"

        return None

    @staticmethod
    def _parse_winning_chances(text: str) -> dict:
        """
        Extract W/G/B percentages from gnubg output.

        Looks for patterns like:
            Cubeless equity: +0.172
            Win: 52.3%  G: 14.2%  B: 0.8%

        or:
            0.523 0.142 0.008 - 0.477 0.124 0.006

        Args:
            text: gnubg output text

        Returns:
            Dictionary with winning chance percentages (or empty dict)
        """
        chances = {}

        # Try pattern 1: "Win: 52.3%  G: 14.2%  B: 0.8%" or "Win: 52,3%  G: 14,2%  B: 0,8%" (European locale)
        win_pattern = re.search(
            r'Win:\s*(\d+[.,]?\d*)%.*?G:\s*(\d+[.,]?\d*)%.*?B:\s*(\d+[.,]?\d*)%',
            text,
            re.IGNORECASE
        )
        if win_pattern:
            chances['player_win_pct'] = GNUBGParser._parse_locale_float(win_pattern.group(1))
            chances['player_gammon_pct'] = GNUBGParser._parse_locale_float(win_pattern.group(2))
            chances['player_backgammon_pct'] = GNUBGParser._parse_locale_float(win_pattern.group(3))

        # Try pattern 2: Decimal probabilities "0.523 0.142 0.008 - 0.477 0.124 0.006" (supports European locale)
        prob_pattern = re.search(
            r'(\d[.,]\d+)\s+(\d[.,]\d+)\s+(\d[.,]\d+)\s*-\s*(\d[.,]\d+)\s+(\d[.,]\d+)\s+(\d[.,]\d+)',
            text
        )
        if prob_pattern:
            chances['player_win_pct'] = GNUBGParser._parse_locale_float(prob_pattern.group(1)) * 100
            chances['player_gammon_pct'] = GNUBGParser._parse_locale_float(prob_pattern.group(2)) * 100
            chances['player_backgammon_pct'] = GNUBGParser._parse_locale_float(prob_pattern.group(3)) * 100
            chances['opponent_win_pct'] = GNUBGParser._parse_locale_float(prob_pattern.group(4)) * 100
            chances['opponent_gammon_pct'] = GNUBGParser._parse_locale_float(prob_pattern.group(5)) * 100
            chances['opponent_backgammon_pct'] = GNUBGParser._parse_locale_float(prob_pattern.group(6)) * 100

        return chances
