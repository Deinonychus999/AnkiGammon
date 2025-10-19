"""Backgammon board renderer - generates PNG images of positions."""

from PIL import Image, ImageDraw, ImageFont
from typing import Optional, Tuple
import math

from xg2anki.models import Position, Player, CubeState
from xg2anki.renderer.color_schemes import ColorScheme, CLASSIC


class BoardRenderer:
    """Renders backgammon positions as PNG images."""

    def __init__(
        self,
        width: int = 900,  # Increased from 800 to make room
        height: int = 600,
        point_height_ratio: float = 0.45,  # Increased from 0.35 to make triangles longer
        color_scheme: ColorScheme = CLASSIC,
        antialias_scale: int = 3,  # Render at 3x resolution for antialiasing
    ):
        """
        Initialize the board renderer.

        Args:
            width: Image width in pixels
            height: Image height in pixels
            point_height_ratio: Height of points as ratio of board height
            color_scheme: ColorScheme object defining board colors
            antialias_scale: Supersampling factor (2-4 recommended, 1=disabled)
        """
        self.target_width = width
        self.target_height = height
        self.antialias_scale = max(1, antialias_scale)

        # Render at higher resolution for antialiasing
        self.width = width * self.antialias_scale
        self.height = height * self.antialias_scale

        self.point_height_ratio = point_height_ratio
        self.color_scheme = color_scheme

        # Set color attributes from scheme for backward compatibility
        self.COLOR_BOARD_LIGHT = color_scheme.board_light
        self.COLOR_BOARD_DARK = color_scheme.board_dark
        self.COLOR_POINT_LIGHT = color_scheme.point_light
        self.COLOR_POINT_DARK = color_scheme.point_dark
        self.COLOR_CHECKER_X = color_scheme.checker_x
        self.COLOR_CHECKER_O = color_scheme.checker_o
        self.COLOR_CHECKER_BORDER = color_scheme.checker_border
        self.COLOR_BAR = color_scheme.bar
        self.COLOR_TEXT = color_scheme.text
        self.COLOR_BEAROFF = color_scheme.bearoff

        # Calculate dimensions with space for cube (left) and bear-off (right)
        # All dimensions are scaled for antialiasing
        self.margin = 20 * self.antialias_scale
        self.cube_area_width = 70 * self.antialias_scale  # Space on left for cube
        self.bearoff_area_width = 100 * self.antialias_scale  # Space on right for bear-off

        # Playing area (the actual board)
        self.playing_width = self.width - 2 * self.margin - self.cube_area_width - self.bearoff_area_width
        self.board_height = self.height - 2 * self.margin

        # Bar width (center divider)
        self.bar_width = self.playing_width * 0.08

        # Each half has 6 points
        self.half_width = (self.playing_width - self.bar_width) / 2
        self.point_width = self.half_width / 6

        # Point height
        self.point_height = self.board_height * point_height_ratio

        # Checker size - increased to take advantage of longer points
        self.checker_radius = min(self.point_width * 0.45, 25 * self.antialias_scale)

    def render(
        self,
        position: Position,
        on_roll: Player = Player.O,
        dice: Optional[Tuple[int, int]] = None,
        dice_opacity: float = 1.0,
        cube_value: int = 1,
        cube_owner: CubeState = CubeState.CENTERED,
        output_path: Optional[str] = None,
    ) -> Image.Image:
        """
        Render a backgammon position.

        The board is rendered as-is from the position data.
        - Points 1-6: bottom-right quadrant (O's home board)
        - Points 7-12: bottom-left quadrant
        - Points 13-18: top-left quadrant
        - Points 19-24: top-right quadrant (X's home board)

        Args:
            position: The position to render
            on_roll: Which player is on roll
            dice: Dice values (if any)
            cube_value: Doubling cube value
            cube_owner: Who owns the cube
            output_path: If provided, save the image to this path

        Returns:
            PIL Image object
        """
        # Create image
        img = Image.new("RGB", (self.width, self.height), self.COLOR_BOARD_LIGHT)
        draw = ImageDraw.Draw(img)

        # Board starts after cube area
        board_x = self.margin + self.cube_area_width
        board_y = self.margin

        # Draw board background (playing area only)
        draw.rectangle(
            [board_x, board_y, board_x + self.playing_width, board_y + self.board_height],
            fill=self.COLOR_BOARD_LIGHT,
            outline=self.COLOR_BOARD_DARK,
            width=3 * self.antialias_scale
        )

        # Draw bar
        bar_x = board_x + self.half_width
        draw.rectangle(
            [bar_x, board_y, bar_x + self.bar_width, board_y + self.board_height],
            fill=self.COLOR_BAR,
            outline=self.COLOR_BOARD_DARK,
            width=2 * self.antialias_scale
        )

        # Draw points
        self._draw_points(draw, board_x, board_y)

        # Don't flip the board - always show from O's perspective
        # (XG positions are already encoded correctly for this)
        flipped = False

        # Draw checkers
        self._draw_checkers(draw, position, board_x, board_y, flipped)

        # Draw bear-off trays
        self._draw_bearoff(draw, position, board_x, board_y, flipped)

        # Draw dice
        if dice:
            self._draw_dice(draw, dice, on_roll, board_x, board_y, dice_opacity, img)

        # Draw cube
        self._draw_cube(draw, cube_value, cube_owner, board_x, board_y, flipped)

        # Draw player indicators
        self._draw_player_indicators(draw, on_roll, board_x, board_y)

        # Draw pip counts
        self._draw_pip_counts(draw, position, board_x, board_y, flipped)

        # Downscale for antialiasing if needed
        if self.antialias_scale > 1:
            img = img.resize(
                (self.target_width, self.target_height),
                Image.Resampling.LANCZOS  # High-quality downsampling
            )

        if output_path:
            img.save(output_path)

        return img

    def _draw_points(self, draw: ImageDraw.Draw, board_x: int, board_y: int):
        """Draw the triangular points with numbers."""
        try:
            font_point_num = ImageFont.truetype("arial.ttf", 10 * self.antialias_scale)
        except:
            font_point_num = ImageFont.load_default()

        for i in range(24):
            point_num = i + 1  # Points are numbered 1-24

            # Determine point position
            if i < 6:
                # Bottom right quadrant (points 1-6)
                x = board_x + self.half_width + self.bar_width + (5 - i) * self.point_width
                y_base = board_y + self.board_height
                y_tip = y_base - self.point_height
                color = self.COLOR_POINT_DARK if i % 2 == 0 else self.COLOR_POINT_LIGHT
                label_y = y_base + 3 * self.antialias_scale  # Below the base
            elif i < 12:
                # Bottom left quadrant (points 7-12)
                x = board_x + (11 - i) * self.point_width
                y_base = board_y + self.board_height
                y_tip = y_base - self.point_height
                color = self.COLOR_POINT_LIGHT if i % 2 == 0 else self.COLOR_POINT_DARK
                label_y = y_base + 3 * self.antialias_scale  # Below the base
            elif i < 18:
                # Top left quadrant (points 13-18)
                x = board_x + (i - 12) * self.point_width
                y_base = board_y
                y_tip = y_base + self.point_height
                color = self.COLOR_POINT_DARK if i % 2 == 0 else self.COLOR_POINT_LIGHT
                label_y = y_base - 15 * self.antialias_scale  # Above the base
            else:
                # Top right quadrant (points 19-24)
                x = board_x + self.half_width + self.bar_width + (i - 18) * self.point_width
                y_base = board_y
                y_tip = y_base + self.point_height
                color = self.COLOR_POINT_LIGHT if i % 2 == 0 else self.COLOR_POINT_DARK
                label_y = y_base - 15 * self.antialias_scale  # Above the base

            # Draw triangle
            points_triangle = [
                (x, y_base),
                (x + self.point_width, y_base),
                (x + self.point_width / 2, y_tip)
            ]
            draw.polygon(points_triangle, fill=color, outline=self.COLOR_BOARD_DARK, width=self.antialias_scale)

            # Draw point number
            label_text = str(point_num)
            text_bbox = draw.textbbox((0, 0), label_text, font=font_point_num)
            text_width = text_bbox[2] - text_bbox[0]
            label_x = x + (self.point_width - text_width) / 2
            draw.text((label_x, label_y), label_text, fill=self.COLOR_TEXT, font=font_point_num)

    def _draw_checkers(
        self,
        draw: ImageDraw.Draw,
        position: Position,
        board_x: int,
        board_y: int,
        flipped: bool
    ):
        """Draw checkers on the board."""
        for point_idx in range(1, 25):  # Points 1-24
            count = position.points[point_idx]
            if count == 0:
                continue

            player = Player.X if count > 0 else Player.O
            num_checkers = abs(count)
            color = self.COLOR_CHECKER_X if player == Player.X else self.COLOR_CHECKER_O

            # Map to display point so the board can be flipped when needed
            display_point_idx = self._map_point_index(point_idx, flipped)

            # Get point position in display coordinates
            x, y_base, is_top = self._get_point_position(display_point_idx, board_x, board_y)

            # Draw checkers
            for checker_num in range(min(num_checkers, 5)):  # Max 5 visible checkers per point
                if is_top:
                    y = y_base + self.checker_radius + checker_num * (self.checker_radius * 2 + 2)
                else:
                    y = y_base - self.checker_radius - checker_num * (self.checker_radius * 2 + 2)

                cx = x + self.point_width / 2
                self._draw_checker(draw, cx, y, color)

            # If more than 5 checkers, draw a number
            if num_checkers > 5:
                if is_top:
                    y = y_base + self.checker_radius + 4 * (self.checker_radius * 2 + 2)
                else:
                    y = y_base - self.checker_radius - 4 * (self.checker_radius * 2 + 2)

                cx = x + self.point_width / 2
                self._draw_checker_with_number(draw, cx, y, color, num_checkers)

        # Draw checkers on bar
        self._draw_bar_checkers(draw, position, board_x, board_y, flipped)

    def _draw_bar_checkers(
        self,
        draw: ImageDraw.Draw,
        position: Position,
        board_x: int,
        board_y: int,
        flipped: bool
    ):
        """Draw checkers on the bar."""
        bar_x = board_x + self.half_width
        bar_center_x = bar_x + self.bar_width / 2

        x_bar_count = max(position.points[0], 0)
        o_bar_count = max(-position.points[25], 0)

        if flipped:
            # When flipped, actual X checkers are at the bottom
            self._draw_bar_stack(draw, bar_center_x, x_bar_count, self.COLOR_CHECKER_X, top=False, board_y=board_y)
            self._draw_bar_stack(draw, bar_center_x, o_bar_count, self.COLOR_CHECKER_O, top=True, board_y=board_y)
        else:
            self._draw_bar_stack(draw, bar_center_x, x_bar_count, self.COLOR_CHECKER_X, top=True, board_y=board_y)
            self._draw_bar_stack(draw, bar_center_x, o_bar_count, self.COLOR_CHECKER_O, top=False, board_y=board_y)

    def _draw_bar_stack(
        self,
        draw: ImageDraw.Draw,
        center_x: float,
        count: int,
        color: str,
        top: bool,
        board_y: int
    ):
        """Draw stacked checkers on the bar for a single player."""
        if count <= 0:
            return

        max_visible = min(count, 3)
        for i in range(max_visible):
            if top:
                y = board_y + self.point_height + i * (self.checker_radius * 2 + 2)
            else:
                y = board_y + self.board_height - self.point_height - i * (self.checker_radius * 2 + 2)

            self._draw_checker(draw, center_x, y, color)

        if count > max_visible:
            if top:
                y = board_y + self.point_height + (max_visible - 1) * (self.checker_radius * 2 + 2)
            else:
                y = board_y + self.board_height - self.point_height - (max_visible - 1) * (self.checker_radius * 2 + 2)

            self._draw_checker_with_number(draw, center_x, y, color, count)

    def _draw_bearoff(
        self,
        draw: ImageDraw.Draw,
        position: Position,
        board_x: int,
        board_y: int,
        flipped: bool
    ):
        """Draw bear-off trays with stacked checker representations."""
        # Bear-off area is to the RIGHT of the playing board
        bearoff_x = board_x + self.playing_width + 10 * self.antialias_scale
        bearoff_width = self.bearoff_area_width - 20 * self.antialias_scale

        # Checker dimensions - thin vertical rectangles
        checker_width = 10 * self.antialias_scale
        checker_height = 50 * self.antialias_scale
        checker_spacing_x = 3 * self.antialias_scale
        checker_spacing_y = 4 * self.antialias_scale
        checkers_per_row = 5

        # Determine which player is at the top/bottom based on orientation
        top_player = Player.X if not flipped else Player.O
        bottom_player = Player.O if not flipped else Player.X

        def get_off_count(player: Player) -> int:
            if player == Player.X:
                return max(position.x_off, 0)
            return max(position.o_off, 0)

        def get_color(player: Player) -> str:
            return self.COLOR_CHECKER_X if player == Player.X else self.COLOR_CHECKER_O

        # Top tray
        tray_top = board_y + 10 * self.antialias_scale
        tray_bottom = board_y + self.board_height / 2 - 10 * self.antialias_scale

        # Draw tray background
        draw.rectangle(
            [bearoff_x, tray_top, bearoff_x + bearoff_width, tray_bottom],
            fill=self.COLOR_BEAROFF,
            outline=self.COLOR_BOARD_DARK,
            width=2 * self.antialias_scale
        )

        # Draw stacked checkers for the player on top
        # Fill left-to-right for each row, starting from bottom row
        top_count = get_off_count(top_player)
        if top_count > 0:
            # Calculate total width needed for 5 checkers
            row_width = checkers_per_row * checker_width + (checkers_per_row - 1) * checker_spacing_x
            start_x = bearoff_x + (bearoff_width - row_width) / 2
            start_y = tray_bottom - 10 * self.antialias_scale - checker_height  # Start from bottom of tray

            for i in range(top_count):
                # Which row (0=bottom, 1=middle, 2=top)
                row = i // checkers_per_row
                # Position within that row (0-4, left to right)
                col = i % checkers_per_row

                # X position: left to right within the row
                x = start_x + col * (checker_width + checker_spacing_x)
                # Y position: bottom to top (subtract for each row)
                y = start_y - row * (checker_height + checker_spacing_y)

                # Draw thin rectangle (checker)
                draw.rectangle(
                    [x, y, x + checker_width, y + checker_height],
                    fill=get_color(top_player),
                    outline=self.COLOR_CHECKER_BORDER,
                    width=self.antialias_scale
                )

        # Bottom tray
        tray_top = board_y + self.board_height / 2 + 10 * self.antialias_scale
        tray_bottom = board_y + self.board_height - 10 * self.antialias_scale

        # Draw tray background
        draw.rectangle(
            [bearoff_x, tray_top, bearoff_x + bearoff_width, tray_bottom],
            fill=self.COLOR_BEAROFF,
            outline=self.COLOR_BOARD_DARK,
            width=2 * self.antialias_scale
        )

        # Draw stacked checkers for the player on bottom
        # Fill left-to-right for each row, starting from bottom row
        bottom_count = get_off_count(bottom_player)
        if bottom_count > 0:
            # Calculate total width needed for 5 checkers
            row_width = checkers_per_row * checker_width + (checkers_per_row - 1) * checker_spacing_x
            start_x = bearoff_x + (bearoff_width - row_width) / 2
            start_y = tray_bottom - 10 * self.antialias_scale - checker_height  # Start from bottom of tray

            for i in range(bottom_count):
                # Which row (0=bottom, 1=middle, 2=top)
                row = i // checkers_per_row
                # Position within that row (0-4, left to right)
                col = i % checkers_per_row

                # X position: left to right within the row
                x = start_x + col * (checker_width + checker_spacing_x)
                # Y position: bottom to top (subtract for each row)
                y = start_y - row * (checker_height + checker_spacing_y)

                # Draw thin rectangle (checker)
                draw.rectangle(
                    [x, y, x + checker_width, y + checker_height],
                    fill=get_color(bottom_player),
                    outline=self.COLOR_CHECKER_BORDER,
                    width=1
                )

    def _draw_checker(self, draw: ImageDraw.Draw, x: float, y: float, color: str):
        """Draw a single checker."""
        r = self.checker_radius
        draw.ellipse([x - r, y - r, x + r, y + r], fill=color, outline=self.COLOR_CHECKER_BORDER, width=2 * self.antialias_scale)

    def _draw_checker_with_number(self, draw: ImageDraw.Draw, x: float, y: float, color: str, number: int):
        """Draw a checker with a number on it."""
        self._draw_checker(draw, x, y, color)

        # Draw number (already scaled via checker_radius which uses scaled dimensions)
        text = str(number)
        try:
            font = ImageFont.truetype("arial.ttf", int(self.checker_radius * 1.2))
        except:
            font = ImageFont.load_default()

        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        text_x = x - text_width / 2
        # Better vertical centering - adjust for font baseline offset
        text_y = y - text_height / 2 - text_bbox[1]

        # Use contrasting color for text
        text_color = self.COLOR_CHECKER_O if color == self.COLOR_CHECKER_X else self.COLOR_CHECKER_X
        draw.text((text_x, text_y), text, fill=text_color, font=font)

    def _draw_dice(
        self,
        draw: ImageDraw.Draw,
        dice: Tuple[int, int],
        on_roll: Player,
        board_x: int,
        board_y: int,
        opacity: float = 1.0,
        base_img: Image.Image = None
    ):
        """Draw dice with optional transparency."""
        die_size = 50 * self.antialias_scale
        die_spacing = 15 * self.antialias_scale

        # Position dice on the playing field (NOT on the bar)
        # Always place dice on the RIGHT half of the board (traditional backgammon placement)
        # Total width of both dice with spacing
        total_dice_width = 2 * die_size + die_spacing

        # Both players' dice ALWAYS go on the RIGHT half, regardless of who is on roll
        # Right half starts after the bar
        right_half_start = board_x + self.half_width + self.bar_width
        # Center the dice horizontally in the right half
        die_x = right_half_start + (self.half_width - total_dice_width) / 2
        # Center vertically in the board
        die_y = board_y + (self.board_height - die_size) / 2

        if opacity < 1.0 and base_img:
            # Create a transparent overlay for the dice
            dice_layer = Image.new("RGBA", base_img.size, (255, 255, 255, 0))
            dice_draw = ImageDraw.Draw(dice_layer)

            # Draw dice on the overlay
            self._draw_die(dice_draw, die_x, die_y, die_size, dice[0])
            self._draw_die(dice_draw, die_x + die_size + die_spacing, die_y, die_size, dice[1])

            # Convert base image to RGBA
            base_rgba = base_img.convert("RGBA")

            # Apply opacity to dice layer
            alpha = dice_layer.split()[3]
            alpha = alpha.point(lambda p: int(p * opacity))
            dice_layer.putalpha(alpha)

            # Composite the layers
            base_rgba.alpha_composite(dice_layer)
            base_img.paste(base_rgba.convert("RGB"), (0, 0))
        else:
            # Draw normally with full opacity
            self._draw_die(draw, die_x, die_y, die_size, dice[0])
            self._draw_die(draw, die_x + die_size + die_spacing, die_y, die_size, dice[1])

    def _draw_die(self, draw: ImageDraw.Draw, x: int, y: int, size: int, value: int):
        """Draw a single die."""
        # Draw die background
        draw.rectangle([x, y, x + size, y + size], fill="#FFFFFF", outline="#000000", width=2 * self.antialias_scale)

        # Draw pips
        pip_radius = size // 10
        center = size // 2

        # Pip positions for each value
        pip_positions = {
            1: [(center, center)],
            2: [(size // 4, size // 4), (3 * size // 4, 3 * size // 4)],
            3: [(size // 4, size // 4), (center, center), (3 * size // 4, 3 * size // 4)],
            4: [(size // 4, size // 4), (3 * size // 4, size // 4),
                (size // 4, 3 * size // 4), (3 * size // 4, 3 * size // 4)],
            5: [(size // 4, size // 4), (3 * size // 4, size // 4),
                (center, center),
                (size // 4, 3 * size // 4), (3 * size // 4, 3 * size // 4)],
            6: [(size // 4, size // 4), (3 * size // 4, size // 4),
                (size // 4, center), (3 * size // 4, center),
                (size // 4, 3 * size // 4), (3 * size // 4, 3 * size // 4)],
        }

        for px, py in pip_positions.get(value, []):
            draw.ellipse(
                [x + px - pip_radius, y + py - pip_radius,
                 x + px + pip_radius, y + py + pip_radius],
                fill="#000000"
            )

    def _draw_cube(
        self,
        draw: ImageDraw.Draw,
        cube_value: int,
        cube_owner: CubeState,
        board_x: int,
        board_y: int,
        flipped: bool
    ):
        """Draw the doubling cube."""
        cube_size = 50 * self.antialias_scale

        # Cube area is to the LEFT of the playing board
        cube_area_x = self.margin + 10 * self.antialias_scale
        cube_area_center = cube_area_x + (self.cube_area_width - 20 * self.antialias_scale) / 2

        # Position cube based on owner
        if cube_owner == CubeState.CENTERED:
            # Left area (like when turned), centered vertically
            cube_x = cube_area_center - cube_size / 2
            cube_y = board_y + (self.board_height - cube_size) / 2
        elif cube_owner == CubeState.O_OWNS:
            # Bottom player - left area, at the very bottom
            cube_x = cube_area_center - cube_size / 2
            if flipped:
                cube_y = board_y + 10 * self.antialias_scale
            else:
                cube_y = board_y + self.board_height - cube_size - 10 * self.antialias_scale
        else:  # X_OWNS
            # Top player - left area, at the very top
            cube_x = cube_area_center - cube_size / 2
            if flipped:
                cube_y = board_y + self.board_height - cube_size - 10 * self.antialias_scale
            else:
                cube_y = board_y + 10 * self.antialias_scale

        # Draw cube
        draw.rectangle(
            [cube_x, cube_y, cube_x + cube_size, cube_y + cube_size],
            fill="#FFD700",  # Gold
            outline="#000000",
            width=2 * self.antialias_scale
        )

        # Draw value - show 64 when centered, otherwise show actual value
        text = "64" if cube_owner == CubeState.CENTERED else str(cube_value)
        try:
            font = ImageFont.truetype("arial.ttf", 32 * self.antialias_scale)
        except:
            font = ImageFont.load_default()

        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        text_x = cube_x + (cube_size - text_width) / 2
        # Better vertical centering - adjust for font baseline offset
        text_y = cube_y + (cube_size - text_height) / 2 - text_bbox[1]

        draw.text((text_x, text_y), text, fill="#000000", font=font)

    def _draw_player_indicators(
        self,
        draw: ImageDraw.Draw,
        on_roll: Player,
        board_x: int,
        board_y: int
    ):
        """Draw player name labels and on-roll indicator."""
        # Labels removed per user request
        pass

    def _map_point_index(self, point_idx: int, flipped: bool) -> int:
        """
        Map a logical point index to the display index based on orientation.

        When flipped, we rotate the board 180 degrees so the player on roll
        appears at the bottom of the rendered board.
        """
        if not flipped:
            return point_idx

        # Rotate positions by 12 points (half a board)
        return ((point_idx + 11) % 24) + 1

    def _get_point_position(self, point_idx: int, board_x: int, board_y: int) -> Tuple[float, float, bool]:
        """
        Get the x, y position and orientation of a point.

        Returns:
            (x, y_base, is_top) where is_top indicates if point extends from top
        """
        if point_idx < 1 or point_idx > 24:
            raise ValueError(f"Invalid point index: {point_idx}")

        if point_idx <= 6:
            # Bottom right quadrant (points 1-6)
            x = board_x + self.half_width + self.bar_width + (6 - point_idx) * self.point_width
            y_base = board_y + self.board_height
            is_top = False
        elif point_idx <= 12:
            # Bottom left quadrant (points 7-12)
            x = board_x + (12 - point_idx) * self.point_width
            y_base = board_y + self.board_height
            is_top = False
        elif point_idx <= 18:
            # Top left quadrant (points 13-18)
            x = board_x + (point_idx - 13) * self.point_width
            y_base = board_y
            is_top = True
        else:
            # Top right quadrant (points 19-24)
            x = board_x + self.half_width + self.bar_width + (point_idx - 19) * self.point_width
            y_base = board_y
            is_top = True

        return x, y_base, is_top

    def _calculate_pip_count(self, position: Position, player: Player) -> int:
        """
        Calculate pip count for a player.

        In backgammon:
        - X (white/top) bears off from points 19-24, so point 1 = 24 pips away, point 24 = 0 pips (home)
        - O (black/bottom) bears off from points 1-6, so point 24 = 24 pips away, point 1 = 0 pips (home)
        """
        pip_count = 0

        if player == Player.X:
            # For X: point 1 is 24 pips away, point 24 is home (0 pips)
            # So pip distance = 25 - point_idx
            for point_idx in range(1, 25):
                if position.points[point_idx] > 0:  # X's checkers (positive)
                    x_pip_distance = 25 - point_idx
                    pip_count += x_pip_distance * position.points[point_idx]

            # Checkers on bar count as 25 pips
            if position.points[0] > 0:
                pip_count += 25 * position.points[0]

        else:  # Player.O
            # For O: point 24 is 24 pips away, point 1 is home (0 pips)
            # So pip distance = point_idx
            for point_idx in range(1, 25):
                if position.points[point_idx] < 0:  # O's checkers (negative)
                    o_pip_distance = point_idx
                    pip_count += o_pip_distance * abs(position.points[point_idx])

            # Checkers on bar count as 25 pips
            if position.points[25] < 0:
                pip_count += 25 * abs(position.points[25])

        return pip_count

    def _draw_pip_counts(
        self,
        draw: ImageDraw.Draw,
        position: Position,
        board_x: int,
        board_y: int,
        flipped: bool
    ):
        """Draw pip counts for both players."""
        try:
            font = ImageFont.truetype("arial.ttf", 12 * self.antialias_scale)
        except:
            font = ImageFont.load_default()

        # Calculate pip counts
        x_pips = self._calculate_pip_count(position, Player.X)
        o_pips = self._calculate_pip_count(position, Player.O)

        # Draw X's pip count (top right area, in top bear-off tray)
        x_text = f"Pip: {x_pips}"
        bearoff_text_x = board_x + self.playing_width + 15 * self.antialias_scale
        x_bearoff_top = board_y + 10 * self.antialias_scale

        # Draw O's pip count (bottom right area, in bottom bear-off tray)
        o_text = f"Pip: {o_pips}"
        o_bearoff_top = board_y + self.board_height / 2 + 10 * self.antialias_scale

        if flipped:
            # When flipped, swap display positions
            draw.text((bearoff_text_x, o_bearoff_top + 12 * self.antialias_scale), x_text, fill=self.COLOR_TEXT, font=font)
            draw.text((bearoff_text_x, x_bearoff_top + 12 * self.antialias_scale), o_text, fill=self.COLOR_TEXT, font=font)
        else:
            draw.text((bearoff_text_x, x_bearoff_top + 12 * self.antialias_scale), x_text, fill=self.COLOR_TEXT, font=font)
            draw.text((bearoff_text_x, o_bearoff_top + 12 * self.antialias_scale), o_text, fill=self.COLOR_TEXT, font=font)

    def _flip_position(self, position: Position) -> Position:
        """
        Flip the board perspective (swap X and O).

        This is used to display the position from X's perspective when X is on roll.
        Point 1 becomes point 24, point 2 becomes point 23, etc.
        X checkers become O checkers and vice versa.

        Args:
            position: Original position

        Returns:
            Flipped position
        """
        flipped = Position()

        # Flip the board points (1->24, 2->23, etc.) and swap X/O
        for i in range(1, 25):
            flipped_point = 25 - i
            # Negate to swap X and O
            flipped.points[flipped_point] = -position.points[i]

        # Swap bar positions and negate
        flipped.points[0] = -position.points[25]  # X bar <- O bar
        flipped.points[25] = -position.points[0]  # O bar <- X bar

        # Swap borne-off checkers
        flipped.x_off = position.o_off
        flipped.o_off = position.x_off

        return flipped
