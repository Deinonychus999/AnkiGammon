"""
Move cube matrix generation for checker play decisions (issue #50).

Re-analyzes a checker play position at three cube positions:
- Neutral: centered 1-cube (either player can double)
- Player: cube owned by the player on roll
- Opponent: cube owned by the opponent

Cube ownership changes the value of gammons and the ability to double, so
the best checker play can differ between these states. The card back only
shows the result (as a collapsed spoiler) when the best move actually
differs; see ``best_move_differs``.

Owned-cube variants reuse the original cube value when the source cube is
already owned; otherwise they use a 2-cube (a centered cube is by definition
a 1-cube, and 2 is the smallest legal owned value).
"""

from dataclasses import dataclass
from typing import List, Optional, Callable

from ankigammon.models import Move


@dataclass
class MoveAtCubeState:
    """Represents a single move at a specific cube position."""

    notation: str       # Move notation (e.g., "13/9 6/5")
    equity: float       # Equity of this move
    error: float        # Error compared to best move at this cube position (0 for best)
    rank: int           # 1, 2, or 3


@dataclass
class CubeMatrixColumn:
    """Represents one column (cube position) in the move cube matrix."""

    cube_type: str                    # Short name: "Neutral", "Player", "Opponent"
    top_moves: List[MoveAtCubeState]  # Top moves at this cube position


# Cube position configurations for the 3 columns
CUBE_CONFIGS = [
    {'type': 'Neutral'},   # Centered 1-cube
    {'type': 'Player'},    # Cube owned by the player on roll
    {'type': 'Opponent'},  # Cube owned by the opponent
]


def generate_move_cube_matrix(
    xgid: str,
    analyzer: 'BackgammonAnalyzer',
    max_moves: int = 3,
    progress_callback: Optional[Callable[[str], None]] = None,
    cancellation_callback: Optional[Callable[[], bool]] = None,
) -> List[CubeMatrixColumn]:
    """
    Generate move cube matrix for checker play decisions.

    Analyzes the position at 3 cube positions, preserving the original
    score, match length, Crawford/Jacoby flags and max cube:
    - Neutral: centered 1-cube
    - Player: cube owned by the player on roll
    - Opponent: cube owned by the opponent

    Args:
        xgid: XGID position string with dice set
        analyzer: BackgammonAnalyzer instance to use for analysis
        max_moves: Maximum moves per cube position (default: 3)
        progress_callback: Optional callback(message: str) for progress updates
        cancellation_callback: Optional callback() that returns True if cancelled

    Returns:
        List of 3 CubeMatrixColumn objects (Neutral, Player, Opponent)

    Raises:
        ValueError: If XGID is invalid, has no dice (not a checker play),
                    is a Crawford game, or a 1-point match (dead cube)
        InterruptedError: If cancelled by user
    """
    from ankigammon.utils.xgid import parse_xgid, encode_xgid
    from ankigammon.models import Player, CubeState

    # Parse XGID to get position and metadata
    position, metadata = parse_xgid(xgid)

    # Verify this is a checker play (has dice)
    dice = metadata.get('dice')
    if not dice:
        raise ValueError("XGID must have dice set for move cube matrix (checker play)")

    match_length = metadata.get('match_length', 0)
    crawford_jacoby = metadata.get('crawford_jacoby', 0)

    # Owned-cube variants are illegal/meaningless states when the cube is dead.
    # In match play bit 0 of the crawford_jacoby field is the Crawford flag.
    if match_length > 0 and bool(crawford_jacoby & 1):
        raise ValueError("Move cube matrix is unavailable in Crawford games (cube is dead)")
    if match_length == 1:
        raise ValueError("Move cube matrix is unavailable in 1-point matches (cube is dead)")

    on_roll = metadata.get('on_roll', Player.O)

    orig_cube_value = metadata.get('cube_value', 1)
    orig_cube_owner = metadata.get('cube_owner', CubeState.CENTERED)

    # A centered cube is by definition a 1-cube, so the owned variants need a
    # value: reuse the original value when the cube is already owned, else 2
    # (the smallest legal owned cube, matching issue #50's own example).
    owned_value = orig_cube_value if orig_cube_owner != CubeState.CENTERED else 2

    # CubeState is ABSOLUTE (O_OWNS/X_OWNS/CENTERED), so "Player"/"Opponent"
    # map through the player on roll; the position itself is never flipped.
    player_owner = CubeState.O_OWNS if on_roll == Player.O else CubeState.X_OWNS
    opponent_owner = CubeState.X_OWNS if on_roll == Player.O else CubeState.O_OWNS

    cube_variants = {
        'Neutral': (1, CubeState.CENTERED),
        'Player': (owned_value, player_owner),
        'Opponent': (owned_value, opponent_owner),
    }

    # Build list of modified XGIDs for each cube config, preserving all
    # other metadata from the original position
    position_ids = []
    for config in CUBE_CONFIGS:
        cube_value, cube_owner = cube_variants[config['type']]

        modified_xgid = encode_xgid(
            position=position,
            cube_value=cube_value,
            cube_owner=cube_owner,
            dice=dice,
            on_roll=on_roll,
            score_x=metadata.get('score_x', 0),
            score_o=metadata.get('score_o', 0),
            match_length=match_length,
            crawford_jacoby=crawford_jacoby,
            max_cube=metadata.get('max_cube', 256)
        )

        position_ids.append(modified_xgid)

    # Progress tracking. The engines invoke this with different conventions
    # (XG reports before each position with completed=0..N-1 plus a final
    # (N, N); GnuBG's process pool reports after each completion with
    # completed=1..N, in arbitrary completion order), so count invocations
    # locally and emit exactly one tick per variant to keep the export
    # progress accounting (3 substeps) honest on both engines.
    ticks_emitted = [0]

    def parallel_progress_callback(completed: int, total: int):
        if cancellation_callback and cancellation_callback():
            raise InterruptedError("Move cube matrix generation cancelled by user")

        if progress_callback and ticks_emitted[0] < len(CUBE_CONFIGS):
            ticks_emitted[0] += 1
            progress_callback(
                f"Analyzing cube positions ({ticks_emitted[0]}/{len(CUBE_CONFIGS)})..."
            )

    # Analyze all 3 positions (parallel with GnuBG, sequential with XG)
    analysis_results = analyzer.analyze_positions_parallel(
        position_ids,
        progress_callback=parallel_progress_callback,
        cancellation_callback=cancellation_callback
    )

    # Parse results and build columns
    columns = []
    for idx, (output, decision_type) in enumerate(analysis_results):
        config = CUBE_CONFIGS[idx]

        # Parse checker play moves from analysis output
        moves = analyzer.parse_checker_play(output)

        if not moves:
            raise ValueError(
                f"Could not parse checker play at {config['type']} cube position"
            )

        # Extract top moves
        sorted_moves = sorted(moves, key=lambda m: m.rank)[:max_moves]

        top_moves = []
        for move in sorted_moves:
            top_moves.append(MoveAtCubeState(
                notation=move.notation,
                equity=move.equity,
                error=abs(move.error) if move.error else 0.0,
                rank=move.rank
            ))

        columns.append(CubeMatrixColumn(
            cube_type=config['type'],
            top_moves=top_moves
        ))

    return columns


def best_move_differs(columns: List[CubeMatrixColumn]) -> bool:
    """
    Return True iff the rank-1 move differs between any two columns.

    Comparison is on whitespace-normalized move notation, so purely
    cosmetic formatting differences do not count as a difference.

    Args:
        columns: List of CubeMatrixColumn from generate_move_cube_matrix()

    Returns:
        True when at least two columns have different best moves
    """
    notations = set()
    for col in columns:
        if not col.top_moves:
            continue
        best = min(col.top_moves, key=lambda m: m.rank)
        notations.add(' '.join(best.notation.split()))
    return len(notations) > 1


def format_move_cube_matrix_as_html(
    columns: List[CubeMatrixColumn],
    analysis_label: Optional[str] = None
) -> str:
    """
    Format move cube matrix as a collapsed spoiler with a compact HTML grid.

    The table is wrapped in <details class="cube-matrix-details"> so the
    answer stays hidden until the reader opts in. The inner
    <div class="move-score-matrix"> wrapper is REQUIRED: the responsive
    hide/compaction CSS rules in card_styles.py are scoped to that wrapper,
    not to the table.

    Layout (3 columns x N rows):
    +----------+----------+----------+
    | Neutral  |  Player  | Opponent |
    +----------+----------+----------+
    | Move1    | Move1    | Move1    | <- Rank 1 (highlighted)
    | +0.000   | +0.000   | +0.000   |
    +----------+----------+----------+
    | Move2    | Move2    | Move2    | <- Rank 2
    | -0.025   | -0.031   | -0.018   |
    +----------+----------+----------+

    Args:
        columns: List of CubeMatrixColumn from generate_move_cube_matrix()
        analysis_label: Display label for analysis depth (e.g., "2-ply" or "World Class")

    Returns:
        HTML string with the collapsible styled table
    """
    if not columns:
        return ""

    # Shared severity thresholds with the Top Moves Analysis table
    from ankigammon.anki.card_styles import get_error_css_class

    # Collapsed spoiler: the summary text itself is the reveal
    html = '<details class="cube-matrix-details">\n'
    html += '<summary>Best move differs for a different cube position</summary>\n'

    # Wrapper div required for the wrapper-scoped responsive CSS
    html += '<div class="move-score-matrix">\n'

    # Title
    title = 'Move Analysis by Cube Position'
    if analysis_label:
        title += f' <span class="ply-indicator">({analysis_label})</span>'
    html += f'<h3>{title}</h3>\n'

    html += '<table class="move-score-matrix-table">\n'

    # Tooltips for each cube position
    tooltips = {
        'Neutral': 'Centered cube - either player can double',
        'Player': 'You own the cube - opponent cannot double',
        'Opponent': 'Opponent owns the cube - you cannot double'
    }

    # Header row with cube positions
    html += '<thead>\n<tr>\n'
    for col in columns:
        tooltip = tooltips.get(col.cube_type, '')
        html += f'<th title="{tooltip}">{col.cube_type}</th>\n'
    html += '</tr>\n</thead>\n'

    # Data rows (one for each rank)
    html += '<tbody>\n'

    # Determine max moves across all columns
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

                # Color-code the cell by error magnitude, matching the
                # Top Moves Analysis table (rank 1 has error 0 -> no class)
                error_class = get_error_css_class(move.error)
                html += f'<td class="{error_class}">' if error_class else '<td>'
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
    html += '</details>\n'

    return html
