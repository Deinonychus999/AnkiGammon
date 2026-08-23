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
- `ScoreMatrixCell.format_equities` and the errors/equities toggle markup
  (issue #56): the card's toggle script keys off the `has-equities` class and
  the toggle element, so their presence is part of the contract.
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


def _minimal_matrix(**equities):
    """Build a 1x1 matrix at 2-away/2-away (smallest legal cube-live cell)."""
    cell = ScoreMatrixCell(
        player_away=2,
        opponent_away=2,
        best_action="D/T",
        error_no_double=0.05,
        error_double=0.0,
        error_pass=0.02,
        **equities,
    )
    return [[cell]]


_EQUITIES = {
    "equity_no_double": 0.412,
    "equity_double_take": 0.556,
    "equity_double_pass": 1.0,
}


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


class TestFormatEquities:
    """The equity pair is what issue #56 asked for; double/pass is deliberately
    left out because both engines normalise it to a constant +1.000."""

    def test_shows_signed_no_double_and_double_take(self):
        cell = _minimal_matrix(**_EQUITIES)[0][0]
        assert cell.format_equities() == "+0.412/+0.556"

    def test_negative_equities_keep_their_sign(self):
        cell = _minimal_matrix(
            equity_no_double=-0.05, equity_double_take=-0.361, equity_double_pass=1.0
        )[0][0]
        assert cell.format_equities() == "-0.050/-0.361"

    @pytest.mark.parametrize("equities", [
        {},
        {"equity_no_double": 0.412},
        {"equity_double_take": 0.556},
    ])
    def test_dash_when_either_value_missing(self, equities):
        assert _minimal_matrix(**equities)[0][0].format_equities() == "—"


class TestEquityToggleMarkup:
    """Cells hold both value pairs; the toggle script decides which is visible."""

    def test_toggle_omitted_without_equities(self):
        html = format_matrix_as_html(_minimal_matrix())
        assert "has-equities" not in html
        assert "matrix-value-toggle" not in html
        assert 'class="equities"' not in html

    def test_both_pairs_rendered_with_equities(self):
        html = format_matrix_as_html(_minimal_matrix(**_EQUITIES))
        assert 'class="score-matrix has-equities"' in html
        assert "matrix-value-toggle" in html
        assert '<div class="errors">50/20</div>' in html
        assert '<div class="equities">+0.412/+0.556</div>' in html

    def test_partial_equities_fall_back_to_errors_only(self):
        """One unparseable cell would otherwise flip the whole matrix to dashes."""
        matrix = [[
            _minimal_matrix(**_EQUITIES)[0][0],
            _minimal_matrix()[0][0],
        ]]
        html = format_matrix_as_html(matrix)
        assert "has-equities" not in html
        assert 'class="equities"' not in html
