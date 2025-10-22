"""
GNU Backgammon command-line interface wrapper.

Provides functionality to analyze backgammon positions using gnubg-cli.exe.
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Tuple

from flashgammon.models import DecisionType
from flashgammon.utils.xgid import parse_xgid


class GNUBGAnalyzer:
    """Wrapper for gnubg-cli.exe command-line interface."""

    def __init__(self, gnubg_path: str, analysis_ply: int = 2):
        """
        Initialize GnuBG analyzer.

        Args:
            gnubg_path: Path to gnubg-cli.exe executable
            analysis_ply: Analysis depth in plies (default: 2)
        """
        self.gnubg_path = gnubg_path
        self.analysis_ply = analysis_ply

        # Validate gnubg path
        if not Path(gnubg_path).exists():
            raise FileNotFoundError(f"GnuBG executable not found: {gnubg_path}")

    def analyze_position(self, position_id: str) -> Tuple[str, DecisionType]:
        """
        Analyze a position from XGID or GNUID.

        Args:
            position_id: Position identifier (XGID or GNUID format)

        Returns:
            Tuple of (gnubg_output_text, decision_type)

        Raises:
            ValueError: If position_id format is invalid
            subprocess.CalledProcessError: If gnubg execution fails
        """
        # Determine if it's XGID or GNUID and extract decision type
        decision_type = self._determine_decision_type(position_id)

        # Create command file
        command_file = self._create_command_file(position_id, decision_type)

        try:
            # Execute gnubg
            output = self._run_gnubg(command_file)
            return output, decision_type
        finally:
            # Cleanup temp file
            try:
                os.unlink(command_file)
            except OSError:
                pass

    def _determine_decision_type(self, position_id: str) -> DecisionType:
        """
        Determine the decision type from position ID.

        For XGID: Parse dice field to determine if it's checker play or cube decision
        For GNUID: Default to checker play (would need position parsing to determine)

        Args:
            position_id: XGID or GNUID string

        Returns:
            DecisionType.CHECKER_PLAY or DecisionType.CUBE_ACTION

        Raises:
            ValueError: If position_id format is invalid
        """
        # Check if it's XGID format
        if position_id.startswith("XGID=") or ":" in position_id:
            try:
                _, metadata = parse_xgid(position_id)

                # Check dice field
                dice = metadata.get('dice', None)
                if dice is None:
                    # No dice rolled yet - could be cube decision
                    # Check if 'decision_type' was set by parse_xgid
                    return metadata.get('decision_type', DecisionType.CUBE_ACTION)
                else:
                    # Dice rolled - checker play decision
                    return DecisionType.CHECKER_PLAY

            except (ValueError, KeyError) as e:
                raise ValueError(f"Invalid XGID format: {e}")
        else:
            # GNUID format - default to checker play
            # (would need to parse GNUID to determine actual decision type)
            return DecisionType.CHECKER_PLAY

    def _create_command_file(self, position_id: str, decision_type: DecisionType) -> str:
        """
        Create a temporary command file for gnubg.

        Args:
            position_id: XGID or GNUID string
            decision_type: Type of decision to analyze

        Returns:
            Path to temporary command file
        """
        # Determine which set command to use
        if position_id.startswith("XGID="):
            set_command = f"set xgid {position_id}"
        elif ":" in position_id and not position_id.startswith("XGID="):
            # Likely XGID without prefix
            set_command = f"set xgid XGID={position_id}"
        else:
            # GNUID format
            set_command = f"set gnubgid {position_id}"

        # Build command sequence
        commands = [
            "set automatic game off",
            "set automatic roll off",
            set_command,
            f"set analysis chequerplay evaluation plies {self.analysis_ply}",
            f"set analysis cubedecision evaluation plies {self.analysis_ply}",
            "set output matchpc off",  # Don't show match equity percentages
        ]

        # Add analysis command based on decision type
        if decision_type == DecisionType.CHECKER_PLAY:
            commands.append("hint")
        else:
            # For cube decisions, hint will give cube advice
            commands.append("hint")

        # Create temp file
        fd, temp_path = tempfile.mkstemp(suffix=".txt", prefix="gnubg_commands_")
        try:
            with os.fdopen(fd, 'w') as f:
                f.write('\n'.join(commands))
                f.write('\n')
        except:
            os.close(fd)
            raise

        return temp_path

    def _run_gnubg(self, command_file: str) -> str:
        """
        Execute gnubg-cli.exe with the command file.

        Args:
            command_file: Path to command file

        Returns:
            Output text from gnubg

        Raises:
            subprocess.CalledProcessError: If gnubg execution fails
        """
        # Build command
        # -t: non-interactive mode
        # -c: execute commands from file
        cmd = [self.gnubg_path, "-t", "-c", command_file]

        # Execute gnubg
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,  # 30 second timeout
        )

        # Check for errors
        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode,
                cmd,
                output=result.stdout,
                stderr=result.stderr
            )

        # Return combined stdout and stderr (gnubg may write to either)
        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr

        return output

    def analyze_cube_at_score(
        self,
        position_id: str,
        match_length: int,
        player_away: int,
        opponent_away: int
    ) -> dict:
        """
        Analyze cube decision at a specific match score.

        Args:
            position_id: XGID position string
            match_length: Match length (e.g., 7 for 7-point match)
            player_away: Points away from match for player on roll
            opponent_away: Points away from match for opponent

        Returns:
            Dictionary with:
                - best_action: Best cube action (e.g., "D/T", "N/T", "D/P")
                - equity_no_double: Equity for no double
                - equity_double_take: Equity for double/take
                - equity_double_pass: Equity for double/pass
                - error_no_double: Error if don't double (when D/T or D/P is best)
                - error_double: Error if double (when N/T is best)
                - error_pass: Error if pass (when D/T is best)

        Raises:
            ValueError: If position_id format is invalid or analysis fails
        """
        from flashgammon.utils.xgid import parse_xgid, encode_xgid

        # Parse original XGID to get position and metadata
        position, metadata = parse_xgid(position_id)

        # Calculate actual scores from "away" values
        # player_away=2 means player has (match_length - 2) points
        score_on_roll = match_length - player_away
        score_opponent = match_length - opponent_away

        # Determine which player is on roll
        from flashgammon.models import Player
        on_roll = metadata.get('on_roll')

        # Map scores to X and O based on who's on roll
        if on_roll == Player.O:
            score_o = score_on_roll
            score_x = score_opponent
        else:
            score_x = score_on_roll
            score_o = score_opponent

        # Create new XGID with modified match score
        modified_xgid = encode_xgid(
            position=position,
            cube_value=metadata.get('cube_value', 1),
            cube_owner=metadata.get('cube_owner'),
            dice=None,  # Cube decision has no dice
            on_roll=on_roll,
            score_x=score_x,
            score_o=score_o,
            match_length=match_length,
            crawford_jacoby=metadata.get('crawford_jacoby', 0),
            max_cube=metadata.get('max_cube', 256)
        )

        # Analyze the position
        output, decision_type = self.analyze_position(modified_xgid)

        # Parse cube decision
        from flashgammon.parsers.gnubg_parser import GNUBGParser
        moves = GNUBGParser._parse_cube_decision(output)

        if not moves:
            raise ValueError(f"Could not parse cube decision from GnuBG output")

        # Build equity map
        equity_map = {m.notation: m.equity for m in moves}

        # Find best move
        best_move = next((m for m in moves if m.rank == 1), None)
        if not best_move:
            raise ValueError("Could not determine best cube action")

        # Get equities for the 3 main actions
        no_double_eq = equity_map.get("No Double/Take", None)
        double_take_eq = equity_map.get("Double/Take", equity_map.get("Redouble/Take", None))
        double_pass_eq = equity_map.get("Double/Pass", equity_map.get("Redouble/Pass", None))

        # Simplify best action notation for display
        best_action_simplified = self._simplify_cube_notation(best_move.notation)

        # Calculate errors for wrong decisions
        best_equity = best_move.equity
        error_no_double = None
        error_double = None
        error_pass = None

        if no_double_eq is not None:
            error_no_double = abs(best_equity - no_double_eq) if best_action_simplified != "N/T" else 0.0
        if double_take_eq is not None:
            error_double = abs(best_equity - double_take_eq) if best_action_simplified not in ["D/T", "TG/T"] else 0.0
        if double_pass_eq is not None:
            error_pass = abs(best_equity - double_pass_eq) if best_action_simplified != "D/P" else 0.0

        return {
            'best_action': best_action_simplified,
            'equity_no_double': no_double_eq,
            'equity_double_take': double_take_eq,
            'equity_double_pass': double_pass_eq,
            'error_no_double': error_no_double,
            'error_double': error_double,
            'error_pass': error_pass
        }

    @staticmethod
    def _simplify_cube_notation(notation: str) -> str:
        """
        Simplify cube notation for display in score matrix.

        Args:
            notation: Full notation (e.g., "No Double/Take", "Double/Take")

        Returns:
            Simplified notation (e.g., "N/T", "D/T", "D/P", "TG/T", "TG/P")
        """
        notation_lower = notation.lower()

        if "too good" in notation_lower:
            if "take" in notation_lower:
                return "TG/T"
            elif "pass" in notation_lower:
                return "TG/P"
        elif "no double" in notation_lower or "no redouble" in notation_lower:
            return "N/T"
        elif "double" in notation_lower or "redouble" in notation_lower:
            if "take" in notation_lower:
                return "D/T"
            elif "pass" in notation_lower or "drop" in notation_lower:
                return "D/P"

        return notation
