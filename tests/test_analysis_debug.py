"""The engine reply behind a failed analysis must reach the bug report.

Users report "GnuBG analysis fails" without the one thing that identifies
the cause: what GnuBG actually printed. That reply is captured to a file
"Create Bug Report" bundles, alongside the engine version.
"""

from pathlib import Path

import pytest

from ankigammon.utils.analysis_debug import (
    DEBUG_FILENAME,
    record_failed_analysis,
)


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))
    return tmp_path


class TestRecordFailedAnalysis:
    def test_records_position_error_and_engine_reply(self, home):
        path = record_failed_analysis(
            "XGID=-b----E-C---eE---c-e----B-:0:0:1:31:0:0:0:0:10",
            "There are no legal moves.",
            ValueError("No moves found in gnubg output for checker_play"),
        )

        assert path == home / ".ankigammon" / DEBUG_FILENAME
        content = path.read_text(encoding="utf-8")
        assert "XGID=-b----E-C---eE---c-e----B-:0:0:1:31:0:0:0:0:10" in content
        assert "There are no legal moves." in content
        assert "ValueError: No moves found in gnubg output" in content

    def test_keeps_only_the_recent_failures(self, home):
        for i in range(9):
            record_failed_analysis(f"XGID=pos{i}", f"engine reply {i}", ValueError("x"))

        content = (home / ".ankigammon" / DEBUG_FILENAME).read_text(encoding="utf-8")
        # Oldest dropped, newest kept — the file cannot grow without bound.
        assert "XGID=pos0" not in content
        assert "XGID=pos8" in content
        assert content.count("Position: XGID=pos") == 5

    def test_long_output_is_truncated(self, home):
        record_failed_analysis("XGID=x", "y" * 50000, ValueError("x"))

        content = (home / ".ankigammon" / DEBUG_FILENAME).read_text(encoding="utf-8")
        assert len(content) < 25000

    def test_unwritable_location_is_not_an_error(self, tmp_path, monkeypatch):
        # This runs on an error path; failing there would mask the real error.
        monkeypatch.setattr(
            Path, "home", staticmethod(lambda: tmp_path / "nope" / "\0invalid")
        )

        assert record_failed_analysis("XGID=x", "out", ValueError("x")) is None
