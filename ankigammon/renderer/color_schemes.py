"""Color schemes for backgammon board rendering."""

from dataclasses import dataclass
from typing import Dict


@dataclass
class ColorScheme:
    """Defines colors for a backgammon board theme."""
    name: str
    board_light: str  # Light board background
    board_dark: str   # Dark board borders
    point_light: str  # Light triangle points
    point_dark: str   # Dark triangle points
    checker_x: str    # X player checkers (white/top)
    checker_o: str    # O player checkers (black/bottom)
    checker_border: str  # Checker borders
    bar: str          # Bar (center divider)
    text: str         # Text color
    bearoff: str      # Bear-off tray background
    dice_color: str   # Dice color (usually matches pale checker)
    dice_pip_color: str = "#000000"  # Dice pip color (contrasts with dice_color)
    cube_fill: str = "#FFD700"    # Cube background (default gold)
    cube_text: str = "#000000"    # Cube text color (default black)

    def with_swapped_checkers(self) -> "ColorScheme":
        """
        Return a new ColorScheme with X and O checker colors swapped.

        By default, O (bottom player) uses the lighter color. This method
        swaps checker_x and checker_o so X uses the lighter color instead.
        The dice color and pip color are also swapped to match.
        """
        return ColorScheme(
            name=self.name,
            board_light=self.board_light,
            board_dark=self.board_dark,
            point_light=self.point_light,
            point_dark=self.point_dark,
            checker_x=self.checker_o,  # Swap
            checker_o=self.checker_x,  # Swap
            checker_border=self.checker_border,
            bar=self.bar,
            text=self.text,
            bearoff=self.bearoff,
            dice_color=self.checker_x,  # Use original dark checker as new dice color
            dice_pip_color=self.dice_color,  # Use original light dice color for pips
            cube_fill=self.cube_fill,
            cube_text=self.cube_text,
        )


# Available color schemes
CLASSIC = ColorScheme(
    name="Classic",
    board_light="#DEB887",    # Burlywood
    board_dark="#8B4513",     # SaddleBrown
    point_light="#F5DEB3",    # Wheat
    point_dark="#8B4513",     # SaddleBrown
    checker_x="#000000",      # Black
    checker_o="#FFFFFF",      # White
    checker_border="#333333", # Dark gray
    bar="#654321",            # Dark brown
    text="#000000",           # Black
    bearoff="#DEB887",        # Burlywood
    dice_color="#FFFFFF"      # White (matches pale checker)
)

FOREST = ColorScheme(
    name="Forest",
    board_light="#A8C5A0",    # Muted sage green
    board_dark="#3D5A3D",     # Deep forest green
    point_light="#C9D9C4",    # Soft mint
    point_dark="#5F7A5F",     # Muted olive green
    checker_x="#6B4423",      # Warm brown
    checker_o="#F5F5DC",      # Beige (off-white)
    checker_border="#3D5A3D", # Deep forest green
    bar="#4A6147",            # Muted forest green
    text="#000000",           # Black
    bearoff="#A8C5A0",        # Muted sage green
    dice_color="#F5F5DC"      # Beige (matches pale checker)
)

OCEAN = ColorScheme(
    name="Ocean",
    board_light="#87CEEB",    # SkyBlue
    board_dark="#191970",     # MidnightBlue
    point_light="#B0E0E6",    # PowderBlue
    point_dark="#4682B4",     # SteelBlue
    checker_x="#8B0000",      # DarkRed
    checker_o="#FFFACD",      # LemonChiffon (light)
    checker_border="#191970", # MidnightBlue
    bar="#1E3A5F",            # Deep ocean blue
    text="#000000",           # Black
    bearoff="#87CEEB",        # SkyBlue
    dice_color="#FFFACD"      # LemonChiffon (matches pale checker)
)

DESERT = ColorScheme(
    name="Desert",
    board_light="#D4A574",    # Muted tan/sand
    board_dark="#8B6F47",     # Warm brown
    point_light="#E8C9A0",    # Soft beige
    point_dark="#B8956A",     # Dusty tan
    checker_x="#6B4E71",      # Muted purple
    checker_o="#FFF8DC",      # Cornsilk (cream)
    checker_border="#6B4E71", # Muted purple
    bar="#9B7653",            # Warm brown
    text="#000000",           # Black
    bearoff="#D4A574",        # Muted tan/sand
    dice_color="#FFF8DC"      # Cornsilk (matches pale checker)
)

SUNSET = ColorScheme(
    name="Sunset",
    board_light="#D4825A",    # Terracotta/burnt orange
    board_dark="#5C3317",     # Dark chocolate brown
    point_light="#E69B7B",    # Soft coral
    point_dark="#B8552F",     # Deep burnt orange
    checker_x="#4A1E1E",      # Deep burgundy
    checker_o="#FFF5E6",      # Warm white
    checker_border="#5C3317", # Dark chocolate brown
    bar="#8B4726",            # Russet brown
    text="#000000",           # Black
    bearoff="#D4825A",        # Terracotta/burnt orange
    dice_color="#FFF5E6"      # Warm white (matches pale checker)
)

MIDNIGHT = ColorScheme(
    name="Midnight",
    board_light="#2F4F4F",    # DarkSlateGray
    board_dark="#000000",     # Black
    point_light="#708090",    # SlateGray
    point_dark="#1C1C1C",     # Nearly black
    checker_x="#DC143C",      # Crimson (red)
    checker_o="#E6E6FA",      # Lavender (light)
    checker_border="#000000", # Black
    bar="#0F0F0F",            # Very dark gray
    text="#FFFFFF",           # White (for contrast)
    bearoff="#2F4F4F",        # DarkSlateGray
    dice_color="#E6E6FA"      # Lavender (matches pale checker)
)

MONOCHROME = ColorScheme(
    name="Monochrome",
    board_light="#FFFFFF",    # White
    board_dark="#000000",     # Black
    point_light="#FFFFFF",    # White
    point_dark="#B0B0B0",     # Light gray
    checker_x="#000000",      # Black
    checker_o="#FFFFFF",      # White
    checker_border="#000000", # Black
    bar="#FFFFFF",            # White
    text="#000000",           # Black
    bearoff="#FFFFFF",        # White
    dice_color="#FFFFFF",     # White (matches pale checker)
    cube_fill="#FFFFFF",      # White
    cube_text="#000000"       # Black
)


# Dictionary of all available schemes
SCHEMES: Dict[str, ColorScheme] = {
    "classic": CLASSIC,
    "forest": FOREST,
    "ocean": OCEAN,
    "desert": DESERT,
    "sunset": SUNSET,
    "midnight": MIDNIGHT,
    "monochrome": MONOCHROME,
}


def get_scheme(name: str) -> ColorScheme:
    """
    Get a color scheme by name.

    Args:
        name: Scheme name (case-insensitive)

    Returns:
        ColorScheme object

    Raises:
        KeyError: If scheme name not found
    """
    return SCHEMES[name.lower()]


def list_schemes() -> list[str]:
    """Get list of available scheme names."""
    return list(SCHEMES.keys())
