"""Generate Anki card content from XG decisions."""

import random
import string
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from xg2anki.models import Decision, Move, Player
from xg2anki.renderer.svg_board_renderer import SVGBoardRenderer
from xg2anki.utils.move_parser import MoveParser


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
        renderer: Optional[SVGBoardRenderer] = None
    ):
        """
        Initialize the card generator.

        Args:
            output_dir: Directory for configuration (no media files needed with SVG)
            show_options: If True, show interactive MCQ with clickable options
            interactive_moves: If True, render positions for all moves (clickable analysis)
            renderer: SVG board renderer instance (creates default if None)
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.show_options = show_options
        self.interactive_moves = interactive_moves
        self.renderer = renderer or SVGBoardRenderer()

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

        # Generate position SVG (before move)
        position_svg = self._render_position_svg(decision)

        # Prepare candidate moves
        from xg2anki.models import DecisionType

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

        if self.interactive_moves:
            # Render all candidate move positions for interactive visualization
            for candidate in candidates:
                if candidate:
                    result_svg = self._render_resulting_position_svg(decision, candidate)
                    move_result_svgs[candidate.notation] = result_svg
            result_svg = move_result_svgs.get(best_move.notation) if best_move else None
        else:
            # Only render the best move's resulting position
            if best_move:
                result_svg = self._render_resulting_position_svg(decision, best_move)
                move_result_svgs[best_move.notation] = result_svg
            else:
                result_svg = None

        # Generate card back
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
                sessionStorage.setItem('xg2anki-mcq-choice', selectedLetter);
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
        selectedLetter = sessionStorage.getItem('xg2anki-mcq-choice');
        sessionStorage.removeItem('xg2anki-mcq-choice');
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
    if (standardAnswer && standardAnswer.dataset.moveMap) {{
        try {{
            moveMap = JSON.parse(standardAnswer.dataset.moveMap);
        }} catch (e) {{}}
    }}

    if (selectedLetter) {{
        feedbackContainer.style.display = 'block';
        if (standardAnswer) standardAnswer.style.display = 'none';

        const selectedMove = moveMap[selectedLetter] || '';
        const correctMove = moveMap[correctLetter] || '';

        if (selectedLetter === correctLetter) {{
            feedbackContainer.innerHTML = `
                <div class="mcq-feedback-correct">
                    <div class="feedback-icon">✓</div>
                    <div class="feedback-text">
                        <strong>${{selectedLetter}} is Correct!</strong>
                    </div>
                </div>
            `;
        }} else {{
            feedbackContainer.innerHTML = `
                <div class="mcq-feedback-incorrect">
                    <div class="feedback-icon">✗</div>
                    <div class="feedback-text">
                        <div><strong>${{selectedLetter}} is Incorrect</strong> (${{selectedMove}}).</div>
                        <div style="margin-top: 8px;"><strong>Correct answer: ${{correctLetter}}</strong></div>
                        <div>${{correctMove}}</div>
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
                    row.classList.add(selectedLetter === correctLetter ? 'user-correct' : 'user-incorrect');
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
        move_result_svgs: Dict[str, str]
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

            if self.interactive_moves:
                row_class = f"{rank_class} move-row"
                svg_content = move_result_svgs.get(move.notation, '')
                svg_id = f"svg-{id(svg_content)}"
                row_attrs = f'data-move-notation="{move.notation}" data-svg-id="{svg_id}"'
            else:
                row_class = rank_class
                row_attrs = ""

            table_rows.append(f"""
<tr class="{row_class}" {row_attrs}>
    <td>{display_rank}</td>
    <td>{display_notation}</td>
    <td>{move.equity:.3f}</td>
    <td>{error_str}</td>
</tr>
""")

        # Generate answer section
        best_move = decision.get_best_move()
        best_notation = best_move.notation if best_move else "Unknown"

        if show_options:
            correct_letter = letters[answer_index] if answer_index < len(letters) else "?"

            import json
            letter_to_move = {}
            for i, move in enumerate(shuffled_candidates):
                if move and i < len(letters):
                    letter_to_move[letters[i]] = move.notation

            answer_html = f"""
    <div class="mcq-feedback-container" id="mcq-feedback" style="display: none;">
    </div>
    <div class="answer" id="mcq-standard-answer" data-correct-answer="{correct_letter}" data-move-map='{json.dumps(letter_to_move)}'>
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
            # Store all result SVGs in hidden divs and show one at a time
            svg_containers = []
            for notation, svg in move_result_svgs.items():
                svg_id = f"svg-{id(svg)}"
                display_style = "display: none;" if svg != result_position_svg else ""
                svg_containers.append(f'''
    <div class="position-svg-container" id="{svg_id}" style="{display_style}">
        {svg}
    </div>''')

            position_viewer_html = f'''
    <div class="position-viewer">
        <div class="position-svg-container" id="original-svg" style="display: none;">
            {original_position_svg}
        </div>
        {''.join(svg_containers)}
    </div>'''
            analysis_title = '<h4>Top Moves Analysis: <span class="click-hint">(click a move to see the resulting position)</span></h4>'
            table_body_id = 'id="moves-tbody"'
        else:
            position_viewer_html = f'''
    <div class="position-svg">
        {result_position_svg or original_position_svg}
    </div>'''
            analysis_title = '<h4>Top Moves Analysis:</h4>'
            table_body_id = ''

        html = f"""
<div class="card-back">
{position_viewer_html}
    <div class="metadata">{metadata}</div>
{answer_html}
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
    {self._generate_source_info(decision)}
</div>
"""

        if show_options:
            html += self._generate_mcq_back_javascript(correct_letter)

        if self.interactive_moves:
            html += """
<script>
(function() {
    const moveRows = document.querySelectorAll('.move-row');
    const svgContainers = document.querySelectorAll('.position-svg-container');
    let currentSelectedRow = null;

    // Initialize - highlight best move row
    const bestMoveRow = document.querySelector('.move-row.best-move');
    if (bestMoveRow) {
        bestMoveRow.classList.add('selected');
        currentSelectedRow = bestMoveRow;
    }

    moveRows.forEach(row => {
        row.addEventListener('click', function() {
            const svgId = this.dataset.svgId;

            if (!svgId) return;

            // If clicking the same row, toggle to original
            if (currentSelectedRow === this) {
                svgContainers.forEach(c => c.style.display = 'none');
                document.getElementById('original-svg').style.display = 'block';
                this.classList.remove('selected');
                currentSelectedRow = null;
                return;
            }

            // Show this move's resulting position
            svgContainers.forEach(c => c.style.display = 'none');
            document.getElementById('original-svg').style.display = 'none';
            const targetSvg = document.getElementById(svgId);
            if (targetSvg) targetSvg.style.display = 'block';

            // Update selection
            moveRows.forEach(r => r.classList.remove('selected'));
            this.classList.add('selected');
            currentSelectedRow = this;
        });
    });
})();
</script>
"""

        return html

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
        tags = ["xg2anki", "backgammon"]

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
