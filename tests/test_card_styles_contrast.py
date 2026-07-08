"""Tests for WCAG contrast of the error-severity colors in CARD_CSS (issue #52)."""

import re

import pytest

from ankigammon.anki.card_styles import CARD_CSS

# Anki backgrounds the colors are rendered against.
LIGHT_CANVAS = "#ffffff"
DARK_CANVAS = "#2c2c2c"

# Tolerates grouped selectors (e.g. ".moves-table td.error-minor, .move-score-matrix-table ...").
ERROR_COLOR_PATTERN = re.compile(
    r"(?P<night>\.night_mode\s+)?\.moves-table td\.error-(?P<severity>minor|blunder)"
    r"[^{}]*\{[^}]*?color:\s*(?P<color>#[0-9a-fA-F]{6})"
)


def _relative_luminance(hex_color: str) -> float:
    """WCAG 2.x relative luminance of an sRGB hex color."""

    def channel(value: int) -> float:
        c = value / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_ratio(foreground: str, background: str) -> float:
    l1 = _relative_luminance(foreground)
    l2 = _relative_luminance(background)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _extract_error_colors() -> dict:
    """Map (is_night_mode, severity) -> hex color from CARD_CSS."""
    colors = {}
    for match in ERROR_COLOR_PATTERN.finditer(CARD_CSS):
        key = (match.group("night") is not None, match.group("severity"))
        colors[key] = match.group("color").lower()
    return colors


def test_all_error_color_rules_present():
    """Guard against selector renames making the contrast tests vacuous."""
    colors = _extract_error_colors()
    expected_keys = {
        (False, "minor"),
        (False, "blunder"),
        (True, "minor"),
        (True, "blunder"),
    }
    assert set(colors.keys()) == expected_keys


# Matrix cells add severity background tints; the text must stay readable
# on them. Values are the canvas blended with the rgba tints in CARD_CSS.
LIGHT_TINTED_CELL = {"minor": "#fff6d3", "blunder": "#fde7e7"}
DARK_TINTED_CELL = {"minor": "#413d2d", "blunder": "#433130"}


@pytest.mark.parametrize("severity", ["minor", "blunder"])
def test_error_colors_readable_light_mode(severity):
    """Light-mode error colors must meet WCAG AA (4.5:1) on the white
    canvas and on the matrix's tinted severity cells."""
    color = _extract_error_colors()[(False, severity)]
    for background in (LIGHT_CANVAS, LIGHT_TINTED_CELL[severity]):
        ratio = contrast_ratio(color, background)
        assert ratio >= 4.5, (
            f"light-mode error-{severity} {color} is {ratio:.2f}:1 on {background}"
        )


BEST_MOVE_COLOR_PATTERN = re.compile(
    r"(?P<night>\.night_mode\s+)?\.moves-table tr\.best-move td"
    r"[^{}]*\{[^}]*?color:\s*(?P<color>#[0-9a-fA-F]{6})"
)

# Row backgrounds under the best-move highlight: the canvas blended with
# rgba(76, 175, 80, 0.15) on white and rgba(76, 175, 80, 0.25) on #2c2c2c.
LIGHT_BEST_MOVE_ROW = "#e4f3e5"
DARK_BEST_MOVE_ROW = "#344d35"


def _extract_best_move_colors() -> dict:
    return {
        match.group("night") is not None: match.group("color").lower()
        for match in BEST_MOVE_COLOR_PATTERN.finditer(CARD_CSS)
    }


def test_best_move_row_readable_light_mode():
    """The best-move/rank-1 row color must meet WCAG AA on its actual
    (green-tinted) row background, not just on the bare canvas."""
    colors = _extract_best_move_colors()
    assert False in colors, "light-mode best-move color rule not found"
    color = colors[False]
    for background in (LIGHT_CANVAS, LIGHT_BEST_MOVE_ROW):
        ratio = contrast_ratio(color, background)
        assert ratio >= 4.5, f"best-move {color} is {ratio:.2f}:1 on {background}"


def test_best_move_row_readable_night_mode():
    colors = _extract_best_move_colors()
    assert True in colors, "night-mode best-move color rule not found"
    color = colors[True]
    ratio = contrast_ratio(color, DARK_BEST_MOVE_ROW)
    assert ratio >= 3.0, f"night best-move {color} is {ratio:.2f}:1 on dark row"


def test_best_move_rules_cover_matrix_rank1():
    """Both moves tables must share the best-move row color rules."""
    for match in BEST_MOVE_COLOR_PATTERN.finditer(CARD_CSS):
        selector_block = match.group(0).split("{")[0]
        assert ".move-score-matrix-table tr.rank-1 td" in selector_block


@pytest.mark.parametrize("severity", ["minor", "blunder"])
def test_error_colors_readable_night_mode(severity):
    """Night-mode error colors on Anki's dark canvas.

    The floor is 3.0:1, not 4.5:1: the intentionally-unchanged night blunder
    color #ef5350 measures 4.01:1 on #2c2c2c, so a 4.5 threshold would fail
    against a color issue #52 deliberately does not touch. 3.0 still catches
    a regression to a genuinely unreadable dark-mode value.
    """
    color = _extract_error_colors()[(True, severity)]
    for background in (DARK_CANVAS, DARK_TINTED_CELL[severity]):
        ratio = contrast_ratio(color, background)
        assert ratio >= 3.0, (
            f"night-mode error-{severity} {color} is {ratio:.2f}:1 on {background}"
        )
