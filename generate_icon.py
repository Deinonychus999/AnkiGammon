"""
Generate a larger dice icon for AnkiGammon with rotation.
"""
from PIL import Image, ImageDraw

# Create 512x512 image with dark blue background
size = 512

# Dice settings - optimized size
die_size = 270  # Good balance of filling space without being too large
corner_radius = 27
pip_radius = 19
border_width = 8

# Colors
die_color = (245, 224, 220, 255)  # Light beige
border_color = (69, 71, 90, 255)  # Dark border
pip_color = (30, 30, 46, 255)  # Dark pips

def draw_die_with_pips(die_size, pips_pattern, rotation_degrees):
    """Draw a die on its own image with rounded corners, pips, and rotation."""
    # Create a larger canvas to accommodate rotation without clipping
    canvas_size = int(die_size * 1.8)
    die_img = Image.new('RGBA', (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(die_img)

    # Draw die centered in canvas
    offset = (canvas_size - die_size) // 2

    # Draw die background with rounded corners
    draw.rounded_rectangle(
        [(offset, offset), (offset + die_size, offset + die_size)],
        radius=corner_radius,
        fill=die_color,
        outline=border_color,
        width=border_width
    )

    # Draw pips based on pattern
    for px, py in pips_pattern:
        pip_x = offset + die_size * px
        pip_y = offset + die_size * py
        draw.ellipse(
            [(pip_x - pip_radius, pip_y - pip_radius),
             (pip_x + pip_radius, pip_y + pip_radius)],
            fill=pip_color
        )

    # Rotate the die
    rotated = die_img.rotate(rotation_degrees, expand=False, resample=Image.BICUBIC)
    return rotated

# Create background image with transparency
img = Image.new('RGBA', (size, size), (0, 0, 0, 0))  # Fully transparent background

# Die 1: showing 5 (four corners + center) - rotated -15 degrees
pips_5 = [
    (0.25, 0.25),
    (0.75, 0.25),
    (0.5, 0.5),
    (0.25, 0.75),
    (0.75, 0.75)
]

# Die 2: showing 3 (diagonal) - rotated +12 degrees
pips_3 = [
    (0.25, 0.25),
    (0.5, 0.5),
    (0.75, 0.75)
]

# Create rotated dice
die1 = draw_die_with_pips(die_size, pips_5, 12)  # Tilt left
die2 = draw_die_with_pips(die_size, pips_3, -15)   # Tilt right

# Position the dice to maximize space with more vertical separation
die1_x = size // 2 - die1.width // 2 - 95
die1_y = size // 2 - die1.height // 2 + 70  # Lower the left die more

die2_x = size // 2 - die2.width // 2 + 95
die2_y = size // 2 - die2.height // 2 - 70  # Raise the right die more

# Composite the dice onto the background
img.paste(die1, (die1_x, die1_y), die1)
img.paste(die2, (die2_x, die2_y), die2)

# Save the icon
img.save('ankigammon/gui/resources/icon.png')
print("Icon generated successfully: ankigammon/gui/resources/icon.png")
print(f"Dice size: {die_size}x{die_size} pixels with rotation for dynamic look")
