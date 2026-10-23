"""A card made again from the same position must not ask the engine again.

Reported against HedgeHog: regenerating a collection (after a theme change, or
to fix a card) re-ran every score matrix and cube-position table, spending the
allowance each time. Finished tables are stored on disk and reused.
"""

from unittest import mock

import pytest

from ankigammon.analysis.extras_cache import (
    KIND_SCORE_MATRIX,
    ExtrasCache,
    decode_move_cube_columns,
    decode_move_score_columns,
    decode_score_matrix,
    encode_columns,
    encode_score_matrix,
)
from ankigammon.analysis.move_cube_matrix import CubeMatrixColumn, MoveAtCubeState
from ankigammon.analysis.move_score_matrix import MoveAtScore, MoveScoreMatrixColumn
from ankigammon.analysis.score_matrix import ScoreMatrixCell, UnlimitedReference
from ankigammon.anki.card_generator import CardGenerator
from ankigammon.models import CubeState, Decision, DecisionType, Move, Player, Position
from ankigammon.settings import Settings

CUBE_XGID = "XGID=-b----E-C--AeD---bAdb---A-:0:0:1:00:0:0:3:0:10"
CHECKER_XGID = "XGID=-b----E-C---eE---c-e----B-:0:0:1:31:0:0:0:0:10"


def _cell(away=2, **extra):
    return ScoreMatrixCell(
        player_away=away, opponent_away=away, best_action="D/T",
        doubler_error=0.01, taker_error=0.02,
        equity_no_double=0.4, equity_double_take=0.5, equity_double_pass=1.0, **extra,
    )


def _matrix_result():
    return [[_cell()]], UnlimitedReference(no_jacoby=_cell(0), jacoby=_cell(0))


class TestStore:
    def test_round_trips_a_score_matrix(self, tmp_path):
        cache = ExtrasCache(tmp_path)
        matrix, unlimited = _matrix_result()
        cache.put(KIND_SCORE_MATRIX, {"k": 1}, encode_score_matrix(matrix, unlimited))

        got_matrix, got_unlimited = decode_score_matrix(cache.get(KIND_SCORE_MATRIX, {"k": 1}))

        assert got_matrix == matrix
        assert got_unlimited == unlimited

    def test_round_trips_move_columns(self):
        score = [MoveScoreMatrixColumn("DMP", [MoveAtScore("13/9 6/5", 0.1, 0.0, 1)])]
        cube = [CubeMatrixColumn("Player", [MoveAtCubeState("24/21", 0.2, 0.0, 1)])]

        assert decode_move_score_columns(encode_columns(score)) == score
        assert decode_move_cube_columns(encode_columns(cube)) == cube

    def test_a_different_key_is_a_miss(self, tmp_path):
        cache = ExtrasCache(tmp_path)
        cache.put(KIND_SCORE_MATRIX, {"engine": "hedgehog:2ply"}, {"matrix": [], "unlimited": None})

        assert cache.get(KIND_SCORE_MATRIX, {"engine": "gnubg:3-ply"}) is None

    def test_a_corrupt_entry_is_a_miss(self, tmp_path):
        cache = ExtrasCache(tmp_path)
        cache.put(KIND_SCORE_MATRIX, {"k": 1}, {"matrix": [], "unlimited": None})
        for path in tmp_path.glob("*.json"):
            path.write_text("{not json", encoding="utf-8")

        assert cache.get(KIND_SCORE_MATRIX, {"k": 1}) is None

    def test_clear_removes_every_entry(self, tmp_path):
        cache = ExtrasCache(tmp_path)
        cache.put(KIND_SCORE_MATRIX, {"k": 1}, {"matrix": [], "unlimited": None})
        cache.put(KIND_SCORE_MATRIX, {"k": 2}, {"matrix": [], "unlimited": None})

        assert cache.stats()[0] == 2
        assert cache.clear() == 2
        assert cache.stats() == (0, 0)


@pytest.fixture
def generator(qapp, tmp_path):
    settings = Settings(config_path=tmp_path / "config.json")
    settings.analyzer_type = "hedgehog"
    settings.generate_score_matrix = True
    settings.generate_move_score_matrix = True
    settings.generate_move_cube_matrix = True
    settings.score_matrix_max_size = 2
    with mock.patch("ankigammon.anki.card_generator.get_settings", return_value=settings):
        yield CardGenerator(
            output_dir=tmp_path / "cards",
            analyzer=mock.MagicMock(),
            extras_cache=ExtrasCache(tmp_path / "cache"),
        )


def _cube_decision():
    return Decision(
        position=Position(points=[0] * 26), xgid=CUBE_XGID, on_roll=Player.X, dice=None,
        match_length=7, cube_value=1, cube_owner=CubeState.CENTERED,
        decision_type=DecisionType.CUBE_ACTION,
        candidate_moves=[Move(notation="No double", equity=-0.08, rank=1)],
    )


def _checker_decision():
    return Decision(
        position=Position(points=[0] * 26), xgid=CHECKER_XGID, on_roll=Player.X, dice=(3, 1),
        match_length=7, cube_value=1, cube_owner=CubeState.CENTERED,
        decision_type=DecisionType.CHECKER_PLAY,
        candidate_moves=[Move(notation="8/5 6/5", equity=0.1, rank=1)],
    )


class TestGeneratorUsesTheCache:
    def test_score_matrix_is_requested_once(self, generator):
        with mock.patch(
            "ankigammon.analysis.score_matrix.generate_score_matrix", return_value=_matrix_result()
        ) as engine:
            first = generator._compute_score_matrix(_cube_decision())
            second = generator._compute_score_matrix(_cube_decision())

        assert engine.call_count == 1
        assert second["matrix"] == first["matrix"]
        assert second["unlimited"] == first["unlimited"]

    def test_a_missing_unlimited_reference_is_not_kept(self, generator):
        """The reference failed once; the next run should try it again."""
        matrix, _ = _matrix_result()
        with mock.patch(
            "ankigammon.analysis.score_matrix.generate_score_matrix", return_value=(matrix, None)
        ) as engine:
            generator._compute_score_matrix(_cube_decision())
            generator._compute_score_matrix(_cube_decision())

        assert engine.call_count == 2

    def test_another_engine_depth_does_not_share_the_entry(self, generator):
        with mock.patch(
            "ankigammon.analysis.score_matrix.generate_score_matrix", return_value=_matrix_result()
        ) as engine:
            generator._compute_score_matrix(_cube_decision())
            generator.settings.hedgehog_preset = "4ply"
            generator._compute_score_matrix(_cube_decision())

        assert engine.call_count == 2

    def test_move_score_matrix_is_requested_once(self, generator):
        columns = [MoveScoreMatrixColumn("Neutral", [MoveAtScore("8/5 6/5", 0.1, 0.0, 1)])]
        with mock.patch(
            "ankigammon.analysis.move_score_matrix.generate_move_score_matrix", return_value=columns
        ) as engine:
            generator._compute_move_score_matrix(_checker_decision())
            again = generator._compute_move_score_matrix(_checker_decision())

        assert engine.call_count == 1
        assert again == columns

    def test_cube_comparison_is_requested_once(self, generator):
        columns = [CubeMatrixColumn("Neutral", [MoveAtCubeState("8/5 6/5", 0.1, 0.0, 1)])]
        with mock.patch(
            "ankigammon.analysis.move_cube_matrix.generate_move_cube_matrix", return_value=columns
        ) as engine:
            generator._compute_move_cube_matrix(_checker_decision())
            again = generator._compute_move_cube_matrix(_checker_decision())

        assert engine.call_count == 1
        assert again == columns

    def test_without_a_cache_every_card_asks_the_engine(self, generator):
        generator.extras_cache = None
        with mock.patch(
            "ankigammon.analysis.score_matrix.generate_score_matrix", return_value=_matrix_result()
        ) as engine:
            generator._compute_score_matrix(_cube_decision())
            generator._compute_score_matrix(_cube_decision())

        assert engine.call_count == 2
