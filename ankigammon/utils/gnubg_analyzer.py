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
        self._current_process = None

        if not Path(gnubg_path).exists():
            raise FileNotFoundError(f"GnuBG executable not found: {gnubg_path}")

    def terminate(self):
        """Terminate any running GnuBG process."""
        if self._current_process is not None:
            try:
                self._current_process.kill()
                self._current_process = None
            except:
                pass

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
        if position_id is None:
            raise ValueError("position_id cannot be None. Decision object must have xgid field populated.")

        decision_type = self._determine_decision_type(position_id)
        command_file = self._create_command_file(position_id, decision_type)

        try:
            output = self._run_gnubg(command_file)
            return output, decision_type
        finally:
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
            progress_callback: Optional callback for progress updates: callback(completed, total)

        Returns:
            List of tuples (gnubg_output_text, decision_type) in same order as position_ids

        Raises:
            ValueError: If any position_id format is invalid
            subprocess.CalledProcessError: If any gnubg execution fails
        """
        if not position_ids:
            return []

        if max_workers is None:
            max_workers = min(multiprocessing.cpu_count(), 8)

        if len(position_ids) <= 2:
            results = []
            for i, pos_id in enumerate(position_ids):
                result = self.analyze_position(pos_id)
                results.append(result)
                if progress_callback:
                    progress_callback(i + 1, len(position_ids))
            return results

        args_list = [(self.gnubg_path, self.analysis_ply, pos_id) for pos_id in position_ids]
        results = [None] * len(position_ids)
        completed = 0

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(_analyze_position_worker, *args): idx
                for idx, args in enumerate(args_list)
            }

            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                    completed += 1
                    if progress_callback:
                        progress_callback(completed, len(position_ids))
                except Exception as e:
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

        Supports both .mat (Jellyfish) and .sgf (Smart Game Format) files.

        Args:
            mat_file_path: Path to match file (.mat or .sgf)
            max_moves: Maximum number of candidate moves to show (default: 8)
            progress_callback: Optional callback(status_message) for progress updates

        Returns:
            List of paths to exported text files (one per game)
            Caller is responsible for cleaning up these temp files after parsing.

        Raises:
            FileNotFoundError: If match file not found
            subprocess.CalledProcessError: If gnubg execution fails
            RuntimeError: If export files were not created
        """
        mat_path = Path(mat_file_path)
        if not mat_path.exists():
            raise FileNotFoundError(f"Match file not found: {mat_file_path}")

        temp_dir = Path(tempfile.mkdtemp(prefix="gnubg_match_"))
        output_base = temp_dir / "analyzed_match.txt"

        if progress_callback:
            progress_callback("Preparing analysis...")

        mat_path_str = str(mat_path)
        output_path_str = str(output_base)

        if ' ' in mat_path_str:
            mat_path_str = f'"{mat_path_str}"'
        if ' ' in output_path_str:
            output_path_str = f'"{output_path_str}"'

        file_ext = mat_path.suffix.lower()
        if file_ext == '.sgf':
            import_cmd = f"load match {mat_path_str}"
        else:
            import_cmd = f"import mat {mat_path_str}"

        commands = [
            "set automatic game off",
            "set automatic roll off",
            f"set analysis chequerplay evaluation plies {self.analysis_ply}",
            f"set analysis cubedecision evaluation plies {self.analysis_ply}",
            f"set export moves number {max_moves}",
            import_cmd,
            "analyse match",
            f"export match text {output_path_str}",
        ]

        command_file = self._create_command_file_from_list(commands)

        import logging
        logger = logging.getLogger(__name__)
        with open(command_file, 'r') as f:
            logger.info(f"GnuBG command file:\n{f.read()}")

        try:
            if progress_callback:
                progress_callback(f"Analyzing match with GnuBG ({self.analysis_ply}-ply)...")

            kwargs = {
                'stdout': subprocess.PIPE,
                'stderr': subprocess.PIPE,
                'text': True,
            }
            if sys.platform == 'win32':
                kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW

            self._current_process = subprocess.Popen(
                [self.gnubg_path, "-t", "-c", command_file],
                **kwargs
            )

            try:
                stdout, stderr = self._current_process.communicate(timeout=600)
                returncode = self._current_process.returncode
            except subprocess.TimeoutExpired:
                self._current_process.kill()
                stdout, stderr = self._current_process.communicate()
                self._current_process = None
                raise subprocess.CalledProcessError(
                    -1,
                    [self.gnubg_path, "-t", "-c", command_file],
                    output="Process timed out after 10 minutes",
                    stderr=""
                )
            finally:
                self._current_process = None

            import logging
            logger = logging.getLogger(__name__)
            if stdout:
                logger.info(f"GnuBG stdout (first 1000 chars):\n{stdout[:1000]}")
            if stderr:
                logger.warning(f"GnuBG stderr:\n{stderr}")

            if returncode != 0:
                raise subprocess.CalledProcessError(
                    returncode,
                    [self.gnubg_path, "-t", "-c", command_file],
                    output=stdout,
                    stderr=stderr
                )

            if progress_callback:
                progress_callback("Finding exported files...")

            temp_files = list(temp_dir.glob("*"))
            logger.info(f"Files in temp dir {temp_dir}: {[f.name for f in temp_files]}")

            exported_files = []

            if output_base.exists():
                exported_files.append(str(output_base))

            game_num = 2
            while True:
                next_file = temp_dir / f"analyzed_match_{game_num:03d}.txt"
                if next_file.exists():
                    exported_files.append(str(next_file))
                    game_num += 1
                else:
                    break

            if not exported_files:
                error_msg = (
                    f"GnuBG did not create any export files.\n"
                    f"Expected files in: {temp_dir}\n"
                    f"Files found: {[f.name for f in temp_files]}\n\n"
                )
                if stdout:
                    error_msg += f"GnuBG output:\n{stdout[:500]}\n"
                if stderr:
                    error_msg += f"GnuBG errors:\n{stderr[:500]}"

                raise RuntimeError(error_msg)

            if exported_files:
                with open(exported_files[0], 'r', encoding='utf-8') as f:
                    content = f.read(5000)
                    has_analysis = bool(re.search(r'Rolled \d\d \([+-]?\d+\.\d+\):', content))
                    if not has_analysis:
                        logger.warning("GnuBG exported files but no analysis found")
                        logger.warning(f"Expected to find 'Rolled XX (±error):' pattern")
                        logger.warning(f"First file preview:\n{content[:800]}")
                        raise RuntimeError(
                            "GnuBG exported the match but did not include analysis.\n"
                            "The 'analyse match' command may have failed.\n\n"
                            f"Check logs for GnuBG output."
                        )

            if progress_callback:
                progress_callback(f"Analysis complete. {len(exported_files)} game(s) exported.")

            if exported_files:
                import shutil
                debug_path = Path(__file__).parent.parent.parent / "debug_gnubg_output.txt"
                shutil.copy2(exported_files[0], debug_path)
                logger.info(f"Copied first export file to {debug_path}")

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

        Args:
            position_id: XGID or GNUID string

        Returns:
            DecisionType.CHECKER_PLAY or DecisionType.CUBE_ACTION

        Raises:
            ValueError: If position_id format is invalid
        """
        if position_id.startswith("XGID=") or ":" in position_id:
            try:
                _, metadata = parse_xgid(position_id)

                dice = metadata.get('dice', None)
                if dice is None:
                    return metadata.get('decision_type', DecisionType.CUBE_ACTION)
                else:
                    return DecisionType.CHECKER_PLAY

            except (ValueError, KeyError) as e:
                raise ValueError(f"Invalid XGID format: {e}")
        else:
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
        if position_id.startswith("XGID="):
            set_command = f"set xgid {position_id}"
        elif ":" in position_id and not position_id.startswith("XGID="):
            set_command = f"set xgid XGID={position_id}"
        else:
            set_command = f"set gnubgid {position_id}"

        commands = [
            "set automatic game off",
            "set automatic roll off",
            set_command,
            f"set analysis chequerplay evaluation plies {self.analysis_ply}",
            f"set analysis cubedecision evaluation plies {self.analysis_ply}",
            "set output matchpc off",
        ]

        if decision_type == DecisionType.CHECKER_PLAY:
            commands.append("hint")
        else:
            commands.append("hint")

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
        cmd = [self.gnubg_path, "-t", "-c", command_file]

        kwargs = {
            'capture_output': True,
            'text': True,
            'timeout': 120,
        }
        if sys.platform == 'win32':
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW

        result = subprocess.run(cmd, **kwargs)

        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode,
                cmd,
                output=result.stdout,
                stderr=result.stderr
            )

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
            Dictionary with cube analysis results:
                - best_action: Best cube action (e.g., "D/T", "N/T", "D/P")
                - equity_no_double: Equity for no double
                - equity_double_take: Equity for double/take
                - equity_double_pass: Equity for double/pass
                - error_no_double: Error if don't double
                - error_double: Error if double
                - error_pass: Error if pass

        Raises:
            ValueError: If position_id format is invalid or analysis fails
        """
        from ankigammon.utils.xgid import parse_xgid, encode_xgid

        position, metadata = parse_xgid(position_id)

        score_on_roll = match_length - player_away
        score_opponent = match_length - opponent_away

        from ankigammon.models import Player
        on_roll = metadata.get('on_roll')

        if on_roll == Player.O:
            score_o = score_on_roll
            score_x = score_opponent
        else:
            score_x = score_on_roll
            score_o = score_opponent

        modified_xgid = encode_xgid(
            position=position,
            cube_value=metadata.get('cube_value', 1),
            cube_owner=metadata.get('cube_owner'),
            dice=None,
            on_roll=on_roll,
            score_x=score_x,
            score_o=score_o,
            match_length=match_length,
            crawford_jacoby=metadata.get('crawford_jacoby', 0),
            max_cube=metadata.get('max_cube', 256)
        )

        output, decision_type = self.analyze_position(modified_xgid)

        from ankigammon.parsers.gnubg_parser import GNUBGParser
        moves = GNUBGParser._parse_cube_decision(output)

        if not moves:
            raise ValueError(f"Could not parse cube decision from GnuBG output")

        equity_map = {m.notation: m.equity for m in moves}

        best_move = next((m for m in moves if m.rank == 1), None)
        if not best_move:
            raise ValueError("Could not determine best cube action")

        no_double_eq = equity_map.get("No Double/Take", None)
        double_take_eq = equity_map.get("Double/Take", equity_map.get("Redouble/Take", None))
        double_pass_eq = equity_map.get("Double/Pass", equity_map.get("Redouble/Pass", None))

        best_action_simplified = self._simplify_cube_notation(best_move.notation)

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
