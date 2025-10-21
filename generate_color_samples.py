"""Generate sample board PNGs for each color scheme."""

from pathlib import Path
from flashgammon.models import Position, Player, CubeState
from flashgammon.renderer.svg_board_renderer import SVGBoardRenderer
from flashgammon.renderer.color_schemes import SCHEMES
from html2image import Html2Image
import os


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
    """Generate sample PNG files for all color schemes."""
    # Create output directory
    output_dir = Path("color_scheme_samples")
    output_dir.mkdir(exist_ok=True)

    # Create sample position
    position = create_sample_position()

    # Initialize html2image
    hti = Html2Image(output_path=str(output_dir))

    # Generate PNG file for each scheme
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

        # Create HTML with embedded SVG
        html = f"""
        <!DOCTYPE html>
        <html>
        <body style="margin:0;padding:0;">
            {svg}
        </body>
        </html>
        """

        # Convert HTML to PNG
        hti.screenshot(
            html_str=html,
            save_as=f"{scheme_name}.png",
            size=(800, 500)
        )

        print(f"  Created: {output_dir / f'{scheme_name}.png'}")

    print(f"\nAll samples generated in: {output_dir.absolute()}")
    print("PNG files ready for viewing.")


if __name__ == "__main__":
    main()
