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

        Algorithm:
        1. Split text into potential positions
        2. For each position, check for XGID/GNUID and analysis
        3. Classify based on what's present

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
            # Mixed input
            full_count = sum(1 for pt in position_types if pt == "full_analysis")
            id_count = sum(1 for pt in position_types if pt == "position_id")

            warnings = []
            if id_count > 0 and not self.settings.is_gnubg_available():
                warnings.append(f"{id_count} position(s) need GnuBG analysis (not configured)")

            return DetectionResult(
                format=InputFormat.FULL_ANALYSIS,  # Treat as full analysis, will handle IDs
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
        Detect format from binary data (for file imports).

        Args:
            data: Raw binary data from file

        Returns:
            DetectionResult with format classification
        """
        # Check for XG binary format
        if self._is_xg_binary(data):
            return DetectionResult(
                format=InputFormat.XG_BINARY,
                count=1,  # Binary files typically contain 1 game (will be updated after parsing)
                details="eXtreme Gammon binary file (.xg)",
                warnings=[],
                position_previews=["XG binary format"]
            )

        # Check for match file format
        if FormatDetector.is_match_file(data):
            warnings = []
            if not self.settings.is_gnubg_available():
                warnings.append("GnuBG required for match analysis (not configured)")

            return DetectionResult(
                format=InputFormat.MATCH_FILE,
                count=1,  # Will be updated after analysis
                details="Backgammon match file (.mat)",
                warnings=warnings,
                position_previews=["Match file - requires analysis"]
            )

        # Try decoding as text and use text detection
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
        Check if data is a backgammon match file (.mat format).

        Match files can be in two formats:
        1. With headers (OpenGammon, Backgammon Studio):
           ; [Site "OpenGammon"]
           ; [Player 1 "..."]
        2. Plain text:
           15 point match
           Game 1

        Args:
            data: Raw file data

        Returns:
            True if this is a match file
        """
        try:
            # Try UTF-8 decoding
            text = data.decode('utf-8', errors='ignore')

            # Check for .mat header format (semicolon comments)
            if text.lstrip().startswith(';'):
                return True

            # Check for plain text match format
            # Look for "N point match" in first few lines
            first_lines = '\n'.join(text.split('\n')[:10])
            if re.search(r'\d+\s+point\s+match', first_lines, re.IGNORECASE):
                return True

            # Check for match-specific keywords in first 500 chars
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

            # If we see 3+ match indicators, it's probably a match file
            return matches >= 3

        except:
            return False

    def _split_positions(self, text: str) -> List[str]:
        """
        Split text into individual position blocks.

        Positions are separated by:
        - Multiple blank lines (2+)
        - "eXtreme Gammon Version:" marker
        - New XGID/OGID/GNUID line after a complete position
        """
        # First, try splitting by eXtreme Gammon version markers
        positions = []

        # Split by XGID, OGID, or GNUID lines, keeping the position ID with its analysis
        # Pattern matches XGID=, OGID (base-26), or GNUID (base64)
        sections = re.split(r'(XGID=[^\n]+|^[0-9a-p]+:[0-9a-p]+:[A-Z0-9]{3}[^\n]*|^[A-Za-z0-9+/]{14}:[A-Za-z0-9+/]{12})', text, flags=re.MULTILINE)

        # Recombine position ID with following content
        current_pos = ""
        for i, section in enumerate(sections):
            # Check if this section starts with a position ID
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

        # Also check for simple line-by-line XGID/GNUID format
        if not positions:
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            if all(self._is_position_id_line(line) for line in lines):
                positions = lines

        return positions

    def _is_position_id_line(self, line: str) -> bool:
        """Check if a single line is a position ID (XGID, GNUID, or OGID)."""
        # XGID format
        if line.startswith('XGID='):
            return True

        # OGID format (base-26 encoding: 0-9a-p characters, at least 3 fields)
        # Format: P1:P2:CUBE[:...] where P1 and P2 use only 0-9a-p
        if re.match(r'^[0-9a-p]+:[0-9a-p]+:[A-Z0-9]{3}', line):
            return True

        # GNUID format (base64: PositionID:MatchID = 14 chars:12 chars)
        # Check for base64 chars after checking OGID to avoid confusion
        if re.match(r'^[A-Za-z0-9+/]{14}:[A-Za-z0-9+/]{12}$', line):
            return True

        return False

    def _classify_position(self, text: str) -> Tuple[str, str]:
        """
        Classify a single position block.

        Returns:
            (type, preview) where type is "position_id", "full_analysis", or "unknown"
        """
        has_xgid = 'XGID=' in text
        has_ogid = bool(re.match(r'^[0-9a-p]+:[0-9a-p]+:[A-Z0-9]{3}', text.strip()))
        has_gnuid = bool(re.match(r'^[A-Za-z0-9+/=]+:[A-Za-z0-9+/=]+$', text.strip()))

        # Check for analysis markers
        has_checker_play = bool(re.search(r'\beq:', text, re.IGNORECASE))
        has_cube_decision = bool(re.search(r'Cubeful Equities:|Proper cube action:', text, re.IGNORECASE))
        has_board = bool(re.search(r'\+13-14-15-16-17-18', text))

        # Extract preview
        preview = self._extract_preview(text, has_xgid, has_ogid, has_gnuid)

        # Classification logic
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
                xgid = match.group(1)[:50]  # First 50 chars

                # Try to find player/dice info
                player_match = re.search(r'([XO]) to play (\d+)', text)
                if player_match:
                    player = player_match.group(1)
                    dice = player_match.group(2)
                    return f"{player} to play {dice}"

                return f"XGID={xgid}..."

        elif has_ogid:
            # Extract player/dice from OGID if possible
            parts = text.strip().split(':')
            if len(parts) >= 5:
                dice = parts[3] if len(parts) > 3 and parts[3] else "to roll"
                turn = parts[4] if len(parts) > 4 and parts[4] else ""
                # OGID color is inverted: W sent → B on roll, B sent → W on roll
                player = "Black" if turn == "W" else "White" if turn == "B" else "?"
                if dice and dice != "to roll":
                    return f"{player} to play {dice}"
            return "OGID position"

        elif has_gnuid:
            return "GNUID position"

        return "Unknown format"
