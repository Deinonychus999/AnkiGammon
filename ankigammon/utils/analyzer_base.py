"""Abstract base class for backgammon position analyzers.

Defines the interface every analysis engine implements (GnuBG, eXtreme Gammon,
HedgeHog), so the rest of the codebase works with whichever is selected.
"""

from abc import ABC, abstractmethod
from typing import Callable, List, Optional, Tuple

from ankigammon.models import Decision, DecisionType, Move


class EngineRefusesRun(Exception):
    """The engine refuses all further analysis for now, e.g. a rate limit.

    Card generation lets it through instead of writing the card without its
    score matrices: on Send to Anki that would strip the tables from a card
    that already had them.
    """


class BackgammonAnalyzer(ABC):
    """Abstract interface for backgammon analysis engines."""

    @abstractmethod
    def analyze_match_file(
        self,
        file_path: str,
        max_moves: int = 8,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> List[Decision]:
        """Analyze a match file and return decisions.

        Parsing is internal — each analyzer handles its own output format.

        Args:
            file_path: Path to match file (.mat, .sgf, .xg)
            max_moves: Maximum candidate moves to include
            progress_callback: Status message callback

        Returns:
            List of Decision objects with analysis data
        """

    @abstractmethod
    def analyze_position(self, position_id: str) -> Tuple[str, DecisionType]:
        """Analyze a single position.

        Args:
            position_id: XGID or GNUID position string

        Returns:
            Tuple of (raw analysis text, decision type)
        """

    @abstractmethod
    def analyze_positions_parallel(
        self,
        position_ids: List[str],
        max_workers: Optional[int] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        cancellation_callback: Optional[Callable[[], bool]] = None
    ) -> List[Tuple[str, DecisionType]]:
        """Analyze multiple positions (parallel if supported).

        Args:
            position_ids: List of XGID/GNUID strings
            max_workers: Max parallel workers (ignored if engine is sequential)
            progress_callback: Called with (completed, total)
            cancellation_callback: Returns True to cancel

        Returns:
            List of (raw analysis text, decision type) tuples
        """

    @abstractmethod
    def parse_analysis(
        self,
        raw_output: str,
        xgid: str,
        decision_type: DecisionType
    ) -> Decision:
        """Parse raw analysis output into a Decision object.

        Each analyzer knows how to parse its own output format.

        Args:
            raw_output: Raw text from analyze_position()
            xgid: Original XGID for position reconstruction
            decision_type: CHECKER_PLAY or CUBE_ACTION

        Returns:
            Decision object with populated candidate_moves
        """

    @abstractmethod
    def parse_checker_play(self, raw_output: str) -> List[Move]:
        """Parse checker play moves from raw analysis output.

        Args:
            raw_output: Raw text from analyze_position()

        Returns:
            List of Move objects sorted by rank
        """

    @abstractmethod
    def parse_cube_decision(self, raw_output: str, cube_value: int = 1) -> List[Move]:
        """Parse cube decision moves from raw analysis output.

        Args:
            raw_output: Raw text from analyze_position()
            cube_value: Current cube value for notation

        Returns:
            List of Move objects for cube actions
        """

    @abstractmethod
    def terminate(self) -> None:
        """Terminate any running analysis."""

    @staticmethod
    def simplify_cube_notation(notation: str) -> str:
        """Simplify cube notation for display in score matrix.

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


def create_analyzer(settings) -> BackgammonAnalyzer:
    """Factory: create the analyzer for ``settings.analyzer_type``.

    Raises:
        ValueError: If the analyzer type is unknown or the engine is not available
    """
    analyzer_type = getattr(settings, 'analyzer_type', 'gnubg')

    if analyzer_type == "xg":
        import sys
        if sys.platform != 'win32':
            raise ValueError(
                "eXtreme Gammon analysis is only available on Windows"
            )
        from ankigammon.utils.xg_analyzer import XGAnalyzer
        return XGAnalyzer(
            xg_path=settings.xg_exe_path,
            analysis_level=settings.xg_analysis_level
        )
    if analyzer_type == "hedgehog":
        from ankigammon.utils.hedgehog_analyzer import HedgehogAnalyzer
        return HedgehogAnalyzer(
            preset=settings.hedgehog_preset,
            preset_label=settings.hedgehog_preset_label(),
        )
    if analyzer_type == "gnubg":
        from ankigammon.utils.gnubg_analyzer import GNUBGAnalyzer
        return GNUBGAnalyzer(
            gnubg_path=settings.gnubg_path,
            analysis_ply=settings.gnubg_analysis_ply
        )
    raise ValueError(f"Unknown analysis engine: {analyzer_type!r}")
