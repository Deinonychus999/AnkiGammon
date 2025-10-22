"""Generate Anki card content from XG decisions."""

import json
import random
import string
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from flashgammon.models import Decision, Move, Player
from flashgammon.renderer.svg_board_renderer import SVGBoardRenderer
from flashgammon.renderer.animation_controller import AnimationController
from flashgammon.utils.move_parser import MoveParser
from flashgammon.settings import get_settings


class CardGenerator:
    """
    Generates Anki card content from XG decisions.

    Supports two variants:
    1. Simple: Shows question only (no options)
    2. Text MCQ: Shows move notation as text options
    """

    def __init__(
        self,
        output_dir: Path,
        show_options: bool = False,
        interactive_moves: bool = False,
        renderer: Optional[SVGBoardRenderer] = None,
        animation_controller: Optional[AnimationController] = None,
        progress_callback: Optional[callable] = None
    ):
        """
        Initialize the card generator.

        Args:
            output_dir: Directory for configuration (no media files needed with SVG)
            show_options: If True, show interactive MCQ with clickable options
            interactive_moves: If True, render positions for all moves (clickable analysis)
            renderer: SVG board renderer instance (creates default if None)
            animation_controller: Animation controller instance (creates default if None)
            progress_callback: Optional callback(message: str) for progress updates
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.show_options = show_options
        self.interactive_moves = interactive_moves
        self.renderer = renderer or SVGBoardRenderer()
        self.animation_controller = animation_controller or AnimationController()
        self.settings = get_settings()
        self.progress_callback = progress_callback

    def generate_card(self, decision: Decision, card_id: Optional[str] = None) -> Dict[str, any]:
        """
        Generate an Anki card from a decision.

        Args:
            decision: The decision to create a card for
            card_id: Optional card ID (generated if not provided)

        Returns:
            Dictionary with card data:
            {
                'front': HTML for card front,
                'back': HTML for card back,
                'tags': List of tags
            }
        """
        if card_id is None:
            card_id = self._generate_id()

        # Validate that we have candidate moves to generate a card
        if not decision.candidate_moves:
            raise ValueError(
                "Cannot generate card: decision has no candidate moves. "
                "For XGID-only input, please use GnuBG analysis to populate moves."
            )

        # Generate position SVG (before move)
        position_svg = self._render_position_svg(decision)

        # Prepare candidate moves
        from flashgammon.models import DecisionType

        if decision.decision_type == DecisionType.CUBE_ACTION:
            candidates = decision.candidate_moves[:5]
        else:
            candidates = decision.candidate_moves[:5]

        # Shuffle candidates for MCQ
        shuffled_candidates, answer_index = self._shuffle_candidates(candidates)

        # Generate card front
        if self.show_options:
            front_html = self._generate_interactive_mcq_front(
                decision, position_svg, shuffled_candidates
            )
        else:
            front_html = self._generate_simple_front(
                decision, position_svg
            )

        # Generate resulting position SVGs
        move_result_svgs = {}
        best_move = decision.get_best_move()

        if not self.interactive_moves:
            # Only render the best move's resulting position (no animation)
            if best_move:
                result_svg = self._render_resulting_position_svg(decision, best_move)
            else:
                result_svg = None
        else:
            # Interactive mode: generate result SVGs for all moves (for proper number display)
            if self.progress_callback:
                self.progress_callback(f"Rendering board positions...")
            for candidate in candidates:
                if candidate:
                    result_svg_for_move = self._render_resulting_position_svg(decision, candidate)
                    move_result_svgs[candidate.notation] = result_svg_for_move
            result_svg = None

        # Generate card back
        if self.progress_callback:
            self.progress_callback("Generating card content...")
        back_html = self._generate_back(
            decision, position_svg, result_svg, candidates, shuffled_candidates,
            answer_index, self.show_options, move_result_svgs
        )

        # Generate tags
        tags = self._generate_tags(decision)

        return {
            'front': front_html,
            'back': back_html,
            'tags': tags,
        }

    def _get_metadata_html(self, decision: Decision) -> str:
        """
        Get metadata HTML with colored player indicator.

        Returns HTML with inline colored circle representing the checker color.
        """
        base_metadata = decision.get_metadata_text()

        # Get actual checker color from the renderer's color scheme
        if decision.on_roll == Player.X:
            checker_color = self.renderer.color_scheme.checker_x
        else:
            checker_color = self.renderer.color_scheme.checker_o

        # Replace "White" or "Black" with colored circle
        colored_circle = f'<span style="color: {checker_color}; font-size: 1.8em;">●</span>'

        if decision.on_roll == Player.X:
            metadata_html = base_metadata.replace("White", colored_circle)
        else:
            metadata_html = base_metadata.replace("Black", colored_circle)

        return metadata_html

    def _generate_simple_front(
        self,
        decision: Decision,
        position_svg: str
    ) -> str:
        """Generate HTML for simple front (no options)."""
        metadata = self._get_metadata_html(decision)

        html = f"""
<div class="card-front">
    <div class="position-svg">
        {position_svg}
    </div>
    <div class="metadata">{metadata}</div>
    <div class="question">
        <h3>What is the best move?</h3>
    </div>
</div>
"""
        return html

    def _generate_interactive_mcq_front(
        self,
        decision: Decision,
        position_svg: str,
        candidates: List[Optional[Move]]
    ) -> str:
        """Generate interactive quiz MCQ front with clickable options."""
        metadata = self._get_metadata_html(decision)
        letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J']

        # Build clickable options
        options_html = []
        for i, candidate in enumerate(candidates):
            if candidate:
                options_html.append(f"""
<div class='mcq-option' data-option-letter='{letters[i]}'>
    <strong>{letters[i]}.</strong> {candidate.notation}
</div>
""")

        html = f"""
<div class="card-front interactive-mcq-front">
    <div class="position-svg">
        {position_svg}
    </div>
    <div class="metadata">{metadata}</div>
    <div class="question">
        <h3>What is the best move?</h3>
        <div class="mcq-options">
            {''.join(options_html)}
        </div>
        <p class="mcq-hint">Click an option to see if you're correct</p>
    </div>
</div>

<script>
{self._generate_mcq_front_javascript()}
</script>
"""
        return html

    def _generate_mcq_front_javascript(self) -> str:
        """Generate JavaScript for interactive MCQ front side."""
        return """
(function() {
    const options = document.querySelectorAll('.mcq-option');

    options.forEach(option => {
        option.addEventListener('click', function() {
            const selectedLetter = this.dataset.optionLetter;

            // Store selection in sessionStorage
            try {
                sessionStorage.setItem('flashgammon-mcq-choice', selectedLetter);
            } catch (e) {
                window.location.hash = 'choice-' + selectedLetter;
            }

            // Visual feedback before flip
            this.classList.add('selected-flash');

            // Trigger Anki flip to back side
            setTimeout(function() {
                if (typeof pycmd !== 'undefined') {
                    pycmd('ans');  // Anki desktop
                } else if (typeof AnkiDroidJS !== 'undefined') {
                    AnkiDroidJS.ankiShowAnswer();  // AnkiDroid
                } else {
                    const event = new KeyboardEvent('keydown', { keyCode: 32 });
                    document.dispatchEvent(event);
                }
            }, 200);
        });
    });
})();
"""

    def _generate_mcq_back_javascript(self, correct_letter: str) -> str:
        """Generate JavaScript for interactive MCQ back side."""
        return f"""
<script>
(function() {{
    let selectedLetter = null;

    try {{
        selectedLetter = sessionStorage.getItem('flashgammon-mcq-choice');
        sessionStorage.removeItem('flashgammon-mcq-choice');
    }} catch (e) {{
        const hash = window.location.hash;
        if (hash.startsWith('#choice-')) {{
            selectedLetter = hash.replace('#choice-', '');
            window.location.hash = '';
        }}
    }}

    const correctLetter = '{correct_letter}';
    const feedbackContainer = document.getElementById('mcq-feedback');
    const standardAnswer = document.getElementById('mcq-standard-answer');

    let moveMap = {{}};
    let errorMap = {{}};
    if (standardAnswer && standardAnswer.dataset.moveMap) {{
        try {{
            moveMap = JSON.parse(standardAnswer.dataset.moveMap);
        }} catch (e) {{}}
    }}
    if (standardAnswer && standardAnswer.dataset.errorMap) {{
        try {{
            errorMap = JSON.parse(standardAnswer.dataset.errorMap);
        }} catch (e) {{}}
    }}

    if (selectedLetter) {{
        feedbackContainer.style.display = 'block';
        if (standardAnswer) standardAnswer.style.display = 'none';

        const selectedMove = moveMap[selectedLetter] || '';
        const correctMove = moveMap[correctLetter] || '';
        const selectedError = errorMap[selectedLetter] || 0.0;

        const CLOSE_THRESHOLD = 0.020;

        if (selectedLetter === correctLetter) {{
            feedbackContainer.innerHTML = `
                <div class="mcq-feedback-correct">
                    <div class="feedback-icon">✓</div>
                    <div class="feedback-text">
                        <strong>${{selectedLetter}} is Correct!</strong>
                    </div>
                </div>
            `;
        }} else if (selectedError < CLOSE_THRESHOLD) {{
            feedbackContainer.innerHTML = `
                <div class="mcq-feedback-close">
                    <div class="feedback-icon">≈</div>
                    <div class="feedback-text">
                        <strong>${{selectedLetter}} is Close!</strong> (${{selectedMove}}) <span class="feedback-separator">•</span> <strong>Best: ${{correctLetter}}</strong> (${{correctMove}})
                    </div>
                </div>
            `;
        }} else {{
            feedbackContainer.innerHTML = `
                <div class="mcq-feedback-incorrect">
                    <div class="feedback-icon">✗</div>
                    <div class="feedback-text">
                        <strong>${{selectedLetter}} is Incorrect</strong> (${{selectedMove}}) <span class="feedback-separator">•</span> <strong>Correct: ${{correctLetter}}</strong> (${{correctMove}})
                    </div>
                </div>
            `;
        }}

        const moveRows = document.querySelectorAll('.moves-table tbody tr');
        moveRows.forEach(row => {{
            const moveCell = row.cells[1];
            if (moveCell) {{
                const moveText = moveCell.textContent.trim();
                if (moveText === selectedMove) {{
                    if (selectedLetter === correctLetter) {{
                        row.classList.add('user-correct');
                    }} else if (selectedError < CLOSE_THRESHOLD) {{
                        row.classList.add('user-close');
                    }} else {{
                        row.classList.add('user-incorrect');
                    }}
                }}
            }}
        }});
    }} else {{
        feedbackContainer.style.display = 'none';
    }}
}})();
</script>
"""

    def _generate_back(
        self,
        decision: Decision,
        original_position_svg: str,
        result_position_svg: str,
        candidates: List[Optional[Move]],
        shuffled_candidates: List[Optional[Move]],
        answer_index: int,
        show_options: bool,
        move_result_svgs: Dict[str, str] = None
    ) -> str:
        """Generate HTML for card back."""
        metadata = self._get_metadata_html(decision)

        # Build move table
        table_rows = []
        letters = ['A', 'B', 'C', 'D', 'E']

        sorted_candidates = sorted(
            [m for m in candidates if m and m.from_xg_analysis],
            key=lambda m: m.xg_rank if m.xg_rank is not None else 999
        )

        for i, move in enumerate(sorted_candidates):
            rank_class = "best-move" if move.rank == 1 else ""
            display_rank = move.xg_rank if move.xg_rank is not None else (i + 1)
            display_error = move.xg_error if move.xg_error is not None else move.error
            display_notation = move.xg_notation if move.xg_notation is not None else move.notation

            error_str = f"{display_error:+.3f}" if display_error != 0 else "0.000"

            # Prepare W/G/B data attributes
            wgb_attrs = ""
            if move.player_win_pct is not None:
                wgb_attrs = (
                    f'data-player-win="{move.player_win_pct:.2f}" '
                    f'data-player-gammon="{move.player_gammon_pct:.2f}" '
                    f'data-player-backgammon="{move.player_backgammon_pct:.2f}" '
                    f'data-opponent-win="{move.opponent_win_pct:.2f}" '
                    f'data-opponent-gammon="{move.opponent_gammon_pct:.2f}" '
                    f'data-opponent-backgammon="{move.opponent_backgammon_pct:.2f}"'
                )

            if self.interactive_moves:
                row_class = f"{rank_class} move-row clickable-move-row"
                row_attrs = f'data-move-notation="{move.notation}" {wgb_attrs}'
            else:
                row_class = f"{rank_class} clickable-move-row"
                row_attrs = wgb_attrs

            # Generate inline W/G/B display
            wgb_inline_html = self._format_wgb_inline(move, decision)

            table_rows.append(f"""
<tr class="{row_class}" {row_attrs}>
    <td>{display_rank}</td>
    <td>
        <div class="move-notation">{display_notation}</div>{wgb_inline_html}
    </td>
    <td>{move.equity:.3f}</td>
    <td>{error_str}</td>
</tr>""")

        # Generate answer section
        best_move = decision.get_best_move()
        best_notation = best_move.notation if best_move else "Unknown"

        if show_options:
            correct_letter = letters[answer_index] if answer_index < len(letters) else "?"

            import json
            letter_to_move = {}
            letter_to_error = {}
            for i, move in enumerate(shuffled_candidates):
                if move and i < len(letters):
                    letter_to_move[letters[i]] = move.notation
                    letter_to_error[letters[i]] = abs(move.error) if move.error is not None else 0.0

            answer_html = f"""
    <div class="mcq-feedback-container" id="mcq-feedback" style="display: none;">
    </div>
    <div class="answer" id="mcq-standard-answer" data-correct-answer="{correct_letter}" data-move-map='{json.dumps(letter_to_move)}' data-error-map='{json.dumps(letter_to_error)}'>
        <h3>Correct Answer: <span class="answer-letter">{correct_letter}</span></h3>
        <p class="best-move-notation">{best_notation}</p>
    </div>
"""
        else:
            answer_html = f"""
    <div class="answer">
        <h3>Best Move:</h3>
        <p class="best-move-notation">{best_notation}</p>
    </div>
"""

        # Generate position viewer HTML
        from flashgammon.models import DecisionType
        is_cube_decision = decision.decision_type == DecisionType.CUBE_ACTION

        if self.interactive_moves:
            # Interactive mode: single board with animated checkers
            position_viewer_html = f'''
    <div class="position-viewer">
        <div class="position-svg-animated" id="animated-board">
            {original_position_svg}
        </div>
    </div>'''
            # Change title and hide animation tip for cube decisions
            if is_cube_decision:
                analysis_title = '<h4>Cube Actions Analysis:</h4>'
            else:
                analysis_title = '<h4>Top Moves Analysis: <span class="click-hint">(click a move to see it animated)</span></h4>'
            table_body_id = 'id="moves-tbody"'
        else:
            position_viewer_html = f'''
    <div class="position-svg">
        {result_position_svg or original_position_svg}
    </div>'''
            # Change title for cube decisions
            if is_cube_decision:
                analysis_title = '<h4>Cube Actions Analysis:</h4>'
            else:
                analysis_title = '<h4>Top Moves Analysis:</h4>'
            table_body_id = ''

        # Generate winning chances HTML for cube decisions
        winning_chances_html = ''
        if is_cube_decision and decision.player_win_pct is not None:
            winning_chances_html = self._generate_winning_chances_html(decision)

        # For cube decisions with W/G/B, create side-by-side layout
        if is_cube_decision and winning_chances_html:
            analysis_and_chances = f"""
    <div class="analysis-container">
        <div class="analysis-section">
            {analysis_title}
            <table class="moves-table">
                <thead>
                    <tr>
                        <th>Rank</th>
                        <th>Move</th>
                        <th>Equity</th>
                        <th>Error</th>
                    </tr>
                </thead>
                <tbody {table_body_id}>
                    {''.join(table_rows)}
                </tbody>
            </table>
        </div>
        <div class="chances-section">
            <h4>Winning Chances:</h4>
{winning_chances_html}
        </div>
    </div>
"""
        else:
            analysis_and_chances = f"""
    <div class="analysis">
        {analysis_title}
        <table class="moves-table">
            <thead>
                <tr>
                    <th>Rank</th>
                    <th>Move</th>
                    <th>Equity</th>
                    <th>Error</th>
                </tr>
            </thead>
            <tbody {table_body_id}>
                {''.join(table_rows)}
            </tbody>
        </table>
    </div>
"""

        # Generate score matrix for cube decisions if enabled
        score_matrix_html = ''
        if is_cube_decision and decision.match_length > 0 and self.settings.get('generate_score_matrix', False):
            score_matrix_html = self._generate_score_matrix_html(decision)
            if score_matrix_html:
                score_matrix_html = f"\n{score_matrix_html}"

        html = f"""
<div class="card-back">
{position_viewer_html}
    <div class="metadata">{metadata}</div>
{answer_html}
{analysis_and_chances}{score_matrix_html}
    {self._generate_source_info(decision)}
</div>
"""

        if show_options:
            html += self._generate_mcq_back_javascript(correct_letter)

        if self.interactive_moves:
            # Generate animation scripts
            animation_scripts = self._generate_checker_animation_scripts(decision, candidates, move_result_svgs or {})
            html += animation_scripts

        return html

    def _generate_checker_animation_scripts(
        self,
        decision: Decision,
        candidates: List[Optional[Move]],
        move_result_svgs: Dict[str, str]
    ) -> str:
        """
        Generate JavaScript for animating actual checker movements on the board.

        Args:
            decision: The decision with the original position
            candidates: List of candidate moves
            move_result_svgs: Dictionary mapping move notation to result SVG

        Returns:
            HTML script tags with animation code
        """
        # Build move data with coordinates for each checker movement
        move_data = {}

        for candidate in candidates:
            if not candidate:
                continue

            # Parse move notation to get individual checker movements
            from flashgammon.renderer.animation_helper import AnimationHelper
            movements = AnimationHelper.parse_move_notation(candidate.notation, decision.on_roll)

            if not movements:
                continue

            # Calculate coordinates for each movement
            # We need to track the position state as we animate
            move_animations = []

            # Create a copy of the position to track changes during the move
            current_position = decision.position.copy()

            for from_point, to_point in movements:
                # Get starting coordinates (top of stack at from_point)
                # Cap at max visible checkers (5 for points, 3 for bar)
                from_count = abs(current_position.points[from_point]) if 0 <= from_point <= 25 else 0
                from_max_visible = 3 if (from_point == 0 or from_point == 25) else 5
                from_index = min(max(0, from_count - 1), from_max_visible - 1)  # Top visible checker
                start_x, start_y = self.animation_controller.get_point_coordinates(from_point, from_index)

                # Get ending coordinates (where it lands at to_point - on top of existing checkers)
                # Cap at max visible checkers to avoid landing above visible stack
                if to_point >= 0 and to_point <= 25:
                    to_count = abs(current_position.points[to_point])
                    to_max_visible = 3 if (to_point == 0 or to_point == 25) else 5
                    to_index = min(to_count, to_max_visible - 1)  # Land on last visible position
                    end_x, end_y = self.animation_controller.get_point_coordinates(to_point, to_index)
                else:
                    # Bear-off or special case
                    end_x, end_y = self.animation_controller.get_point_coordinates(to_point, 0)

                move_animations.append({
                    'from_point': from_point,
                    'to_point': to_point,
                    'start_x': start_x,
                    'start_y': start_y,
                    'end_x': end_x,
                    'end_y': end_y
                })

                # Update position for next movement calculation
                if 0 <= from_point <= 25:
                    if current_position.points[from_point] > 0:
                        current_position.points[from_point] -= 1
                    elif current_position.points[from_point] < 0:
                        current_position.points[from_point] += 1

                if 0 <= to_point <= 25:
                    if decision.on_roll == Player.X:
                        current_position.points[to_point] += 1
                    else:
                        current_position.points[to_point] -= 1

            move_data[candidate.notation] = move_animations

        move_data_json = json.dumps(move_data)
        move_result_svgs_json = json.dumps(move_result_svgs)

        # Get player on roll and checker colors
        on_roll_player = 'X' if decision.on_roll == Player.X else 'O'
        checker_x_color = self.renderer.color_scheme.checker_x
        checker_o_color = self.renderer.color_scheme.checker_o
        checker_border_color = self.renderer.color_scheme.checker_border
        checker_radius = self.renderer.checker_radius

        # Generate animation JavaScript
        script = f"""
<script>
// Checker movement animation system
(function() {{
    const ANIMATION_DURATION = 200; // milliseconds
    const moveData = {move_data_json};
    const moveResultSVGs = {move_result_svgs_json};
    const onRollPlayer = '{on_roll_player}';
    const checkerXColor = '{checker_x_color}';
    const checkerOColor = '{checker_o_color}';
    const checkerBorderColor = '{checker_border_color}';
    const checkerRadius = {checker_radius};
    let isAnimating = false;
    let cancelCurrentAnimation = false;
    let currentSelectedRow = null;
    let originalBoardHTML = null;

    // Store original board HTML for reset
    function storeOriginalBoard() {{
        const board = document.getElementById('animated-board');
        if (board) {{
            originalBoardHTML = board.innerHTML;
        }}
    }}

    // Reset board to original state
    function resetBoard() {{
        if (originalBoardHTML) {{
            const board = document.getElementById('animated-board');
            if (board) {{
                board.innerHTML = originalBoardHTML;
            }}
        }}
    }}

    // Helper to find checkers at a specific point
    function getCheckersAtPoint(svg, pointNum) {{
        return svg.querySelectorAll('.checker[data-point="' + pointNum + '"]');
    }}

    // Get the checker count text element at a point (if it exists)
    function getCheckerCountText(svg, pointNum) {{
        const checkers = getCheckersAtPoint(svg, pointNum);
        if (checkers.length === 0) return null;

        // Search for text element near any checker at this point
        const allTexts = svg.querySelectorAll('text.checker-text');
        for (const checker of checkers) {{
            const checkerCx = parseFloat(checker.getAttribute('cx'));
            const checkerCy = parseFloat(checker.getAttribute('cy'));

            for (const text of allTexts) {{
                const textX = parseFloat(text.getAttribute('x'));
                const textY = parseFloat(text.getAttribute('y'));

                if (5 > Math.abs(checkerCx - textX) && 5 > Math.abs(checkerCy - textY)) {{
                    return text;
                }}
            }}
        }}

        return null;
    }}

    // Update checker count display for a point (with count adjustment)
    function updateCheckerCount(svg, pointNum, countAdjustment) {{
        const checkers = getCheckersAtPoint(svg, pointNum);
        const countText = getCheckerCountText(svg, pointNum);

        // Determine actual current count
        let currentCount;
        if (countText) {{
            currentCount = parseInt(countText.textContent);
        }} else {{
            currentCount = checkers.length;
        }}

        // Apply adjustment
        const newCount = currentCount + countAdjustment;

        // Determine threshold based on point type
        const isBar = (pointNum === 0 || pointNum === 25);
        const threshold = isBar ? 3 : 5;

        if (threshold >= newCount) {{
            // No count needed, remove if exists
            if (countText) {{
                countText.remove();
            }}
            return;
        }}

        // Need to show count - find the target checker (at threshold - 1 index)
        const checkersArray = Array.from(checkers);
        const targetChecker = checkersArray[threshold - 1];

        if (!targetChecker) return;

        const cx = parseFloat(targetChecker.getAttribute('cx'));
        const cy = parseFloat(targetChecker.getAttribute('cy'));

        // Get checker color to determine text color (inverse)
        const isX = targetChecker.classList.contains('checker-x');
        const textColor = isX ? '{self.renderer.color_scheme.checker_o}' : '{self.renderer.color_scheme.checker_x}';
        const fontSize = {self.renderer.checker_radius} * 1.2;

        if (countText) {{
            // Update existing text
            countText.textContent = newCount;
            countText.setAttribute('x', cx);
            countText.setAttribute('y', cy);
            // Move to end of parent to ensure it's on top (SVG z-index)
            const parent = countText.parentNode;
            parent.removeChild(countText);
            parent.appendChild(countText);
        }} else {{
            // Create new text element
            const textElement = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            textElement.setAttribute('class', 'checker-text');
            textElement.setAttribute('x', cx);
            textElement.setAttribute('y', cy);
            textElement.setAttribute('font-size', fontSize);
            textElement.setAttribute('fill', textColor);
            textElement.textContent = newCount;

            // Append to parent (end of DOM) to ensure it appears on top
            targetChecker.parentNode.appendChild(textElement);
        }}
    }}

    // Create SVG arrow element from start to end coordinates
    function createArrow(svg, startX, startY, endX, endY) {{
        const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        g.setAttribute('class', 'move-arrow');

        // Calculate arrow direction
        const dx = endX - startX;
        const dy = endY - startY;
        const length = Math.sqrt(dx * dx + dy * dy);
        const angle = Math.atan2(dy, dx);

        // Arrow parameters
        const arrowheadSize = 15;
        const strokeWidth = 3;
        const arrowAngle = Math.PI / 6; // 30 degrees

        // Calculate arrowhead points
        const arrowTipX = endX;
        const arrowTipY = endY;
        const arrowBase1X = endX - arrowheadSize * Math.cos(angle - arrowAngle);
        const arrowBase1Y = endY - arrowheadSize * Math.sin(angle - arrowAngle);
        const arrowBase2X = endX - arrowheadSize * Math.cos(angle + arrowAngle);
        const arrowBase2Y = endY - arrowheadSize * Math.sin(angle + arrowAngle);

        // Calculate where line should end (at the center of the arrowhead base)
        const arrowBaseLength = arrowheadSize * Math.cos(arrowAngle);
        const lineEndX = endX - arrowBaseLength * Math.cos(angle);
        const lineEndY = endY - arrowBaseLength * Math.sin(angle);

        // Create line
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', startX);
        line.setAttribute('y1', startY);
        line.setAttribute('x2', lineEndX);
        line.setAttribute('y2', lineEndY);
        line.setAttribute('stroke', '#FF6B35');
        line.setAttribute('stroke-width', strokeWidth);
        line.setAttribute('stroke-linecap', 'round');
        line.setAttribute('opacity', '0.8');

        // Create arrowhead
        const arrowhead = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
        arrowhead.setAttribute('points',
            `${{arrowTipX}},${{arrowTipY}} ${{arrowBase1X}},${{arrowBase1Y}} ${{arrowBase2X}},${{arrowBase2Y}}`);
        arrowhead.setAttribute('fill', '#FF6B35');
        arrowhead.setAttribute('opacity', '0.8');

        g.appendChild(line);
        g.appendChild(arrowhead);

        return g;
    }}

    // Remove all arrows from SVG
    function removeArrows(svg) {{
        const arrows = svg.querySelectorAll('.move-arrow');
        arrows.forEach(arrow => arrow.remove());
    }}

    // Remove all ghost checkers from SVG
    function removeGhostCheckers(svg) {{
        const ghosts = svg.querySelectorAll('.ghost-checker');
        ghosts.forEach(ghost => ghost.remove());
    }}

    // Create a transparent checker at the original position
    function createGhostChecker(svg, x, y) {{
        const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        g.setAttribute('class', 'ghost-checker');

        // Determine checker color based on which player is moving
        const checkerColor = onRollPlayer === 'X' ? checkerXColor : checkerOColor;

        // Create the checker circle
        const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        circle.setAttribute('cx', x);
        circle.setAttribute('cy', y);
        circle.setAttribute('r', checkerRadius);
        circle.setAttribute('fill', checkerColor);
        circle.setAttribute('stroke', checkerBorderColor);
        circle.setAttribute('stroke-width', '2');
        circle.setAttribute('opacity', '0.3');

        g.appendChild(circle);
        return g;
    }}

    // Add arrows and ghost checkers for all movements in a move
    function addMoveArrows(svg, animations) {{
        // Remove any existing arrows and ghost checkers first
        removeArrows(svg);
        removeGhostCheckers(svg);

        // Add arrow and ghost checker for each movement
        animations.forEach(anim => {{
            // Add ghost checker at start position
            const ghost = createGhostChecker(svg, anim.start_x, anim.start_y);
            svg.appendChild(ghost);

            // Add arrow showing the move path
            const arrow = createArrow(svg, anim.start_x, anim.start_y, anim.end_x, anim.end_y);
            svg.appendChild(arrow);
        }});
    }}

    // Animate a single checker from start to end coordinates
    function animateChecker(checker, startX, startY, endX, endY, duration) {{
        return new Promise((resolve) => {{
            const startTime = performance.now();

            function animate(currentTime) {{
                // Check if animation was cancelled
                if (cancelCurrentAnimation) {{
                    resolve('cancelled');
                    return;
                }}

                const elapsed = currentTime - startTime;
                const progress = Math.min(elapsed / duration, 1);

                // Easing function (ease-in-out)
                const eased = 0.5 > progress
                    ? 2 * progress * progress
                    : 1 - Math.pow(-2 * progress + 2, 2) / 2;

                // Interpolate position
                const currentX = startX + (endX - startX) * eased;
                const currentY = startY + (endY - startY) * eased;

                // Update checker position
                checker.setAttribute('cx', currentX);
                checker.setAttribute('cy', currentY);

                if (1 > progress) {{
                    requestAnimationFrame(animate);
                }} else {{
                    resolve('completed');
                }}
            }}

            requestAnimationFrame(animate);
        }});
    }}

    // Animate a move
    async function animateMove(moveNotation) {{
        // If already animating, cancel the current animation
        if (isAnimating) {{
            cancelCurrentAnimation = true;
            // Wait a bit for the cancellation to take effect
            await new Promise(resolve => setTimeout(resolve, 50));
        }}

        const animations = moveData[moveNotation];
        if (!animations || animations.length === 0) return;

        // Reset cancellation flag and set animating flag
        cancelCurrentAnimation = false;
        isAnimating = true;

        // Reset board to original position before animating
        resetBoard();

        // Small delay to ensure DOM update
        await new Promise(resolve => setTimeout(resolve, 50));

        const board = document.getElementById('animated-board');
        const svg = board.querySelector('svg');

        if (!svg) {{
            isAnimating = false;
            return;
        }}

        // Animate each checker movement sequentially
        let totalAnimationTime = 0;
        for (const anim of animations) {{
            // Check if we should cancel
            if (cancelCurrentAnimation) {{
                break;
            }}

            const checkers = getCheckersAtPoint(svg, anim.from_point);

            if (checkers.length > 0) {{
                // Animate the LAST checker (top of stack, at pointy end)
                const checker = checkers[checkers.length - 1];

                // Update data-point attribute to new position
                checker.setAttribute('data-point', anim.to_point);

                // Animate movement
                const result = await animateChecker(
                    checker,
                    anim.start_x, anim.start_y,
                    anim.end_x, anim.end_y,
                    ANIMATION_DURATION
                );

                totalAnimationTime += ANIMATION_DURATION;

                // If cancelled, stop processing
                if (result === 'cancelled') {{
                    break;
                }}
            }}
        }}

        // Add delay proportional to animation time (100% extra buffer to ensure animations complete)
        const bufferDelay = Math.max(300, totalAnimationTime * 1.0);
        await new Promise(resolve => setTimeout(resolve, bufferDelay));

        // After animation completes, replace with result SVG if available
        const resultSVG = moveResultSVGs[moveNotation];
        if (resultSVG && !cancelCurrentAnimation) {{
            const board = document.getElementById('animated-board');
            if (board) {{
                board.innerHTML = resultSVG;

                // Add arrows to the final result SVG showing the move paths
                const finalSvg = board.querySelector('svg');
                if (finalSvg) {{
                    addMoveArrows(finalSvg, animations);
                }}
            }}
        }}

        isAnimating = false;
    }}

    // Initialize when DOM is ready
    function initialize() {{
        // Store the original board state
        storeOriginalBoard();

        // Set up click handlers for move rows
        const moveRows = document.querySelectorAll('.move-row');

        // Initialize - highlight best move row
        const bestMoveRow = document.querySelector('.move-row.best-move');
        if (bestMoveRow) {{
            bestMoveRow.classList.add('selected');
            currentSelectedRow = bestMoveRow;

            // Automatically trigger animation for best move
            const bestMoveNotation = bestMoveRow.dataset.moveNotation;
            if (bestMoveNotation) {{
                // Small delay to ensure DOM is fully ready
                setTimeout(() => {{
                    animateMove(bestMoveNotation);
                }}, 100);
            }}
        }}

        moveRows.forEach(row => {{
            row.addEventListener('click', function() {{
                const moveNotation = this.dataset.moveNotation;

                if (!moveNotation) return;

                // Update selection highlighting
                moveRows.forEach(r => r.classList.remove('selected'));
                this.classList.add('selected');
                currentSelectedRow = this;

                // Trigger animation
                animateMove(moveNotation);
            }});
        }});
    }}

    // Run initialization
    if (document.readyState === 'loading') {{
        document.addEventListener('DOMContentLoaded', initialize);
    }} else {{
        initialize();
    }}
}})();
</script>
"""

        return script

    def _format_wgb_inline(self, move: Move, decision: Decision) -> str:
        """
        Generate inline HTML for W/G/B percentages to display within move table cell.

        Returns HTML with two lines showing player and opponent win/gammon/backgammon percentages.
        Returns empty string if move has no W/G/B data.
        """
        if move.player_win_pct is None:
            return ""

        # Get checker colors from the renderer's color scheme
        player_color = self.renderer.color_scheme.checker_x if decision.on_roll == Player.X else self.renderer.color_scheme.checker_o
        opponent_color = self.renderer.color_scheme.checker_o if decision.on_roll == Player.X else self.renderer.color_scheme.checker_x

        wgb_html = f'''
        <div class="move-wgb-inline">
            <div class="wgb-line">
                <span style="color: {player_color};">●</span> P: <strong>{move.player_win_pct:.1f}%</strong> <span class="wgb-detail">(G:{move.player_gammon_pct:.1f}% B:{move.player_backgammon_pct:.1f}%)</span>
            </div>
            <div class="wgb-line">
                <span style="color: {opponent_color};">○</span> O: <strong>{move.opponent_win_pct:.1f}%</strong> <span class="wgb-detail">(G:{move.opponent_gammon_pct:.1f}% B:{move.opponent_backgammon_pct:.1f}%)</span>
            </div>
        </div>'''

        return wgb_html

    def _generate_winning_chances_html(self, decision: Decision) -> str:
        """
        Generate HTML for winning chances display (W/G/B percentages).

        Shows player and opponent winning chances with gammon and backgammon percentages.
        Note: Title is added separately in side-by-side layout.
        """
        # Get checker colors from the renderer's color scheme
        player_color = self.renderer.color_scheme.checker_x if decision.on_roll == Player.X else self.renderer.color_scheme.checker_o
        opponent_color = self.renderer.color_scheme.checker_o if decision.on_roll == Player.X else self.renderer.color_scheme.checker_x

        html = f'''            <div class="winning-chances">
                <div class="chances-grid">
                    <div class="chances-row">
                        <span class="chances-label"><span style="color: {player_color}; font-size: 1.2em;">●</span> Player:</span>
                        <span class="chances-values">
                            <strong>{decision.player_win_pct:.2f}%</strong>
                            <span class="chances-detail">(G: {decision.player_gammon_pct:.2f}% B: {decision.player_backgammon_pct:.2f}%)</span>
                        </span>
                    </div>
                    <div class="chances-row">
                        <span class="chances-label"><span style="color: {opponent_color}; font-size: 1.2em;">●</span> Opp.:</span>
                        <span class="chances-values">
                            <strong>{decision.opponent_win_pct:.2f}%</strong>
                            <span class="chances-detail">(G: {decision.opponent_gammon_pct:.2f}% B: {decision.opponent_backgammon_pct:.2f}%)</span>
                        </span>
                    </div>
                </div>
            </div>
'''
        return html

    def _generate_score_matrix_html(self, decision: Decision) -> str:
        """
        Generate score matrix HTML for cube decisions.

        Args:
            decision: The cube decision

        Returns:
            HTML string with score matrix, or empty string if generation fails
        """
        # Only generate if GnuBG is available
        if not self.settings.is_gnubg_available():
            return ""

        try:
            from flashgammon.analysis.score_matrix import generate_score_matrix, format_matrix_as_html

            # Calculate current score (away from match)
            current_player_away = decision.match_length - (
                decision.score_o if decision.on_roll == Player.O else decision.score_x
            )
            current_opponent_away = decision.match_length - (
                decision.score_x if decision.on_roll == Player.O else decision.score_o
            )

            # Generate matrix with progress callback
            matrix = generate_score_matrix(
                xgid=decision.xgid,
                match_length=decision.match_length,
                gnubg_path=self.settings.gnubg_path,
                ply_level=self.settings.gnubg_analysis_ply,
                progress_callback=self.progress_callback
            )

            # Format as HTML
            matrix_html = format_matrix_as_html(
                matrix=matrix,
                current_player_away=current_player_away,
                current_opponent_away=current_opponent_away
            )

            return matrix_html

        except Exception as e:
            # Silently fail if matrix generation fails
            # (e.g., GnuBG not available, analysis error)
            print(f"Warning: Failed to generate score matrix: {e}")
            return ""

    def _generate_source_info(self, decision: Decision) -> str:
        """Generate source information HTML."""
        parts = []
        if decision.xgid:
            parts.append(f"<code>{decision.xgid}</code>")
        if decision.source_file:
            parts.append(f"Source: {decision.source_file}")
        if decision.game_number:
            parts.append(f"Game #{decision.game_number}")
        if decision.move_number:
            parts.append(f"Move #{decision.move_number}")

        if parts:
            return f"""
<div class="source-info">
    <p>{'<br>'.join(parts)}</p>
</div>
"""
        return ""

    def _generate_tags(self, decision: Decision) -> List[str]:
        """Generate tags for the card."""
        tags = ["flashgammon", "backgammon"]

        tags.append(decision.decision_type.value)

        if decision.match_length > 0:
            tags.append(f"match_{decision.match_length}pt")
        else:
            tags.append("money_game")

        if decision.cube_value > 1:
            tags.append(f"cube_{decision.cube_value}")

        return tags

    def _render_position_svg(self, decision: Decision) -> str:
        """Render position as SVG markup."""
        return self.renderer.render_svg(
            position=decision.position,
            on_roll=decision.on_roll,
            dice=decision.dice,
            cube_value=decision.cube_value,
            cube_owner=decision.cube_owner,
        )

    def _render_resulting_position_svg(self, decision: Decision, move: Move) -> str:
        """Render the resulting position after a move as SVG markup."""
        if move.resulting_position:
            resulting_pos = move.resulting_position
        else:
            resulting_pos = MoveParser.apply_move(
                decision.position,
                move.notation,
                decision.on_roll
            )

        return self.renderer.render_svg(
            position=resulting_pos,
            on_roll=decision.on_roll,
            dice=decision.dice,
            dice_opacity=0.3,
            cube_value=decision.cube_value,
            cube_owner=decision.cube_owner,
        )

    def _shuffle_candidates(
        self,
        candidates: List[Optional[Move]]
    ) -> Tuple[List[Optional[Move]], int]:
        """
        Shuffle candidates for MCQ and return answer index.

        Returns:
            (shuffled_candidates, answer_index_of_best_move)
        """
        best_idx = 0
        for i, candidate in enumerate(candidates):
            if candidate and candidate.rank == 1:
                best_idx = i
                break

        indices = list(range(len(candidates)))
        random.shuffle(indices)

        shuffled = [candidates[i] for i in indices]
        answer_idx = indices.index(best_idx)

        return shuffled, answer_idx

    def _generate_id(self) -> str:
        """Generate a random ID for a card."""
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))
