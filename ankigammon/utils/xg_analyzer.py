"""eXtreme Gammon UI automation analyzer.

Drives XG2 via Win32 UI automation (bundled xg_auto module) to analyze
backgammon positions and match files. Implements the BackgammonAnalyzer
interface for use as a pluggable analysis engine.

Requires:
- Windows OS
- eXtreme Gammon 2 installed
- pywinauto and pyautogui packages
"""

import logging
import tempfile
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from ankigammon.models import Decision, DecisionType, Move
from ankigammon.utils.analyzer_base import BackgammonAnalyzer
from ankigammon.utils.xgid import parse_xgid

logger = logging.getLogger(__name__)

# XG analysis level names → used in progress messages
XG_LEVEL_NAMES = {
    "none": "None",
    "very quick": "Very Quick",
    "fast": "Fast",
    "deep": "Deep",
    "thorough": "Thorough",
    "world class": "World Class",
    "extensive": "Extensive",
}


class XGAnalyzer(BackgammonAnalyzer):
    """Analyze backgammon positions using eXtreme Gammon 2 via UI automation.

    Uses the bundled xg_auto.automator.XGAutomator to drive XG's GUI, sending
    WM_COMMAND messages for menu actions and handling dialogs.

    Connection is lazy — XG is connected on first use and the connection
    is reused for subsequent operations.
    """

    def __init__(
        self,
        xg_path: Optional[str] = None,
        analysis_level: str = "world class",
        poll_interval: float = 3.0,
        timeout: float = 600.0,
    ):
        """Initialize XG analyzer.

        Args:
            xg_path: Path to eXtremeGammon2.exe (optional if XG is already running)
            analysis_level: Analysis depth ("very quick", "fast", "deep",
                          "thorough", "world class", "extensive")
            poll_interval: Seconds between completion checks
            timeout: Max seconds to wait for analysis
        """
        self._xg_path = Path(xg_path) if xg_path else None
        self._analysis_level = analysis_level
        self._poll_interval = poll_interval
        self._timeout = timeout
        self._automator = None
        self._connected = False

    def _ensure_connected(self) -> None:
        """Lazily connect to XG, creating the automator if needed."""
        if self._connected and self._automator is not None:
            return

        try:
            from ankigammon.utils.xg_auto.automator import XGAutomator
        except ImportError:
            raise ImportError(
                "XG automation dependencies not installed. "
                "Please update AnkiGammon to the latest version."
            )

        self._automator = XGAutomator(
            xg_path=self._xg_path,
            analysis_level=self._analysis_level,
            poll_interval=self._poll_interval,
            timeout=self._timeout,
            headless=True,
        )
        self._automator.connect()
        self._connected = True
        logger.info("Connected to eXtreme Gammon")

    def analyze_match_file(
        self,
        file_path: str,
        max_moves: int = 8,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> List[Decision]:
        """Analyze a match file via XG UI automation.

        Flow:
        1. Open file in XG (handles .mat, .sgf, .xg via appropriate import)
        2. Trigger analysis and wait for completion
        3. Save analyzed match as .xg to temp directory
        4. Parse the .xg file with XGBinaryParser
        5. Return Decision objects
        """
        from ankigammon.parsers.xg_binary_parser import XGBinaryParser
        import shutil

        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            raise FileNotFoundError(f"Match file not found: {file_path}")

        level_display = XG_LEVEL_NAMES.get(self._analysis_level, self._analysis_level)

        if progress_callback:
            progress_callback(f"Connecting to eXtreme Gammon...")

        self._ensure_connected()

        if progress_callback:
            progress_callback(f"Opening {file_path_obj.name}...")

        self._automator.open_file(file_path_obj)

        if progress_callback:
            progress_callback(
                f"Analyzing with eXtreme Gammon ({level_display})...\n"
                f"This may take several minutes for long matches."
            )

        self._automator.run_analysis()

        # Save analyzed match to temp .xg file
        temp_dir = Path(tempfile.mkdtemp(prefix="xg_analysis_"))
        temp_output = temp_dir / f"{file_path_obj.stem}_analyzed.xg"

        if progress_callback:
            progress_callback("Saving analyzed match...")

        # Snapshot .xg files in the input directory before saving, so we can
        # detect new/modified files if the IFileDialog ignores our target path.
        input_dir = file_path_obj.parent
        xg_candidates = {
            f: f.stat().st_mtime
            for f in input_dir.glob("*.xg") if f.is_file()
        }

        self._automator.save_as(temp_output)
        self._automator.close_match()

        if progress_callback:
            progress_callback("Parsing analysis results...")

        # Locate the saved .xg file — may not be at temp_output if the
        # IFileDialog's COM state ignored our typed path.
        xg_file = self._find_saved_xg(
            temp_output, input_dir, file_path_obj.stem,
            xg_candidates, self._automator,
        )

        try:
            decisions = XGBinaryParser.parse_file(str(xg_file))
            logger.info(
                f"XG analysis complete: {len(decisions)} positions "
                f"from {file_path_obj.name}"
            )

            # Set source description
            for decision in decisions:
                decision.source_description = (
                    f"eXtreme Gammon analysis ({level_display}) "
                    f"from '{file_path_obj.name}'"
                )

            return decisions

        finally:
            # Clean up temp files
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                logger.warning(f"Failed to cleanup temp files: {e}")

    @staticmethod
    def _find_saved_xg(
        expected_path: Path,
        input_dir: Path,
        stem: str,
        pre_snapshot: dict,
        automator=None,
    ) -> Path:
        """Find the .xg file that XG just saved.

        In headless mode, the IFileDialog may ignore the specified path and
        save to the input directory instead. This method checks multiple
        sources: expected path, Frida hook events, and directory scanning.
        """
        # 1. Check expected path
        if expected_path.exists() and expected_path.stat().st_size > 0:
            logger.info("Found saved .xg at expected path: %s", expected_path)
            return expected_path

        # 2. Check Frida hooks for actual file write paths
        if automator and automator._hooks:
            try:
                events = automator._hooks.drain_events()
                for event in reversed(events):
                    data = event.data or {}
                    path_str = data.get("path", "")
                    if path_str.lower().endswith(".xg"):
                        hook_path = Path(path_str)
                        if hook_path.exists() and hook_path.stat().st_size > 0:
                            logger.info(
                                "Found saved .xg via Frida hooks: %s",
                                hook_path,
                            )
                            return hook_path
            except Exception as e:
                logger.debug("Hook-based file detection failed: %s", e)

        # 3. Check input directory for a .xg with the same stem (most common)
        fallback = input_dir / f"{stem}.xg"
        if fallback.exists():
            old_mtime = pre_snapshot.get(fallback, 0)
            if fallback.stat().st_mtime > old_mtime:
                logger.info(
                    "IFileDialog saved to input dir: %s (mtime changed)",
                    fallback,
                )
                return fallback

        # 4. Search input directory for any newly modified .xg file
        for f in input_dir.glob("*.xg"):
            if f.is_file():
                old_mtime = pre_snapshot.get(f, 0)
                if f.stat().st_mtime > old_mtime:
                    logger.info(
                        "Found newly modified .xg in input dir: %s", f
                    )
                    return f

        # 5. Search common XG save locations
        import os
        search_dirs = [
            Path(os.environ.get("USERPROFILE", "")) / "Documents",
            Path(os.environ.get("USERPROFILE", "")) / "Desktop",
        ]
        if automator and automator.xg_path:
            search_dirs.append(automator.xg_path.parent)

        for search_dir in search_dirs:
            if not search_dir.exists():
                continue
            candidate = search_dir / f"{stem}.xg"
            if candidate.exists() and candidate.stat().st_size > 0:
                import time as _time
                # Only accept if modified within the last 60 seconds
                if _time.time() - candidate.stat().st_mtime < 60:
                    logger.info(
                        "Found saved .xg in %s: %s", search_dir, candidate
                    )
                    return candidate

        raise FileNotFoundError(
            f"Could not find saved .xg file. "
            f"Expected: {expected_path}, also checked: {input_dir}"
        )

    def analyze_position(self, position_id: str) -> Tuple[str, DecisionType]:
        """Analyze a single position via XG clipboard import.

        Flow:
        1. Import XGID via clipboard (creates a mini-match context in XG)
        2. Run full match analysis (handles dialog + completion polling)
        3. Export position analysis to clipboard (avoids file dialog issues)
        4. Close match to prepare for next position
        5. Return (text, decision_type)
        """
        import time
        from ankigammon.utils.xg_auto.automator import XGCmd

        if position_id is None:
            raise ValueError(
                "position_id cannot be None. "
                "Decision object must have xgid field populated."
            )

        self._ensure_connected()

        # Determine decision type from XGID
        decision_type = self._determine_decision_type(position_id)

        # Ensure XGID= prefix
        xgid = position_id
        if not xgid.startswith("XGID="):
            xgid = f"XGID={xgid}"

        # Import position via clipboard — XG creates a match context
        self._automator.import_xgid(xgid)

        # Run analysis with proper completion detection
        self._automator.run_analysis()

        # Export position analysis to clipboard (no file dialog needed)
        self._automator.send_command(XGCmd.EXPORT_POS_CLIPBOARD)
        time.sleep(1.0)
        text_content = self._automator.get_clipboard_text()

        if not text_content:
            raise ValueError("Clipboard export returned empty text")

        # Close the match to prepare for the next position
        try:
            self._automator.close_match()
        except Exception:
            pass

        return text_content, decision_type

    def analyze_positions_parallel(
        self,
        position_ids: List[str],
        max_workers: Optional[int] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        cancellation_callback: Optional[Callable[[], bool]] = None
    ) -> List[Tuple[str, DecisionType]]:
        """Analyze multiple positions sequentially (XG is single-threaded).

        XG can only process one position at a time, so this runs sequentially
        despite the 'parallel' name (interface compatibility).
        """
        import time

        if not position_ids:
            return []

        results = []
        total = len(position_ids)

        for i, pos_id in enumerate(position_ids):
            # Check for cancellation
            if cancellation_callback and cancellation_callback():
                raise InterruptedError("Analysis cancelled by user")

            result = self.analyze_position(pos_id)
            results.append(result)

            if progress_callback:
                progress_callback(i + 1, total)

            # Brief pause between positions to let XG stabilize
            if i < total - 1:
                time.sleep(1.0)

        return results

    def parse_analysis(
        self,
        raw_output: str,
        xgid: str,
        decision_type: DecisionType
    ) -> Decision:
        """Parse XG text export into a Decision object.

        Uses XGTextParser which already handles XG's text export format.
        """
        from ankigammon.parsers.xg_text_parser import XGTextParser

        decisions = XGTextParser.parse_string(raw_output)
        if decisions:
            # Return the first (and usually only) decision
            decision = decisions[0]
            # Preserve the original XGID if the parsed one differs
            if xgid and not decision.xgid:
                decision.xgid = xgid
            return decision

        raise ValueError(
            f"No analysis found in XG output for {decision_type.value}"
        )

    def parse_checker_play(self, raw_output: str) -> List[Move]:
        """Parse checker play moves from XG text export."""
        from ankigammon.parsers.xg_text_parser import XGTextParser

        decisions = XGTextParser.parse_string(raw_output)
        if decisions and decisions[0].candidate_moves:
            return decisions[0].candidate_moves
        return []

    def parse_cube_decision(self, raw_output: str, cube_value: int = 1) -> List[Move]:
        """Parse cube decision moves from XG text export."""
        from ankigammon.parsers.xg_text_parser import XGTextParser

        decisions = XGTextParser.parse_string(raw_output)
        if decisions and decisions[0].candidate_moves:
            return decisions[0].candidate_moves
        return []

    def terminate(self) -> None:
        """Disconnect from XG and clean up."""
        if self._automator is not None:
            try:
                self._automator.close_match()
            except Exception:
                pass
            try:
                self._automator.disconnect()
            except Exception:
                pass
            self._automator = None
        self._connected = False

    def _determine_decision_type(self, position_id: str) -> DecisionType:
        """Determine decision type from position ID.

        If the XGID has dice set, it's a checker play decision.
        Otherwise, it's a cube action.
        """
        try:
            _, metadata = parse_xgid(position_id)
            dice = metadata.get('dice', None)
            if dice is None:
                return metadata.get('decision_type', DecisionType.CUBE_ACTION)
            return DecisionType.CHECKER_PLAY
        except (ValueError, KeyError):
            # Default to checker play if we can't parse
            return DecisionType.CHECKER_PLAY
