"""Generate Anki card content from XG decisions."""

import json
import random
import string
import html
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from ankigammon.models import Decision, Move, Player, DecisionType
from ankigammon.renderer.svg_board_renderer import SVGBoardRenderer
from ankigammon.renderer.animation_controller import AnimationController
from ankigammon.utils.move_parser import MoveParser
from ankigammon.settings import get_settings


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
        progress_callback: Optional[callable] = None,
        cancellation_callback: Optional[callable] = None
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
            cancellation_callback: Optional callback() that returns True if cancelled
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.show_options = show_options
        self.interactive_moves = interactive_moves
        self.settings = get_settings()

        # Create default renderer and animation controller with settings if not provided
        from ankigammon.renderer.color_schemes import get_scheme
        self.renderer = renderer or SVGBoardRenderer(
            color_scheme=get_scheme(self.settings.color_scheme),
            orientation=self.settings.board_orientation
        )
        self.animation_controller = animation_controller or AnimationController(
            orientation=self.settings.board_orientation
        )

        self.progress_callback = progress_callback
        self.cancellation_callback = cancellation_callback

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

        # Ensure decision has candidate moves
        if not decision.candidate_moves:
            raise ValueError(
                "Cannot generate card: decision has no candidate moves. "
                "For XGID-only input, use GnuBG analysis to populate moves."
            )

        # Generate position SVG
        position_svg = self._render_position_svg(decision)

        # Prepare candidate moves
        max_options = self.settings.max_mcq_options
        if decision.decision_type == DecisionType.CUBE_ACTION:
            # Cube decisions always show all 5 actions
            candidates = decision.candidate_moves[:5]
        else:
            candidates = decision.candidate_moves[:max_options]

        # Shuffle candidates for MCQ (preserve order for cube decisions)
        if decision.decision_type == DecisionType.CUBE_ACTION:
            # Preserve logical order for cube actions
            shuffled_candidates = candidates
            answer_index = next((i for i, c in enumerate(candidates) if c and c.rank == 1), 0)
        else:
            # Randomize order for checker play
            shuffled_candidates, answer_index = self._shuffle_candidates(candidates)

        # Generate resulting position SVGs (for front card preview or back card interactive moves)
        move_result_svgs = {}
        move_result_svgs_front = {}
        best_move = decision.get_best_move()

        # Preview only makes sense for checker play decisions (not cube actions)
        preview_enabled = (
            self.settings.preview_moves_before_submit
            and self.show_options
            and decision.decision_type == DecisionType.CHECKER_PLAY
        )

        if not self.interactive_moves and not preview_enabled:
            # Render only the best move's resulting position
            if best_move:
                result_svg = self._render_resulting_position_svg(decision, best_move)
            else:
                result_svg = None
        else:
            # Render all move results for interactive visualization and/or preview
            if self.progress_callback:
                self.progress_callback(f"Rendering board positions...")

            # Use shuffled_candidates for front card (MCQ order), candidates for back card (analysis order)
            if preview_enabled:
                for candidate in shuffled_candidates:
                    if candidate:
                        result_svg_for_move = self._render_resulting_position_svg(decision, candidate)
                        move_result_svgs_front[candidate.notation] = result_svg_for_move

            if self.interactive_moves:
                for candidate in candidates:
                    if candidate:
                        result_svg_for_move = self._render_resulting_position_svg(decision, candidate)
                        move_result_svgs[candidate.notation] = result_svg_for_move

            result_svg = None

        # Generate card front
        if self.show_options:
            front_html = self._generate_interactive_mcq_front(
                decision, position_svg, shuffled_candidates, move_result_svgs_front
            )
        else:
            front_html = self._generate_simple_front(
                decision, position_svg
            )

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

        # On-roll player uses bottom color after perspective transform
        checker_color = self.renderer.color_scheme.checker_o

        # Replace "Black" with colored circle
        colored_circle = f'<span style="color: {checker_color}; font-size: 1.8em;">●</span>'
        metadata_html = base_metadata.replace("Black", colored_circle)

        return metadata_html

    def _generate_simple_front(
        self,
        decision: Decision,
        position_svg: str
    ) -> str:
        """Generate HTML for simple front (no options)."""
        metadata = self._get_metadata_html(decision)

        # Determine question text based on decision type
        if decision.decision_type == DecisionType.CUBE_ACTION:
            question_text = "What is the best cube action?"
        else:
            question_text = "What is the best move?"

        html = f"""
<div class="card-front">
    <div class="position-svg">
        {position_svg}
    </div>
    <div class="metadata">{metadata}</div>
    <div class="question">
        <h3>{question_text}</h3>
    </div>
</div>
"""
        return html

    def _generate_interactive_mcq_front(
        self,
        decision: Decision,
        position_svg: str,
        candidates: List[Optional[Move]],
        move_result_svgs: Dict[str, str] = None
    ) -> str:
        """Generate interactive quiz MCQ front with clickable options."""
        metadata = self._get_metadata_html(decision)
        letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J']
        preview_enabled = self.settings.preview_moves_before_submit and move_result_svgs

        # Determine question text based on decision type
        if decision.decision_type == DecisionType.CUBE_ACTION:
            question_text = "What is the best cube action?"
        else:
            question_text = "What is the best move?"

        # Build clickable options with move notation data
        options_html = []
        for i, candidate in enumerate(candidates):
            if candidate:
                options_html.append(f"""
<div class='mcq-option' data-option-letter='{letters[i]}' data-move-notation='{html.escape(candidate.notation)}'>
    <strong>{letters[i]}.</strong> {candidate.notation}
</div>
""")

        # Use ID "animated-board" when preview is enabled
        position_container_id = 'id="animated-board"' if preview_enabled else ''

        # Determine hint text
        if preview_enabled:
            hint_text = "Click an option to preview the move, then submit your answer"
        else:
            hint_text = "Click an option to see if you're correct"

        # Build submit button HTML (only show when preview enabled)
        submit_button_html = ""
        if preview_enabled:
            submit_button_html = """
        <div id="mcq-submit-container" style="display: none; margin-top: 15px;">
            <button id="mcq-submit-btn" class="mcq-submit-button">
                Submit Answer: <span id="mcq-selected-letter"></span>
            </button>
        </div>
"""

        result_html = f"""
<div class="card-front interactive-mcq-front">
    <div class="position-svg" {position_container_id}>
        {position_svg}
    </div>
    <div class="metadata">{metadata}</div>
    <div class="question">
        <h3>{question_text}</h3>
        <div class="mcq-options">
            {''.join(options_html)}
        </div>
        <p class="mcq-hint">{hint_text}</p>
        {submit_button_html}
    </div>
</div>

<script>
{self._generate_mcq_front_javascript(decision, candidates, move_result_svgs or {})}
</script>
"""
        return result_html

    def _generate_mcq_front_javascript(
        self,
        decision: Decision,
        candidates: List[Optional[Move]],
        move_result_svgs: Dict[str, str]
    ) -> str:
        """Generate JavaScript for interactive MCQ front side."""
        preview_enabled = self.settings.preview_moves_before_submit and move_result_svgs

        if not preview_enabled:
            # Original instant-flip behavior
            return """
(function() {
    const options = document.querySelectorAll('.mcq-option');

    options.forEach(option => {
        option.addEventListener('click', function() {
            const selectedLetter = this.dataset.optionLetter;

            // Store selection in sessionStorage
            try {
                sessionStorage.setItem('ankigammon-mcq-choice', selectedLetter);
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

        # Preview mode - include animation system
        # Generate animation scripts similar to back card
        animation_script = self._generate_checker_animation_scripts_for_front(
            decision, candidates, move_result_svgs
        )

        return animation_script

    def _generate_mcq_back_javascript(self, correct_letter: str) -> str:
        """Generate JavaScript for interactive MCQ back side."""
        return f"""
<script>
(function() {{
    let selectedLetter = null;

    try {{
        selectedLetter = sessionStorage.getItem('ankigammon-mcq-choice');
        sessionStorage.removeItem('ankigammon-mcq-choice');
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
        letters = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J']

        # Determine decision type for formatting
        is_cube_decision = decision.decision_type == DecisionType.CUBE_ACTION

        # Filter analysis moves (exclude synthetic options)
        analysis_moves = [m for m in candidates if m and m.from_xg_analysis]

        # Sort moves by type
        if decision.decision_type == DecisionType.CUBE_ACTION:
            # Preserve standard cube action order
            cube_order_map = {
                "No double": 1,
                "Double, take": 2,
                "Double, pass": 3
            }
            sorted_candidates = sorted(
                analysis_moves,
                key=lambda m: cube_order_map.get(m.xg_notation if m.xg_notation else m.notation, 99)
            )
        else:
            # Sort checker plays by error magnitude
            sorted_candidates = sorted(
                analysis_moves,
                key=lambda m: abs(m.error) if m.error is not None else 999.0
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

            # Include W/G/B data for checker play decisions
            if decision.decision_type == DecisionType.CHECKER_PLAY:
                wgb_inline_html = self._format_wgb_inline(move, decision)
            else:
                wgb_inline_html = ""

            # Cube decisions omit rank column
            if is_cube_decision:
                table_rows.append(f"""
<tr class="{row_class}" {row_attrs}>
    <td>
        <div class="move-notation">{display_notation}</div>{wgb_inline_html}
    </td>
    <td>{move.equity:.3f}</td>
    <td>{error_str}</td>
</tr>""")
            else:
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
        if self.interactive_moves:
            # Interactive mode: single board with animated checkers
            position_viewer_html = f'''
    <div class="position-viewer">
        <div class="position-svg-animated" id="animated-board">
            {original_position_svg}
        </div>
    </div>'''
            # Set title based on decision type
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
            # Set title based on decision type
            if is_cube_decision:
                analysis_title = '<h4>Cube Actions Analysis:</h4>'
            else:
                analysis_title = '<h4>Top Moves Analysis:</h4>'
            table_body_id = ''

        # Generate winning chances HTML for cube decisions
        winning_chances_html = ''
        if is_cube_decision and decision.player_win_pct is not None:
            winning_chances_html = self._generate_winning_chances_html(decision)

        # Prepare table headers based on decision type
        if is_cube_decision:
            table_headers = """
                    <tr>
                        <th>Action</th>
                        <th>Equity</th>
                        <th>Error</th>
                    </tr>"""
        else:
            table_headers = """
                    <tr>
                        <th>Rank</th>
                        <th>Move</th>
                        <th>Equity</th>
                        <th>Error</th>
                    </tr>"""

        # Generate analysis table
        analysis_table = f"""
            {analysis_title}
            <table class="moves-table">
                <thead>{table_headers}
                </thead>
                <tbody {table_body_id}>
                    {''.join(table_rows)}
                </tbody>
            </table>"""

        # Wrap with appropriate layout
        if is_cube_decision and winning_chances_html:
            analysis_and_chances = f"""
    <div class="analysis-container">
        <div class="analysis-section">{analysis_table}
        </div>
        <div class="chances-section">
            <h4>Winning Chances:</h4>
{winning_chances_html}
        </div>
    </div>
"""
        else:
            analysis_and_chances = f"""
    <div class="analysis">{analysis_table}
    </div>
"""

        # Generate score matrix for cube decisions if enabled
        score_matrix_html = ''
        if is_cube_decision and decision.match_length > 0 and self.settings.generate_score_matrix:
            score_matrix_html = self._generate_score_matrix_html(decision)
            if score_matrix_html:
                score_matrix_html = f"\n{score_matrix_html}"

        # Generate note HTML if note exists
        note_html = self._generate_note_html(decision)

        html = f"""
<div class="card-back">
{position_viewer_html}
    <div class="metadata">{metadata}</div>
{answer_html}
{note_html}
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

    def _generate_move_animation_data(
        self,
        decision: Decision,
        candidates: List[Optional[Move]]
    ) -> Dict[str, List[Dict]]:
        """
        Generate animation coordinate data for checker movements.

        Args:
            decision: The decision with the original position
            candidates: List of candidate moves

        Returns:
            Dictionary mapping move notation to list of animation data
        """
        move_data = {}

        for candidate in candidates:
            if not candidate:
                continue

            # Parse move notation into individual checker movements
            from ankigammon.renderer.animation_helper import AnimationHelper
            movements = AnimationHelper.parse_move_notation(candidate.notation, decision.on_roll)

            if not movements:
                continue

            # Track position state during animation
            move_animations = []
            current_position = decision.position.copy()

            for from_point, to_point in movements:
                # Calculate start coordinates (top checker at source point)
                from_count = abs(current_position.points[from_point]) if 0 <= from_point <= 25 else 0
                from_max_visible = 3 if (from_point == 0 or from_point == 25) else 5
                from_index = min(max(0, from_count - 1), from_max_visible - 1)
                start_x, start_y = self.animation_controller.get_point_coordinates(from_point, from_index)

                # Calculate end coordinates (top of destination stack)
                if to_point >= 0 and to_point <= 25:
                    to_count = abs(current_position.points[to_point])
                    to_max_visible = 3 if (to_point == 0 or to_point == 25) else 5
                    to_index = min(to_count, to_max_visible - 1)
                    end_x, end_y = self.animation_controller.get_point_coordinates(to_point, to_index)
                else:
                    end_x, end_y = self.animation_controller.get_point_coordinates(to_point, 0)

                move_animations.append({
                    'from_point': from_point,
                    'to_point': to_point,
                    'start_x': start_x,
                    'start_y': start_y,
                    'end_x': end_x,
                    'end_y': end_y
                })

                # Update position state for next movement
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

        return move_data

    def _generate_animation_javascript(
        self,
        move_data_json: str,
        move_result_svgs_json: str,
        on_roll_player: str,
        ghost_checker_color: str,
        checker_x_color: str,
        checker_o_color: str,
        checker_border_color: str,
        checker_radius: float,
        mode: str  # 'back' or 'front'
    ) -> str:
        """
        Generate JavaScript animation code for checker movements.

        Args:
            move_data_json: JSON string of move animation data
            move_result_svgs_json: JSON string of result SVGs
            on_roll_player: 'X' or 'O'
            ghost_checker_color: Color for ghost checkers
            checker_x_color: Color for X checkers
            checker_o_color: Color for O checkers
            checker_border_color: Color for checker borders
            checker_radius: Radius of checkers
            mode: 'back' for back card, 'front' for front card

        Returns:
            JavaScript code string (without <script> tags)
        """
        # Mode-specific state variables
        if mode == 'back':
            mode_state_vars = "let currentSelectedRow = null;"
        else:  # front
            mode_state_vars = """let currentSelectedOption = null;
    let currentSelectedLetter = null;"""

        # Mode-specific initialize function
        if mode == 'back':
            initialize_function = """    // Initialize when DOM is ready
    function initialize() {
        // Store the original board state
        storeOriginalBoard();

        // Set up click handlers for move rows
        const moveRows = document.querySelectorAll('.move-row');

        // Initialize - highlight best move row
        const bestMoveRow = document.querySelector('.move-row.best-move');
        if (bestMoveRow) {
            bestMoveRow.classList.add('selected');
            currentSelectedRow = bestMoveRow;

            // Automatically trigger animation for best move
            const bestMoveNotation = bestMoveRow.dataset.moveNotation;
            if (bestMoveNotation) {
                // Small delay to ensure DOM is fully ready
                setTimeout(() => {
                    animateMove(bestMoveNotation);
                }, 100);
            }
        }

        moveRows.forEach(row => {
            row.addEventListener('click', function() {
                const moveNotation = this.dataset.moveNotation;

                if (!moveNotation) return;

                // Update selection highlighting
                moveRows.forEach(r => r.classList.remove('selected'));
                this.classList.add('selected');
                currentSelectedRow = this;

                // Trigger animation
                animateMove(moveNotation);
            });
        });
    }"""
        else:  # front
            initialize_function = """    // Initialize when DOM is ready
    function initialize() {
        // Store the original board state
        storeOriginalBoard();

        // Set up click handlers for MCQ options
        const options = document.querySelectorAll('.mcq-option');
        const submitContainer = document.getElementById('mcq-submit-container');
        const submitBtn = document.getElementById('mcq-submit-btn');
        const selectedLetterSpan = document.getElementById('mcq-selected-letter');

        options.forEach(option => {
            option.addEventListener('click', function() {
                const moveNotation = this.dataset.moveNotation;
                const letter = this.dataset.optionLetter;

                if (!moveNotation) return;

                // Update selection highlighting
                options.forEach(opt => opt.classList.remove('selected'));
                this.classList.add('selected');
                currentSelectedOption = this;
                currentSelectedLetter = letter;

                // Show submit button with selected letter
                if (submitContainer && selectedLetterSpan) {
                    selectedLetterSpan.textContent = letter;
                    submitContainer.style.display = 'block';
                }

                // Trigger animation
                animateMove(moveNotation);
            });
        });

        // Submit button handler
        if (submitBtn) {
            submitBtn.addEventListener('click', function() {
                if (!currentSelectedLetter) return;

                // Store selection in sessionStorage
                try {
                    sessionStorage.setItem('ankigammon-mcq-choice', currentSelectedLetter);
                } catch (e) {
                    window.location.hash = 'choice-' + currentSelectedLetter;
                }

                // Visual feedback
                if (currentSelectedOption) {
                    currentSelectedOption.classList.add('selected-flash');
                }

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
        }
    }"""

        comment = "Checker movement animation system for MCQ front card" if mode == 'front' else "Checker movement animation system"

        return f"""// {comment}
(function() {{
    const ANIMATION_DURATION = 200; // milliseconds
    const moveData = {move_data_json};
    const moveResultSVGs = {move_result_svgs_json};
    const onRollPlayer = '{on_roll_player}';
    const ghostCheckerColor = '{ghost_checker_color}';
    const checkerXColor = '{checker_x_color}';
    const checkerOColor = '{checker_o_color}';
    const checkerBorderColor = '{checker_border_color}';
    const checkerRadius = {checker_radius};
    let isAnimating = false;
    let cancelCurrentAnimation = false;
    {mode_state_vars}
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
        const textColor = isX ? checkerOColor : checkerXColor;
        const fontSize = checkerRadius * 1.2;

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

        // Use bottom player's color after perspective transform
        const checkerColor = ghostCheckerColor;

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

{initialize_function}

    // Run initialization
    if (document.readyState === 'loading') {{
        document.addEventListener('DOMContentLoaded', initialize);
    }} else {{
        initialize();
    }}
}})();
"""

    def _generate_checker_animation_scripts(
        self,
        decision: Decision,
        candidates: List[Optional[Move]],
        move_result_svgs: Dict[str, str]
    ) -> str:
        """
        Generate JavaScript for animating checker movements on back card.

        Args:
            decision: The decision with the original position
            candidates: List of candidate moves
            move_result_svgs: Dictionary mapping move notation to result SVG

        Returns:
            HTML script tags with animation code
        """
        # Calculate coordinates for each checker movement
        move_data = self._generate_move_animation_data(decision, candidates)

        move_data_json = json.dumps(move_data)
        move_result_svgs_json = json.dumps(move_result_svgs)

        # Prepare animation parameters
        on_roll_player = 'X' if decision.on_roll == Player.X else 'O'
        ghost_checker_color = self.renderer.color_scheme.checker_o
        checker_x_color = self.renderer.color_scheme.checker_x
        checker_o_color = self.renderer.color_scheme.checker_o
        checker_border_color = self.renderer.color_scheme.checker_border
        checker_radius = self.renderer.checker_radius

        # Generate JavaScript using shared method
        javascript = self._generate_animation_javascript(
            move_data_json=move_data_json,
            move_result_svgs_json=move_result_svgs_json,
            on_roll_player=on_roll_player,
            ghost_checker_color=ghost_checker_color,
            checker_x_color=checker_x_color,
            checker_o_color=checker_o_color,
            checker_border_color=checker_border_color,
            checker_radius=checker_radius,
            mode='back'
        )

        return f"\n<script>\n{javascript}\n</script>\n"

    def _generate_checker_animation_scripts_for_front(
        self,
        decision: Decision,
        candidates: List[Optional[Move]],
        move_result_svgs: Dict[str, str]
    ) -> str:
        """
        Generate JavaScript for animating checker movements on front card.

        Args:
            decision: The decision with the original position
            candidates: List of candidate moves
            move_result_svgs: Dictionary mapping move notation to result SVG

        Returns:
            JavaScript code (without script tags, for embedding in front HTML)
        """
        # Calculate coordinates for each checker movement
        move_data = self._generate_move_animation_data(decision, candidates)

        move_data_json = json.dumps(move_data)
        move_result_svgs_json = json.dumps(move_result_svgs)

        # Prepare animation parameters
        on_roll_player = 'X' if decision.on_roll == Player.X else 'O'
        ghost_checker_color = self.renderer.color_scheme.checker_o
        checker_x_color = self.renderer.color_scheme.checker_x
        checker_o_color = self.renderer.color_scheme.checker_o
        checker_border_color = self.renderer.color_scheme.checker_border
        checker_radius = self.renderer.checker_radius

        # Generate JavaScript using shared method
        return self._generate_animation_javascript(
            move_data_json=move_data_json,
            move_result_svgs_json=move_result_svgs_json,
            on_roll_player=on_roll_player,
            ghost_checker_color=ghost_checker_color,
            checker_x_color=checker_x_color,
            checker_o_color=checker_o_color,
            checker_border_color=checker_border_color,
            checker_radius=checker_radius,
            mode='front'
        )

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
            HTML string with score matrix, or empty string if unavailable
        """
        if not self.settings.is_gnubg_available():
            return ""

        try:
            from ankigammon.analysis.score_matrix import generate_score_matrix, format_matrix_as_html

            # Calculate away scores
            current_player_away = decision.match_length - (
                decision.score_o if decision.on_roll == Player.O else decision.score_x
            )
            current_opponent_away = decision.match_length - (
                decision.score_x if decision.on_roll == Player.O else decision.score_o
            )

            matrix = generate_score_matrix(
                xgid=decision.xgid,
                match_length=decision.match_length,
                gnubg_path=self.settings.gnubg_path,
                ply_level=self.settings.gnubg_analysis_ply,
                progress_callback=self.progress_callback,
                cancellation_callback=self.cancellation_callback,
                cube_value=decision.cube_value,
                cube_owner=decision.cube_owner
            )

            matrix_html = format_matrix_as_html(
                matrix=matrix,
                current_player_away=current_player_away,
                current_opponent_away=current_opponent_away,
                ply_level=self.settings.gnubg_analysis_ply,
                cube_value=decision.cube_value,
                cube_owner=decision.cube_owner
            )

            return matrix_html

        except Exception as e:
            print(f"Warning: Failed to generate score matrix: {e}")
            return ""

    def _generate_note_html(self, decision: Decision) -> str:
        """Generate note HTML if a note exists."""
        if not decision.note:
            return ""

        # Escape HTML characters and preserve line breaks
        escaped_note = html.escape(decision.note)
        # Convert newlines to <br> tags for proper HTML display
        escaped_note = escaped_note.replace('\n', '<br>')

        return f"""
<div class="note-section">
    <h4>Note:</h4>
    <div class="note-content">{escaped_note}</div>
</div>
"""

    def _generate_source_info(self, decision: Decision) -> str:
        """Generate source information HTML."""
        if not decision.xgid and not decision.source_description:
            return ""

        xgid_html = f"<code>{decision.xgid}</code>" if decision.xgid else ""
        source_html = f'<span style="display: block; margin-top: 1em;">{decision.source_description}</span>' if decision.source_description else ""

        return f"""
<div class="source-info">
    <p>{xgid_html}{source_html}</p>
</div>
"""

    def _generate_tags(self, decision: Decision) -> List[str]:
        """Generate tags for the card."""
        tags = ["ankigammon", "backgammon"]

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
            score_x=decision.score_x,
            score_o=decision.score_o,
            match_length=decision.match_length,
        )

    def _render_resulting_position_svg(self, decision: Decision, move: Move) -> str:
        """Render the resulting position after a move as SVG markup."""
        if move.resulting_position:
            resulting_pos = move.resulting_position
        else:
            # On-roll player is at bottom after perspective transform
            move_player = Player.O
            resulting_pos = MoveParser.apply_move(
                decision.position,
                move.notation,
                move_player
            )

        return self.renderer.render_svg(
            position=resulting_pos,
            on_roll=decision.on_roll,
            dice=decision.dice,
            dice_opacity=0.3,
            cube_value=decision.cube_value,
            cube_owner=decision.cube_owner,
            score_x=decision.score_x,
            score_o=decision.score_o,
            match_length=decision.match_length,
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
