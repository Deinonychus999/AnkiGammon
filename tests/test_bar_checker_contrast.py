"""Bar checker visibility across color schemes (issue #47).

The bar is painted in each scheme's board surface color (except Midnight,
whose near-black bar already contrasts with both checkers, and Monochrome,
where they were always equal). A checker on the bar is considered visible
when its fill or its border clears 3:1 -- the WCAG minimum for graphics --
against the bar. The original bug: Ocean's dark checker measured 1.15:1
fill and 1.10:1 border against the old deep-blue bar.
"""

import pytest

from ankigammon.renderer.color_schemes import get_scheme, list_schemes


def _relative_luminance(hex_color: str) -> float:
    """WCAG 2.x relative luminance of an sRGB hex color."""

    def channel(value: int) -> float:
        c = value / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_ratio(foreground: str, background: str) -> float:
    l1 = _relative_luminance(foreground)
    l2 = _relative_luminance(background)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _checker_visibility(fill: str, border: str, bar: str) -> float:
    """A checker is delineated by whichever of fill or border contrasts more."""
    return max(contrast_ratio(fill, bar), contrast_ratio(border, bar))


@pytest.mark.parametrize("name", list_schemes())
def test_bar_checkers_visible_in_every_scheme(name):
    scheme = get_scheme(name)
    for fill in (scheme.checker_x, scheme.checker_o):
        visibility = _checker_visibility(fill, scheme.checker_border, scheme.bar)
        assert visibility >= 3.0, (
            f"{name}: checker {fill} is illegible on the bar {scheme.bar} "
            f"(best channel {visibility:.2f}:1, need 3:1)"
        )


@pytest.mark.parametrize("name", list_schemes())
def test_bar_checkers_visible_with_swapped_colors(name):
    scheme = get_scheme(name).with_swapped_checkers()
    for fill in (scheme.checker_x, scheme.checker_o):
        visibility = _checker_visibility(fill, scheme.checker_border, scheme.bar)
        assert visibility >= 3.0, (
            f"{name} (swapped): checker {fill} is illegible on the bar "
            f"{scheme.bar} (best channel {visibility:.2f}:1, need 3:1)"
        )
