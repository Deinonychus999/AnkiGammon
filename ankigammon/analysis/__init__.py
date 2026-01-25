"""Analysis module for AnkiGammon."""

from ankigammon.analysis.score_matrix import (
    ScoreMatrixCell,
    generate_score_matrix,
    format_matrix_as_html
)
from ankigammon.analysis.move_score_matrix import (
    MoveAtScore,
    MoveScoreMatrixColumn,
    generate_move_score_matrix,
    format_move_matrix_as_html
)

__all__ = [
    'ScoreMatrixCell',
    'generate_score_matrix',
    'format_matrix_as_html',
    'MoveAtScore',
    'MoveScoreMatrixColumn',
    'generate_move_score_matrix',
    'format_move_matrix_as_html'
]
