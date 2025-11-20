"""
Score matrix generation for cube decisions.

Generates matrices showing optimal cube actions across all score combinations
in a match (e.g., 2a-2a through 7a-7a for a 7-point match).
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ScoreMatrixCell:
    """Represents one cell in the score matrix."""

    player_away: int  # Player on roll's score (away from match)
    opponent_away: int  # Opponent's score (away from match)
    best_action: str  # "D/T", "D/P", "N/T", "TG/T", "TG/P"
    error_no_double: Optional[float]  # Error if don't double
    error_double: Optional[float]  # Error if double/take
    error_pass: Optional[float]  # Error if pass

    def format_errors(self) -> str:
        """
        Format error values for display in matrix.

        Always displays errors in order: ND, D/T, D/P (skipping the cell's best action).
        For example:
        - N/T cell: shows D/T error, then D/P error
        - D/T cell: shows ND error, then D/P error
        - D/P cell: shows ND error, then D/T error

        Returns:
            String like "24/543" (errors scaled by 1000), or "—" if no alternatives exist
        """
        if self.error_no_double is None and self.error_double is None and self.error_pass is None:
            return "—"

        def scale_error(error: Optional[float]) -> int:
            return int(round(error * 1000)) if error is not None else 0

        nd_error = scale_error(self.error_no_double)
        dt_error = scale_error(self.error_double)
        dp_error = scale_error(self.error_pass)

        best_action_upper = self.best_action.upper()

        if best_action_upper in ["N/T", "TG/T", "TG/P"]:
            displayed_errors = [dt_error, dp_error]
        elif best_action_upper == "D/T":
            displayed_errors = [nd_error, dp_error]
        elif best_action_upper == "D/P":
            displayed_errors = [nd_error, dt_error]
        else:
            displayed_errors = [nd_error, dt_error]

        if self.error_double is None and self.error_pass is None and best_action_upper in ["N/T", "TG/T", "TG/P"]:
            return "—"
        if self.error_no_double is None and self.error_pass is None and best_action_upper == "D/T":
            return "—"
        if self.error_no_double is None and self.error_double is None and best_action_upper == "D/P":
            return "—"

        return f"{displayed_errors[0]}/{displayed_errors[1]}"

    def has_low_errors(self, threshold: int = 20) -> bool:
        """
        Check if the minimum displayed error is below the threshold.

        This checks the two errors shown in the cell (not the one matching the best action).
        If the smallest shown error is < threshold, it means at least one alternative
        action is very close to the best action, indicating a close decision.

        Args:
            threshold: Error threshold (scaled by 1000). Default 20 = 0.020

        Returns:
            True if minimum of displayed errors is below threshold (close decision)
        """
        # Helper to scale error
        def scale_error(error: Optional[float]) -> int:
            return int(round(error * 1000)) if error is not None else 0

        # Get all three errors
        nd_error = scale_error(self.error_no_double)
        dt_error = scale_error(self.error_double)
        dp_error = scale_error(self.error_pass)

        # Determine which two errors are displayed based on best action
        best_action_upper = self.best_action.upper()

        if best_action_upper in ["N/T", "TG/T", "TG/P"]:
            # Display DT and DP errors
            displayed_errors = [dt_error, dp_error]
        elif best_action_upper == "D/T":
            # Display ND and DP errors
            displayed_errors = [nd_error, dp_error]
        elif best_action_upper == "D/P":
            # Display ND and DT errors
            displayed_errors = [nd_error, dt_error]
        else:
            # Fallback: use ND and DT
            displayed_errors = [nd_error, dt_error]

        # Check if minimum of displayed errors is below threshold
        return min(displayed_errors) < threshold


def generate_score_matrix(
    xgid: str,
    match_length: int,
    gnubg_path: str,
    ply_level: int = 3,
    progress_callback: Optional[callable] = None,
    use_parallel: bool = True
) -> List[List[ScoreMatrixCell]]:
    """
    Generate a score matrix for all score combinations in a match.

    Args:
        xgid: XGID position string (cube decision)
        match_length: Match length (e.g., 7 for 7-point match)
        gnubg_path: Path to gnubg-cli.exe
        ply_level: Analysis depth in plies
        progress_callback: Optional callback(message: str) for progress updates
        use_parallel: Use parallel analysis (default: True, ~5-9x faster)

    Returns:
        2D list of ScoreMatrixCell objects, indexed as [row][col]
        where row = player_away - 2, col = opponent_away - 2

        For a 7-point match:
        - Returns 6x6 matrix (2a through 7a)
        - matrix[0][0] = 2a-2a
        - matrix[5][5] = 7a-7a

    Raises:
        ValueError: If match_length < 2
        FileNotFoundError: If gnubg_path doesn't exist
    """
    if match_length < 2:
        raise ValueError(f"Match length must be >= 2, got {match_length}")

    from ankigammon.utils.gnubg_analyzer import GNUBGAnalyzer
    from ankigammon.utils.xgid import parse_xgid, encode_xgid
    from ankigammon.models import Player, CubeState
    from ankigammon.parsers.gnubg_parser import GNUBGParser

    # Initialize analyzer
    analyzer = GNUBGAnalyzer(gnubg_path, ply_level)

    # Parse original XGID to get position and metadata
    position, metadata = parse_xgid(xgid)
    on_roll = metadata.get('on_roll')

    # Matrix size is (match_length - 1) x (match_length - 1)
    # For 7-point match: 6x6 (scores from 2a to 7a)
    matrix_size = match_length - 1

    # Calculate total cells for progress
    total_cells = matrix_size * matrix_size

    # Prepare all position IDs and coordinate mappings
    position_ids = []
    coord_list = []  # [(player_away, opponent_away), ...]

    for player_away in range(2, match_length + 1):
        for opponent_away in range(2, match_length + 1):
            # Calculate actual scores from "away" values
            score_on_roll = match_length - player_away
            score_opponent = match_length - opponent_away

            # Map scores to X and O based on who's on roll
            if on_roll == Player.O:
                score_o = score_on_roll
                score_x = score_opponent
            else:
                score_x = score_on_roll
                score_o = score_opponent

            # IMPORTANT: Score matrix always uses INITIAL DOUBLE (cube=1, centered)
            modified_xgid = encode_xgid(
                position=position,
                cube_value=1,
                cube_owner=CubeState.CENTERED,
                dice=None,
                on_roll=on_roll,
                score_x=score_x,
                score_o=score_o,
                match_length=match_length,
                crawford_jacoby=metadata.get('crawford_jacoby', 0),
                max_cube=metadata.get('max_cube', 256)
            )

            position_ids.append(modified_xgid)
            coord_list.append((player_away, opponent_away))

    # Analyze all positions (parallel or sequential)
    if use_parallel and len(position_ids) > 2:
        # Parallel analysis with progress tracking
        def parallel_progress_callback(completed: int, total: int):
            if progress_callback:
                # Get current coordinates for display
                if completed > 0 and completed <= len(coord_list):
                    p_away, o_away = coord_list[completed - 1]
                    progress_callback(
                        f"Analyzing score {p_away}a-{o_away}a ({completed}/{total})..."
                    )

        analysis_results = analyzer.analyze_positions_parallel(
            position_ids,
            progress_callback=parallel_progress_callback
        )
    else:
        # Sequential analysis (fallback for small matrices or if disabled)
        analysis_results = []
        for idx, pos_id in enumerate(position_ids):
            if progress_callback:
                p_away, o_away = coord_list[idx]
                progress_callback(
                    f"Analyzing score {p_away}a-{o_away}a ({idx + 1}/{total_cells})..."
                )
            analysis_results.append(analyzer.analyze_position(pos_id))

    # Process results and build matrix
    matrix = []
    result_idx = 0

    for player_away in range(2, match_length + 1):
        row = []
        for opponent_away in range(2, match_length + 1):
            # Get analysis result
            output, decision_type = analysis_results[result_idx]
            result_idx += 1

            # Parse cube decision
            moves = GNUBGParser._parse_cube_decision(output)

            if not moves:
                raise ValueError(
                    f"Could not parse cube decision at score {player_away}a-{opponent_away}a"
                )

            # Build equity map
            equity_map = {m.notation: m.equity for m in moves}

            # Find best move
            best_move = next((m for m in moves if m.rank == 1), None)
            if not best_move:
                raise ValueError(
                    f"Could not determine best cube action at score {player_away}a-{opponent_away}a"
                )

            # Get equities for the 3 main actions
            no_double_eq = equity_map.get("No Double/Take", None)
            double_take_eq = equity_map.get("Double/Take", equity_map.get("Redouble/Take", None))
            double_pass_eq = equity_map.get("Double/Pass", equity_map.get("Redouble/Pass", None))

            # Simplify best action notation
            best_action_simplified = analyzer._simplify_cube_notation(best_move.notation)

            # Calculate errors for wrong decisions
            best_equity = best_move.equity
            error_no_double = None
            error_double = None
            error_pass = None

            if no_double_eq is not None:
                error_no_double = abs(best_equity - no_double_eq) if best_action_simplified != "N/T" else 0.0
            if double_take_eq is not None:
                error_double = abs(best_equity - double_take_eq) if best_action_simplified not in ["D/T", "TG/T"] else 0.0
            if double_pass_eq is not None:
                error_pass = abs(best_equity - double_pass_eq) if best_action_simplified != "D/P" else 0.0

            # Create cell
            cell = ScoreMatrixCell(
                player_away=player_away,
                opponent_away=opponent_away,
                best_action=best_action_simplified,
                error_no_double=error_no_double,
                error_double=error_double,
                error_pass=error_pass
            )
            row.append(cell)

        matrix.append(row)

    return matrix


def format_matrix_as_html(
    matrix: List[List[ScoreMatrixCell]],
    current_player_away: Optional[int] = None,
    current_opponent_away: Optional[int] = None,
    ply_level: Optional[int] = None
) -> str:
    """
    Format score matrix as HTML table.

    Args:
        matrix: Score matrix from generate_score_matrix()
        current_player_away: Highlight this cell (player's score away)
        current_opponent_away: Highlight this cell (opponent's score away)
        ply_level: Analysis depth in plies (for display in title)

    Returns:
        HTML string with styled table
    """
    if not matrix or not matrix[0]:
        return ""

    matrix_size = len(matrix)

    # Start table
    html = '<div class="score-matrix">\n'

    # Build title with optional ply level indicator
    title = 'Score Matrix for Initial Double'
    if ply_level is not None:
        title += f' <span class="ply-indicator">({ply_level}-ply)</span>'
    html += f'<h3>{title}</h3>\n'

    html += '<table class="score-matrix-table">\n'

    # Header row
    html += '<tr><th></th>'
    for col in range(matrix_size):
        away = col + 2
        html += f'<th>{away}a</th>'
    html += '</tr>\n'

    # Data rows
    for row_idx, row in enumerate(matrix):
        player_away = row_idx + 2
        html += f'<tr><th>{player_away}a</th>'

        for col_idx, cell in enumerate(row):
            opponent_away = col_idx + 2

            # Determine if this is the current cell
            is_current = (
                current_player_away == player_away and
                current_opponent_away == opponent_away
            )

            action_class = _get_action_css_class(cell.best_action)
            current_class = " current-score" if is_current else ""
            low_error_class = " low-error" if cell.has_low_errors() else ""
            formatted_errors = cell.format_errors()

            # Show only em dash when no alternatives available
            if formatted_errors == "—":
                html += f'<td class="action-no-alternatives{current_class}">'
                html += f'<div class="action">—</div>'
                html += '</td>'
            else:
                html += f'<td class="{action_class}{current_class}{low_error_class}">'
                html += f'<div class="action">{cell.best_action}</div>'
                html += f'<div class="errors">{formatted_errors}</div>'
                html += '</td>'

        html += '</tr>\n'

    html += '</table>\n'
    html += '</div>\n'

    return html


def _get_action_css_class(action: str) -> str:
    """
    Get CSS class name for cube action.

    Args:
        action: Cube action ("D/T", "N/T", etc.)

    Returns:
        CSS class name
    """
    action_upper = action.upper()

    if action_upper == "D/T":
        return "action-double-take"
    elif action_upper == "D/P":
        return "action-double-pass"
    elif action_upper == "N/T":
        return "action-no-double"
    elif action_upper.startswith("TG"):
        return "action-too-good"
    else:
        return "action-unknown"
