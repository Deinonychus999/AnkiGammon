"""Helper for generating GSAP-based checker movement animations."""

import re
from typing import List, Tuple, Dict, Optional
from flashgammon.models import Position, Move, Player
from flashgammon.utils.move_parser import MoveParser


class AnimationHelper:
    """Generates animation data and JavaScript for checker movements."""

    @staticmethod
    def parse_move_notation(notation: str, on_roll: Player) -> List[Tuple[int, int]]:
        """
        Parse backgammon move notation into (from_point, to_point) pairs.

        Args:
            notation: Move notation (e.g., "24/23 24/23" or "bar/24")
            on_roll: Player making the move

        Returns:
            List of (from_point, to_point) tuples (0-25, where 0=X bar, 25=O bar)
        """
        moves = []

        if not notation or notation == "Can't move":
            return moves

        # Split by spaces to get individual checker moves
        parts = notation.strip().split()

        for part in parts:
            if '/' not in part:
                continue

            # Check for repetition notation like "6/4(4)" meaning "move 4 checkers from 6 to 4"
            repetition_count = 1
            repetition_match = re.search(r'\((\d+)\)$', part)
            if repetition_match:
                repetition_count = int(repetition_match.group(1))
                # Remove the repetition notation from the part
                part = re.sub(r'\(\d+\)$', '', part)

            from_str, to_str = part.split('/')

            # Remove asterisk (hit indicator) from notation
            from_str = from_str.rstrip('*')
            to_str = to_str.rstrip('*')

            # Parse "from" point
            if from_str.lower() == 'bar':
                # Bar position depends on player
                from_point = 0 if on_roll == Player.X else 25
            elif from_str.lower() == 'off':
                # Bearing off - skip (no visual animation needed)
                continue
            else:
                try:
                    from_point = int(from_str)
                except ValueError:
                    continue

            # Parse "to" point
            if to_str.lower() == 'bar':
                # Opponent bar
                to_point = 25 if on_roll == Player.X else 0
            elif to_str.lower() == 'off':
                # Bearing off - use special marker (-1)
                to_point = -1
            else:
                try:
                    to_point = int(to_str)
                except ValueError:
                    continue

            # Add the move repetition_count times (handles notation like "6/4(4)")
            for _ in range(repetition_count):
                moves.append((from_point, to_point))

        return moves

    @staticmethod
    def generate_animation_javascript(
        move_notation: str,
        on_roll: Player,
        duration: float = 0.8,
        stagger: float = 0.05
    ) -> str:
        """
        Generate JavaScript code for animating a backgammon move using GSAP.

        Args:
            move_notation: Move notation string
            on_roll: Player making the move
            duration: Animation duration in seconds
            stagger: Stagger time between checkers in seconds

        Returns:
            JavaScript code string
        """
        moves = AnimationHelper.parse_move_notation(move_notation, on_roll)

        if not moves:
            return ""

        # Generate GSAP animation code
        js_code = f"""
<script src="https://cdn.jsdelivr.net/npm/gsap@3/dist/gsap.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/gsap@3/dist/MotionPathPlugin.min.js"></script>
<script>
if (typeof gsap !== 'undefined') {{
    gsap.registerPlugin(MotionPathPlugin);

    // Animation data
    const moves = {moves};
    const duration = {duration};
    const stagger = {stagger};

    // Animate checkers
    function animateMove() {{
        moves.forEach((move, index) => {{
            const [fromPoint, toPoint] = move;

            // Find checker at fromPoint
            const checkers = document.querySelectorAll('.checker[data-point="' + fromPoint + '"]');

            if (checkers.length > 0) {{
                const checker = checkers[0]; // Animate first checker at point

                // Calculate target position (simplified - would need actual point coordinates)
                // This is a placeholder - actual implementation would calculate SVG coordinates

                gsap.to(checker, {{
                    duration: duration,
                    delay: index * stagger,
                    attr: {{
                        cx: '+=100',  // Placeholder translation
                        cy: '+=0'
                    }},
                    ease: 'power2.inOut'
                }});
            }}
        }});
    }}

    // Optionally auto-play animation or add button to trigger
    // animateMove();
}}
</script>
"""
        return js_code

    @staticmethod
    def get_gsap_cdn_scripts() -> str:
        """
        Get GSAP CDN script tags.

        Returns:
            HTML script tags for GSAP and MotionPathPlugin
        """
        return """
<script src="https://cdn.jsdelivr.net/npm/gsap@3/dist/gsap.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/gsap@3/dist/MotionPathPlugin.min.js"></script>
"""

    @staticmethod
    def generate_animation_button() -> str:
        """
        Generate HTML for an animation trigger button.

        Returns:
            HTML button element
        """
        return """
<div style="text-align: center; margin: 10px 0;">
    <button onclick="animateCheckers()" class="toggle-btn">
        ▶ Animate Move
    </button>
</div>
"""
