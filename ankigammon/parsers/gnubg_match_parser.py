"""
GNU Backgammon match text export parser.

Parses 'export match text' output from gnubg into Decision objects.
"""

import re
from typing import List, Optional, Tuple, Dict
from pathlib import Path

from ankigammon.models import Decision, DecisionType, Move, Player, Position, CubeState
from ankigammon.utils.gnuid import parse_gnuid


class GNUBGMatchParser:
    """Parse GNU Backgammon 'export match text' output."""

    @staticmethod
    def extract_player_names_from_mat(mat_file_path: str) -> Tuple[str, str]:
        """
        Extract player names from .mat file header.

        Args:
            mat_file_path: Path to .mat file

        Returns:
            Tuple of (player1_name, player2_name)
            Defaults to ("Player 1", "Player 2") if not found
        """
        player1 = "Player 1"
        player2 = "Player 2"

        try:
            with open(mat_file_path, 'r', encoding='utf-8') as f:
                # Read first 1000 characters (header section)
                header = f.read(1000)

                # Try Format 1: Semicolon header (OpenGammon, Backgammon Studio)
                # Format: ; [Player 1 "PlayerName"]
                player1_match = re.search(r';\s*\[Player 1\s+"([^"]+)"\]', header, re.IGNORECASE)
                player2_match = re.search(r';\s*\[Player 2\s+"([^"]+)"\]', header, re.IGNORECASE)

                if player1_match:
                    player1 = player1_match.group(1)
                if player2_match:
                    player2 = player2_match.group(1)

                # Try Format 2: Score line (plain text match files)
                # Format: PlayerName1 : Score [whitespace] PlayerName2 : Score
                # Example: " Double98 : 0                        Deinonychus999 : 0"
                if player1 == "Player 1" or player2 == "Player 2":
                    score_match = re.search(
                        r'^\s*([A-Za-z0-9_]+)\s*:\s*\d+\s+([A-Za-z0-9_]+)\s*:\s*\d+',
                        header,
                        re.MULTILINE
                    )
                    if score_match:
                        player1 = score_match.group(1)
                        player2 = score_match.group(2)

        except Exception:
            # If parsing fails, return defaults
            pass

        return player1, player2

    @staticmethod
    def parse_match_files(file_paths: List[str]) -> List[Decision]:
        """
        Parse multiple gnubg match export files into Decision objects.

        Args:
            file_paths: List of paths to text files (one per game)

        Returns:
            List of Decision objects for all positions with analysis

        Raises:
            ValueError: If parsing fails
        """
        import logging
        logger = logging.getLogger(__name__)

        all_decisions = []

        logger.info(f"\n=== Parsing {len(file_paths)} game files ===")
        for i, file_path in enumerate(file_paths, 1):
            logger.info(f"\nGame {i}: {Path(file_path).name}")
            decisions = GNUBGMatchParser.parse_file(file_path)
            logger.info(f"  Parsed {len(decisions)} decisions")

            # Show cube decisions for debugging
            cube_decisions = [d for d in decisions if d.decision_type == DecisionType.CUBE_ACTION]
            logger.info(f"  Found {len(cube_decisions)} cube decisions")
            if cube_decisions:
                for cd in cube_decisions:
                    attr = cd.get_cube_error_attribution()
                    doubler_err = attr['doubler_error']
                    responder_err = attr['responder_error']
                    logger.info(f"    Move {cd.move_number}: doubler={cd.on_roll}, doubler_error={doubler_err}, responder_error={responder_err}")

            all_decisions.extend(decisions)

        logger.info(f"\n=== Total: {len(all_decisions)} decisions from all games ===\n")
        return all_decisions

    @staticmethod
    def parse_file(file_path: str) -> List[Decision]:
        """
        Parse single gnubg match export file.

        Args:
            file_path: Path to text file

        Returns:
            List of Decision objects

        Raises:
            ValueError: If parsing fails
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Extract match metadata
        metadata = GNUBGMatchParser._parse_match_metadata(content)

        # Parse all positions in the file
        decisions = GNUBGMatchParser._parse_positions(content, metadata)

        return decisions

    @staticmethod
    def _parse_match_metadata(text: str) -> Dict:
        """
        Parse match metadata from header.

        Format:
            The score (after 0 games) is: chrhaase 0, Deinonychus 0 (match to 7 points)

        Returns:
            Dictionary with player names and match length
        """
        metadata = {
            'player_o_name': None,
            'player_x_name': None,
            'match_length': 0
        }

        # Parse score line
        score_match = re.search(
            r'The score.*?is:\s*(\w+)\s+(\d+),\s*(\w+)\s+(\d+)\s*\(match to (\d+) point',
            text
        )
        if score_match:
            metadata['player_o_name'] = score_match.group(1)
            metadata['player_x_name'] = score_match.group(3)
            metadata['match_length'] = int(score_match.group(5))

        return metadata

    @staticmethod
    def _parse_positions(text: str, metadata: Dict) -> List[Decision]:
        """
        Parse all positions from match text.

        Args:
            text: Full match text export
            metadata: Match metadata (player names, match length)

        Returns:
            List of Decision objects
        """
        decisions = []
        lines = text.split('\n')
        i = 0

        while i < len(lines):
            line = lines[i]

            # Look for move number header with dice roll
            # Format: "Move number 1:  Deinonychus to play 64"
            move_match = re.match(r'Move number (\d+):\s+(\w+) to play (\d)(\d)', line)
            if move_match:
                try:
                    # Parse checker play decision
                    checker_decision = GNUBGMatchParser._parse_position(
                        lines, i, metadata
                    )

                    # Also check for cube decision in this move
                    cube_decision = GNUBGMatchParser._parse_cube_decision(
                        lines, i, metadata
                    )

                    if cube_decision:
                        decisions.append(cube_decision)
                    if checker_decision:
                        decisions.append(checker_decision)
                except Exception as e:
                    # Log parsing errors for debugging
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Failed to parse position at line {i}: {e}")

            # Also look for cube-only moves (no dice roll)
            # Format: "Move number 24:  De_Luci on roll, cube decision?"
            # Format: "Move number 25:  De_Luci doubles to 2"
            cube_only_match = re.match(r'Move number (\d+):\s+(\w+)(?:\s+on roll,\s+cube decision\?|\s+doubles)', line)
            if cube_only_match:
                try:
                    cube_decision = GNUBGMatchParser._parse_cube_decision_standalone(
                        lines, i, metadata
                    )
                    if cube_decision:
                        decisions.append(cube_decision)
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning(f"Failed to parse cube decision at line {i}: {e}")

            i += 1

        return decisions

    @staticmethod
    def _parse_cube_decision(
        lines: List[str],
        start_idx: int,
        metadata: Dict
    ) -> Optional[Decision]:
        """
        Parse cube decision if present in this move.

        Args:
            lines: All lines from file
            start_idx: Index of "Move number X:" line
            metadata: Match metadata

        Returns:
            Decision object for cube action or None if no cube decision found
        """
        # Extract move number and player
        move_line = lines[start_idx]
        move_match = re.match(r'Move number (\d+):\s+(\w+) to play (\d)(\d)', move_line)
        if not move_match:
            return None

        move_number = int(move_match.group(1))
        player_name = move_match.group(2)
        dice1 = int(move_match.group(3))
        dice2 = int(move_match.group(4))

        # Determine which player
        on_roll = Player.O if player_name == metadata['player_o_name'] else Player.X

        # Look for "Cube analysis" section
        cube_section_idx = None
        for offset in range(1, 50):
            if start_idx + offset >= len(lines):
                break
            line = lines[start_idx + offset]
            if line.strip() == "Cube analysis":
                cube_section_idx = start_idx + offset
                break
            # Stop if we reach the next move or "Rolled XX:"
            if line.startswith('Move number') or re.match(r'Rolled \d\d', line):
                break

        if cube_section_idx is None:
            return None

        # Find Position ID and Match ID
        position_id = None
        match_id = None
        for offset in range(1, 30):
            if start_idx + offset >= len(lines):
                break
            line = lines[start_idx + offset]
            if 'Position ID:' in line:
                pos_match = re.search(r'Position ID:\s+([A-Za-z0-9+/=]+)', line)
                if pos_match:
                    position_id = pos_match.group(1)
            elif 'Match ID' in line:
                mat_match = re.search(r'Match ID\s*:\s+([A-Za-z0-9+/=]+)', line)
                if mat_match:
                    match_id = mat_match.group(1)

        if not position_id:
            return None

        # Parse position from GNUID
        try:
            position, pos_metadata = parse_gnuid(position_id + ":" + match_id if match_id else position_id)
        except:
            return None

        # Generate XGID for score matrix support
        xgid = position.to_xgid(
            cube_value=pos_metadata.get('cube_value', 1),
            cube_owner=pos_metadata.get('cube_owner', CubeState.CENTERED),
            dice=None,  # Cube decision happens before dice roll
            on_roll=on_roll,
            score_x=pos_metadata.get('score_x', 0),
            score_o=pos_metadata.get('score_o', 0),
            match_length=metadata.get('match_length', 0),
            crawford_jacoby=1 if pos_metadata.get('crawford', False) else 0
        )

        # Extract winning chances from "Cube analysis" section
        # Format (cube_section_idx points to "Cube analysis" line):
        #   Cube analysis                                <-- cube_section_idx
        #   1-ply cubeless equity  -0.009 (Money:  -0.009)  <-- +1 line
        #     0.493 0.138 0.006 - 0.507 0.132 0.006   <-- +2 lines (probabilities)
        #   Cubeful equities:
        no_double_probs = None
        for offset in range(1, 10):  # Search forward from cube_section_idx
            if cube_section_idx + offset >= len(lines):
                break
            line = lines[cube_section_idx + offset]

            # Look for "1-ply cubeless equity" line
            if '1-ply cubeless equity' in line:
                # Probabilities are on the next line
                if cube_section_idx + offset + 1 < len(lines):
                    prob_line = lines[cube_section_idx + offset + 1]
                    # Format: "  0.493 0.138 0.006 - 0.507 0.132 0.006"
                    prob_match = re.match(
                        r'\s*(0\.\d+)\s+(0\.\d+)\s+(0\.\d+)\s+-\s+(0\.\d+)\s+(0\.\d+)\s+(0\.\d+)',
                        prob_line
                    )
                    if prob_match:
                        no_double_probs = tuple(float(p) for p in prob_match.groups())
                break

        # Parse cube equities from "Cubeful equities:" section
        equities = {}
        proper_action = None

        for offset in range(cube_section_idx - start_idx, cube_section_idx - start_idx + 20):
            if start_idx + offset >= len(lines):
                break
            line = lines[start_idx + offset]

            # Parse equity lines
            # Format: "1. No double            -0.014"
            equity_match = re.match(r'\s*\d+\.\s+(.+?)\s+([+-]?\d+\.\d+)', line)
            if equity_match:
                action = equity_match.group(1).strip()
                equity = float(equity_match.group(2))
                equities[action] = equity

            # Parse proper cube action
            # Format: "Proper cube action: No double, take (26.0%)" or "Proper cube action: Double, take"
            if 'Proper cube action:' in line:
                proper_match = re.search(r'Proper cube action:\s+(.+?)(?:\s+\(|$)', line)
                if proper_match:
                    proper_action = proper_match.group(1).strip()

            # Stop at "Rolled XX:" line
            if re.match(r'Rolled \d\d', line):
                break

        if not equities or not proper_action:
            return None

        # Find cube error and which action was taken
        # Look for cube-specific error messages and * markers
        cube_error = None  # Doubler's error
        take_error = None  # Responder's error
        doubled = False
        cube_action_taken = None

        # Search for error message - it appears BEFORE "Cube analysis" section
        # Start searching from the beginning of this move, not from "Cube analysis"
        for offset in range(0, cube_section_idx - start_idx + 20):
            if start_idx + offset >= len(lines):
                break
            line = lines[start_idx + offset]

            # Check for doubling action: "* PlayerName doubles"
            double_match = re.search(r'\*\s+\w+\s+doubles', line)
            if double_match:
                doubled = True

            # Check for response action: "* PlayerName accepts" or "* PlayerName passes" or "* PlayerName rejects"
            response_match = re.search(r'\*\s+\w+\s+(accepts|passes|rejects)', line)
            if response_match:
                action = response_match.group(1)
                # Normalize: "rejects" means the same as "passes"
                cube_action_taken = "passes" if action == "rejects" else action

            # Look for cube-specific error messages
            # Format: "Alert: wrong take|bad double|wrong double|missed double|wrong pass ( -X.XXX)!"
            cube_alert_match = re.search(r'Alert: (wrong take|bad double|wrong double|missed double|wrong pass)\s+\(\s*([+-]?\d+\.\d+)\s*\)', line, re.IGNORECASE)
            if cube_alert_match:
                error_type = cube_alert_match.group(1).lower()
                error_value = abs(float(cube_alert_match.group(2)))

                # Assign to correct error field based on error type
                if "take" in error_type or "pass" in error_type:
                    take_error = error_value  # Responder made error (wrong take or wrong pass)
                elif "double" in error_type or "missed" in error_type:
                    cube_error = error_value  # Doubler made error (bad double or missed double)

            # Stop at "Rolled XX:" (actual move content) or board diagram for next move
            # Don't stop at "Move number" header - the error appears between the header and the content
            if re.match(r'Rolled \d\d', line):
                break
            if re.match(r'\s*GNU Backgammon\s+Position ID:', line):
                # Found board diagram for next move, stop here
                if cube_error is not None:  # But only if we already found the error
                    break

        # Only create decision if there was an error (either doubler or responder)
        if (cube_error is None or cube_error == 0.0) and (take_error is None or take_error == 0.0):
            return None

        # Create cube decision moves
        from ankigammon.models import Move
        candidate_moves = []

        # GnuBG provides 3 equities, but we create 5 options like XG does
        # Extract the 3 equities
        nd_equity = equities.get("No double", 0.0)
        dt_equity = equities.get("Double, take", 0.0)
        dp_equity = equities.get("Double, pass", 0.0)

        best_equity = max(nd_equity, dt_equity, dp_equity)

        # Determine which action was actually played
        was_nd = not doubled
        was_dt = doubled and cube_action_taken == "accepts"
        was_dp = doubled and cube_action_taken == "passes"

        # Default: if doubled but response unknown, assume take
        if doubled and cube_action_taken is None:
            was_dt = True

        # Check if proper action indicates "Too good"
        is_too_good = "too good" in proper_action.lower() if proper_action else False

        # Create all 5 moves
        # 1. No Double/Take
        candidate_moves.append(Move(
            notation="No Double/Take",
            equity=nd_equity,
            error=abs(best_equity - nd_equity),
            rank=1,  # Will be recalculated
            was_played=was_nd
        ))

        # 2. Double/Take
        candidate_moves.append(Move(
            notation="Double/Take",
            equity=dt_equity,
            error=abs(best_equity - dt_equity),
            rank=1,  # Will be recalculated
            was_played=was_dt and not is_too_good
        ))

        # 3. Too Good/Take (synthetic - uses Double/Pass equity)
        candidate_moves.append(Move(
            notation="Too Good/Take",
            equity=dp_equity,
            error=abs(best_equity - dp_equity),
            rank=1,  # Will be recalculated
            was_played=was_dt and is_too_good,
            from_xg_analysis=False  # Synthetic option
        ))

        # 4. Too Good/Pass (synthetic - uses Double/Pass equity)
        candidate_moves.append(Move(
            notation="Too Good/Pass",
            equity=dp_equity,
            error=abs(best_equity - dp_equity),
            rank=1,  # Will be recalculated
            was_played=was_dp and is_too_good,
            from_xg_analysis=False  # Synthetic option
        ))

        # 5. Double/Pass
        candidate_moves.append(Move(
            notation="Double/Pass",
            equity=dp_equity,
            error=abs(best_equity - dp_equity),
            rank=1,  # Will be recalculated
            was_played=was_dp and not is_too_good
        ))

        # Determine best move based on proper action (not just raw equity)
        # In "Too good" situations, raw equities are misleading
        if proper_action and "too good to double, pass" in proper_action.lower():
            # Too good to double, if you did opponent would pass
            best_move_notation = "Too Good/Pass"
            # For error calculation, use "No double" equity (the actual correct action)
            best_equity_for_errors = nd_equity
        elif proper_action and "too good to double, take" in proper_action.lower():
            # Too good to double, if you did opponent would take
            best_move_notation = "Too Good/Take"
            # For error calculation, use "No double" equity
            best_equity_for_errors = nd_equity
        elif proper_action and "no double" in proper_action.lower():
            # Not strong enough to double yet
            best_move_notation = "No Double/Take"
            best_equity_for_errors = nd_equity
        elif proper_action and "double, take" in proper_action.lower():
            best_move_notation = "Double/Take"
            best_equity_for_errors = dt_equity
        elif proper_action and "double, pass" in proper_action.lower():
            best_move_notation = "Double/Pass"
            best_equity_for_errors = dp_equity
        else:
            # Fallback: use equity
            best_move = max(candidate_moves, key=lambda m: m.equity)
            best_move_notation = best_move.notation
            best_equity_for_errors = best_move.equity

        # Set ranks: proper action gets rank 1, others ranked by equity
        for move in candidate_moves:
            if move.notation == best_move_notation:
                move.rank = 1
            else:
                # Rank other moves by equity (excluding the best move)
                better_count = sum(1 for m in candidate_moves
                                 if m.notation != best_move_notation and m.equity > move.equity)
                move.rank = 2 + better_count

        # Recalculate errors based on actual best equity (not synthetic option equity)
        for move in candidate_moves:
            move.error = abs(best_equity_for_errors - move.equity)

        # Sort by logical order (not by rank) to maintain consistent display
        # Order: No Double, Double/Take, Double/Pass, Too Good/Take, Too Good/Pass
        order_map = {
            "No Double/Take": 1,
            "Double/Take": 2,
            "Double/Pass": 3,
            "Too Good/Take": 4,
            "Too Good/Pass": 5
        }
        candidate_moves.sort(key=lambda m: order_map.get(m.notation, 99))

        # Create Decision object
        decision = Decision(
            position=position,
            on_roll=on_roll,
            dice=None,  # Cube decision happens before dice roll
            decision_type=DecisionType.CUBE_ACTION,
            candidate_moves=candidate_moves,
            score_x=pos_metadata.get('score_x', 0),
            score_o=pos_metadata.get('score_o', 0),
            match_length=metadata.get('match_length', 0),
            cube_value=pos_metadata.get('cube_value', 1),
            cube_owner=pos_metadata.get('cube_owner', CubeState.CENTERED),
            crawford=pos_metadata.get('crawford', False),
            xgid=xgid,
            move_number=move_number,
            cube_error=cube_error,  # Doubler's error
            take_error=take_error,  # Responder's error
            # Add decision-level winning chances from "No double" evaluation
            player_win_pct=no_double_probs[0] * 100 if no_double_probs else None,
            player_gammon_pct=no_double_probs[1] * 100 if no_double_probs else None,
            player_backgammon_pct=no_double_probs[2] * 100 if no_double_probs else None,
            opponent_win_pct=no_double_probs[3] * 100 if no_double_probs else None,
            opponent_gammon_pct=no_double_probs[4] * 100 if no_double_probs else None,
            opponent_backgammon_pct=no_double_probs[5] * 100 if no_double_probs else None
        )

        return decision

    @staticmethod
    def _parse_cube_decision_standalone(
        lines: List[str],
        start_idx: int,
        metadata: Dict
    ) -> Optional[Decision]:
        """
        Parse standalone cube decision (cube-only move with no checker play).

        These moves have formats like:
        - "Move number 24:  De_Luci on roll, cube decision?"
        - "Move number 25:  De_Luci doubles to 2"

        Args:
            lines: All lines from file
            start_idx: Index of "Move number X:" line
            metadata: Match metadata

        Returns:
            Decision object for cube action or None if no error found
        """
        # Reuse the existing _parse_cube_decision logic
        # but adapt the move number extraction
        move_line = lines[start_idx]

        # Extract move number and player name
        # Handles both formats: "on roll, cube decision?" and "doubles to 2"
        move_match = re.match(r'Move number (\d+):\s+(\w+)', move_line)
        if not move_match:
            return None

        move_number = int(move_match.group(1))
        player_name = move_match.group(2)

        # Determine which player
        on_roll = Player.O if player_name == metadata['player_o_name'] else Player.X

        # Look for "Cube analysis" section
        cube_section_idx = None
        for offset in range(1, 50):
            if start_idx + offset >= len(lines):
                break
            line = lines[start_idx + offset]
            if line.strip() == "Cube analysis":
                cube_section_idx = start_idx + offset
                break
            # Stop if we reach the next move
            if line.startswith('Move number'):
                break

        if cube_section_idx is None:
            return None

        # Find Position ID and Match ID
        position_id = None
        match_id = None
        for offset in range(1, 30):
            if start_idx + offset >= len(lines):
                break
            line = lines[start_idx + offset]
            if 'Position ID:' in line:
                pos_match = re.search(r'Position ID:\s+([A-Za-z0-9+/=]+)', line)
                if pos_match:
                    position_id = pos_match.group(1)
            elif 'Match ID' in line:
                mat_match = re.search(r'Match ID\s*:\s+([A-Za-z0-9+/=]+)', line)
                if mat_match:
                    match_id = mat_match.group(1)

        if not position_id:
            return None

        # Parse position from GNUID
        try:
            position, pos_metadata = parse_gnuid(position_id + ":" + match_id if match_id else position_id)
        except:
            return None

        # Generate XGID for score matrix support
        xgid = position.to_xgid(
            cube_value=pos_metadata.get('cube_value', 1),
            cube_owner=pos_metadata.get('cube_owner', CubeState.CENTERED),
            dice=None,  # Cube decision happens before dice roll
            on_roll=on_roll,
            score_x=pos_metadata.get('score_x', 0),
            score_o=pos_metadata.get('score_o', 0),
            match_length=metadata.get('match_length', 0),
            crawford_jacoby=1 if pos_metadata.get('crawford', False) else 0
        )

        # Extract winning chances from "Cube analysis" section
        # Format (cube_section_idx points to "Cube analysis" line):
        #   Cube analysis                                <-- cube_section_idx
        #   1-ply cubeless equity  -0.009 (Money:  -0.009)  <-- +1 line
        #     0.493 0.138 0.006 - 0.507 0.132 0.006   <-- +2 lines (probabilities)
        #   Cubeful equities:
        no_double_probs = None
        for offset in range(1, 10):  # Search forward from cube_section_idx
            if cube_section_idx + offset >= len(lines):
                break
            line = lines[cube_section_idx + offset]

            # Look for "1-ply cubeless equity" line
            if '1-ply cubeless equity' in line:
                # Probabilities are on the next line
                if cube_section_idx + offset + 1 < len(lines):
                    prob_line = lines[cube_section_idx + offset + 1]
                    # Format: "  0.493 0.138 0.006 - 0.507 0.132 0.006"
                    prob_match = re.match(
                        r'\s*(0\.\d+)\s+(0\.\d+)\s+(0\.\d+)\s+-\s+(0\.\d+)\s+(0\.\d+)\s+(0\.\d+)',
                        prob_line
                    )
                    if prob_match:
                        no_double_probs = tuple(float(p) for p in prob_match.groups())
                break

        # Parse cube equities from "Cubeful equities:" section
        equities = {}
        proper_action = None

        for offset in range(cube_section_idx - start_idx, cube_section_idx - start_idx + 20):
            if start_idx + offset >= len(lines):
                break
            line = lines[start_idx + offset]

            # Parse equity lines
            # Format: "1. No double            -0.014"
            equity_match = re.match(r'\s*\d+\.\s+(.+?)\s+([+-]?\d+\.\d+)', line)
            if equity_match:
                action = equity_match.group(1).strip()
                equity = float(equity_match.group(2))
                equities[action] = equity

            # Parse proper cube action
            # Format: "Proper cube action: Double, pass"
            if 'Proper cube action:' in line:
                proper_match = re.search(r'Proper cube action:\s+(.+?)(?:\s+\(|$)', line)
                if proper_match:
                    proper_action = proper_match.group(1).strip()

            # Stop at next move
            if line.startswith('Move number'):
                break

        if not equities or not proper_action:
            return None

        # Find cube error and which action was taken
        cube_error = None  # Doubler's error
        take_error = None  # Responder's error
        doubled = False
        cube_action_taken = None

        # Search for error message - it appears BEFORE "Cube analysis" section
        # Start searching from the beginning of this move, not from "Cube analysis"
        for offset in range(0, cube_section_idx - start_idx + 20):
            if start_idx + offset >= len(lines):
                break
            line = lines[start_idx + offset]

            # Check for doubling action: "* PlayerName doubles"
            double_match = re.search(r'\*\s+\w+\s+doubles', line)
            if double_match:
                doubled = True

            # Check for response action: "* PlayerName accepts" or "* PlayerName passes" or "* PlayerName rejects"
            response_match = re.search(r'\*\s+\w+\s+(accepts|passes|rejects)', line)
            if response_match:
                action = response_match.group(1)
                # Normalize: "rejects" means the same as "passes"
                cube_action_taken = "passes" if action == "rejects" else action

            # Look for cube-specific error messages
            # Format: "Alert: wrong take|bad double|wrong double|missed double|wrong pass ( -X.XXX)!"
            cube_alert_match = re.search(r'Alert: (wrong take|bad double|wrong double|missed double|wrong pass)\s+\(\s*([+-]?\d+\.\d+)\s*\)', line, re.IGNORECASE)
            if cube_alert_match:
                error_type = cube_alert_match.group(1).lower()
                error_value = abs(float(cube_alert_match.group(2)))

                # Assign to correct error field based on error type
                if "take" in error_type or "pass" in error_type:
                    take_error = error_value  # Responder made error (wrong take or wrong pass)
                elif "double" in error_type or "missed" in error_type:
                    cube_error = error_value  # Doubler made error (bad double or missed double)

            # Stop when we encounter actual move content (board diagram or dice roll)
            # Don't stop at "Move number" header - the error appears between the header and the content
            if line.startswith('Rolled'):
                break
            if re.match(r'\s*GNU Backgammon\s+Position ID:', line):
                # Found board diagram for next move, stop here
                if cube_error is not None:  # But only if we already found the error
                    break

        # Only create decision if there was an error (either doubler or responder)
        if (cube_error is None or cube_error == 0.0) and (take_error is None or take_error == 0.0):
            return None

        # Create cube decision moves
        from ankigammon.models import Move
        candidate_moves = []

        # GnuBG provides 3 equities, but we create 5 options like XG does
        # Extract the 3 equities
        nd_equity = equities.get("No double", 0.0)
        dt_equity = equities.get("Double, take", 0.0)
        dp_equity = equities.get("Double, pass", 0.0)

        best_equity = max(nd_equity, dt_equity, dp_equity)

        # Determine which action was actually played
        was_nd = not doubled
        was_dt = doubled and cube_action_taken == "accepts"
        was_dp = doubled and cube_action_taken == "passes"

        # Default: if doubled but response unknown, assume take
        if doubled and cube_action_taken is None:
            was_dt = True

        # Check if proper action indicates "Too good"
        is_too_good = "too good" in proper_action.lower() if proper_action else False

        # Create all 5 moves
        # 1. No Double/Take
        candidate_moves.append(Move(
            notation="No Double/Take",
            equity=nd_equity,
            error=abs(best_equity - nd_equity),
            rank=1,  # Will be recalculated
            was_played=was_nd
        ))

        # 2. Double/Take
        candidate_moves.append(Move(
            notation="Double/Take",
            equity=dt_equity,
            error=abs(best_equity - dt_equity),
            rank=1,  # Will be recalculated
            was_played=was_dt and not is_too_good
        ))

        # 3. Too Good/Take (synthetic - uses Double/Pass equity)
        candidate_moves.append(Move(
            notation="Too Good/Take",
            equity=dp_equity,
            error=abs(best_equity - dp_equity),
            rank=1,  # Will be recalculated
            was_played=was_dt and is_too_good,
            from_xg_analysis=False  # Synthetic option
        ))

        # 4. Too Good/Pass (synthetic - uses Double/Pass equity)
        candidate_moves.append(Move(
            notation="Too Good/Pass",
            equity=dp_equity,
            error=abs(best_equity - dp_equity),
            rank=1,  # Will be recalculated
            was_played=was_dp and is_too_good,
            from_xg_analysis=False  # Synthetic option
        ))

        # 5. Double/Pass
        candidate_moves.append(Move(
            notation="Double/Pass",
            equity=dp_equity,
            error=abs(best_equity - dp_equity),
            rank=1,  # Will be recalculated
            was_played=was_dp and not is_too_good
        ))

        # Determine best move based on proper action (not just raw equity)
        # In "Too good" situations, raw equities are misleading
        if proper_action and "too good to double, pass" in proper_action.lower():
            # Too good to double, if you did opponent would pass
            best_move_notation = "Too Good/Pass"
            # For error calculation, use "No double" equity (the actual correct action)
            best_equity_for_errors = nd_equity
        elif proper_action and "too good to double, take" in proper_action.lower():
            # Too good to double, if you did opponent would take
            best_move_notation = "Too Good/Take"
            # For error calculation, use "No double" equity
            best_equity_for_errors = nd_equity
        elif proper_action and "no double" in proper_action.lower():
            # Not strong enough to double yet
            best_move_notation = "No Double/Take"
            best_equity_for_errors = nd_equity
        elif proper_action and "double, take" in proper_action.lower():
            best_move_notation = "Double/Take"
            best_equity_for_errors = dt_equity
        elif proper_action and "double, pass" in proper_action.lower():
            best_move_notation = "Double/Pass"
            best_equity_for_errors = dp_equity
        else:
            # Fallback: use equity
            best_move = max(candidate_moves, key=lambda m: m.equity)
            best_move_notation = best_move.notation
            best_equity_for_errors = best_move.equity

        # Set ranks: proper action gets rank 1, others ranked by equity
        for move in candidate_moves:
            if move.notation == best_move_notation:
                move.rank = 1
            else:
                # Rank other moves by equity (excluding the best move)
                better_count = sum(1 for m in candidate_moves
                                 if m.notation != best_move_notation and m.equity > move.equity)
                move.rank = 2 + better_count

        # Recalculate errors based on actual best equity (not synthetic option equity)
        for move in candidate_moves:
            move.error = abs(best_equity_for_errors - move.equity)

        # Sort by logical order (not by rank) to maintain consistent display
        # Order: No Double, Double/Take, Double/Pass, Too Good/Take, Too Good/Pass
        order_map = {
            "No Double/Take": 1,
            "Double/Take": 2,
            "Double/Pass": 3,
            "Too Good/Take": 4,
            "Too Good/Pass": 5
        }
        candidate_moves.sort(key=lambda m: order_map.get(m.notation, 99))

        # Create Decision object
        decision = Decision(
            position=position,
            on_roll=on_roll,
            dice=None,  # Cube decision happens before dice roll
            decision_type=DecisionType.CUBE_ACTION,
            candidate_moves=candidate_moves,
            score_x=pos_metadata.get('score_x', 0),
            score_o=pos_metadata.get('score_o', 0),
            match_length=metadata.get('match_length', 0),
            cube_value=pos_metadata.get('cube_value', 1),
            cube_owner=pos_metadata.get('cube_owner', CubeState.CENTERED),
            crawford=pos_metadata.get('crawford', False),
            xgid=xgid,
            move_number=move_number,
            cube_error=cube_error,  # Doubler's error
            take_error=take_error,  # Responder's error
            # Add decision-level winning chances from "No double" evaluation
            player_win_pct=no_double_probs[0] * 100 if no_double_probs else None,
            player_gammon_pct=no_double_probs[1] * 100 if no_double_probs else None,
            player_backgammon_pct=no_double_probs[2] * 100 if no_double_probs else None,
            opponent_win_pct=no_double_probs[3] * 100 if no_double_probs else None,
            opponent_gammon_pct=no_double_probs[4] * 100 if no_double_probs else None,
            opponent_backgammon_pct=no_double_probs[5] * 100 if no_double_probs else None
        )

        return decision

    @staticmethod
    def _parse_position(
        lines: List[str],
        start_idx: int,
        metadata: Dict
    ) -> Optional[Decision]:
        """
        Parse single position starting from move number line.

        Args:
            lines: All lines from file
            start_idx: Index of "Move number X:" line
            metadata: Match metadata

        Returns:
            Decision object or None if position has no analysis
        """
        # Extract move number and player
        move_line = lines[start_idx]
        move_match = re.match(r'Move number (\d+):\s+(\w+) to play (\d)(\d)', move_line)
        if not move_match:
            return None

        move_number = int(move_match.group(1))
        player_name = move_match.group(2)
        dice1 = int(move_match.group(3))
        dice2 = int(move_match.group(4))

        # Determine which player
        on_roll = Player.O if player_name == metadata['player_o_name'] else Player.X

        # Find Position ID and Match ID lines
        # Format: " GNU Backgammon  Position ID: 4HPwATDgc/ABMA"
        #         "                 Match ID   : cAjzAAAAAAAE"
        position_id = None
        match_id = None
        for offset in range(1, 30):  # Search next 30 lines
            if start_idx + offset >= len(lines):
                break
            line = lines[start_idx + offset]
            if 'Position ID:' in line:
                pos_match = re.search(r'Position ID:\s+([A-Za-z0-9+/=]+)', line)
                if pos_match:
                    position_id = pos_match.group(1)
            elif 'Match ID' in line:
                mat_match = re.search(r'Match ID\s*:\s+([A-Za-z0-9+/=]+)', line)
                if mat_match:
                    match_id = mat_match.group(1)

        if not position_id:
            return None

        # Parse position from GNUID
        try:
            position, pos_metadata = parse_gnuid(position_id + ":" + match_id if match_id else position_id)
        except:
            return None

        # Generate XGID for score matrix support
        xgid = position.to_xgid(
            cube_value=pos_metadata.get('cube_value', 1),
            cube_owner=pos_metadata.get('cube_owner', CubeState.CENTERED),
            dice=(dice1, dice2),
            on_roll=on_roll,
            score_x=pos_metadata.get('score_x', 0),
            score_o=pos_metadata.get('score_o', 0),
            match_length=metadata.get('match_length', 0),
            crawford_jacoby=1 if pos_metadata.get('crawford', False) else 0
        )

        # Find the move that was played (marked with *)
        # Format: "* Deinonychus moves 24/18 13/9"
        move_played = None
        for offset in range(1, 40):
            if start_idx + offset >= len(lines):
                break
            line = lines[start_idx + offset]
            if line.strip().startswith('*') and 'moves' in line:
                move_match = re.search(r'\* \w+ moves (.+)', line)
                if move_match:
                    move_played = move_match.group(1).strip()
                break

        # Find the error value
        # Format: "Rolled 64 (+0.031):"
        error = None
        for offset in range(1, 50):
            if start_idx + offset >= len(lines):
                break
            line = lines[start_idx + offset]
            error_match = re.match(r'Rolled \d\d \(([+-]?\d+\.\d+)\):', line)
            if error_match:
                error = abs(float(error_match.group(1)))  # Take absolute value
                break

        # If no error found, this position wasn't analyzed (skip it)
        if error is None:
            return None

        # Parse candidate moves
        # Format:
        #      1. Cubeful 1-ply    24/14                        Eq.:  +0.016
        #        0.509 0.125 0.005 - 0.491 0.133 0.005
        # *    2. Cubeful 1-ply    24/18 13/9                   Eq.:  +0.015 ( -0.001)
        #        0.505 0.136 0.007 - 0.495 0.138 0.006
        candidate_moves = []
        for offset in range(1, 100):
            if start_idx + offset >= len(lines):
                break
            line = lines[start_idx + offset]

            # Check if we've reached next position
            if line.startswith('Move number'):
                break

            # Parse move line
            # Note: GnuBG puts a space inside the error parentheses: "( -0.096)" not "(-0.096)"
            move_match = re.match(
                r'\s*\*?\s*(\d+)\.\s+Cubeful\s+\d+-ply\s+(.+?)\s+Eq\.:\s+([+-]?\d+\.\d+)(?:\s+\(\s*([+-]?\d+\.\d+)\s*\))?',
                line
            )
            if move_match:
                rank = int(move_match.group(1))
                notation = move_match.group(2).strip()
                equity = float(move_match.group(3))
                move_error = float(move_match.group(4)) if move_match.group(4) else 0.0

                # Check if this is the move that was played
                was_played = (move_played and notation == move_played)

                # Parse probabilities from next line
                probs = None
                if start_idx + offset + 1 < len(lines):
                    prob_line = lines[start_idx + offset + 1]
                    prob_match = re.match(
                        r'\s*(0\.\d+)\s+(0\.\d+)\s+(0\.\d+)\s+-\s+(0\.\d+)\s+(0\.\d+)\s+(0\.\d+)',
                        prob_line
                    )
                    if prob_match:
                        probs = tuple(float(p) for p in prob_match.groups())

                # Create Move object
                move = Move(
                    notation=notation,
                    equity=equity,
                    error=abs(move_error),  # Absolute error
                    rank=rank,
                    was_played=was_played
                )

                # Add probabilities if found
                if probs:
                    move.player_win_pct = probs[0]
                    move.player_gammon_pct = probs[1]
                    move.player_backgammon_pct = probs[2]
                    move.opponent_win_pct = probs[3]
                    move.opponent_gammon_pct = probs[4]
                    move.opponent_backgammon_pct = probs[5]

                candidate_moves.append(move)

        if not candidate_moves:
            return None

        # Create Decision object
        decision = Decision(
            position=position,
            on_roll=on_roll,
            dice=(dice1, dice2),
            decision_type=DecisionType.CHECKER_PLAY,
            candidate_moves=candidate_moves,
            score_x=pos_metadata.get('score_x', 0),
            score_o=pos_metadata.get('score_o', 0),
            match_length=metadata.get('match_length', 0),
            cube_value=pos_metadata.get('cube_value', 1),
            cube_owner=pos_metadata.get('cube_owner', CubeState.CENTERED),
            crawford=pos_metadata.get('crawford', False),
            xgid=xgid,
            move_number=move_number
        )

        return decision


# Helper function for easy import
def parse_gnubg_match_files(file_paths: List[str]) -> List[Decision]:
    """
    Parse gnubg match export files into Decision objects.

    Args:
        file_paths: List of paths to exported text files

    Returns:
        List of Decision objects
    """
    return GNUBGMatchParser.parse_match_files(file_paths)
