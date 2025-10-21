"""
GNU Backgammon command-line interface wrapper.

Provides functionality to analyze backgammon positions using gnubg-cli.exe.
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Tuple

from xg2anki.models import DecisionType
from xg2anki.utils.xgid import parse_xgid


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
