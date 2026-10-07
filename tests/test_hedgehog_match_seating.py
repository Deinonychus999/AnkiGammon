"""HedgeHog seats a .mat/.sgf file's players the other way round from GnuBG.

The import dialog names the players from the file header and seats header
player 1 as Player.O, as GnuBG does. HedgeHog returns OGXM, which seats White as
Player.X, and its conversion puts header player 1 (.mat left column, .sgf PW) on
White. Unhandled, checking your own name imported your opponent's mistakes.

analysis.ogxm is HedgeHog's analysis of match_files/rchoicebug.mat: header
player 1 rchoice is White there, and opens with 64.
"""

from pathlib import Path
from unittest import mock

import pytest
from PySide6.QtWidgets import QApplication

from ankigammon.gui.main_window import MatchAnalysisWorker
from ankigammon.models import Player
from ankigammon.settings import Settings
from ankigammon.utils.hedgehog_analyzer import HedgehogAnalyzer

ROOT = Path(__file__).parent.parent
OGXM = (ROOT / "tests" / "data" / "hedgehog" / "analysis.ogxm").read_bytes()
MAT = str(ROOT / "match_files" / "rchoicebug.mat")


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class StubClient:
    def import_match(self, path):
        return {"data": {}}

    def save_match(self, match):
        return {"match_id": "m1"}

    def analyze_match(self, match_id, preset):
        return {"analysis_id": "a1"}

    def wait_analysis(self, analysis_id, cancelled=None):
        return {"id": "a1", "model_name": "HedgeHog"}

    def analysis_file(self, analysis_id):
        return OGXM


def _sgf(tmp_path: Path, white: str, black: str) -> str:
    path = tmp_path / "match.sgf"
    path.write_text(
        f"(;FF[4]GM[6]CA[UTF-8]MI[length:3][game:0][bs:0][ws:0]PB[{black}]PW[{white}]RU[Crawford]\n"
        ";W[64xrrn]\n;B[31qtst])",
        encoding="utf-8",
    )
    return str(path)


def _import(file_path: str, include_player_x: bool, include_player_o: bool):
    seen = {}

    def record(decisions, checker, cube, include_x, include_o):
        seen["flags"] = (include_x, include_o)
        seen["decisions"] = list(decisions)
        return [d for d in decisions
                if (d.on_roll == Player.X and include_x) or (d.on_roll == Player.O and include_o)]

    worker = MatchAnalysisWorker(
        file_path=file_path,
        settings=Settings(),
        checker_threshold=0.0,
        cube_threshold=0.0,
        include_player_x=include_player_x,
        include_player_o=include_player_o,
        filter_func=record,
        max_moves=8,
    )
    analyzer = HedgehogAnalyzer(client=StubClient())
    with mock.patch("ankigammon.utils.analyzer_base.create_analyzer", return_value=analyzer):
        worker.run()
    return seen


class TestSeatsSwapped:
    def test_mat_header_player_1_is_hedgehogs_white(self):
        analyzer = HedgehogAnalyzer(client=StubClient())
        analyzer.analyze_match_file(MAT)
        assert analyzer.seats_swapped

    def test_sgf_white_is_header_player_1(self, tmp_path):
        analyzer = HedgehogAnalyzer(client=StubClient())
        analyzer.analyze_match_file(_sgf(tmp_path, white="rchoice", black="Jezebel"))
        assert analyzer.seats_swapped

    def test_seating_follows_the_names_not_the_format(self, tmp_path):
        """Control: header player 1 named as HedgeHog's Black is not swapped."""
        analyzer = HedgehogAnalyzer(client=StubClient())
        analyzer.analyze_match_file(_sgf(tmp_path, white="Jezebel", black="rchoice"))
        assert not analyzer.seats_swapped

    def test_unmatched_names_keep_hedgehogs_convention(self, tmp_path):
        analyzer = HedgehogAnalyzer(client=StubClient())
        analyzer.analyze_match_file(_sgf(tmp_path, white="someone", black="else"))
        assert analyzer.seats_swapped


class TestImportSelectsTheCheckedPlayer:
    def test_checking_header_player_1_keeps_their_plays(self, qapp):
        # The dialog seats header player 1 (rchoice) as Player.O
        seen = _import(MAT, include_player_x=False, include_player_o=True)

        assert seen["flags"] == (True, False)
        opening = seen["decisions"][0]
        assert opening.dice == (6, 4) and opening.on_roll == Player.X

    def test_checking_header_player_2_keeps_their_plays(self, qapp):
        seen = _import(MAT, include_player_x=True, include_player_o=False)
        assert seen["flags"] == (False, True)

    def test_both_players_stay_both(self, qapp):
        seen = _import(MAT, include_player_x=True, include_player_o=True)
        assert seen["flags"] == (True, True)
