"""
GNU Backgammon command-line interface wrapper.

Provides functionality to analyze backgammon positions using gnubg-cli.exe.
"""

import os
import sys
import re
import subprocess
import tempfile
import multiprocessing
from pathlib import Path
from typing import Tuple, List, Callable, Optional
from concurrent.futures import ProcessPoolExecutor, as_completed

from ankigammon.models import DecisionType
from ankigammon.utils.xgid import parse_xgid


class GNUBGAnalyzer:
    """Wrapper for gnubg-cli.exe command-line interface."""

    def __init__(self, gnubg_path: str, analysis_ply: int = 3):
        """
        Initialize GnuBG analyzer.

        Args:
            gnubg_path: Path to gnubg-cli.exe executable
            analysis_ply: Analysis depth in plies (default: 3)
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
        # Validate position_id
        if position_id is None:
            raise ValueError("position_id cannot be None. Decision object must have xgid field populated.")

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

    def analyze_positions_parallel(
        self,
        position_ids: List[str],
        max_workers: Optional[int] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> List[Tuple[str, DecisionType]]:
        """
        Analyze multiple positions in parallel.

        Args:
            position_ids: List of position identifiers (XGID or GNUID format)
            max_workers: Maximum number of parallel workers (default: min(cpu_count, 8))
            progress_callback: Optional callback function(completed, total) for progress updates

        Returns:
            List of tuples (gnubg_output_text, decision_type) in same order as position_ids

        Raises:
            ValueError: If any position_id format is invalid
            subprocess.CalledProcessError: If any gnubg execution fails
        """
        if not position_ids:
            return []

        # Determine number of workers
        if max_workers is None:
            max_workers = min(multiprocessing.cpu_count(), 8)

        # Use single-threaded for small batches (overhead not worth it)
        if len(position_ids) <= 2:
            results = []
            for i, pos_id in enumerate(position_ids):
                result = self.analyze_position(pos_id)
                results.append(result)
                if progress_callback:
                    progress_callback(i + 1, len(position_ids))
            return results

        # Prepare arguments for parallel processing
        args_list = [(self.gnubg_path, self.analysis_ply, pos_id) for pos_id in position_ids]

        # Execute in parallel with progress tracking
        results = [None] * len(position_ids)  # Pre-allocate results list
        completed = 0

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_idx = {
                executor.submit(_analyze_position_worker, *args): idx
                for idx, args in enumerate(args_list)
            }

            # Collect results as they complete
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                    completed += 1
                    if progress_callback:
                        progress_callback(completed, len(position_ids))
                except Exception as e:
                    # Re-raise with context about which position failed
                    raise RuntimeError(f"Failed to analyze position {idx} ({position_ids[idx]}): {e}") from e

        return results

    def analyze_match_file(
        self,
        mat_file_path: str,
        max_moves: int = 8,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> List[str]:
        """
        Analyze entire match file using gnubg and export to text files.

        Args:
            mat_file_path: Path to .mat match file
            max_moves: Maximum number of candidate moves to show (default: 8)
            progress_callback: Optional callback(status_message) for progress updates

        Returns:
            List of paths to exported text files (one per game)
            Caller is responsible for cleaning up these temp files after parsing.

        Raises:
            FileNotFoundError: If mat_file not found
            subprocess.CalledProcessError: If gnubg execution fails
            RuntimeError: If export files were not created
        """
        # Validate input file
        mat_path = Path(mat_file_path)
        if not mat_path.exists():
            raise FileNotFoundError(f"Match file not found: {mat_file_path}")

        # Create temp directory for output
        temp_dir = Path(tempfile.mkdtemp(prefix="gnubg_match_"))
        output_base = temp_dir / "analyzed_match.txt"

        if progress_callback:
            progress_callback("Preparing analysis...")

        # Create command file
        # Note: Paths with spaces must be quoted for gnubg
        mat_path_str = str(mat_path)
        output_path_str = str(output_base)

        # Quote paths if they contain spaces
        if ' ' in mat_path_str:
            mat_path_str = f'"{mat_path_str}"'
        if ' ' in output_path_str:
            output_path_str = f'"{output_path_str}"'

        commands = [
            "set automatic game off",
            "set automatic roll off",
            f"set analysis chequerplay evaluation plies {self.analysis_ply}",
            f"set analysis cubedecision evaluation plies {self.analysis_ply}",
            f"set export moves number {max_moves}",
            f"import mat {mat_path_str}",
            "analyse match",
            f"export match text {output_path_str}",
        ]

        command_file = self._create_command_file_from_list(commands)

        # Debug: Log command file contents
        import logging
        logger = logging.getLogger(__name__)
        with open(command_file, 'r') as f:
            logger.info(f"GnuBG command file:\n{f.read()}")

        try:
            if progress_callback:
                progress_callback("Analyzing match... this may take several minutes")

            # Execute gnubg (with longer timeout for match analysis)
            kwargs = {
                'capture_output': True,
                'text': True,
                'timeout': 600,  # 10 minute timeout for match analysis
            }
            if sys.platform == 'win32':
                kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW

            result = subprocess.run(
                [self.gnubg_path, "-t", "-c", command_file],
                **kwargs
            )

            # Log gnubg output for debugging
            import logging
            logger = logging.getLogger(__name__)
            if result.stdout:
                logger.info(f"GnuBG stdout (first 1000 chars):\n{result.stdout[:1000]}")
            if result.stderr:
                logger.warning(f"GnuBG stderr:\n{result.stderr}")

            if result.returncode != 0:
                raise subprocess.CalledProcessError(
                    result.returncode,
                    [self.gnubg_path, "-t", "-c", command_file],
                    output=result.stdout,
                    stderr=result.stderr
                )

            if progress_callback:
                progress_callback("Finding exported files...")

            # Debug: Log temp directory contents
            temp_files = list(temp_dir.glob("*"))
            logger.info(f"Files in temp dir {temp_dir}: {[f.name for f in temp_files]}")

            # Find all exported text files (gnubg creates one per game)
            # Pattern: analyzed_match.txt, analyzed_match_002.txt, analyzed_match_003.txt, etc.
            exported_files = []

            # First file (no suffix)
            if output_base.exists():
                exported_files.append(str(output_base))

            # Additional files (with _NNN suffix)
            game_num = 2
            while True:
                next_file = temp_dir / f"analyzed_match_{game_num:03d}.txt"
                if next_file.exists():
                    exported_files.append(str(next_file))
                    game_num += 1
                else:
                    break

            if not exported_files:
                # Provide detailed error message with gnubg output
                error_msg = (
                    f"GnuBG did not create any export files.\n"
                    f"Expected files in: {temp_dir}\n"
                    f"Files found: {[f.name for f in temp_files]}\n\n"
                )
                if result.stdout:
                    error_msg += f"GnuBG output:\n{result.stdout[:500]}\n"
                if result.stderr:
                    error_msg += f"GnuBG errors:\n{result.stderr[:500]}"

                raise RuntimeError(error_msg)

            # Verify that files were actually analyzed (not just exported without analysis)
            # Quick check: look for analysis markers in first file
            if exported_files:
                with open(exported_files[0], 'r', encoding='utf-8') as f:
                    content = f.read(5000)  # Read first 5KB
                    # Check for analysis markers: "Rolled XX (±ERROR):"
                    has_analysis = bool(re.search(r'Rolled \d\d \([+-]?\d+\.\d+\):', content))
                    if not has_analysis:
                        logger.warning("⚠️ GnuBG exported files but NO ANALYSIS FOUND!")
                        logger.warning(f"Expected to find 'Rolled XX (±error):' pattern")
                        logger.warning(f"First file preview:\n{content[:800]}")
                        raise RuntimeError(
                            "GnuBG exported the match but did not include analysis.\n"
                            "The 'analyse match' command may have failed.\n\n"
                            f"Check logs for GnuBG output."
                        )

            if progress_callback:
                progress_callback(f"Analysis complete. {len(exported_files)} game(s) exported.")

            # DEBUG: Copy first file to repo for inspection
            if exported_files:
                import shutil
                debug_path = Path(__file__).parent.parent.parent / "debug_gnubg_output.txt"
                shutil.copy2(exported_files[0], debug_path)
                logger.info(f"DEBUG: Copied first export file to {debug_path}")

            return exported_files

        finally:
            # Cleanup command file
            try:
                os.unlink(command_file)
            except OSError:
                pass

    def _create_command_file_from_list(self, commands: List[str]) -> str:
        """
        Create temporary command file from list of commands.

        Args:
            commands: List of gnubg commands

        Returns:
            Path to temporary command file
        """
        fd, temp_path = tempfile.mkstemp(suffix=".txt", prefix="gnubg_commands_")
        try:
            with os.fdopen(fd, 'w') as f:
                f.write('\n'.join(commands))
                f.write('\n')
        except:
            os.close(fd)
            raise
        return temp_path

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
        # On Windows, prevent console window from appearing
        kwargs = {
            'capture_output': True,
            'text': True,
            'timeout': 120,  # 120 second timeout
        }
        if sys.platform == 'win32':
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW

        result = subprocess.run(cmd, **kwargs)

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
        from ankigammon.utils.xgid import parse_xgid, encode_xgid

        # Parse original XGID to get position and metadata
        position, metadata = parse_xgid(position_id)

        # Calculate actual scores from "away" values
        # player_away=2 means player has (match_length - 2) points
        score_on_roll = match_length - player_away
        score_opponent = match_length - opponent_away

        # Determine which player is on roll
        from ankigammon.models import Player
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
        from ankigammon.parsers.gnubg_parser import GNUBGParser
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


def _analyze_position_worker(gnubg_path: str, analysis_ply: int, position_id: str) -> Tuple[str, DecisionType]:
    """
    Worker function for parallel position analysis.

    This is a module-level function to support pickling for multiprocessing.

    Args:
        gnubg_path: Path to gnubg-cli.exe executable
        analysis_ply: Analysis depth in plies
        position_id: Position identifier (XGID or GNUID format)

    Returns:
        Tuple of (gnubg_output_text, decision_type)
    """
    analyzer = GNUBGAnalyzer(gnubg_path, analysis_ply)
    return analyzer.analyze_position(position_id)
