"""SVG-based backgammon board renderer for animated cards."""

from typing import Optional, Tuple, List, Dict
import json

from ankigammon.models import Position, Player, CubeState, Move
from ankigammon.renderer.color_schemes import ColorScheme, CLASSIC


class SVGBoardRenderer:
    """Renders backgammon positions as SVG markup."""

    def __init__(
        self,
        width: int = 900,
        height: int = 600,
        point_height_ratio: float = 0.45,
        color_scheme: ColorScheme = CLASSIC,
        orientation: str = "counter-clockwise",
    ):
        """
        Initialize the SVG board renderer.

        Args:
            width: SVG viewBox width
            height: SVG viewBox height
            point_height_ratio: Height of points as ratio of board height
            color_scheme: ColorScheme object defining board colors
            orientation: Board orientation ("clockwise" or "counter-clockwise")
        """
        self.width = width
        self.height = height
        self.point_height_ratio = point_height_ratio
        self.color_scheme = color_scheme
        self.orientation = orientation

        # Calculate dimensions (same logic as PNG renderer)
        self.margin = 20
        self.cube_area_width = 70
        self.bearoff_area_width = 100

        self.playing_width = self.width - 2 * self.margin - self.cube_area_width - self.bearoff_area_width
        self.board_height = self.height - 2 * self.margin

        self.bar_width = self.playing_width * 0.08
        self.half_width = (self.playing_width - self.bar_width) / 2
        self.point_width = self.half_width / 6
        self.point_height = self.board_height * point_height_ratio

        self.checker_radius = min(self.point_width * 0.45, 25)

    def render_svg(
        self,
        position: Position,
        on_roll: Player = Player.O,
        dice: Optional[Tuple[int, int]] = None,
        dice_opacity: float = 1.0,
        cube_value: int = 1,
        cube_owner: CubeState = CubeState.CENTERED,
        move_data: Optional[Dict] = None,
    ) -> str:
        """
        Render a backgammon position as SVG.

        Args:
            position: The position to render
            on_roll: Which player is on roll
            dice: Dice values (if any)
            dice_opacity: Opacity for dice (0.0-1.0)
            cube_value: Doubling cube value
            cube_owner: Who owns the cube
            move_data: Optional move animation data (for animated cards)

        Returns:
            SVG markup string
        """
        svg_parts = []

        # Start SVG with viewBox
        svg_parts.append(f'<svg viewBox="0 0 {self.width} {self.height}" '
                        f'xmlns="http://www.w3.org/2000/svg" '
                        f'class="backgammon-board">')

        # Add styles
        svg_parts.append(self._generate_styles())

        # Board coordinates
        board_x = self.margin + self.cube_area_width
        board_y = self.margin

        # Draw full background (covers entire SVG viewBox)
        svg_parts.append(self._draw_full_background())

        # Draw board background
        svg_parts.append(self._draw_board_background(board_x, board_y))

        # Draw bar
        svg_parts.append(self._draw_bar(board_x, board_y))

        # Draw points
        svg_parts.append(self._draw_points(board_x, board_y))

        # Draw checkers
        flipped = False
        svg_parts.append(self._draw_checkers(position, board_x, board_y, flipped, move_data))

        # Draw bear-off trays
        svg_parts.append(self._draw_bearoff(position, board_x, board_y, flipped))

        # Draw dice
        if dice:
            svg_parts.append(self._draw_dice(dice, on_roll, board_x, board_y, dice_opacity))

        # Draw cube
        svg_parts.append(self._draw_cube(cube_value, cube_owner, board_x, board_y, flipped))

        # Draw pip counts
        svg_parts.append(self._draw_pip_counts(position, board_x, board_y, flipped))

        # Close SVG
        svg_parts.append('</svg>')

        return ''.join(svg_parts)

    def _generate_styles(self) -> str:
        """Generate CSS styles for the SVG."""
        return f"""
<defs>
    <style>
        .backgammon-board {{
            max-width: 100%;
            height: auto;
        }}
        .point {{
            stroke: {self.color_scheme.board_dark};
            stroke-width: 1;
        }}
        .checker {{
            stroke: {self.color_scheme.checker_border};
            stroke-width: 2;
        }}
        .checker-x {{
            fill: {self.color_scheme.checker_x};
        }}
        .checker-o {{
            fill: {self.color_scheme.checker_o};
        }}
        .checker-text {{
            font-family: Arial, sans-serif;
            font-weight: bold;
            text-anchor: middle;
            dominant-baseline: middle;
            pointer-events: none;
        }}
        .point-label {{
            font-family: Arial, sans-serif;
            font-size: 10px;
            fill: {self.color_scheme.text};
            text-anchor: middle;
        }}
        .pip-count {{
            font-family: Arial, sans-serif;
            font-size: 12px;
            fill: {self.color_scheme.text};
        }}
        .die {{
            fill: #FFFFFF;
            stroke: #000000;
            stroke-width: 2;
        }}
        .die-pip {{
            fill: #000000;
        }}
        .cube {{
            fill: #FFD700;
            stroke: #000000;
            stroke-width: 2;
        }}
        .cube-text {{
            font-family: Arial, sans-serif;
            font-size: 32px;
            font-weight: bold;
            fill: #000000;
            text-anchor: middle;
            dominant-baseline: middle;
        }}
        /* Animation support */
        .checker-animated {{
            transition: transform 0.8s ease-in-out;
        }}
    </style>
</defs>
"""

    def _draw_full_background(self) -> str:
        """Draw the full SVG background (covers entire viewBox)."""
        return f'''
<rect x="0" y="0" width="{self.width}" height="{self.height}"
      fill="{self.color_scheme.board_light}"/>
'''

    def _draw_board_background(self, board_x: float, board_y: float) -> str:
        """Draw the board background rectangle."""
        return f'''
<rect x="{board_x}" y="{board_y}"
      width="{self.playing_width}" height="{self.board_height}"
      fill="{self.color_scheme.board_light}"
      stroke="{self.color_scheme.board_dark}"
      stroke-width="3"/>
'''

    def _draw_bar(self, board_x: float, board_y: float) -> str:
        """Draw the center bar."""
        bar_x = board_x + self.half_width
        return f'''
<rect x="{bar_x}" y="{board_y}"
      width="{self.bar_width}" height="{self.board_height}"
      fill="{self.color_scheme.bar}"
      stroke="{self.color_scheme.board_dark}"
      stroke-width="2"/>
'''

    def _get_visual_point_index(self, point_num: int) -> int:
        """
        Map point number to visual position index based on orientation.

        Counter-clockwise (standard):
          Top: 13 14 15 16 17 18 | 19 20 21 22 23 24
          Bottom: 12 11 10 9 8 7 | 6 5 4 3 2 1

        Clockwise (horizontally mirrored):
          Top: 24 23 22 21 20 19 | 18 17 16 15 14 13
          Bottom: 1 2 3 4 5 6 | 7 8 9 10 11 12

        Args:
            point_num: Point number (1-24)

        Returns:
            Visual index for rendering (0-23)
        """
        if self.orientation == "clockwise":
            # Simple horizontal mirror
            if point_num <= 12:
                # Points 1-12: bottom row, mirror horizontally
                # Point 1 → visual 11, Point 12 → visual 0
                return 12 - point_num
            else:
                # Points 13-24: top row, both quadrants need reversal
                # Point 13 → visual 23, Point 18 → visual 18
                # Point 19 → visual 17, Point 24 → visual 12
                return 36 - point_num
        else:
            # Counter-clockwise: standard layout
            return point_num - 1

    def _draw_points(self, board_x: float, board_y: float) -> str:
        """Draw the triangular points with numbers."""
        svg_parts = ['<g class="points">']

        # Iterate through all point numbers (1-24)
        for point_num in range(1, 25):
            # Get visual position for this point
            visual_idx = self._get_visual_point_index(point_num)

            # Determine point position based on visual index
            if visual_idx < 6:
                # Bottom right quadrant (visual positions 0-5)
                x = board_x + self.half_width + self.bar_width + (5 - visual_idx) * self.point_width
                y_base = board_y + self.board_height
                y_tip = y_base - self.point_height
                color = self.color_scheme.point_dark if point_num % 2 == 1 else self.color_scheme.point_light
                label_y = y_base + 13
            elif visual_idx < 12:
                # Bottom left quadrant (visual positions 6-11)
                x = board_x + (11 - visual_idx) * self.point_width
                y_base = board_y + self.board_height
                y_tip = y_base - self.point_height
                color = self.color_scheme.point_dark if point_num % 2 == 1 else self.color_scheme.point_light
                label_y = y_base + 13
            elif visual_idx < 18:
                # Top left quadrant (visual positions 12-17)
                x = board_x + (visual_idx - 12) * self.point_width
                y_base = board_y
                y_tip = y_base + self.point_height
                color = self.color_scheme.point_dark if point_num % 2 == 1 else self.color_scheme.point_light
                label_y = y_base - 5
            else:
                # Top right quadrant (visual positions 18-23)
                x = board_x + self.half_width + self.bar_width + (visual_idx - 18) * self.point_width
                y_base = board_y
                y_tip = y_base + self.point_height
                color = self.color_scheme.point_dark if point_num % 2 == 1 else self.color_scheme.point_light
                label_y = y_base - 5

            # Draw triangle
            x_mid = x + self.point_width / 2
            svg_parts.append(f'''
<polygon class="point" points="{x},{y_base} {x + self.point_width},{y_base} {x_mid},{y_tip}"
         fill="{color}"/>
''')

            # Draw point number
            svg_parts.append(f'''
<text class="point-label" x="{x_mid}" y="{label_y}">{point_num}</text>
''')

        svg_parts.append('</g>')
        return ''.join(svg_parts)

    def _draw_checkers(
        self,
        position: Position,
        board_x: float,
        board_y: float,
        flipped: bool,
        move_data: Optional[Dict] = None
    ) -> str:
        """Draw checkers on the board with optional animation data."""
        svg_parts = ['<g class="checkers">']

        for point_idx in range(1, 25):
            count = position.points[point_idx]
            if count == 0:
                continue

            player = Player.X if count > 0 else Player.O
            num_checkers = abs(count)

            # Get point position
            x, y_base, is_top = self._get_point_position(point_idx, board_x, board_y)

            # Draw checkers
            for checker_num in range(min(num_checkers, 5)):
                if is_top:
                    y = y_base + self.checker_radius + checker_num * (self.checker_radius * 2 + 2)
                else:
                    y = y_base - self.checker_radius - checker_num * (self.checker_radius * 2 + 2)

                cx = x + self.point_width / 2

                # Add animation data attributes
                checker_attrs = f'data-point="{point_idx}" data-checker-index="{checker_num}"'
                if move_data:
                    checker_attrs += f' data-move-info=\'{json.dumps(move_data)}\''

                svg_parts.append(
                    self._draw_checker(cx, y, player, checker_attrs)
                )

            # If more than 5 checkers, draw a number on the last one
            if num_checkers > 5:
                if is_top:
                    y = y_base + self.checker_radius + 4 * (self.checker_radius * 2 + 2)
                else:
                    y = y_base - self.checker_radius - 4 * (self.checker_radius * 2 + 2)

                cx = x + self.point_width / 2
                checker_attrs = f'data-point="{point_idx}" data-checker-index="4"'
                svg_parts.append(
                    self._draw_checker_with_number(cx, y, player, num_checkers, checker_attrs)
                )

        # Draw bar checkers
        svg_parts.append(self._draw_bar_checkers(position, board_x, board_y, flipped))

        svg_parts.append('</g>')
        return ''.join(svg_parts)

    def _draw_checker(self, cx: float, cy: float, player: Player, extra_attrs: str = "") -> str:
        """Draw a single checker."""
        player_class = "checker-x" if player == Player.X else "checker-o"
        return f'''
<circle class="checker {player_class}" cx="{cx}" cy="{cy}" r="{self.checker_radius}" {extra_attrs}/>
'''

    def _draw_checker_with_number(self, cx: float, cy: float, player: Player, number: int, extra_attrs: str = "") -> str:
        """Draw a checker with a number on it."""
        player_class = "checker-x" if player == Player.X else "checker-o"
        text_color = (self.color_scheme.checker_o if player == Player.X
                     else self.color_scheme.checker_x)

        return f'''
<circle class="checker {player_class}" cx="{cx}" cy="{cy}" r="{self.checker_radius}" {extra_attrs}/>
<text class="checker-text" x="{cx}" y="{cy}"
      font-size="{self.checker_radius * 1.2}" fill="{text_color}">{number}</text>
'''

    def _draw_bar_checkers(
        self,
        position: Position,
        board_x: float,
        board_y: float,
        flipped: bool
    ) -> str:
        """Draw checkers on the bar."""
        svg_parts = []
        bar_x = board_x + self.half_width
        bar_center_x = bar_x + self.bar_width / 2

        x_bar_count = max(position.points[0], 0)
        o_bar_count = max(-position.points[25], 0)

        if not flipped:
            svg_parts.append(
                self._draw_bar_stack(bar_center_x, x_bar_count, Player.X, True, board_y)
            )
            svg_parts.append(
                self._draw_bar_stack(bar_center_x, o_bar_count, Player.O, False, board_y)
            )
        else:
            svg_parts.append(
                self._draw_bar_stack(bar_center_x, x_bar_count, Player.X, False, board_y)
            )
            svg_parts.append(
                self._draw_bar_stack(bar_center_x, o_bar_count, Player.O, True, board_y)
            )

        return ''.join(svg_parts)

    def _draw_bar_stack(
        self,
        center_x: float,
        count: int,
        player: Player,
        top: bool,
        board_y: float
    ) -> str:
        """Draw stacked checkers on the bar for a single player."""
        if count <= 0:
            return ""

        svg_parts = []
        max_visible = min(count, 3)

        # Bar point: 0 for X (top), 25 for O (bottom)
        bar_point = 0 if player == Player.X else 25

        # Calculate starting Y position - start from center and go outward
        board_center_y = board_y + self.board_height / 2
        # Add extra spacing to separate the two players more
        separation_offset = self.checker_radius * 2 + 10

        for i in range(max_visible):
            if top:
                # X checkers: start below center, stack toward bottom
                y = board_center_y + separation_offset + i * (self.checker_radius * 2 + 2)
            else:
                # O checkers: start above center, stack toward top
                y = board_center_y - separation_offset - i * (self.checker_radius * 2 + 2)

            # Add data attributes for animation
            checker_attrs = f'data-point="{bar_point}" data-checker-index="{i}"'

            if i == max_visible - 1 and count > max_visible:
                # Last visible checker - show count
                svg_parts.append(
                    self._draw_checker_with_number(center_x, y, player, count, checker_attrs)
                )
            else:
                svg_parts.append(
                    self._draw_checker(center_x, y, player, checker_attrs)
                )

        return ''.join(svg_parts)

    def _draw_bearoff(
        self,
        position: Position,
        board_x: float,
        board_y: float,
        flipped: bool
    ) -> str:
        """Draw bear-off trays with stacked checker representations."""
        svg_parts = ['<g class="bearoff">']

        bearoff_x = board_x + self.playing_width + 10
        bearoff_width = self.bearoff_area_width - 20

        checker_width = 10
        checker_height = 50
        checker_spacing_x = 3
        checker_spacing_y = 4
        checkers_per_row = 5

        top_player = Player.X if not flipped else Player.O
        bottom_player = Player.O if not flipped else Player.X

        def get_off_count(player: Player) -> int:
            if player == Player.X:
                return max(position.x_off, 0)
            return max(position.o_off, 0)

        def get_color(player: Player) -> str:
            return self.color_scheme.checker_x if player == Player.X else self.color_scheme.checker_o

        # Top tray
        tray_top = board_y + 10
        tray_bottom = board_y + self.board_height / 2 - 10

        svg_parts.append(f'''
<rect x="{bearoff_x}" y="{tray_top}"
      width="{bearoff_width}" height="{tray_bottom - tray_top}"
      fill="{self.color_scheme.bearoff}"
      stroke="{self.color_scheme.board_dark}"
      stroke-width="2"/>
''')

        # Draw stacked checkers for top player
        top_count = get_off_count(top_player)
        if top_count > 0:
            row_width = checkers_per_row * checker_width + (checkers_per_row - 1) * checker_spacing_x
            start_x = bearoff_x + (bearoff_width - row_width) / 2
            start_y = tray_bottom - 10 - checker_height

            for i in range(top_count):
                row = i // checkers_per_row
                col = i % checkers_per_row
                x = start_x + col * (checker_width + checker_spacing_x)
                y = start_y - row * (checker_height + checker_spacing_y)

                svg_parts.append(f'''
<rect x="{x}" y="{y}"
      width="{checker_width}" height="{checker_height}"
      fill="{get_color(top_player)}"
      stroke="{self.color_scheme.checker_border}"
      stroke-width="1"/>
''')

        # Bottom tray
        tray_top = board_y + self.board_height / 2 + 10
        tray_bottom = board_y + self.board_height - 10

        svg_parts.append(f'''
<rect x="{bearoff_x}" y="{tray_top}"
      width="{bearoff_width}" height="{tray_bottom - tray_top}"
      fill="{self.color_scheme.bearoff}"
      stroke="{self.color_scheme.board_dark}"
      stroke-width="2"/>
''')

        # Draw stacked checkers for bottom player
        bottom_count = get_off_count(bottom_player)
        if bottom_count > 0:
            row_width = checkers_per_row * checker_width + (checkers_per_row - 1) * checker_spacing_x
            start_x = bearoff_x + (bearoff_width - row_width) / 2
            start_y = tray_bottom - 10 - checker_height

            for i in range(bottom_count):
                row = i // checkers_per_row
                col = i % checkers_per_row
                x = start_x + col * (checker_width + checker_spacing_x)
                y = start_y - row * (checker_height + checker_spacing_y)

                svg_parts.append(f'''
<rect x="{x}" y="{y}"
      width="{checker_width}" height="{checker_height}"
      fill="{get_color(bottom_player)}"
      stroke="{self.color_scheme.checker_border}"
      stroke-width="1"/>
''')

        svg_parts.append('</g>')
        return ''.join(svg_parts)

    def _draw_dice(
        self,
        dice: Tuple[int, int],
        on_roll: Player,
        board_x: float,
        board_y: float,
        opacity: float = 1.0
    ) -> str:
        """Draw dice with optional transparency."""
        svg_parts = ['<g class="dice"']
        if opacity < 1.0:
            svg_parts.append(f' opacity="{opacity}"')
        svg_parts.append('>')

        die_size = 50
        die_spacing = 15

        # Position dice on the right half of the board
        total_dice_width = 2 * die_size + die_spacing
        right_half_start = board_x + self.half_width + self.bar_width
        die_x = right_half_start + (self.half_width - total_dice_width) / 2
        die_y = board_y + (self.board_height - die_size) / 2

        svg_parts.append(self._draw_die(die_x, die_y, die_size, dice[0]))
        svg_parts.append(self._draw_die(die_x + die_size + die_spacing, die_y, die_size, dice[1]))

        svg_parts.append('</g>')
        return ''.join(svg_parts)

    def _draw_die(self, x: float, y: float, size: float, value: int) -> str:
        """Draw a single die."""
        svg_parts = [f'''
<rect class="die" x="{x}" y="{y}" width="{size}" height="{size}" rx="5"/>
''']

        # Draw pips
        pip_radius = size / 10
        center = size / 2

        pip_positions = {
            1: [(center, center)],
            2: [(size / 4, size / 4), (3 * size / 4, 3 * size / 4)],
            3: [(size / 4, size / 4), (center, center), (3 * size / 4, 3 * size / 4)],
            4: [(size / 4, size / 4), (3 * size / 4, size / 4),
                (size / 4, 3 * size / 4), (3 * size / 4, 3 * size / 4)],
            5: [(size / 4, size / 4), (3 * size / 4, size / 4),
                (center, center),
                (size / 4, 3 * size / 4), (3 * size / 4, 3 * size / 4)],
            6: [(size / 4, size / 4), (3 * size / 4, size / 4),
                (size / 4, center), (3 * size / 4, center),
                (size / 4, 3 * size / 4), (3 * size / 4, 3 * size / 4)],
        }

        for px, py in pip_positions.get(value, []):
            svg_parts.append(f'''
<circle class="die-pip" cx="{x + px}" cy="{y + py}" r="{pip_radius}"/>
''')

        return ''.join(svg_parts)

    def _draw_cube(
        self,
        cube_value: int,
        cube_owner: CubeState,
        board_x: float,
        board_y: float,
        flipped: bool
    ) -> str:
        """Draw the doubling cube."""
        cube_size = 50

        cube_area_x = self.margin + 10
        cube_area_center = cube_area_x + (self.cube_area_width - 20) / 2

        # Position cube based on owner
        if cube_owner == CubeState.CENTERED:
            cube_x = cube_area_center - cube_size / 2
            cube_y = board_y + (self.board_height - cube_size) / 2
        elif cube_owner == CubeState.O_OWNS:
            cube_x = cube_area_center - cube_size / 2
            cube_y = board_y + self.board_height - cube_size - 10 if not flipped else board_y + 10
        else:  # X_OWNS
            cube_x = cube_area_center - cube_size / 2
            cube_y = board_y + 10 if not flipped else board_y + self.board_height - cube_size - 10

        # Draw cube
        text = "64" if cube_owner == CubeState.CENTERED else str(cube_value)

        return f'''
<g class="cube">
    <rect class="cube" x="{cube_x}" y="{cube_y}"
          width="{cube_size}" height="{cube_size}" rx="3"/>
    <text class="cube-text" x="{cube_x + cube_size / 2}" y="{cube_y + cube_size / 2}">{text}</text>
</g>
'''

    def _draw_pip_counts(
        self,
        position: Position,
        board_x: float,
        board_y: float,
        flipped: bool
    ) -> str:
        """Draw pip counts for both players."""
        x_pips = self._calculate_pip_count(position, Player.X)
        o_pips = self._calculate_pip_count(position, Player.O)

        bearoff_text_x = board_x + self.playing_width + 15
        x_bearoff_top = board_y + 10 + 12
        o_bearoff_top = board_y + self.board_height / 2 + 10 + 12

        if flipped:
            return f'''
<g class="pip-counts">
    <text class="pip-count" x="{bearoff_text_x}" y="{o_bearoff_top}">Pip: {x_pips}</text>
    <text class="pip-count" x="{bearoff_text_x}" y="{x_bearoff_top}">Pip: {o_pips}</text>
</g>
'''
        else:
            return f'''
<g class="pip-counts">
    <text class="pip-count" x="{bearoff_text_x}" y="{x_bearoff_top}">Pip: {x_pips}</text>
    <text class="pip-count" x="{bearoff_text_x}" y="{o_bearoff_top}">Pip: {o_pips}</text>
</g>
'''

    def _get_point_position(self, point_idx: int, board_x: float, board_y: float) -> Tuple[float, float, bool]:
        """
        Get the x, y position and orientation of a point.

        Returns:
            (x, y_base, is_top) where is_top indicates if point extends from top
        """
        if point_idx < 1 or point_idx > 24:
            raise ValueError(f"Invalid point index: {point_idx}")

        # Get visual position based on orientation
        visual_idx = self._get_visual_point_index(point_idx)

        # Calculate position based on visual index
        if visual_idx < 6:
            # Bottom right quadrant (visual positions 0-5)
            x = board_x + self.half_width + self.bar_width + (5 - visual_idx) * self.point_width
            y_base = board_y + self.board_height
            is_top = False
        elif visual_idx < 12:
            # Bottom left quadrant (visual positions 6-11)
            x = board_x + (11 - visual_idx) * self.point_width
            y_base = board_y + self.board_height
            is_top = False
        elif visual_idx < 18:
            # Top left quadrant (visual positions 12-17)
            x = board_x + (visual_idx - 12) * self.point_width
            y_base = board_y
            is_top = True
        else:
            # Top right quadrant (visual positions 18-23)
            x = board_x + self.half_width + self.bar_width + (visual_idx - 18) * self.point_width
            y_base = board_y
            is_top = True

        return x, y_base, is_top

    def _calculate_pip_count(self, position: Position, player: Player) -> int:
        """Calculate pip count for a player."""
        pip_count = 0

        if player == Player.X:
            for point_idx in range(1, 25):
                if position.points[point_idx] > 0:
                    x_pip_distance = 25 - point_idx
                    pip_count += x_pip_distance * position.points[point_idx]
            if position.points[0] > 0:
                pip_count += 25 * position.points[0]
        else:
            for point_idx in range(1, 25):
                if position.points[point_idx] < 0:
                    o_pip_distance = point_idx
                    pip_count += o_pip_distance * abs(position.points[point_idx])
            if position.points[25] < 0:
                pip_count += 25 * abs(position.points[25])

        return pip_count
