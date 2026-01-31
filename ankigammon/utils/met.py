"""
Match Equity Table (MET) utilities.

Provides functions for loading METs and calculating normalized match play equity.
"""

import os
from dataclasses import dataclass
from typing import Optional, Tuple

# Path to the default MET file (Kazaross XG2)
DEFAULT_MET_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "Kazaross XG2.met")


@dataclass
class MatchEquityTable:
    """Represents a Match Equity Table."""
    name: str
    version: str
    description: str
    copyright: str
    size: int  # Maximum away score supported (e.g., 25 for 25-away)
    post_crawford: list[float]  # MWC for leader (1-away) vs opponent N-away (index 0 = vs 1-away)
    pre_crawford: list[list[float]]  # MWC[player_away-1][opponent_away-1]

    def get_mwc(self, player_away: int, opponent_away: int, crawford: bool = False, post_crawford: bool = False) -> float:
        """
        Get match winning chance for player.

        Args:
            player_away: Points player needs to win (1 to size)
            opponent_away: Points opponent needs to win (1 to size)
            crawford: Whether this is a Crawford game
            post_crawford: Whether this is post-Crawford (player is 1-away, opponent > 1-away)

        Returns:
            Match winning chance as a decimal (0.0 to 1.0)
        """
        # Clamp to table size
        player_away = min(max(1, player_away), self.size)
        opponent_away = min(max(1, opponent_away), self.size)

        # Post-Crawford: player is 1-away, opponent is trailing
        if post_crawford and player_away == 1 and opponent_away > 1:
            return 1.0 - self.post_crawford[opponent_away - 1]

        # Post-Crawford: opponent is 1-away, player is trailing
        if post_crawford and opponent_away == 1 and player_away > 1:
            return self.post_crawford[player_away - 1]

        # Pre-Crawford or Crawford (Crawford uses same table, just no doubling allowed)
        return self.pre_crawford[player_away - 1][opponent_away - 1]

    def get_mwc_after_result(
        self,
        player_away: int,
        opponent_away: int,
        points_won: int,
        player_won: bool,
        crawford: bool = False
    ) -> float:
        """
        Get MWC after a game result.

        Args:
            player_away: Current points player needs
            opponent_away: Current points opponent needs
            points_won: Points won in the game (1, 2, or 3)
            player_won: Whether the player won
            crawford: Whether this was a Crawford game

        Returns:
            New MWC after the result
        """
        if player_won:
            new_player_away = max(0, player_away - points_won)
            new_opponent_away = opponent_away
        else:
            new_player_away = player_away
            new_opponent_away = max(0, opponent_away - points_won)

        # Check if match is over
        if new_player_away == 0:
            return 1.0
        if new_opponent_away == 0:
            return 0.0

        # Check for post-Crawford
        # Post-Crawford is the game(s) after Crawford game
        post_crawford = False
        if crawford:
            # After Crawford game, we're in post-Crawford
            post_crawford = True
        elif player_away == 1 or opponent_away == 1:
            # If someone was 1-away before and it wasn't Crawford, we're post-Crawford
            post_crawford = True

        return self.get_mwc(new_player_away, new_opponent_away, post_crawford=post_crawford)


def parse_met_file(filepath: str) -> MatchEquityTable:
    """
    Parse a .met file and return a MatchEquityTable.

    Args:
        filepath: Path to the .met file

    Returns:
        Parsed MatchEquityTable
    """
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        content = f.read()

    lines = content.strip().split('\n')

    name = ""
    version = ""
    description = ""
    copyright_str = ""
    size = 0
    post_crawford: list[float] = []
    pre_crawford: list[list[float]] = []

    current_section = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # Section headers
        if line.startswith('[') and line.endswith(']'):
            current_section = line[1:-1].lower()
            continue

        # Key=Value pairs
        if '=' in line:
            key, value = line.split('=', 1)
            key = key.strip().lower()
            value = value.strip()

            if current_section == 'current':
                if key == 'name':
                    name = value
                elif key == 'version':
                    version = value
                elif key == 'description':
                    description = value
                elif key == 'copyright':
                    copyright_str = value

            elif current_section == 'postcrawford':
                if key == 'size':
                    size = int(value)
                elif key == 'data':
                    post_crawford = [float(x) for x in value.split()]

            elif current_section == 'precrawford':
                if key == 'size':
                    size = int(value)
                else:
                    # Row data: "1=0.50000 0.67736 ..."
                    try:
                        row_values = [float(x) for x in value.split()]
                        pre_crawford.append(row_values)
                    except ValueError:
                        pass

    return MatchEquityTable(
        name=name,
        version=version,
        description=description,
        copyright=copyright_str,
        size=size,
        post_crawford=post_crawford,
        pre_crawford=pre_crawford
    )


# Global cached MET instance
_cached_met: Optional[MatchEquityTable] = None


def get_met() -> MatchEquityTable:
    """Get the default MET (Kazaross XG2), cached for performance."""
    global _cached_met
    if _cached_met is None:
        _cached_met = parse_met_file(DEFAULT_MET_PATH)
    return _cached_met


def calculate_match_cubeless_equity(
    player_win_pct: float,
    player_gammon_pct: float,
    player_backgammon_pct: float,
    opponent_win_pct: float,
    opponent_gammon_pct: float,
    opponent_backgammon_pct: float,
    player_away: int,
    opponent_away: int,
    cube_value: int = 1,
    crawford: bool = False,
    post_crawford: bool = False,
    cumulative_gammons: bool = True,
    met: Optional[MatchEquityTable] = None
) -> float:
    """
    Calculate normalized cubeless equity for match play.

    This converts win/gammon/backgammon probabilities into a normalized equity
    value that accounts for the match score and cube value.

    Args:
        player_win_pct: Player's winning percentage (0-100)
        player_gammon_pct: Player's gammon percentage (0-100)
        player_backgammon_pct: Player's backgammon percentage (0-100)
        opponent_win_pct: Opponent's winning percentage (0-100)
        opponent_gammon_pct: Opponent's gammon percentage (0-100)
        opponent_backgammon_pct: Opponent's backgammon percentage (0-100)
        player_away: Points player needs to win
        opponent_away: Points opponent needs to win
        cube_value: Current cube value (1, 2, 4, etc.)
        crawford: Whether this is a Crawford game
        post_crawford: Whether this is post-Crawford
        cumulative_gammons: If True, gammon % includes backgammons (XG format)
        met: Match Equity Table to use (defaults to Kazaross XG2)

    Returns:
        Normalized cubeless equity (-1.0 to +1.0 scale, can exceed for gammons)
    """
    if met is None:
        met = get_met()

    # Convert percentages to decimals
    W = player_win_pct / 100
    L = opponent_win_pct / 100
    Wg = player_gammon_pct / 100
    Lg = opponent_gammon_pct / 100
    Wbg = player_backgammon_pct / 100
    Lbg = opponent_backgammon_pct / 100

    if cumulative_gammons:
        # XG format: gammon % includes backgammons
        # Single win = W - Wg (wins that aren't gammons)
        # Gammon win = Wg - Wbg (gammons that aren't backgammons)
        # Backgammon win = Wbg
        Ws = W - Wg  # Single wins
        Wg_only = Wg - Wbg  # Gammon wins (not backgammon)
        Ls = L - Lg  # Single losses
        Lg_only = Lg - Lbg  # Gammon losses (not backgammon)
    else:
        # GNUBG format: gammon % excludes backgammons
        Ws = W - Wg - Wbg
        Wg_only = Wg
        Ls = L - Lg - Lbg
        Lg_only = Lg

    # Calculate MWC for each possible outcome
    # Points won/lost are multiplied by cube value
    single_pts = cube_value
    gammon_pts = 2 * cube_value
    backgammon_pts = 3 * cube_value

    # MWC after each outcome
    def mwc_after_win(pts: int) -> float:
        new_away = max(0, player_away - pts)
        if new_away == 0:
            return 1.0
        return met.get_mwc(new_away, opponent_away, crawford=False, post_crawford=post_crawford)

    def mwc_after_loss(pts: int) -> float:
        new_away = max(0, opponent_away - pts)
        if new_away == 0:
            return 0.0
        return met.get_mwc(player_away, new_away, crawford=False, post_crawford=post_crawford)

    # Calculate expected MWC
    mwc = (
        Ws * mwc_after_win(single_pts) +
        Wg_only * mwc_after_win(gammon_pts) +
        Wbg * mwc_after_win(backgammon_pts) +
        Ls * mwc_after_loss(single_pts) +
        Lg_only * mwc_after_loss(gammon_pts) +
        Lbg * mwc_after_loss(backgammon_pts)
    )

    # Normalize to equity scale
    # ALWAYS use 1-point win/loss as baseline for normalization
    # This makes equities directly comparable regardless of cube value
    mwc_win = mwc_after_win(1)  # MWC if we win 1 point
    mwc_loss = mwc_after_loss(1)  # MWC if we lose 1 point

    # Normalized equity: linear interpolation where loss=-1, win=+1
    # equity = (mwc - mwc_loss) / (mwc_win - mwc_loss) * 2 - 1
    if mwc_win == mwc_loss:
        return 0.0  # Avoid division by zero (shouldn't happen in practice)

    equity = (mwc - mwc_loss) / (mwc_win - mwc_loss) * 2 - 1

    return equity


def calculate_money_cubeless_equity(
    player_win_pct: float,
    player_gammon_pct: float,
    player_backgammon_pct: float,
    opponent_win_pct: float,
    opponent_gammon_pct: float,
    opponent_backgammon_pct: float,
    cumulative_gammons: bool = True
) -> float:
    """
    Calculate cubeless equity for money games.

    Args:
        player_win_pct: Player's winning percentage (0-100)
        player_gammon_pct: Player's gammon percentage (0-100)
        player_backgammon_pct: Player's backgammon percentage (0-100)
        opponent_win_pct: Opponent's winning percentage (0-100)
        opponent_gammon_pct: Opponent's gammon percentage (0-100)
        opponent_backgammon_pct: Opponent's backgammon percentage (0-100)
        cumulative_gammons: If True, gammon % includes backgammons (XG format)

    Returns:
        Cubeless equity (-3 to +3 range for backgammon wins/losses)
    """
    # Convert percentages to decimals
    W = player_win_pct / 100
    L = opponent_win_pct / 100
    Wg = player_gammon_pct / 100
    Lg = opponent_gammon_pct / 100
    Wbg = player_backgammon_pct / 100
    Lbg = opponent_backgammon_pct / 100

    if cumulative_gammons:
        # XG format: gammon % includes backgammons
        # Equity = (W - L) + (Wg - Lg) + (Wbg - Lbg)
        return (W - L) + (Wg - Lg) + (Wbg - Lbg)
    else:
        # GNUBG format: gammon % excludes backgammons
        # Equity = 2*W - 1 + 2*(Wg - Lg) + 3*(Wbg - Lbg)
        return 2 * W - 1 + 2 * (Wg - Lg) + 3 * (Wbg - Lbg)
