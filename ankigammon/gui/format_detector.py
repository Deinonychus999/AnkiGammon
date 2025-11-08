"""
Format detection for smart input handling.

Detects whether pasted text contains:
- Position IDs only (XGID/OGID/GNUID) - requires GnuBG analysis
- Full XG analysis text - ready to parse
"""

import re
from typing import List, Tuple
from dataclasses import dataclass
from enum import Enum

from ankigammon.settings import Settings


class InputFormat(Enum):
    """Detected input format type."""
    POSITION_IDS = "position_ids"
    FULL_ANALYSIS = "full_analysis"
    XG_BINARY = "xg_binary"
    MATCH_FILE = "match_file"
    SGF_FILE = "sgf_file"
    UNKNOWN = "unknown"


@dataclass
class DetectionResult:
    """Result of format detection."""
    format: InputFormat
    count: int  # Number of positions detected
    details: str  # Human-readable explanation
    warnings: List[str]  # Any warnings
    position_previews: List[str]  # Preview text for each position


class FormatDetector:
    """Detects input format from pasted text."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def detect(self, text: str) -> DetectionResult:
        """
        Detect format from input text.

        Splits text into positions, checks for position IDs and analysis markers,
        then classifies as position IDs only or full analysis.

        Args:
            text: Input text to analyze

        Returns:
            DetectionResult with format classification
        """
        text = text.strip()
        if not text:
            return DetectionResult(
                format=InputFormat.UNKNOWN,
                count=0,
                details="No input",
                warnings=[],
                position_previews=[]
            )

        # Split into potential positions
        positions = self._split_positions(text)

        if not positions:
            return DetectionResult(
                format=InputFormat.UNKNOWN,
                count=0,
                details="No valid positions found",
                warnings=["Could not parse input"],
                position_previews=[]
            )

        # Analyze each position
        position_types = []
        previews = []

        for pos_text in positions:
            pos_type, preview = self._classify_position(pos_text)
            position_types.append(pos_type)
            previews.append(preview)

        # Aggregate results
        if all(pt == "position_id" for pt in position_types):
            warnings = []
            if not self.settings.is_gnubg_available():
                warnings.append("GnuBG not configured - analysis required")

            return DetectionResult(
                format=InputFormat.POSITION_IDS,
                count=len(positions),
                details=f"{len(positions)} position ID(s) detected",
                warnings=warnings,
                position_previews=previews
            )

        elif all(pt == "full_analysis" for pt in position_types):
            return DetectionResult(
                format=InputFormat.FULL_ANALYSIS,
                count=len(positions),
                details=f"{len(positions)} full analysis position(s) detected",
                warnings=[],
                position_previews=previews
            )

        elif any(pt == "full_analysis" for pt in position_types) and any(pt == "position_id" for pt in position_types):
            full_count = sum(1 for pt in position_types if pt == "full_analysis")
            id_count = sum(1 for pt in position_types if pt == "position_id")

            warnings = []
            if id_count > 0 and not self.settings.is_gnubg_available():
                warnings.append(f"{id_count} position(s) need GnuBG analysis (not configured)")

            return DetectionResult(
                format=InputFormat.FULL_ANALYSIS,
                count=len(positions),
                details=f"Mixed input: {full_count} with analysis, {id_count} ID(s) only",
                warnings=warnings,
                position_previews=previews
            )

        else:
            return DetectionResult(
                format=InputFormat.UNKNOWN,
                count=len(positions),
                details="Unable to determine format",
                warnings=["Check input format - should be XGID/OGID/GNUID or full XG analysis"],
                position_previews=previews
            )

    def detect_binary(self, data: bytes) -> DetectionResult:
        """
        Detect format from binary data for file imports.

        Args:
            data: Raw binary data from file

        Returns:
            DetectionResult with format classification
        """
        if self._is_xg_binary(data):
            return DetectionResult(
                format=InputFormat.XG_BINARY,
                count=1,
                details="eXtreme Gammon binary file (.xg)",
                warnings=[],
                position_previews=["XG binary format"]
            )

        if FormatDetector.is_sgf_file(data):
            warnings = []
            if not self.settings.is_gnubg_available():
                warnings.append("GnuBG required for match analysis (not configured)")

            return DetectionResult(
                format=InputFormat.SGF_FILE,
                count=1,
                details="SGF backgammon match file (.sgf)",
                warnings=warnings,
                position_previews=["SGF file - requires analysis"]
            )

        if FormatDetector.is_match_file(data):
            warnings = []
            if not self.settings.is_gnubg_available():
                warnings.append("GnuBG required for match analysis (not configured)")

            return DetectionResult(
                format=InputFormat.MATCH_FILE,
                count=1,
                details="Backgammon match file (.mat)",
                warnings=warnings,
                position_previews=["Match file - requires analysis"]
            )

        try:
            text = data.decode('utf-8', errors='ignore')
            return self.detect(text)
        except:
            return DetectionResult(
                format=InputFormat.UNKNOWN,
                count=0,
                details="Unknown binary format",
                warnings=["Could not parse binary data"],
                position_previews=[]
            )

    def _is_xg_binary(self, data: bytes) -> bool:
        """Check if data is XG binary format (.xg file)."""
        if len(data) < 4:
            return False
        return data[0:4] == b'RGMH'

    @staticmethod
    def is_match_file(data: bytes) -> bool:
        """
        Check if data is a backgammon match file.

        Supports header format (OpenGammon, Backgammon Studio) with semicolon
        comments, or plain text format with match indicators.

        Args:
            data: Raw file data

        Returns:
            True if this is a match file
        """
        try:
            text = data.decode('utf-8', errors='ignore')

            # Strip UTF-8 BOM if present (not considered whitespace by lstrip())
            text = text.lstrip('\ufeff').lstrip()

            if text.startswith(';'):
                return True

            first_lines = '\n'.join(text.split('\n')[:10])
            if re.search(r'\d+\s+point\s+match', first_lines, re.IGNORECASE):
                return True

            header = text[:500]
            match_indicators = [
                'point match',
                'Game 1',
                'Doubles =>',
                'Takes',
                'Drops',
                'Wins.*point'
            ]

            matches = sum(1 for indicator in match_indicators
                         if re.search(indicator, header, re.IGNORECASE))

            return matches >= 3

        except:
            return False

    @staticmethod
    def is_sgf_file(data: bytes) -> bool:
        """
        Check if data is an SGF (Smart Game Format) backgammon file.

        Verifies SGF structure with format 4 and game type 6 (backgammon).

        Args:
            data: Raw file data

        Returns:
            True if this is an SGF backgammon file
        """
        try:
            text = data.decode('utf-8', errors='ignore')

            if not text.lstrip().startswith('(;'):
                return False

            if 'GM[6]' not in text[:200]:
                return False

            sgf_indicators = [
                'FF[4]',
                'GM[6]',
                'PB[',
                'PW[',
            ]

            matches = sum(1 for indicator in sgf_indicators if indicator in text[:500])

            return matches >= 3

        except:
            return False

    def _split_positions(self, text: str) -> List[str]:
        """
        Split text into individual position blocks.

        Separates positions by XGID/OGID/GNUID markers, keeping position IDs
        with their associated analysis content.
        """
        positions = []

        sections = re.split(r'(XGID=[^\n]+|^[0-9a-p]+:[0-9a-p]+:[A-Z0-9]{3}[^\n]*|^[A-Za-z0-9+/]{14}:[A-Za-z0-9+/]{12})', text, flags=re.MULTILINE)

        current_pos = ""
        for i, section in enumerate(sections):
            if (section.startswith('XGID=') or
                re.match(r'^[0-9a-p]+:[0-9a-p]+:[A-Z0-9]{3}', section) or
                re.match(r'^[A-Za-z0-9+/]{14}:[A-Za-z0-9+/]{12}$', section)):
                if current_pos:
                    positions.append(current_pos.strip())
                current_pos = section
            elif section.strip():
                current_pos += "\n" + section

        if current_pos:
            positions.append(current_pos.strip())

        if not positions:
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            if all(self._is_position_id_line(line) for line in lines):
                positions = lines

        return positions

    def _is_position_id_line(self, line: str) -> bool:
        """Check if a single line is a position ID (XGID, GNUID, or OGID)."""
        if line.startswith('XGID='):
            return True

        if re.match(r'^[0-9a-p]+:[0-9a-p]+:[A-Z0-9]{3}', line):
            return True

        if re.match(r'^[A-Za-z0-9+/]{14}:[A-Za-z0-9+/]{12}$', line):
            return True

        return False

    def _classify_position(self, text: str) -> Tuple[str, str]:
        """
        Classify a single position block as position ID, full analysis, or unknown.

        Returns:
            (type, preview) tuple
        """
        has_xgid = 'XGID=' in text
        has_ogid = bool(re.match(r'^[0-9a-p]+:[0-9a-p]+:[A-Z0-9]{3}', text.strip()))
        has_gnuid = bool(re.match(r'^[A-Za-z0-9+/=]+:[A-Za-z0-9+/=]+$', text.strip()))

        has_checker_play = bool(re.search(r'\beq:', text, re.IGNORECASE))
        has_cube_decision = bool(re.search(r'Cubeful Equities:|Proper cube action:', text, re.IGNORECASE))
        has_board = bool(re.search(r'\+13-14-15-16-17-18', text))

        preview = self._extract_preview(text, has_xgid, has_ogid, has_gnuid)

        if (has_xgid or has_ogid or has_gnuid):
            if has_checker_play or has_cube_decision or has_board:
                return ("full_analysis", preview)
            else:
                return ("position_id", preview)

        return ("unknown", preview)

    def _extract_preview(self, text: str, has_xgid: bool, has_ogid: bool, has_gnuid: bool) -> str:
        """Extract a short preview of the position."""
        if has_xgid:
            match = re.search(r'XGID=([^\n]+)', text)
            if match:
                xgid = match.group(1)[:50]

                player_match = re.search(r'([XO]) to play (\d+)', text)
                if player_match:
                    player = player_match.group(1)
                    dice = player_match.group(2)
                    return f"{player} to play {dice}"

                return f"XGID={xgid}..."

        elif has_ogid:
            parts = text.strip().split(':')
            if len(parts) >= 5:
                dice = parts[3] if len(parts) > 3 and parts[3] else "to roll"
                turn = parts[4] if len(parts) > 4 and parts[4] else ""
                player = "Black" if turn == "W" else "White" if turn == "B" else "?"
                if dice and dice != "to roll":
                    return f"{player} to play {dice}"
            return "OGID position"

        elif has_gnuid:
            return "GNUID position"

        return "Unknown format"
