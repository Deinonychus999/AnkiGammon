"""Generate sample board SVGs for each color scheme."""

from pathlib import Path
from xg2anki.models import Position, Player, CubeState
from xg2anki.renderer.svg_board_renderer import SVGBoardRenderer
from xg2anki.renderer.color_schemes import SCHEMES


def create_sample_position():
    """Create an interesting sample position for demonstration."""
    # Create a position with checkers distributed across the board
    position = Position()

    # X's checkers (white, positive values)
    position.points[24] = 2  # X's home board
    position.points[23] = 3
    position.points[20] = 2
    position.points[13] = 5  # Mid-point
    position.points[8] = 3
    position.points[6] = 2

    # O's checkers (black, negative values)
    position.points[1] = -2   # O's home board
    position.points[3] = -3
    position.points[5] = -2
    position.points[12] = -5  # Mid-point
    position.points[17] = -3
    position.points[19] = -2

    # Bear-off
    position.x_off = 3
    position.o_off = 3

    return position


def main():
    """Generate sample HTML files with SVG for all color schemes."""
    # Create output directory
    output_dir = Path("color_scheme_samples")
    output_dir.mkdir(exist_ok=True)

    # Create sample position
    position = create_sample_position()

    # Generate HTML file for each scheme
    for scheme_name, scheme in SCHEMES.items():
        print(f"Generating sample for {scheme_name}...")

        # Create renderer with this color scheme
        renderer = SVGBoardRenderer(color_scheme=scheme)

        # Render the position as SVG
        svg = renderer.render_svg(
            position=position,
            on_roll=Player.O,
            dice=(5, 3),
            dice_opacity=1.0,
            cube_value=2,
            cube_owner=CubeState.CENTERED
        )

        # Create HTML wrapper
        html = f'''<!DOCTYPE html>
<html>
<head>
    <title>{scheme.name} Color Scheme</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            text-align: center;
            padding: 20px;
            background: #f0f0f0;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            margin-bottom: 20px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{scheme.name} Color Scheme</h1>
        {svg}
    </div>
</body>
</html>'''

        # Save to file
        output_path = output_dir / f"{scheme_name}.html"
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html)

        print(f"  Created: {output_path}")

    print(f"\nAll samples generated in: {output_dir.absolute()}")
    print("Open the HTML files in a browser to view the color schemes.")


if __name__ == "__main__":
    main()
