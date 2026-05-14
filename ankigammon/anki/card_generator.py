"""Generate Anki card content from XG decisions."""

import json
import logging
import random
import string
import html
from pathlib import Path
from typing import List, Dict, Optional, Tuple

from ankigammon.models import Decision, Move, Player, DecisionType, CubeState
from ankigammon.renderer.svg_board_renderer import SVGBoardRenderer
from ankigammon.renderer.animation_controller import AnimationController
from ankigammon.utils.move_parser import MoveParser
from ankigammon.settings import get_settings
from ankigammon.anki.decision_serialize import decision_to_json

logger = logging.getLogger(__name__)


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
        cancellation_callback: Optional[callable] = None,
        analyzer=None
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
            analyzer: Optional BackgammonAnalyzer instance for score matrix generation.
                      If None, one will be lazily created on first use. Pass an existing
                      instance to reuse a connection across multiple cards.
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.show_options = show_options
        self.interactive_moves = interactive_moves
        self.settings = get_settings()
        self._analyzer = analyzer

        # Create default renderer and animation controller with settings if not provided
        from ankigammon.renderer.color_schemes import get_scheme
        scheme = get_scheme(self.settings.color_scheme)
        if self.settings.swap_checker_colors:
            scheme = scheme.with_swapped_checkers()
        self.renderer = renderer or SVGBoardRenderer(
            color_scheme=scheme,
            orientation=self.settings.board_orientation
        )
        self.animation_controller = animation_controller or AnimationController(
            orientation=self.settings.board_orientation
        )

        self.progress_callback = progress_callback
        self.cancellation_callback = cancellation_callback

    def _get_analyzer(self):
        """Return the shared analyzer, lazily creating one if needed."""
        if self._analyzer is None:
            from ankigammon.utils.analyzer_base import create_analyzer
            self._analyzer = create_analyzer(self.settings)
        return self._analyzer

    def _analysis_label(self) -> str:
        """Return a display label for the current analyzer's depth setting."""
        analyzer_type = getattr(self.settings, 'analyzer_type', 'gnubg')
        if analyzer_type == "xg":
            return self.settings.xg_analysis_level.title()
        return f"{self.settings.gnubg_analysis_ply}-ply"

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

        # Randomize board orientation per card if "random" is selected
        if self.settings.board_orientation == "random":
            orientation = random.choice(["clockwise", "counter-clockwise"])
            from ankigammon.renderer.color_schemes import get_scheme
            scheme = get_scheme(self.settings.color_scheme)
            if self.settings.swap_checker_colors:
                scheme = scheme.with_swapped_checkers()
            self.renderer = SVGBoardRenderer(
                color_scheme=scheme,
                orientation=orientation
            )
            self.animation_controller = AnimationController(orientation=orientation)

        # Ensure decision has candidate moves
        if not decision.candidate_moves:
            raise ValueError(
                "Cannot generate card: decision has no candidate moves. "
                "For XGID-only input, use GnuBG analysis to populate moves."
            )

        # If split_cube_decisions is on and the import filter tagged this
        # decision with a single user_player, swap in a focused 2- or 3-option
        # MCQ (Roll/Double for the doubler, Take/Pass[/Beaver] for the receiver)
        # and render the board from the appropriate POV.
        cube_variant = self._maybe_build_cube_variant(decision)
        variant_candidates: Optional[List[Move]] = None
        variant_cube_value: Optional[int] = None
        variant_cube_offered: bool = False
        variant_flip_for_receiver: bool = False
        variant_kind: Optional[str] = None
        if cube_variant is not None:
            variant_candidates, _ = cube_variant
            variant_notations = {c.notation for c in variant_candidates if c}
            # Receiver take card: synthetic candidates are Take/Pass(/Beaver).
            # Show the doubled cube as an offered (unaccepted) cube — drawn
            # inside the playing area — and physically flip the position so
            # the receiver sits at the bottom (the parser put the doubler
            # there, which is what the existing 5-option card wants).
            if "Take" in variant_notations:
                variant_cube_value = decision.cube_value * 2
                variant_cube_offered = True
                variant_flip_for_receiver = True
                variant_kind = (
                    "receiver_with_beaver"
                    if "Beaver" in variant_notations
                    else "receiver"
                )
            else:
                variant_kind = "doubler"

        # Generate position SVG
        # Front uses the global show_pip_count setting; back always shows pip count
        # so the user can verify the answer regardless of the setting.
        position_svg_front = self._render_position_svg(
            decision,
            cube_value_override=variant_cube_value,
            cube_offered=variant_cube_offered,
            flip_for_receiver_pov=variant_flip_for_receiver,
        )
        position_svg_back = self._render_position_svg(
            decision,
            show_pip_count=True,
            cube_value_override=variant_cube_value,
            cube_offered=variant_cube_offered,
            flip_for_receiver_pov=variant_flip_for_receiver,
        )

        # Prepare candidate moves
        max_options = self.settings.max_moves
        if decision.decision_type == DecisionType.CUBE_ACTION:
            # Cube decisions always show all 5 actions in the analysis table
            candidates = decision.candidate_moves[:5]
        else:
            candidates = decision.candidate_moves[:max_options]

        # Shuffle candidates for MCQ (preserve order for cube decisions and variants).
        # For split-cube variants, the front-of-card MCQ uses the focused 2- or 3-option
        # set while the back-of-card analysis table still shows the full 5-option set.
        if variant_candidates is not None:
            shuffled_candidates = variant_candidates
            answer_index = next(
                (i for i, c in enumerate(variant_candidates) if c and c.rank == 1), 0
            )
        elif decision.decision_type == DecisionType.CUBE_ACTION:
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
            # Render only the best move's resulting position (back card).
            # For split-cube variants the synthetic moves don't represent
            # checker plays, so we just re-render the original position from
            # the variant's POV.
            if variant_candidates is not None:
                result_svg = position_svg_back
            elif best_move:
                result_svg = self._render_resulting_position_svg(
                    decision, best_move, show_pip_count=True,
                )
            else:
                result_svg = None
        else:
            # Render all move results for interactive visualization and/or preview.
            # Front previews follow the user's show_pip_count setting,
            # back-card interactive renders always show pip count.
            if preview_enabled:
                for candidate in shuffled_candidates:
                    if candidate:
                        result_svg_for_move = self._render_resulting_position_svg(
                            decision, candidate
                        )
                        move_result_svgs_front[candidate.notation] = result_svg_for_move

            if self.interactive_moves and variant_candidates is None:
                # Skip per-move rendering for split-cube variants — synthetic
                # cube actions (Roll/Double/Take/Pass/Beaver) have no resulting
                # checker positions to show.
                for candidate in candidates:
                    if candidate:
                        result_svg_for_move = self._render_resulting_position_svg(
                            decision, candidate, show_pip_count=True,
                        )
                        move_result_svgs[candidate.notation] = result_svg_for_move

            result_svg = None

        # Generate card front
        if self.show_options:
            front_html = self._generate_interactive_mcq_front(
                decision, position_svg_front, shuffled_candidates, move_result_svgs_front
            )
        else:
            front_html = self._generate_simple_front(
                decision, position_svg_front, variant_kind=variant_kind
            )

        # Generate card back
        back_html = self._generate_back(
            decision, position_svg_back, result_svg, candidates, shuffled_candidates,
            answer_index, self.show_options, move_result_svgs
        )

        # Generate tags
        tags = self._generate_tags(decision)

        return {
            'front': front_html,
            'back': back_html,
            'tags': tags,
            'xgid': decision.xgid or '',
            'analysis_data': decision_to_json(decision),
        }

    def _get_metadata_html(self, decision: Decision) -> str:
        """
        Get metadata HTML with colored player indicator.

        Returns HTML with inline colored circle representing the checker color.
        """
        base_metadata = decision.get_metadata_text(score_format=self.settings.score_format)

        # On-roll player uses bottom color after perspective transform
        checker_color = self.renderer.color_scheme.checker_o

        # Replace "Black" with colored circle
        colored_circle = f'<span style="color: {checker_color}; font-size: 1.8em;">●</span>'
        metadata_html = base_metadata.replace("Black", colored_circle)

        return metadata_html

    def _generate_simple_front(
        self,
        decision: Decision,
        position_svg: str,
        variant_kind: Optional[str] = None,
    ) -> str:
        """Generate HTML for simple front (no options).

        variant_kind: when the caller built a split-cube variant, "doubler" or
        "receiver" / "receiver_with_beaver" picks the appropriate question text.
        None means the standard cube/checker question is shown.
        """
        metadata = self._get_metadata_html(decision)

        if variant_kind == "doubler":
            question_text = "Should you double or roll?"
        elif variant_kind == "receiver_with_beaver":
            question_text = "Take, pass, or beaver?"
        elif variant_kind == "receiver":
            question_text = "Take or pass?"
        elif decision.decision_type == DecisionType.CUBE_ACTION:
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

        # Determine question text based on decision type and (optionally) split-cube variant.
        candidate_notations = {c.notation for c in candidates if c}
        if {"Roll", "Double"} <= candidate_notations:
            question_text = "Should you double or roll?"
        elif "Take" in candidate_notations and "Pass" in candidate_notations:
            question_text = (
                "Take, pass, or beaver?"
                if "Beaver" in candidate_notations
                else "Take or pass?"
            )
        elif decision.decision_type == DecisionType.CUBE_ACTION:
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
    <div class="mcq-layout">
        <div class="mcq-board-section">
            <div class="position-svg" {position_container_id}>
                {position_svg}
            </div>
        </div>
        <div class="mcq-options-section">
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
            # Simple mode - store choice on body element, try auto-flip
            return """
(function() {
    var options = document.querySelectorAll('.mcq-option');

    options.forEach(function(option) {
        option.addEventListener('click', function() {
            var selectedLetter = this.dataset.optionLetter;

            // Store selection on body element (persists between front/back on all platforms)
            document.body.dataset.ankigammonChoice = selectedLetter;

            // Visual feedback before flip
            this.classList.add('selected-flash');

            // Try to auto-flip (works on Desktop/AnkiDroid, not AnkiWeb)
            setTimeout(function() {
                if (typeof pycmd !== 'undefined') {
                    pycmd('ans');
                } else if (typeof showAnswer === 'function') {
                    showAnswer();
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
    // Read selection from body element (set by front card)
    var selectedLetter = document.body.dataset.ankigammonChoice || null;
    // Clear after reading
    if (selectedLetter) {{
        document.body.dataset.ankigammonChoice = '';
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
            // Check cells[0] for cube decisions (Action | Equity | Error)
            // or cells[1] for checker plays (Rank | Move | Equity | Error)
            let moveText = '';
            if (row.cells[0]) {{
                const firstCellText = row.cells[0].textContent.trim();
                // If first cell contains "/" it's a cube action notation
                if (firstCellText.includes('/')) {{
                    moveText = firstCellText;
                }} else if (row.cells[1]) {{
                    moveText = row.cells[1].textContent.trim();
                }}
            }}
            if (moveText === selectedMove) {{
                if (selectedLetter === correctLetter) {{
                    row.classList.add('user-correct');
                }} else if (selectedError < CLOSE_THRESHOLD) {{
                    row.classList.add('user-close');
                }} else {{
                    row.classList.add('user-incorrect');
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
            # Sort checker plays first by analysis tier (descending — higher
            # tier shown first) and then by error magnitude within tier. This
            # keeps a noisy lower-tier eval from sliding above a deeper eval
            # in the displayed ranking just because its raw equity happens
            # to look favorable.
            sorted_candidates = sorted(
                analysis_moves,
                key=lambda m: (
                    -m.analysis_tier_rank(),
                    abs(m.error) if m.error is not None else 999.0,
                )
            )

        # Get best equity for calculating signed errors
        best_move = decision.get_best_move()
        best_equity = best_move.equity if best_move else 0.0
        # Keep original best equity for MCQ error calculations (before any adjustment)
        mcq_best_equity = best_equity

        # For "too good" scenarios, use No Double equity as the baseline for ANALYSIS TABLE
        # (XG convention: errors are relative to the best actual action, which is No Double)
        # Also track which displayed move should be marked as "best" for highlighting
        # NOTE: This adjustment is ONLY for the analysis table display, NOT for MCQ feedback
        best_displayed_move = None
        if best_move and best_move.notation.startswith("Too good"):
            no_double_move = next(
                (m for m in candidates if m.notation.startswith("No ")), None
            )
            if no_double_move:
                best_equity = no_double_move.equity
                best_displayed_move = no_double_move

        for i, move in enumerate(sorted_candidates):
            # For "too good" scenarios, highlight No Double as best; otherwise use rank == 1
            is_best = (move == best_displayed_move) if best_displayed_move else (move.rank == 1)
            rank_class = "best-move" if is_best else ""
            display_rank = move.xg_rank if move.xg_rank is not None else (i + 1)
            display_error = move.xg_error if move.xg_error is not None else move.error
            display_notation = move.xg_notation if move.xg_notation is not None else move.notation

            # For cube decisions, use signed error (equity - best_equity)
            # For checker plays, always show negative error
            if is_cube_decision:
                signed_error = move.equity - best_equity
                error_str = f"{signed_error:+.3f}" if signed_error != 0 else "0.000"
                abs_error = abs(signed_error)
            else:
                error_str = f"{-abs(display_error):+.3f}" if display_error != 0 else "0.000"
                abs_error = abs(display_error) if display_error else 0.0

            # Color-code row by error magnitude
            if abs_error >= 0.020 and abs_error <= 0.080:
                error_class = "error-minor"
            elif abs_error > 0.080:
                error_class = "error-blunder"
            else:
                error_class = ""

            # Add played indicator if this move was played
            played_indicator = ' <span class="played-indicator">← Played</span>' if move.was_played else ""

            # Subtle analysis-tier badge. Set when the parser knows the per-move
            # evaluation depth (e.g. "4-ply", "Rollout", "Screening"). Lets the
            # user spot moves whose equity is from a weaker analysis tier.
            level_badge = (
                f' <span class="analysis-level">{move.analysis_level}</span>'
                if move.analysis_level else ""
            )

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

            # Build td class attribute for error coloring (applied to each td)
            td_error_attr = f' class="{error_class}"' if error_class else ""

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

            # Format equity cell with data attributes for column toggle
            equity_classes = f"equity-cell {error_class}".strip() if move.cubeless_equity is not None else error_class
            if move.cubeless_equity is not None:
                equity_cell = f'<td class="{equity_classes}" data-cubeful="{move.equity:.3f}" data-cubeless="{move.cubeless_equity:.3f}">{move.equity:.3f}</td>'
            elif error_class:
                equity_cell = f'<td class="{error_class}">{move.equity:.3f}</td>'
            else:
                equity_cell = f'<td>{move.equity:.3f}</td>'

            # Cube decisions omit rank column
            if is_cube_decision:
                table_rows.append(f"""
<tr class="{row_class}" {row_attrs}>
    <td{td_error_attr}>
        <div class="move-notation">{display_notation}{played_indicator}{level_badge}</div>{wgb_inline_html}
    </td>
    {equity_cell}
    <td{td_error_attr}>{error_str}</td>
</tr>""")
            else:
                table_rows.append(f"""
<tr class="{row_class}" {row_attrs}>
    <td{td_error_attr}>{display_rank}</td>
    <td{td_error_attr}>
        <div class="move-notation">{display_notation}{played_indicator}{level_badge}</div>{wgb_inline_html}
    </td>
    {equity_cell}
    <td{td_error_attr}>{error_str}</td>
</tr>""")

        # Generate answer section
        best_notation = best_move.notation if best_move else "Unknown"

        if show_options:
            correct_letter = letters[answer_index] if answer_index < len(letters) else "?"

            import json
            letter_to_move = {}
            letter_to_error = {}
            for i, move in enumerate(shuffled_candidates):
                if move and i < len(letters):
                    letter_to_move[letters[i]] = move.notation
                    # For cube decisions: Each option represents a distinct strategic concept.
                    # "Close" based on equity doesn't apply - only the exact correct answer is correct.
                    # Each cube action has a different equity and meaning (e.g., Double/Pass = 1.000,
                    # Too good/Pass = No Double equity which is higher when position is "too good").
                    if is_cube_decision:
                        # Set error to 0 only for the correct answer, high error for all others
                        if i == answer_index:
                            corrected_error = 0.0
                        else:
                            # Use a high error to ensure all wrong answers are INCORRECT, not CLOSE
                            corrected_error = 1.0
                    else:
                        # For checker plays, use equity-based error (close moves are similar)
                        corrected_error = abs(move.equity - mcq_best_equity) if move.equity is not None else 0.0
                    letter_to_error[letters[i]] = corrected_error

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

        # Check if any moves have cubeless equity for toggle functionality
        has_cubeless = any(m and m.cubeless_equity is not None for m in sorted_candidates)
        equity_header = '<th class="equity-header" data-mode="cubeful">Equity</th>' if has_cubeless else '<th>Equity</th>'

        # Prepare table headers based on decision type
        if is_cube_decision:
            table_headers = f"""
                    <tr>
                        <th>Action</th>
                        {equity_header}
                        <th>Error</th>
                    </tr>"""
        else:
            table_headers = f"""
                    <tr>
                        <th>Rank</th>
                        <th>Move</th>
                        {equity_header}
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

        # Generate score matrix for cube decisions if enabled (works for both
        # match play and unlimited games — the latter gets a hypothetical projection)
        score_matrix_html = ''
        if is_cube_decision and self.settings.generate_score_matrix:
            score_matrix_html = self._generate_score_matrix_html(decision)
            if score_matrix_html:
                score_matrix_html = f"\n{score_matrix_html}"

        # Generate move score matrix for checker play if enabled
        move_matrix_html = ''
        if not is_cube_decision and self.settings.generate_move_score_matrix:
            move_matrix_html = self._generate_move_score_matrix_html(decision)
            if move_matrix_html:
                move_matrix_html = f"\n{move_matrix_html}"

        # Generate note HTML if note exists
        note_html = self._generate_note_html(decision)

        html = f"""
<div class="card-back">
{position_viewer_html}
    <div class="metadata">{metadata}</div>
{answer_html}
{note_html}
{analysis_and_chances}{score_matrix_html}{move_matrix_html}
    {self._generate_source_info(decision)}
</div>
"""

        if show_options:
            html += self._generate_mcq_back_javascript(correct_letter)

        if self.interactive_moves:
            # Generate animation scripts
            animation_scripts = self._generate_checker_animation_scripts(decision, candidates, move_result_svgs or {})
            html += animation_scripts

        # Add equity toggle script if any moves have cubeless equity
        has_cubeless = any(m and m.cubeless_equity is not None for m in candidates)
        if has_cubeless:
            html += self._generate_equity_toggle_script()

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

                // Reset toggle state and remove icon when selecting a new move
                showingOriginal = false;
                removeRevertIcon();

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

                // Store selection on body element (persists between front/back on all platforms)
                document.body.dataset.ankigammonChoice = currentSelectedLetter;

                // Visual feedback
                if (currentSelectedOption) {
                    currentSelectedOption.classList.add('selected-flash');
                }

                // Trigger Anki flip to back side
                // Note: AnkiWeb and AnkiMobile have no JS API - users must manually flip
                setTimeout(function() {
                    if (typeof pycmd !== 'undefined') {
                        pycmd('ans');  // Anki desktop
                    } else if (typeof showAnswer === 'function') {
                        showAnswer();  // AnkiDroid (signal-based function from card.js)
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
    let currentResultHTML = null;
    let showingOriginal = false;

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

    // Store current result HTML for toggle
    function storeCurrentResult() {{
        const board = document.getElementById('animated-board');
        if (board) {{
            currentResultHTML = board.innerHTML;
        }}
    }}

    // Remove any existing revert icon
    function removeRevertIcon() {{
        const existing = document.querySelector('.revert-icon');
        if (existing) existing.remove();
    }}

    // Add revert icon to the selected row
    function addRevertIconToRow(row) {{
        removeRevertIcon();
        if (!row) return;

        const icon = document.createElement('span');
        icon.className = 'revert-icon';
        icon.dataset.tip = 'Show original position';
        icon.innerHTML = '<svg viewBox="0 0 24 24"><path d="M12.5 8c-2.65 0-5.05.99-6.9 2.6L2 7v9h9l-3.62-3.62c1.39-1.16 3.16-1.88 5.12-1.88 3.54 0 6.55 2.31 7.6 5.5l2.37-.78C21.08 11.03 17.15 8 12.5 8z"/></svg>';

        icon.addEventListener('click', function(e) {{
            e.stopPropagation();
            togglePosition();
        }});

        row.appendChild(icon);
    }}

    // Update revert icon state
    function updateRevertIcon(isShowingOriginal) {{
        const icon = document.querySelector('.revert-icon');
        if (!icon) return;

        if (isShowingOriginal) {{
            icon.classList.add('showing-original');
            icon.dataset.tip = 'Show position after move';
        }} else {{
            icon.classList.remove('showing-original');
            icon.dataset.tip = 'Show original position';
        }}
    }}

    // Toggle between original and result positions
    function togglePosition() {{
        const board = document.getElementById('animated-board');
        if (!board) return;

        if (showingOriginal) {{
            // Switch back to result
            if (currentResultHTML) {{
                board.innerHTML = currentResultHTML;
            }}
            showingOriginal = false;
        }} else {{
            // Store current result before switching
            storeCurrentResult();
            // Switch to original
            if (originalBoardHTML) {{
                board.innerHTML = originalBoardHTML;
            }}
            showingOriginal = true;
        }}

        updateRevertIcon(showingOriginal);
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

                // Store result for toggle functionality and add revert icon to selected row
                storeCurrentResult();
                showingOriginal = false;
                addRevertIconToRow(currentSelectedRow);
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

    def _generate_equity_toggle_script(self) -> str:
        """Generate JavaScript for equity column toggle functionality."""
        return """
<script>
(function() {
    var header = document.querySelector('.equity-header');
    var table = document.querySelector('.moves-table');
    if (!header || !table) return;

    var cells = document.querySelectorAll('.equity-cell');

    function toggleEquity() {
        var mode = header.dataset.mode;
        if (mode === 'cubeful') {
            header.textContent = 'Cubeless';
            header.dataset.mode = 'cubeless';
            table.classList.add('showing-cubeless');
            cells.forEach(function(cell) {
                cell.textContent = cell.dataset.cubeless;
            });
        } else {
            header.textContent = 'Equity';
            header.dataset.mode = 'cubeful';
            table.classList.remove('showing-cubeless');
            cells.forEach(function(cell) {
                cell.textContent = cell.dataset.cubeful;
            });
        }
    }

    function addHover() { table.classList.add('equity-hover'); }
    function removeHover() { table.classList.remove('equity-hover'); }

    header.addEventListener('click', toggleEquity);
    header.addEventListener('mouseenter', addHover);
    header.addEventListener('mouseleave', removeHover);

    cells.forEach(function(cell) {
        cell.addEventListener('click', function(e) {
            e.stopPropagation();
            toggleEquity();
        });
        cell.addEventListener('mouseenter', addHover);
        cell.addEventListener('mouseleave', removeHover);
    });
})();
</script>
"""

    def _format_wgb_inline(self, move: Move, decision: Decision) -> str:
        """
        Generate inline HTML for W/G/B percentages to display within move table cell.

        Returns HTML with two lines showing player and opponent win/gammon/backgammon percentages.
        Returns empty string if move has no W/G/B data.
        """
        if move.player_win_pct is None:
            return ""

        # On-roll player is always at bottom after perspective transform
        player_color = self.renderer.color_scheme.checker_o
        opponent_color = self.renderer.color_scheme.checker_x

        wgb_html = f'''
        <div class="move-wgb-inline">
            <div class="wgb-line">
                <span style="color: {player_color};">●</span> P: <strong>{move.player_win_pct:.1f}%</strong> <span class="wgb-detail">(G:{move.player_gammon_pct:.1f}% B:{move.player_backgammon_pct:.1f}%)</span>
            </div>
            <div class="wgb-line">
                <span style="color: {opponent_color};">●</span> O: <strong>{move.opponent_win_pct:.1f}%</strong> <span class="wgb-detail">(G:{move.opponent_gammon_pct:.1f}% B:{move.opponent_backgammon_pct:.1f}%)</span>
            </div>
        </div>'''

        return wgb_html

    def _generate_winning_chances_html(self, decision: Decision) -> str:
        """
        Generate HTML for winning chances display (W/G/B percentages).

        Shows player and opponent winning chances with gammon and backgammon percentages.
        Also shows cubeless equity and doubled cubeless equity if available.
        Note: Title is added separately in side-by-side layout.
        """
        # On-roll player is always at bottom after perspective transform
        player_color = self.renderer.color_scheme.checker_o
        opponent_color = self.renderer.color_scheme.checker_x

        # Generate cubeless equity section if available (collapsed by default)
        cubeless_html = ''
        if decision.cubeless_equity is not None:
            # Use stored double_cubeless_equity if available, fallback to 2× for money games
            doubled_cubeless = decision.double_cubeless_equity if decision.double_cubeless_equity is not None else decision.cubeless_equity * 2
            cubeless_html = f'''
                <details class="cubeless-equity-details">
                    <summary>Cubeless Equity</summary>
                    <div class="cubeless-equity-content">
                        <div class="equity-row">
                            <span class="equity-label">Cubeless:</span>
                            <span class="equity-value">{decision.cubeless_equity:+.3f}</span>
                        </div>
                        <div class="equity-row">
                            <span class="equity-label">Doubled:</span>
                            <span class="equity-value">{doubled_cubeless:+.3f}</span>
                        </div>
                    </div>
                </details>'''

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
                </div>{cubeless_html}
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
        analyzer_type = getattr(self.settings, 'analyzer_type', 'gnubg')
        if analyzer_type == "xg":
            if not self.settings.is_xg_available():
                return ""
        else:
            if not self.settings.is_gnubg_available():
                return ""

        try:
            from ankigammon.analysis.score_matrix import (
                generate_score_matrix,
                format_matrix_as_html,
                resolve_effective_match_length,
            )

            max_size = getattr(self.settings, 'score_matrix_max_size', 0)
            effective_ml = resolve_effective_match_length(decision.match_length, max_size)
            is_projection = decision.match_length == 0

            # generate_score_matrix requires match_length >= 2; this guards 1-point
            # matches (decision.match_length == 1) — silently disabled here rather
            # than raised downstream, since a 1pt match has no cube action to study.
            if effective_ml < 2:
                return ""

            # Current-cell highlight only makes sense for real match games, and only
            # when the live away coordinates fall inside the (possibly capped) matrix.
            # When they don't, surface a caption so the reader knows the matrix
            # doesn't cover their actual current position.
            current_player_away = None
            current_opponent_away = None
            caption = None
            if not is_projection:
                player_away = decision.match_length - (
                    decision.score_o if decision.on_roll == Player.O else decision.score_x
                )
                opponent_away = decision.match_length - (
                    decision.score_x if decision.on_roll == Player.O else decision.score_o
                )
                # min_away mirrors generate_score_matrix's cube-live floor
                min_away = decision.cube_value + 1
                if (min_away <= player_away <= effective_ml and
                        min_away <= opponent_away <= effective_ml):
                    current_player_away = player_away
                    current_opponent_away = opponent_away
                else:
                    caption = (
                        f"Current score ({player_away}-away / {opponent_away}-away) "
                        "is outside the displayed range."
                    )

            matrix = generate_score_matrix(
                xgid=decision.xgid,
                match_length=effective_ml,
                analyzer=self._get_analyzer(),
                progress_callback=self.progress_callback,
                cancellation_callback=self.cancellation_callback,
                cube_value=decision.cube_value,
                cube_owner=decision.cube_owner
            )

            matrix_html = format_matrix_as_html(
                matrix=matrix,
                current_player_away=current_player_away,
                current_opponent_away=current_opponent_away,
                analysis_label=self._analysis_label(),
                cube_value=decision.cube_value,
                cube_owner=decision.cube_owner,
                caption=caption,
            )

            return matrix_html

        except InterruptedError:
            # Cancellation must propagate so the export worker can stop cleanly
            raise
        except Exception:
            logger.exception("Failed to generate score matrix for xgid=%r", decision.xgid)
            return ""

    def _generate_move_score_matrix_html(self, decision: Decision) -> str:
        """
        Generate move score matrix HTML for checker play decisions.

        Shows top 3 moves at 4 different score contexts:
        - Neutral (money)
        - DMP (double match point)
        - Gammon-Save (player ahead, needs to save gammons)
        - Gammon-Go (player behind, wants gammons)

        Args:
            decision: The checker play decision

        Returns:
            HTML string with move score matrix, or empty string if unavailable
        """
        # Check analyzer availability
        analyzer_type = getattr(self.settings, 'analyzer_type', 'gnubg')
        if analyzer_type == "xg":
            if not self.settings.is_xg_available():
                return ""
        else:
            if not self.settings.is_gnubg_available():
                return ""

        # Only for checker play decisions
        if decision.decision_type != DecisionType.CHECKER_PLAY:
            return ""

        # Skip if no dice (shouldn't happen for checker play)
        if not decision.dice:
            return ""

        try:
            from ankigammon.analysis.move_score_matrix import (
                generate_move_score_matrix,
                format_move_matrix_as_html
            )

            columns = generate_move_score_matrix(
                xgid=decision.xgid,
                analyzer=self._get_analyzer(),
                max_moves=self.settings.max_moves,
                progress_callback=self.progress_callback,
                cancellation_callback=self.cancellation_callback
            )

            return format_move_matrix_as_html(
                columns=columns,
                analysis_label=self._analysis_label()
            )

        except Exception as e:
            print(f"Warning: Failed to generate move score matrix: {e}")
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

        if decision.xgid:
            xgid_html = f"""<span class="xgid-container">
    <code class="xgid-text">{decision.xgid}</code>
    <button class="xgid-copy-btn" data-tip="Copy XGID">
        <svg class="copy-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
        </svg>
        <svg class="check-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="display:none;">
            <polyline points="20 6 9 17 4 12"></polyline>
        </svg>
    </button>
</span>"""
        else:
            xgid_html = ""
        source_html = f'<span style="display: block; margin-top: 1em;">{decision.source_description}</span>' if decision.source_description else ""

        return f"""
<div class="source-info">
    <p>{xgid_html}{source_html}</p>
</div>
<script>
(function() {{
    var copyBtn = document.querySelector('.xgid-copy-btn');
    if (!copyBtn) return;

    copyBtn.addEventListener('click', function() {{
        var xgidText = this.previousElementSibling.textContent;
        var btn = this;

        // Fallback copy method using textarea
        var textarea = document.createElement('textarea');
        textarea.value = xgidText;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();

        try {{
            document.execCommand('copy');
            // Show success state
            btn.classList.add('copied');
            btn.querySelector('.copy-icon').style.display = 'none';
            btn.querySelector('.check-icon').style.display = 'block';
            setTimeout(function() {{
                btn.classList.remove('copied');
                btn.querySelector('.copy-icon').style.display = 'block';
                btn.querySelector('.check-icon').style.display = 'none';
            }}, 1500);
        }} catch(e) {{
            console.log('Copy failed:', e);
        }}

        document.body.removeChild(textarea);
    }});
}})();
</script>
"""

    def _generate_tags(self, decision: Decision) -> List[str]:
        """Generate tags for the card."""
        tags = ["ankigammon", "backgammon"]

        tags.append(decision.decision_type.value)

        if decision.match_length > 0:
            tags.append(f"match_{decision.match_length}pt")
        else:
            tags.append("unlimited_game")

        if decision.cube_value > 1:
            tags.append(f"cube_{decision.cube_value}")

        return tags

    @staticmethod
    def _flip_position_for_pov(position):
        """Return a flipped copy of the position swapping X/O semantics.

        Mirrors the same flip the XG binary parser applies when the doubler is
        X (xg_binary_parser.py:1048-1063). Used to invert the player at the
        bottom of the rendered board — needed for receiver-POV take cards,
        since the parser has already flipped the position to put the doubler
        at the bottom (Player.O slot) and we need the receiver there instead.
        """
        from ankigammon.models import Position
        flipped = Position()
        flipped.points = [0] * 26
        flipped.points[0] = -position.points[25]
        flipped.points[25] = -position.points[0]
        for i in range(1, 25):
            flipped.points[i] = -position.points[25 - i]
        flipped.x_off = position.o_off
        flipped.o_off = position.x_off
        return flipped

    def _maybe_build_cube_variant(
        self, decision: Decision
    ) -> Optional[Tuple[List[Move], Optional[Player]]]:
        """Build a focused doubler-only or receiver-only cube card variant.

        Returns (synthetic_candidates, view_from) when split_cube_decisions is
        enabled and the decision was tagged with a single user_player at import
        filter time. Returns None otherwise — caller falls through to the
        standard 5-option cube card.

        Variants:
          - Doubler-only (user is on roll): 2-option MCQ {Roll, Double},
            board rendered with default doubler POV (view_from=None).
          - Receiver-only (user is the responder): {Take, Pass} or
            {Take, Pass, Beaver} for unlimited games when the analyzer flagged
            decision.beaverable. Board rendered from receiver POV (view_from
            set to the responder).
        """
        if not self.settings.split_cube_decisions:
            return None
        if decision.decision_type != DecisionType.CUBE_ACTION:
            return None
        if decision.user_player is None:
            return None

        doubler = decision.on_roll
        responder = Player.X if doubler == Player.O else Player.O
        best = decision.get_best_move()
        if best is None:
            return None

        by_notation = {m.notation: m for m in decision.candidate_moves}
        nd_move = by_notation.get("No Double/Take")
        dt_move = by_notation.get("Double/Take")
        dp_move = by_notation.get("Double/Pass")
        if not (nd_move and dt_move and dp_move):
            return None

        best_lower = best.notation.lower()

        if decision.user_player == doubler:
            roll_correct = (
                "no double" in best_lower or "too good" in best_lower
            )
            # When doubling, an optimal receiver picks the response worst for
            # the doubler — so the doubler's expected equity is min(DT, DP).
            doubling_equity = min(dt_move.equity, dp_move.equity)
            best_equity = max(nd_move.equity, doubling_equity)

            roll_move = Move(
                notation="Roll",
                equity=nd_move.equity,
                error=abs(best_equity - nd_move.equity),
                rank=1 if roll_correct else 2,
                from_xg_analysis=False,
            )
            double_move = Move(
                notation="Double",
                equity=doubling_equity,
                error=abs(best_equity - doubling_equity),
                rank=2 if roll_correct else 1,
                from_xg_analysis=False,
            )
            return ([roll_move, double_move], None)

        if decision.user_player == responder:
            # Equities are kept from the doubler's POV (matching the rest of
            # the analysis tables) but ranking reflects what the receiver
            # should do.
            # Beaver is the right answer only when the analyzer flagged the
            # take as beaverable AND the rule is on for this game.
            is_beaver_correct = bool(decision.beaverable and decision.beavers_allowed)
            is_pass_correct = "pass" in best_lower

            # Synthetic equities from receiver POV (negate doubler equities).
            take_eq = -dt_move.equity
            pass_eq = -dp_move.equity

            take_move = Move(
                notation="Take",
                equity=take_eq,
                error=0.0,
                rank=2,
                from_xg_analysis=False,
            )
            pass_move = Move(
                notation="Pass",
                equity=pass_eq,
                error=0.0,
                rank=2,
                from_xg_analysis=False,
            )
            candidates = [take_move, pass_move]

            beaver_move: Optional[Move] = None
            # beavers_allowed already encodes the match_length==0 precondition
            # — parsers gate it on match_length, and GameRules.__post_init__
            # rejects beavers_allowed=True in match play.
            if decision.beavers_allowed:
                # After a beaver the cube doubles for the receiver. The
                # receiver's equity is approximately 2x the take equity.
                beaver_move = Move(
                    notation="Beaver",
                    equity=take_eq * 2,
                    error=0.0,
                    rank=2,
                    from_xg_analysis=False,
                )
                candidates.append(beaver_move)

            if is_beaver_correct and beaver_move is not None:
                beaver_move.rank = 1
                best_eq = beaver_move.equity
            elif is_pass_correct:
                pass_move.rank = 1
                best_eq = pass_move.equity
            else:
                take_move.rank = 1
                best_eq = take_move.equity

            for m in candidates:
                m.error = abs(best_eq - m.equity)

            # Receiver POV: invert the default cube-card flipped flag so the
            # receiver — not the doubler — drives score/cube placement. The
            # renderer derives `flipped` from view_from when set, so passing
            # the responder as view_from inverts flipped relative to the
            # default (which is keyed off on_roll = doubler).
            return (candidates, responder)

        return None

    def _render_position_svg(
        self,
        decision: Decision,
        show_pip_count: Optional[bool] = None,
        view_from: Optional[Player] = None,
        cube_value_override: Optional[int] = None,
        cube_offered: bool = False,
        flip_for_receiver_pov: bool = False,
    ) -> str:
        """Render position as SVG markup.

        show_pip_count overrides the global setting (None = use setting).
        Back-card renders pass True so pip counts always appear on the answer side.
        view_from forces a non-default POV (used for receiver-POV cube take cards).
        cube_value_override displays a different cube value (e.g. doubled for take cards).
        cube_offered draws the cube inside the playing area to indicate an
        unaccepted double offer, instead of the side-area "owned" placement.
        flip_for_receiver_pov physically flips the position (and swaps scores,
        bears-off, cube ownership) so the receiver — currently in the Player.X
        slot post-parser-flip — visually sits at the bottom (Player.O slot).
        """
        position = decision.position
        score_x = decision.score_x
        score_o = decision.score_o
        on_roll = decision.on_roll
        cube_owner = decision.cube_owner

        if flip_for_receiver_pov:
            position = self._flip_position_for_pov(position)
            score_x, score_o = score_o, score_x
            # on_roll flips: X ↔ O. Cube owner X↔O too (CENTERED stays).
            on_roll = Player.O if on_roll == Player.X else Player.X
            if cube_owner == CubeState.X_OWNS:
                cube_owner = CubeState.O_OWNS
            elif cube_owner == CubeState.O_OWNS:
                cube_owner = CubeState.X_OWNS

        return self.renderer.render_svg(
            position=position,
            on_roll=on_roll,
            dice=decision.dice,
            cube_value=(
                cube_value_override if cube_value_override is not None else decision.cube_value
            ),
            cube_owner=cube_owner,
            score_x=score_x,
            score_o=score_o,
            match_length=decision.match_length,
            score_format=self.settings.score_format,
            show_pip_count=show_pip_count,
            view_from=view_from,
            cube_offered=cube_offered,
        )

    def _render_resulting_position_svg(
        self,
        decision: Decision,
        move: Move,
        show_pip_count: Optional[bool] = None,
        view_from: Optional[Player] = None,
        cube_value_override: Optional[int] = None,
        cube_offered: bool = False,
    ) -> str:
        """Render the resulting position after a move as SVG markup.

        show_pip_count overrides the global setting (None = use setting).
        view_from forces a non-default POV (used for receiver-POV cube take cards).
        """
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
            cube_value=(
                cube_value_override if cube_value_override is not None else decision.cube_value
            ),
            cube_owner=decision.cube_owner,
            score_x=decision.score_x,
            score_o=decision.score_o,
            match_length=decision.match_length,
            score_format=self.settings.score_format,
            show_pip_count=show_pip_count,
            view_from=view_from,
            cube_offered=cube_offered,
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
