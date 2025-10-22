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
            String like "24/543" (errors scaled by 1000)
        """
        # Helper to scale error
        def scale_error(error: Optional[float]) -> int:
            return int(round(error * 1000)) if error is not None else 0

        # Get all three errors
        nd_error = scale_error(self.error_no_double)
        dt_error = scale_error(self.error_double)
        dp_error = scale_error(self.error_pass)

        # Determine which two to show based on best action
        # Order: ND, D/T, D/P (skip the one matching the cell)
        best_action_upper = self.best_action.upper()

        if best_action_upper in ["N/T", "TG/T", "TG/P"]:
            # Skip ND error (TG is a variant of no double)
            return f"{dt_error}/{dp_error}"
        elif best_action_upper == "D/T":
            # Skip D/T error
            return f"{nd_error}/{dp_error}"
        elif best_action_upper == "D/P":
            # Skip D/P error
            return f"{nd_error}/{dt_error}"
        else:
            # Fallback: show first two
            return f"{nd_error}/{dt_error}"

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
    ply_level: int = 2,
    progress_callback: Optional[callable] = None
) -> List[List[ScoreMatrixCell]]:
    """
    Generate a score matrix for all score combinations in a match.

    Args:
        xgid: XGID position string (cube decision)
        match_length: Match length (e.g., 7 for 7-point match)
        gnubg_path: Path to gnubg-cli.exe
        ply_level: Analysis depth in plies
        progress_callback: Optional callback(message: str) for progress updates

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

    from flashgammon.utils.gnubg_analyzer import GNUBGAnalyzer

    # Initialize analyzer
    analyzer = GNUBGAnalyzer(gnubg_path, ply_level)

    # Matrix size is (match_length - 1) x (match_length - 1)
    # For 7-point match: 6x6 (scores from 2a to 7a)
    matrix_size = match_length - 1
    matrix = []

    # Calculate total cells for progress
    total_cells = matrix_size * matrix_size
    current_cell = 0

    # Generate matrix row by row
    for player_away in range(2, match_length + 1):
        row = []
        for opponent_away in range(2, match_length + 1):
            current_cell += 1

            # Report progress
            if progress_callback:
                progress_callback(
                    f"Analyzing score {player_away}a-{opponent_away}a "
                    f"({current_cell}/{total_cells})..."
                )

            # Analyze cube at this score
            result = analyzer.analyze_cube_at_score(
                position_id=xgid,
                match_length=match_length,
                player_away=player_away,
                opponent_away=opponent_away
            )

            # Create cell
            cell = ScoreMatrixCell(
                player_away=player_away,
                opponent_away=opponent_away,
                best_action=result['best_action'],
                error_no_double=result['error_no_double'],
                error_double=result['error_double'],
                error_pass=result['error_pass']
            )
            row.append(cell)

        matrix.append(row)

    return matrix


def format_matrix_as_html(
    matrix: List[List[ScoreMatrixCell]],
    current_player_away: Optional[int] = None,
    current_opponent_away: Optional[int] = None
) -> str:
    """
    Format score matrix as HTML table.

    Args:
        matrix: Score matrix from generate_score_matrix()
        current_player_away: Highlight this cell (player's score away)
        current_opponent_away: Highlight this cell (opponent's score away)

    Returns:
        HTML string with styled table
    """
    if not matrix or not matrix[0]:
        return ""

    matrix_size = len(matrix)

    # Start table
    html = '<div class="score-matrix">\n'
    html += '<h3>Score Matrix for Initial Double</h3>\n'
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

            # Get CSS class based on best action
            action_class = _get_action_css_class(cell.best_action)
            current_class = " current-score" if is_current else ""
            low_error_class = " low-error" if cell.has_low_errors() else ""

            html += f'<td class="{action_class}{current_class}{low_error_class}">'
            html += f'<div class="action">{cell.best_action}</div>'
            html += f'<div class="errors">{cell.format_errors()}</div>'
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
