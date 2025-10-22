"""Analysis module for FlashGammon."""

from flashgammon.analysis.score_matrix import (
    ScoreMatrixCell,
    generate_score_matrix,
    format_matrix_as_html
)

__all__ = [
    'ScoreMatrixCell',
    'generate_score_matrix',
    'format_matrix_as_html'
]
