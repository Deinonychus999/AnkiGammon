"""Data models for backgammon positions, moves, and decisions."""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple


class Player(Enum):
    """Player identifier."""
    X = "X"  # Top player
    O = "O"  # Bottom player


class CubeState(Enum):
    """Doubling cube state."""
    CENTERED = "centered"
    X_OWNS = "x_owns"
    O_OWNS = "o_owns"


class DecisionType(Enum):
    """Type of decision."""
    CHECKER_PLAY = "checker_play"
    CUBE_ACTION = "cube_action"


@dataclass
class Position:
    """
    Represents a backgammon position.

    Board representation:
    - points[0] = bar for X (top player)
    - points[1-24] = board points (point 24 is X's home, point 1 is O's home)
    - points[25] = bar for O (bottom player)

    Positive numbers = X checkers, negative numbers = O checkers
    """
    points: List[int] = field(default_factory=lambda: [0] * 26)
    x_off: int = 0  # Checkers borne off by X
    o_off: int = 0  # Checkers borne off by O

    def __post_init__(self):
        """Validate position."""
        if len(self.points) != 26:
            raise ValueError("Position must have exactly 26 points (0=X bar, 1-24=board, 25=O bar)")

    @classmethod
    def from_xgid(cls, xgid: str) -> 'Position':
        """
        Parse a position from XGID format.
        XGID format: e.g., "XGID=-b----E-C---eE---c-e----B-:1:0:1:63:0:0:0:0:10"
        """
        # Import here to avoid circular dependency
        from ankigammon.utils.xgid import parse_xgid
        position, _ = parse_xgid(xgid)
        return position

    @classmethod
    def from_ogid(cls, ogid: str) -> 'Position':
        """
        Parse a position from OGID format.
        OGID format: e.g., "11jjjjjhhhccccc:ooddddd88866666:N0N::W:IW:0:0:1:0"
        """
        # Import here to avoid circular dependency
        from ankigammon.utils.ogid import parse_ogid
        position, _ = parse_ogid(ogid)
        return position

    @classmethod
    def from_gnuid(cls, gnuid: str) -> 'Position':
        """
        Parse a position from GNUID format.
        GNUID format: e.g., "4HPwATDgc/ABMA:8IhuACAACAAE"
        """
        # Import here to avoid circular dependency
        from ankigammon.utils.gnuid import parse_gnuid
        position, _ = parse_gnuid(gnuid)
        return position

    def to_xgid(
        self,
        cube_value: int = 1,
        cube_owner: 'CubeState' = None,
        dice: Optional[Tuple[int, int]] = None,
        on_roll: 'Player' = None,
        score_x: int = 0,
        score_o: int = 0,
        match_length: int = 0,
        crawford_jacoby: int = 0,
    ) -> str:
        """Convert position to XGID format."""
        # Import here to avoid circular dependency
        from ankigammon.utils.xgid import encode_xgid
        if cube_owner is None:
            cube_owner = CubeState.CENTERED
        if on_roll is None:
            on_roll = Player.O
        return encode_xgid(
            self,
            cube_value=cube_value,
            cube_owner=cube_owner,
            dice=dice,
            on_roll=on_roll,
            score_x=score_x,
            score_o=score_o,
            match_length=match_length,
            crawford_jacoby=crawford_jacoby,
        )

    def to_ogid(
        self,
        cube_value: int = 1,
        cube_owner: 'CubeState' = None,
        cube_action: str = 'N',
        dice: Optional[Tuple[int, int]] = None,
        on_roll: 'Player' = None,
        game_state: str = '',
        score_x: int = 0,
        score_o: int = 0,
        match_length: Optional[int] = None,
        match_modifier: str = '',
        only_position: bool = False,
    ) -> str:
        """Convert position to OGID format."""
        # Import here to avoid circular dependency
        from ankigammon.utils.ogid import encode_ogid
        if cube_owner is None:
            cube_owner = CubeState.CENTERED
        return encode_ogid(
            self,
            cube_value=cube_value,
            cube_owner=cube_owner,
            cube_action=cube_action,
            dice=dice,
            on_roll=on_roll,
            game_state=game_state,
            score_x=score_x,
            score_o=score_o,
            match_length=match_length,
            match_modifier=match_modifier,
            only_position=only_position,
        )

    def to_gnuid(
        self,
        cube_value: int = 1,
        cube_owner: 'CubeState' = None,
        dice: Optional[Tuple[int, int]] = None,
        on_roll: 'Player' = None,
        score_x: int = 0,
        score_o: int = 0,
        match_length: int = 0,
        crawford: bool = False,
        only_position: bool = False,
    ) -> str:
        """Convert position to GNUID format."""
        # Import here to avoid circular dependency
        from ankigammon.utils.gnuid import encode_gnuid
        if cube_owner is None:
            cube_owner = CubeState.CENTERED
        if on_roll is None:
            on_roll = Player.X
        return encode_gnuid(
            self,
            cube_value=cube_value,
            cube_owner=cube_owner,
            dice=dice,
            on_roll=on_roll,
            score_x=score_x,
            score_o=score_o,
            match_length=match_length,
            crawford=crawford,
            only_position=only_position,
        )

    def copy(self) -> 'Position':
        """Create a deep copy of the position."""
        return Position(
            points=self.points.copy(),
            x_off=self.x_off,
            o_off=self.o_off
        )


@dataclass
class Move:
    """
    Represents a candidate move with its analysis.
    """
    notation: str  # e.g., "13/9 6/5" or "double/take" (for MCQ and answer display)
    equity: float  # Equity of this move
    error: float = 0.0  # Error compared to best move (0 for best move)
    rank: int = 1  # Rank among all candidates (including synthetic, 1 = best)
    xg_rank: Optional[int] = None  # Order in XG's "Cubeful Equities:" section (1-3)
    xg_error: Optional[float] = None  # Error as shown by XG (relative to first option in Cubeful Equities)
    xg_notation: Optional[str] = None  # Original notation from XG (e.g., "No double" not "No double/Take")
    resulting_position: Optional[Position] = None  # Position after this move (if available)
    from_xg_analysis: bool = True  # True if from XG's analysis, False if synthetically generated
    # Winning chances percentages
    player_win_pct: Optional[float] = None  # Player winning percentage (e.g., 52.68)
    player_gammon_pct: Optional[float] = None  # Player gammon percentage (e.g., 14.35)
    player_backgammon_pct: Optional[float] = None  # Player backgammon percentage (e.g., 0.69)
    opponent_win_pct: Optional[float] = None  # Opponent winning percentage (e.g., 47.32)
    opponent_gammon_pct: Optional[float] = None  # Opponent gammon percentage (e.g., 12.42)
    opponent_backgammon_pct: Optional[float] = None  # Opponent backgammon percentage (e.g., 0.55)

    def __str__(self) -> str:
        """Human-readable representation."""
        if self.rank == 1:
            return f"{self.notation} (Equity: {self.equity:.3f})"
        else:
            return f"{self.notation} (Equity: {self.equity:.3f}, Error: {self.error:.3f})"


@dataclass
class Decision:
    """
    Represents a single decision point from XG analysis.
    """
    # Position information
    position: Position
    position_image_path: Optional[str] = None  # Path to board image (from HTML export)
    xgid: Optional[str] = None

    # Game context
    on_roll: Player = Player.O
    dice: Optional[Tuple[int, int]] = None  # None for cube decisions
    score_x: int = 0
    score_o: int = 0
    match_length: int = 0  # 0 for money games
    crawford: bool = False  # True if Crawford game (no doubling allowed)
    cube_value: int = 1
    cube_owner: CubeState = CubeState.CENTERED

    # Decision analysis
    decision_type: DecisionType = DecisionType.CHECKER_PLAY
    candidate_moves: List[Move] = field(default_factory=list)

    # Winning chances percentages (for cube decisions)
    player_win_pct: Optional[float] = None
    player_gammon_pct: Optional[float] = None
    player_backgammon_pct: Optional[float] = None
    opponent_win_pct: Optional[float] = None
    opponent_gammon_pct: Optional[float] = None
    opponent_backgammon_pct: Optional[float] = None

    # Source metadata
    source_file: Optional[str] = None
    game_number: Optional[int] = None
    move_number: Optional[int] = None

    # User annotations
    note: Optional[str] = None  # User's note/comment/explanation for this position

    def get_best_move(self) -> Optional[Move]:
        """Get the best move (rank 1)."""
        for move in self.candidate_moves:
            if move.rank == 1:
                return move
        return self.candidate_moves[0] if self.candidate_moves else None

    def get_short_display_text(self) -> str:
        """Get short display text for list views."""
        # Build score/game type string
        if self.match_length > 0:
            # Match play - show score and match info
            score = f"{self.score_x}-{self.score_o} of {self.match_length}"
            if self.crawford:
                score += " Crawford"
        else:
            # Money game - just show "Money"
            score = "Money"

        if self.decision_type == DecisionType.CHECKER_PLAY:
            dice_str = f"{self.dice[0]}{self.dice[1]}" if self.dice else "—"
            return f"Checker | {dice_str} | {score}"
        else:
            # Cube decision - no dice to show
            return f"Cube | {score}"

    def get_metadata_text(self) -> str:
        """Get formatted metadata for card display."""
        dice_str = f"{self.dice[0]}{self.dice[1]}" if self.dice else "N/A"

        # Show em dash when cube is centered, otherwise just show value
        if self.cube_owner == CubeState.CENTERED:
            cube_str = "—"
        else:
            cube_str = f"{self.cube_value}"

        # Map Player enum to color names
        # Player.X = TOP player (plays with white checkers from top)
        # Player.O = BOTTOM player (plays with black checkers from bottom)
        player_name = "White" if self.on_roll == Player.X else "Black"

        # Build metadata string based on game type
        if self.match_length > 0:
            # Match play - show score and match info
            match_str = f"{self.match_length}pt"
            if self.crawford:
                match_str += " (Crawford)"
            return (
                f"{player_name} | "
                f"Dice: {dice_str} | "
                f"Score: {self.score_x}-{self.score_o} | "
                f"Cube: {cube_str} | "
                f"Match: {match_str}"
            )
        else:
            # Money game - don't show score, just "Money"
            return (
                f"{player_name} | "
                f"Dice: {dice_str} | "
                f"Cube: {cube_str} | "
                f"Money"
            )

    def __str__(self) -> str:
        """Human-readable representation."""
        return f"Decision({self.decision_type.value}, {self.get_metadata_text()})"
