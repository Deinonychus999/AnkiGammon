"""
Animation controller for backgammon checker movements.

Generates JavaScript code for animating checker movements using various strategies:
- Cross-fade: Simple opacity transition between positions
- Arc movement: GSAP-based arc animation of individual checkers
"""

import json
from typing import List, Tuple, Dict, Optional
from xg2anki.models import Position, Move, Player
from xg2anki.renderer.animation_helper import AnimationHelper


class AnimationController:
    """
    Orchestrates checker movement animations for Anki cards.

    This controller generates JavaScript code that animates transitions
    between backgammon positions using either simple cross-fade or
    sophisticated GSAP-based arc movements.
    """

    def __init__(
        self,
        board_width: int = 900,
        board_height: int = 600,
        point_height_ratio: float = 0.45
    ):
        """
        Initialize the animation controller.

        Args:
            board_width: SVG viewBox width (must match renderer)
            board_height: SVG viewBox height (must match renderer)
            point_height_ratio: Height of points as ratio of board height
        """
        self.board_width = board_width
        self.board_height = board_height
        self.point_height_ratio = point_height_ratio

        # Calculate board dimensions (match SVGBoardRenderer calculations)
        self.margin = 20
        self.cube_area_width = 70
        self.bearoff_area_width = 100

        self.playing_width = (
            self.board_width - 2 * self.margin -
            self.cube_area_width - self.bearoff_area_width
        )
        self.board_height_inner = self.board_height - 2 * self.margin

        self.bar_width = self.playing_width * 0.08
        self.half_width = (self.playing_width - self.bar_width) / 2
        self.point_width = self.half_width / 6
        self.point_height = self.board_height_inner * point_height_ratio

        self.checker_radius = min(self.point_width * 0.45, 25)

        # Board origin (matches SVGBoardRenderer)
        self.board_x = self.margin + self.cube_area_width
        self.board_y = self.margin

    def get_point_coordinates(self, point_num: int, checker_index: int = 0, player: Optional[Player] = None) -> Tuple[float, float]:
        """
        Calculate SVG coordinates for a checker on a specific point.

        Args:
            point_num: Point number (0=X bar, 1-24=board points, 25=O bar, -1=bear off)
            checker_index: Index of checker in stack (0=bottom, 1=next up, etc.)
            player: Player bearing off (required when point_num == -1)

        Returns:
            (x, y) coordinates in SVG space
        """
        # Handle bar positions
        if point_num == 0:  # X's bar (top)
            bar_x = self.board_x + self.half_width
            bar_center_x = bar_x + self.bar_width / 2
            y = self.board_y + self.point_height + checker_index * (self.checker_radius * 2 + 2)
            return (bar_center_x, y)

        if point_num == 25:  # O's bar (bottom)
            bar_x = self.board_x + self.half_width
            bar_center_x = bar_x + self.bar_width / 2
            y = (self.board_y + self.board_height_inner - self.point_height -
                 checker_index * (self.checker_radius * 2 + 2))
            return (bar_center_x, y)

        # Handle bear-off (special marker -1)
        if point_num == -1:
            # Return off-board position (will be animated to bear-off tray)
            # X-coordinate: center of bearoff area
            bearoff_x = self.board_x + self.playing_width + 50

            # Y-coordinate: bottom of appropriate tray where thin rectangles are drawn
            # (matches SVGBoardRenderer._draw_bearoff checker placement)
            checker_height = 50  # Must match SVGBoardRenderer

            if player == Player.X:
                # X uses top tray (not flipped)
                tray_bottom = self.board_y + self.board_height_inner / 2 - 10
                bearoff_y = tray_bottom - 10 - checker_height
            else:
                # O uses bottom tray (not flipped)
                tray_bottom = self.board_y + self.board_height_inner - 10
                bearoff_y = tray_bottom - 10 - checker_height

            return (bearoff_x, bearoff_y)

        # Handle regular board points (1-24)
        if point_num < 1 or point_num > 24:
            raise ValueError(f"Invalid point number: {point_num}")

        x, y_base, is_top = self._get_point_position(point_num)

        # Calculate checker position in stack
        if is_top:
            y = y_base + self.checker_radius + checker_index * (self.checker_radius * 2 + 2)
        else:
            y = y_base - self.checker_radius - checker_index * (self.checker_radius * 2 + 2)

        cx = x + self.point_width / 2

        return (cx, y)

    def _get_point_position(self, point_idx: int) -> Tuple[float, float, bool]:
        """
        Get the x, y position and orientation of a point.

        Returns:
            (x, y_base, is_top) where is_top indicates if point extends from top
        """
        if point_idx <= 6:
            x = self.board_x + self.half_width + self.bar_width + (6 - point_idx) * self.point_width
            y_base = self.board_y + self.board_height_inner
            is_top = False
        elif point_idx <= 12:
            x = self.board_x + (12 - point_idx) * self.point_width
            y_base = self.board_y + self.board_height_inner
            is_top = False
        elif point_idx <= 18:
            x = self.board_x + (point_idx - 13) * self.point_width
            y_base = self.board_y
            is_top = True
        else:
            x = self.board_x + self.half_width + self.bar_width + (point_idx - 19) * self.point_width
            y_base = self.board_y
            is_top = True

        return x, y_base, is_top

    def generate_animation_script(
        self,
        from_position: Position,
        to_position: Position,
        move_notation: str,
        on_roll: Player,
        animation_style: str = "arc",
        duration: float = 0.8,
        svg_id_original: str = "original-svg",
        svg_id_result: str = "result-svg"
    ) -> str:
        """
        Generate JavaScript for animating a move.

        Args:
            from_position: Starting position
            to_position: Ending position
            move_notation: Move notation (e.g., "24/23 24/23")
            on_roll: Player making the move
            animation_style: 'fade', 'arc', or 'none'
            duration: Animation duration in seconds
            svg_id_original: ID of original position SVG container
            svg_id_result: ID of result position SVG container

        Returns:
            JavaScript code as string
        """
        if animation_style == "none":
            return ""

        if animation_style == "fade":
            return self._generate_fade_animation(
                svg_id_original, svg_id_result, duration
            )

        if animation_style == "arc":
            return self._generate_arc_animation(
                from_position, to_position, move_notation, on_roll,
                duration, svg_id_original, svg_id_result
            )

        return ""

    def _generate_fade_animation(
        self,
        svg_id_original: str,
        svg_id_result: str,
        duration: float
    ) -> str:
        """Generate simple cross-fade animation JavaScript."""
        return f"""
// Cross-fade animation
function animatePositionTransition() {{
    const originalSvg = document.getElementById('{svg_id_original}');
    const resultSvg = document.getElementById('{svg_id_result}');

    if (!originalSvg || !resultSvg) return;

    // Set up initial state
    originalSvg.style.opacity = '1';
    originalSvg.style.transition = 'opacity {duration}s ease-in-out';
    resultSvg.style.opacity = '0';
    resultSvg.style.transition = 'opacity {duration}s ease-in-out';
    resultSvg.style.display = 'block';

    // Trigger fade
    setTimeout(() => {{
        originalSvg.style.opacity = '0';
        resultSvg.style.opacity = '1';
    }}, 50);

    // Clean up
    setTimeout(() => {{
        originalSvg.style.display = 'none';
    }}, {duration * 1000 + 100});
}}
"""

    def _generate_arc_animation(
        self,
        from_position: Position,
        to_position: Position,
        move_notation: str,
        on_roll: Player,
        duration: float,
        svg_id_original: str,
        svg_id_result: str
    ) -> str:
        """Generate GSAP-based arc animation JavaScript."""
        # Parse the move to get checker movements
        moves = AnimationHelper.parse_move_notation(move_notation, on_roll)

        if not moves:
            # Fall back to fade if no moves can be parsed
            return self._generate_fade_animation(svg_id_original, svg_id_result, duration)

        # Calculate movements with coordinates
        movements = []
        for from_point, to_point in moves:
            # Get checker stack index (always move top checker)
            checker_index = 0

            # Get start and end coordinates
            start_x, start_y = self.get_point_coordinates(from_point, checker_index)
            # For bearoff moves (to_point == -1), pass the player information
            end_x, end_y = self.get_point_coordinates(to_point, checker_index, player=on_roll if to_point == -1 else None)

            # Calculate control point for arc (parabolic curve)
            mid_x = (start_x + end_x) / 2
            mid_y = min(start_y, end_y) - 80  # Arc upward

            movements.append({
                'from_point': from_point,
                'to_point': to_point,
                'start': [start_x, start_y],
                'control': [mid_x, mid_y],
                'end': [end_x, end_y],
            })

        movements_json = json.dumps(movements)
        stagger = 0.05  # Delay between multiple checker animations

        return f"""
// GSAP arc animation
if (typeof gsap !== 'undefined') {{
    gsap.registerPlugin(MotionPathPlugin);

    const movements = {movements_json};
    const duration = {duration};
    const stagger = {stagger};

    function animatePositionTransition() {{
        const originalSvg = document.getElementById('{svg_id_original}');
        const resultSvg = document.getElementById('{svg_id_result}');

        if (!originalSvg || !resultSvg) return;

        // Clone the original SVG for animation
        const animSvg = originalSvg.cloneNode(true);
        animSvg.id = 'animation-svg';
        animSvg.style.position = 'absolute';
        animSvg.style.top = '0';
        animSvg.style.left = '0';
        animSvg.style.width = '100%';
        animSvg.style.height = '100%';

        originalSvg.parentNode.style.position = 'relative';
        originalSvg.parentNode.appendChild(animSvg);

        // Hide result initially
        resultSvg.style.opacity = '0';
        resultSvg.style.display = 'block';

        // Animate each checker movement
        const timeline = gsap.timeline({{
            onComplete: function() {{
                // Show final position
                resultSvg.style.transition = 'opacity 0.2s';
                resultSvg.style.opacity = '1';

                // Remove animation SVG
                setTimeout(() => {{
                    if (animSvg.parentNode) {{
                        animSvg.parentNode.removeChild(animSvg);
                    }}
                    originalSvg.style.display = 'none';
                }}, 200);
            }}
        }});

        movements.forEach((movement, index) => {{
            // Find checkers at from_point in the animation SVG
            const checkers = animSvg.querySelectorAll('.checker[data-point="' + movement.from_point + '"]');

            if (checkers.length > 0) {{
                const checker = checkers[0];  // Animate first (top) checker

                // Create path for arc movement
                const path = [
                    {{ x: movement.start[0], y: movement.start[1] }},
                    {{ x: movement.control[0], y: movement.control[1] }},
                    {{ x: movement.end[0], y: movement.end[1] }}
                ];

                timeline.to(checker, {{
                    duration: duration,
                    motionPath: {{
                        path: path,
                        type: 'soft',
                        autoRotate: false
                    }},
                    ease: 'power2.inOut'
                }}, index * stagger);
            }}
        }});
    }}
}} else {{
    // GSAP not available, fall back to fade
    function animatePositionTransition() {{
        const originalSvg = document.getElementById('{svg_id_original}');
        const resultSvg = document.getElementById('{svg_id_result}');

        if (!originalSvg || !resultSvg) return;

        originalSvg.style.transition = 'opacity {duration}s';
        resultSvg.style.transition = 'opacity {duration}s';
        resultSvg.style.display = 'block';
        resultSvg.style.opacity = '0';

        setTimeout(() => {{
            originalSvg.style.opacity = '0';
            resultSvg.style.opacity = '1';
        }}, 50);

        setTimeout(() => {{
            originalSvg.style.display = 'none';
        }}, {duration * 1000 + 100});
    }}
}}
"""

    def get_gsap_cdn_urls(self) -> List[str]:
        """
        Get GSAP CDN URLs for inclusion in card HTML.

        Returns:
            List of CDN URLs
        """
        return [
            "https://cdn.jsdelivr.net/npm/gsap@3/dist/gsap.min.js",
            "https://cdn.jsdelivr.net/npm/gsap@3/dist/MotionPathPlugin.min.js"
        ]

    def generate_trigger_button_html(
        self,
        button_text: str = "▶ Animate Move",
        button_class: str = "animate-btn"
    ) -> str:
        """
        Generate HTML for animation trigger button.

        Args:
            button_text: Text to display on button
            button_class: CSS class for button

        Returns:
            HTML string
        """
        return f"""
<div class="animation-controls" style="text-align: center; margin: 10px 0;">
    <button onclick="if(typeof animatePositionTransition === 'function') animatePositionTransition();"
            class="{button_class}">{button_text}</button>
</div>
"""
