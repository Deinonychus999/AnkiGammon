"""Every gnubg invocation must ask for English output.

The parsers match gnubg's English labels ("Cubeful", "Eq.:", "Cubeful
equities:", "There are no legal moves.") and tolerate both decimal
separators. A gnubg configured for another language formats equities as
"-0,111" and, on builds whose message catalogs bind, translates those
labels out of reach of every pattern. "set lang en" is prepended to the
command file so the engine answers in English regardless of the user's
gnubg preferences; it is per-run and does not touch their gnubgautorc.
"""

from pathlib import Path
from unittest import mock

import pytest

from ankigammon.models import DecisionType
from ankigammon.utils.gnubg_analyzer import GNUBGAnalyzer


XGID = "XGID=-b----E-C---eE---c-e----B-:0:0:1:31:0:0:0:0:10"


@pytest.fixture
def analyzer():
    with mock.patch.object(Path, "exists", return_value=True):
        return GNUBGAnalyzer("/fake/gnubg", analysis_ply=2)


class TestCommandFileLocale:
    def test_position_analysis_asks_for_english_first(self, analyzer):
        path = analyzer._create_command_file(XGID, DecisionType.CHECKER_PLAY)
        try:
            commands = Path(path).read_text().splitlines()
        finally:
            Path(path).unlink()

        # First, so even the commands that follow report in English.
        assert commands[0] == "set lang en"

    def test_match_analysis_asks_for_english_first(self, analyzer, tmp_path):
        mat = tmp_path / "match.mat"
        mat.write_text("; dummy")
        captured = []

        def capture(commands):
            captured.append(list(commands))
            raise RuntimeError("stop before launching gnubg")

        with mock.patch.object(analyzer, "_create_command_file_from_list", capture):
            with pytest.raises(RuntimeError, match="stop before launching gnubg"):
                analyzer.analyze_match_file(str(mat))

        assert captured[0][0] == "set lang en"
