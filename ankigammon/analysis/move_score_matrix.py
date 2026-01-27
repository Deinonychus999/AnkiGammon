"""
Move score matrix generation for checker play decisions.

Generates tables showing top moves at different match score contexts:
- Neutral (0-0 to 7)
- DMP (Double Match Point: 0-0 to 1)
- Gammon-Save (2-1 to 3 Crawford - player ahead)
- Gammon-Go (1-2 to 3 Crawford - player behind)
"""

from dataclasses import dataclass
from typing import List, Optional, Callable

from ankigammon.models import Move


@dataclass
class MoveAtScore:
    """Represents a single move at a specific score context."""

    notation: str       # Move notation (e.g., "13/9 6/5")
    equity: float       # Equity of this move
    error: float        # Error compared to best move at this score (0 for best)
    rank: int           # 1, 2, or 3


@dataclass
class MoveScoreMatrixColumn:
    """Represents one column (score type) in the move score matrix."""

    score_type: str           # Short name: "Neutral", "DMP", "G-Save", "G-Go"
    top_moves: List[MoveAtScore]  # Top 3 moves at this score


# Score configurations for the 4 score types
SCORE_CONFIGS = [
    {
        'type': 'Neutral',
        'match_length': 7,
        'score_x': 0,
        'score_o': 0,
        'crawford': 0
    },
    {
        'type': 'DMP',
        'match_length': 1,
        'score_x': 0,
        'score_o': 0,
        'crawford': 0
    },
    {
        'type': 'G-Save',
        'match_length': 3,
        'score_x': 1,  # Opponent (behind)
        'score_o': 2,  # Player on roll (ahead) - wants to SAVE gammons
        'crawford': 1  # Crawford game
    },
    {
        'type': 'G-Go',
        'match_length': 3,
        'score_x': 2,  # Opponent (ahead)
        'score_o': 1,  # Player on roll (behind) - wants to WIN gammons
        'crawford': 1  # Crawford game
    }
]


def generate_move_score_matrix(
    xgid: str,
    gnubg_path: str,
    ply_level: int = 3,
    max_moves: int = 3,
    progress_callback: Optional[Callable[[str], None]] = None,
    cancellation_callback: Optional[Callable[[], bool]] = None
) -> List[MoveScoreMatrixColumn]:
    """
    Generate move score matrix for checker play decisions.

    Analyzes the position at 4 key score types:
    - Neutral: Money game (match_length=0)
    - DMP: 0-0 to 1 (Double Match Point)
    - Gammon-Save: 2-1 to 3 Crawford (player ahead, needs to save gammons)
    - Gammon-Go: 1-2 to 3 Crawford (player behind, wants gammons)

    Args:
        xgid: XGID position string with dice set
        gnubg_path: Path to gnubg-cli.exe
        ply_level: Analysis depth (default: 3)
        progress_callback: Optional callback(message: str) for progress updates
        cancellation_callback: Optional callback() that returns True if cancelled

    Returns:
        List of 4 MoveScoreMatrixColumn objects

    Raises:
        ValueError: If XGID is invalid or has no dice (not a checker play)
        FileNotFoundError: If gnubg_path doesn't exist
        InterruptedError: If cancelled by user
    """
    from ankigammon.utils.gnubg_analyzer import GNUBGAnalyzer
    from ankigammon.utils.xgid import parse_xgid, encode_xgid
    from ankigammon.parsers.gnubg_parser import GNUBGParser
    from ankigammon.models import Player, CubeState

    # Parse XGID to get position and metadata
    position, metadata = parse_xgid(xgid)

    # Verify this is a checker play (has dice)
    dice = metadata.get('dice')
    if not dice:
        raise ValueError("XGID must have dice set for move score matrix (checker play)")

    on_roll = metadata.get('on_roll', Player.O)

    # Initialize analyzer
    analyzer = GNUBGAnalyzer(gnubg_path, ply_level)

    # Build list of modified XGIDs for each score config
    position_ids = []
    for config in SCORE_CONFIGS:
        match_length = config['match_length']

        # Scores are configured relative to player on roll
        # config assumes O is on roll; if X is on roll, swap scores
        if on_roll == Player.O:
            score_x = config['score_x']
            score_o = config['score_o']
        else:
            # X is on roll - swap the perspective
            score_x = config['score_o']
            score_o = config['score_x']

        modified_xgid = encode_xgid(
            position=position,
            cube_value=1,  # Cube at 1 (centered) for these score contexts
            cube_owner=CubeState.CENTERED,
            dice=dice,
            on_roll=on_roll,
            score_x=score_x,
            score_o=score_o,
            match_length=match_length,
            crawford_jacoby=config['crawford'],
            max_cube=metadata.get('max_cube', 256)
        )

        position_ids.append(modified_xgid)

    # Progress tracking
    def parallel_progress_callback(completed: int, total: int):
        if cancellation_callback and cancellation_callback():
            raise InterruptedError("Move score matrix generation cancelled by user")

        if progress_callback:
            config = SCORE_CONFIGS[completed - 1] if completed > 0 else SCORE_CONFIGS[0]
            progress_callback(
                f"Analyzing {config['type']} ({completed}/{total})..."
            )

    # Analyze all 4 positions
    if len(position_ids) > 2:
        analysis_results = analyzer.analyze_positions_parallel(
            position_ids,
            progress_callback=parallel_progress_callback,
            cancellation_callback=cancellation_callback
        )
    else:
        # Sequential fallback
        analysis_results = []
        for idx, pos_id in enumerate(position_ids):
            if cancellation_callback and cancellation_callback():
                raise InterruptedError("Move score matrix generation cancelled by user")

            if progress_callback:
                config = SCORE_CONFIGS[idx]
                progress_callback(
                    f"Analyzing {config['type']} ({idx + 1}/{len(position_ids)})..."
                )
            analysis_results.append(analyzer.analyze_position(pos_id))

    # Parse results and build columns
    columns = []
    for idx, (output, decision_type) in enumerate(analysis_results):
        config = SCORE_CONFIGS[idx]

        # Parse checker play moves from GnuBG output
        moves = GNUBGParser._parse_checker_play(output)

        if not moves:
            raise ValueError(
                f"Could not parse checker play at {config['type']} score"
            )

        # Extract top 3 moves
        sorted_moves = sorted(moves, key=lambda m: m.rank)[:max_moves]

        top_moves = []
        for move in sorted_moves:
            top_moves.append(MoveAtScore(
                notation=move.notation,
                equity=move.equity,
                error=abs(move.error) if move.error else 0.0,
                rank=move.rank
            ))

        columns.append(MoveScoreMatrixColumn(
            score_type=config['type'],
            top_moves=top_moves
        ))

    return columns


def format_move_matrix_as_html(
    columns: List[MoveScoreMatrixColumn],
    ply_level: Optional[int] = None
) -> str:
    """
    Format move score matrix as compact HTML grid.

    Layout (4 columns x 3 rows):
    +----------+----------+----------+----------+
    | Neutral  |   DMP    | G-Save   |  G-Go    |
    | (Money)  | (0-0/1)  | (2-1/3C) | (1-2/3C) |
    +----------+----------+----------+----------+
    | Move1    | Move1    | Move1    | Move1    | <- Rank 1 (highlighted)
    | +0.000   | +0.000   | +0.000   | +0.000   |
    +----------+----------+----------+----------+
    | Move2    | Move2    | Move2    | Move2    | <- Rank 2
    | -0.025   | -0.031   | -0.018   | -0.042   |
    +----------+----------+----------+----------+

    Args:
        columns: List of MoveScoreMatrixColumn from generate_move_score_matrix()
        ply_level: Analysis depth in plies (for display in title)

    Returns:
        HTML string with styled table
    """
    if not columns:
        return ""

    # Start table
    html = '<div class="move-score-matrix">\n'

    # Title
    title = 'Move Analysis by Score'
    if ply_level is not None:
        title += f' <span class="ply-indicator">({ply_level}-ply)</span>'
    html += f'<h3>{title}</h3>\n'

    html += '<table class="move-score-matrix-table">\n'

    # Tooltips for each score type
    tooltips = {
        'Neutral': '0-0 to 7 point match - balanced gammon values',
        'DMP': 'Double Match Point (0-0 to 1) - gammons worthless',
        'G-Save': 'Gammon-Save (2-1 to 3 Crawford) - avoid losing gammon',
        'G-Go': 'Gammon-Go (1-2 to 3 Crawford) - gammon wins match'
    }

    # Header row with score types
    html += '<thead>\n<tr>\n'
    for col in columns:
        tooltip = tooltips.get(col.score_type, '')
        html += f'<th title="{tooltip}">{col.score_type}</th>\n'
    html += '</tr>\n</thead>\n'

    # Data rows (one for each rank)
    html += '<tbody>\n'

    # Determine max moves across all columns (should be 3)
    max_moves = max(len(col.top_moves) for col in columns) if columns else 0

    for rank_idx in range(max_moves):
        rank = rank_idx + 1
        row_class = f'rank-{rank}'
        html += f'<tr class="{row_class}">\n'

        for col in columns:
            if rank_idx < len(col.top_moves):
                move = col.top_moves[rank_idx]

                # Format error/equity display
                if rank == 1:
                    # Best move - show equity with + sign
                    equity_display = f'<span class="equity">{move.equity:+.3f}</span>'
                else:
                    # Other moves - show error as negative
                    error_val = -abs(move.error) if move.error != 0 else 0
                    equity_display = f'<span class="error">{error_val:.3f}</span>'

                html += '<td>'
                html += f'<div class="move-notation">{move.notation}</div>'
                html += f'<div class="equity-error">{equity_display}</div>'
                html += '</td>\n'
            else:
                # No move at this rank for this column
                html += '<td><span class="no-move">-</span></td>\n'

        html += '</tr>\n'

    html += '</tbody>\n'
    html += '</table>\n'
    html += '</div>\n'

    return html
