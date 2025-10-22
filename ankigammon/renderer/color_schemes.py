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


# Define 5 beautiful color schemes
CLASSIC = ColorScheme(
    name="Classic",
    board_light="#DEB887",    # Burlywood
    board_dark="#8B4513",     # SaddleBrown
    point_light="#F5DEB3",    # Wheat
    point_dark="#8B4513",     # SaddleBrown
    checker_x="#FFFFFF",      # White
    checker_o="#000000",      # Black
    checker_border="#333333", # Dark gray
    bar="#654321",            # Dark brown
    text="#000000",           # Black
    bearoff="#DEB887"         # Burlywood
)

FOREST = ColorScheme(
    name="Forest",
    board_light="#A8C5A0",    # Muted sage green
    board_dark="#3D5A3D",     # Deep forest green
    point_light="#C9D9C4",    # Soft mint
    point_dark="#5F7A5F",     # Muted olive green
    checker_x="#F5F5DC",      # Beige (off-white)
    checker_o="#6B4423",      # Warm brown
    checker_border="#3D5A3D", # Deep forest green
    bar="#4A6147",            # Muted forest green
    text="#000000",           # Black
    bearoff="#A8C5A0"         # Muted sage green
)

OCEAN = ColorScheme(
    name="Ocean",
    board_light="#87CEEB",    # SkyBlue
    board_dark="#191970",     # MidnightBlue
    point_light="#B0E0E6",    # PowderBlue
    point_dark="#4682B4",     # SteelBlue
    checker_x="#FFFACD",      # LemonChiffon (light)
    checker_o="#8B0000",      # DarkRed
    checker_border="#191970", # MidnightBlue
    bar="#1E3A5F",            # Deep ocean blue
    text="#000000",           # Black
    bearoff="#87CEEB"         # SkyBlue
)

DESERT = ColorScheme(
    name="Desert",
    board_light="#D4A574",    # Muted tan/sand
    board_dark="#8B6F47",     # Warm brown
    point_light="#E8C9A0",    # Soft beige
    point_dark="#B8956A",     # Dusty tan
    checker_x="#FFF8DC",      # Cornsilk (cream)
    checker_o="#6B4E71",      # Muted purple
    checker_border="#6B4E71", # Muted purple
    bar="#9B7653",            # Warm brown
    text="#000000",           # Black
    bearoff="#D4A574"         # Muted tan/sand
)

SUNSET = ColorScheme(
    name="Sunset",
    board_light="#D4825A",    # Terracotta/burnt orange
    board_dark="#5C3317",     # Dark chocolate brown
    point_light="#E69B7B",    # Soft coral
    point_dark="#B8552F",     # Deep burnt orange
    checker_x="#FFF5E6",      # Warm white
    checker_o="#4A1E1E",      # Deep burgundy
    checker_border="#5C3317", # Dark chocolate brown
    bar="#8B4726",            # Russet brown
    text="#000000",           # Black
    bearoff="#D4825A"         # Terracotta/burnt orange
)

MIDNIGHT = ColorScheme(
    name="Midnight",
    board_light="#2F4F4F",    # DarkSlateGray
    board_dark="#000000",     # Black
    point_light="#708090",    # SlateGray
    point_dark="#1C1C1C",     # Nearly black
    checker_x="#E6E6FA",      # Lavender (light)
    checker_o="#DC143C",      # Crimson (red)
    checker_border="#000000", # Black
    bar="#0F0F0F",            # Very dark gray
    text="#FFFFFF",           # White (for contrast)
    bearoff="#2F4F4F"         # DarkSlateGray
)


# Dictionary of all available schemes
SCHEMES: Dict[str, ColorScheme] = {
    "classic": CLASSIC,
    "forest": FOREST,
    "ocean": OCEAN,
    "desert": DESERT,
    "sunset": SUNSET,
    "midnight": MIDNIGHT,
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
