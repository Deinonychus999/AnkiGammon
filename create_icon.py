#!/usr/bin/env python3
"""
Create app icon from dice design using pure Python.

Requirements:
    pip install pillow

Usage:
    python create_icon.py
"""

import os
from pathlib import Path
import math

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("Error: Pillow not installed")
    print("Please run: pip install pillow")
    exit(1)

# Paths
RESOURCES_DIR = Path(__file__).parent / "flashgammon" / "gui" / "resources"
ICO_PATH = RESOURCES_DIR / "icon.ico"
PNG_PATH = RESOURCES_DIR / "icon.png"

# Colors (from the SVG)
BG_COLOR = (30, 30, 46)  # #1e1e2e
DIE_COLOR = (245, 224, 220)  # #f5e0dc
BORDER_COLOR = (69, 71, 90)  # #45475a - Subtle gray from design system
PIP_COLOR = (30, 30, 46)  # #1e1e2e

def draw_rotated_rect(draw, x, y, width, height, angle, fill, outline, outline_width, radius):
    """Draw a rotated rounded rectangle."""
    # For simplicity with rotation, we'll draw a regular rotated rect
    # Create a temporary image for the die
    temp = Image.new('RGBA', (width + 20, height + 20), (0, 0, 0, 0))
    temp_draw = ImageDraw.Draw(temp)

    # Draw rounded rectangle at center
    temp_draw.rounded_rectangle(
        [(10, 10), (10 + width, 10 + height)],
        radius=radius,
        fill=fill,
        outline=outline,
        width=outline_width
    )

    # Rotate
    rotated = temp.rotate(angle, expand=False)

    return rotated

def draw_dice_icon(size: int) -> Image.Image:
    """Draw the dice icon at specified size - optimized for square icons."""
    # Calculate scale factor
    scale = size / 256

    # Create image with background
    img = Image.new('RGBA', (size, size), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Die dimensions - much larger for icon visibility
    die_size = int(80 * scale)
    corner_radius = int(8 * scale)
    pip_radius = int(6 * scale)
    border_width = max(2, int(3 * scale))

    # Center point
    center_x = size // 2
    center_y = size // 2

    # First die (showing 5) - left side, vertically centered
    die1_x = int(center_x - die_size - 10 * scale)
    die1_y = int(center_y - die_size // 2)

    # Draw first die
    die1_temp = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    die1_draw = ImageDraw.Draw(die1_temp)

    # Die rectangle
    die1_draw.rounded_rectangle(
        [(die1_x, die1_y), (die1_x + die_size, die1_y + die_size)],
        radius=corner_radius,
        fill=DIE_COLOR,
        outline=BORDER_COLOR,
        width=border_width
    )

    # Pips for 5 (corners + center)
    pip_offset = int(16 * scale)
    pips_5 = [
        (die1_x + pip_offset, die1_y + pip_offset),  # top-left
        (die1_x + die_size - pip_offset, die1_y + pip_offset),  # top-right
        (die1_x + die_size // 2, die1_y + die_size // 2),  # center
        (die1_x + pip_offset, die1_y + die_size - pip_offset),  # bottom-left
        (die1_x + die_size - pip_offset, die1_y + die_size - pip_offset),  # bottom-right
    ]

    for px, py in pips_5:
        die1_draw.ellipse(
            [(px - pip_radius, py - pip_radius), (px + pip_radius, py + pip_radius)],
            fill=PIP_COLOR
        )

    # Rotate first die slightly (-12 degrees)
    die1_rotated = die1_temp.rotate(-12, expand=False, resample=Image.BICUBIC)
    img = Image.alpha_composite(img, die1_rotated)

    # Second die (showing 3) - right side, vertically centered
    die2_x = int(center_x + 10 * scale)
    die2_y = int(center_y - die_size // 2)

    # Draw second die
    die2_temp = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    die2_draw = ImageDraw.Draw(die2_temp)

    # Die rectangle
    die2_draw.rounded_rectangle(
        [(die2_x, die2_y), (die2_x + die_size, die2_y + die_size)],
        radius=corner_radius,
        fill=DIE_COLOR,
        outline=BORDER_COLOR,
        width=border_width
    )

    # Pips for 3 (diagonal)
    pips_3 = [
        (die2_x + pip_offset, die2_y + pip_offset),  # top-left
        (die2_x + die_size // 2, die2_y + die_size // 2),  # center
        (die2_x + die_size - pip_offset, die2_y + die_size - pip_offset),  # bottom-right
    ]

    for px, py in pips_3:
        die2_draw.ellipse(
            [(px - pip_radius, py - pip_radius), (px + pip_radius, py + pip_radius)],
            fill=PIP_COLOR
        )

    # Rotate second die slightly (+12 degrees)
    die2_rotated = die2_temp.rotate(12, expand=False, resample=Image.BICUBIC)
    img = Image.alpha_composite(img, die2_rotated)

    return img

def create_ico(ico_path: Path):
    """Create .ico file with multiple sizes."""
    print(f"Creating {ico_path.name}...")

    # Windows ICO should contain multiple sizes
    sizes = [16, 24, 32, 48, 64, 128, 256]
    images = [draw_dice_icon(size) for size in sizes]

    # Save as ICO
    images[0].save(
        ico_path,
        format='ICO',
        sizes=[(img.width, img.height) for img in images],
        append_images=images[1:]
    )
    print(f"[OK] Created {ico_path}")

def create_png(png_path: Path):
    """Create high-res PNG for macOS."""
    print(f"Creating {png_path.name}...")

    # Create 512x512 PNG (suitable for macOS)
    img = draw_dice_icon(512)
    img.save(png_path, format='PNG')
    print(f"[OK] Created {png_path}")
    print("  Note: On macOS, you can convert to .icns using: iconutil -c icns icon.iconset")

def main():
    print("Creating application icons with dice design...")
    print()

    # Create Windows ICO
    create_ico(ICO_PATH)

    # Create PNG for macOS/preview
    create_png(PNG_PATH)

    print()
    print("Done! Icon files created:")
    if ICO_PATH.exists():
        print(f"  - {ICO_PATH.relative_to(Path.cwd())}")
    if PNG_PATH.exists():
        print(f"  - {PNG_PATH.relative_to(Path.cwd())}")

if __name__ == '__main__':
    main()
