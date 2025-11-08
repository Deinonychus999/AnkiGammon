"""
Tests for format detection, especially edge cases.
"""

import pytest
from ankigammon.gui.format_detector import FormatDetector, InputFormat
from ankigammon.settings import get_settings


class TestMatchFileDetection:
    """Test match file format detection."""

    def test_match_file_with_utf8_bom(self):
        """Test that match files with UTF-8 BOM are correctly detected."""
        # Sample match file content with UTF-8 BOM
        content_without_bom = '; [Site "test"]\n; [Match ID "123"]\n\n11 point match\n\nGame 1\n'
        content_with_bom = '\ufeff' + content_without_bom

        # Encode to bytes (as files are read)
        data_with_bom = content_with_bom.encode('utf-8')
        data_without_bom = content_without_bom.encode('utf-8')

        # Both should be detected as match files
        assert FormatDetector.is_match_file(data_with_bom), "Match file with BOM should be detected"
        assert FormatDetector.is_match_file(data_without_bom), "Match file without BOM should be detected"

    def test_match_file_with_semicolon_header(self):
        """Test match files with semicolon headers (OpenGammon format)."""
        content = '; [Player 1 "Alice"]\n; [Player 2 "Bob"]\n\n7 point match\n'
        data = content.encode('utf-8')

        assert FormatDetector.is_match_file(data), "Semicolon header match file should be detected"

    def test_match_file_with_plain_text(self):
        """Test match files with plain text format (no semicolon headers)."""
        content = """
11 point match

 Game 1
 Alice : 0                           Bob : 0
  1) 41: 13/9 24/23              53: 24/4
  2) 41: 9/5 6/5                 51: 8/3 4/3
  3)  Doubles => 2
  4)  Takes
"""
        data = content.encode('utf-8')

        assert FormatDetector.is_match_file(data), "Plain text match file should be detected"

    def test_not_match_file(self):
        """Test that non-match files are not detected as match files."""
        # Random text
        data1 = b"This is just some random text\nwith no match indicators"
        assert not FormatDetector.is_match_file(data1), "Random text should not be detected as match file"

        # XG text (has some similar keywords but different format)
        data2 = b"XGID=-a----E-C---eE---c-e----B-:0:0:1:00:0:0:3:0:10\nX to play 31"
        assert not FormatDetector.is_match_file(data2), "XG text should not be detected as match file"


class TestBinaryFormatDetection:
    """Test binary format detection (XG, match files, etc)."""

    def test_detect_match_file_with_bom(self):
        """Test detect_binary correctly identifies match files with BOM."""
        settings = get_settings()
        detector = FormatDetector(settings)

        content = '\ufeff; [Site "test"]\n; [Match ID "123"]\n\n11 point match\n\nGame 1\n'
        data = content.encode('utf-8')

        result = detector.detect_binary(data)

        assert result.format == InputFormat.MATCH_FILE, f"Expected MATCH_FILE, got {result.format}"
        assert result.count == 1
        assert "match file" in result.details.lower()
