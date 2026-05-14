"""Tests for the score-matrix module's pure-function helpers.

Covers:
- `resolve_effective_match_length`: the rule that turns the source match
  length and the user's `score_matrix_max_size` setting into the matrix's
  effective dimensions. Feeds three call sites (`card_generator`,
  `export_dialog` x2); a regression here silently produces wrong-sized
  matrices or skewed progress-bar steps.
- `format_matrix_as_html`'s caption rendering: surfaces a note when the
  user's live current score falls outside the (possibly capped) matrix —
  important UX safeguard against silently misleading a card reader.
"""

import pytest

from ankigammon.analysis.score_matrix import (
    ScoreMatrixCell,
    format_matrix_as_html,
    resolve_effective_match_length,
)


class TestResolveEffectiveMatchLength:
    """Cover the four documented branches plus the 1-point match boundary."""

    @pytest.mark.parametrize("match_length,max_size,expected", [
        # Match game + Auto (max_size=0): use full match length, no cap
        (7, 0, 7),
        (13, 0, 13),
        # Match game + cap: take min(match_length, max_size) — the cap shrinks long matches
        (13, 7, 7),
        # Match game + cap larger than match: no inflation — the match length wins
        (5, 7, 5),
        # Unlimited (match_length=0) + Auto: fall back to 7-pt projection
        (0, 0, 7),
        # Unlimited + cap: use cap directly as the virtual match length
        (0, 11, 11),
        (0, 3, 3),
        # Boundary: real 1-point match returns 1 (callers must treat as "skip")
        (1, 0, 1),
        (1, 7, 1),
    ])
    def test_branches(self, match_length, max_size, expected):
        assert resolve_effective_match_length(match_length, max_size) == expected


def _minimal_matrix():
    """Build a 1x1 matrix at 2-away/2-away (smallest legal cube-live cell)."""
    cell = ScoreMatrixCell(
        player_away=2,
        opponent_away=2,
        best_action="D/T",
        error_no_double=0.05,
        error_double=0.0,
        error_pass=0.02,
    )
    return [[cell]]


class TestFormatMatrixCaption:
    """The off-grid caption protects against silently misleading the card reader
    when the live score falls outside a capped matrix."""

    def test_no_caption_by_default(self):
        html = format_matrix_as_html(_minimal_matrix())
        assert "matrix-caption" not in html

    def test_caption_rendered_below_table(self):
        caption_text = "Current score (12-away / 11-away) is outside the displayed range."
        html = format_matrix_as_html(_minimal_matrix(), caption=caption_text)
        assert "matrix-caption" in html
        assert caption_text in html
        # Caption sits after the closing </table> tag, inside the wrapping div
        # (rindex for the outer </div> — the inner <div class="action"> cells also close)
        assert html.index("</table>") < html.index("matrix-caption") < html.rindex("</div>")
