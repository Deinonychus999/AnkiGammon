"""
Parser for eXtreme Gammon binary (.xg) files.

This parser wraps the xgdatatools library to convert XG binary format
into AnkiGammon's Decision objects.
"""

import logging
from pathlib import Path
from typing import List, Optional, Tuple

from ankigammon.models import (
    Decision,
    Move,
    Position,
    Player,
    CubeState,
    DecisionType
)

# Import xgdatatools modules from thirdparty
from ankigammon.thirdparty.xgdatatools import xgimport
from ankigammon.thirdparty.xgdatatools import xgstruct

logger = logging.getLogger(__name__)


class ParseError(Exception):
    """Custom exception for parsing failures"""
    pass


class XGBinaryParser:
    """Parser for eXtreme Gammon binary (.xg) files"""

    @staticmethod
    def extract_player_names(file_path: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract player names from .xg binary file.

        Args:
            file_path: Path to .xg file

        Returns:
            Tuple[Optional[str], Optional[str]]: (player1_name, player2_name)
                Returns (None, None) if names cannot be extracted.
        """
        path = Path(file_path)
        if not path.exists():
            return (None, None)

        try:
            xg_import = xgimport.Import(str(path))

            # Look for the first HeaderMatchEntry to get player names
            for segment in xg_import.getfilesegment():
                if segment.type == xgimport.Import.Segment.XG_GAMEFILE:
                    segment.fd.seek(0)
                    record = xgstruct.GameFileRecord(version=-1).fromstream(segment.fd)

                    if isinstance(record, xgstruct.HeaderMatchEntry):
                        # Try to get player names (prefer Unicode over ANSI)
                        player1 = record.get('Player1') or record.get('SPlayer1')
                        player2 = record.get('Player2') or record.get('SPlayer2')

                        # Decode bytes if needed
                        if isinstance(player1, bytes):
                            player1 = player1.decode('utf-8', errors='ignore')
                        if isinstance(player2, bytes):
                            player2 = player2.decode('utf-8', errors='ignore')

                        logger.debug(f"Extracted player names: {player1} vs {player2}")
                        return (player1, player2)

            # No header found
            return (None, None)

        except Exception as e:
            logger.warning(f"Failed to extract player names from {file_path}: {e}")
            return (None, None)

    @staticmethod
    def parse_file(file_path: str) -> List[Decision]:
        """
        Parse .xg binary file.

        Args:
            file_path: Path to .xg file

        Returns:
            List[Decision]: Parsed decisions

        Raises:
            FileNotFoundError: File not found
            ValueError: Invalid .xg format
            ParseError: Parsing failed
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        logger.info(f"Parsing XG binary file: {file_path}")

        try:
            # Use xgimport to read the .xg file
            xg_import = xgimport.Import(str(path))
            decisions = []

            # Track game state across records
            file_version = -1
            match_length = 0
            score_x = 0
            score_o = 0
            crawford = False

            # Process file segments
            for segment in xg_import.getfilesegment():
                if segment.type == xgimport.Import.Segment.XG_GAMEFILE:
                    # Parse game file segment
                    segment.fd.seek(0)

                    while True:
                        record = xgstruct.GameFileRecord(version=file_version).fromstream(segment.fd)
                        if record is None:
                            break

                        # Process different record types
                        if isinstance(record, xgstruct.HeaderMatchEntry):
                            file_version = record.Version
                            match_length = record.MatchLength
                            logger.debug(f"Match header: version={file_version}, match_length={match_length}")

                        elif isinstance(record, xgstruct.HeaderGameEntry):
                            score_x = record.Score1
                            score_o = record.Score2
                            crawford = bool(record.CrawfordApply)
                            logger.debug(f"Game header: score={score_x}-{score_o}, crawford={crawford}")

                        elif isinstance(record, xgstruct.MoveEntry):
                            try:
                                decision = XGBinaryParser._parse_move_entry(
                                    record, match_length, score_x, score_o, crawford
                                )
                                if decision:
                                    decisions.append(decision)
                            except Exception as e:
                                logger.warning(f"Failed to parse move entry: {e}")

                        elif isinstance(record, xgstruct.CubeEntry):
                            try:
                                decision = XGBinaryParser._parse_cube_entry(
                                    record, match_length, score_x, score_o, crawford
                                )
                                if decision:
                                    decisions.append(decision)
                            except Exception as e:
                                logger.warning(f"Failed to parse cube entry: {e}")

            if not decisions:
                raise ParseError("No valid positions found in file")

            logger.info(f"Successfully parsed {len(decisions)} decisions from {file_path}")
            return decisions

        except xgimport.Error as e:
            raise ParseError(f"XG import error: {e}")
        except Exception as e:
            raise ParseError(f"Failed to parse .xg file: {e}")

    @staticmethod
    def _transform_position(raw_points: List[int], on_roll: Player) -> Position:
        """
        Transform XG binary position array to internal Position model.

        XG binary format uses OPPOSITE sign convention from AnkiGammon:
        - XG: Positive = O checkers, Negative = X checkers
        - AnkiGammon: Positive = X checkers, Negative = O checkers

        Therefore, we need to invert all signs when copying the position.

        IMPORTANT: This method only handles sign inversion. XG binary ALWAYS stores
        positions from O's (Player 1's) perspective. The caller must flip the position
        if it needs to be shown from X's perspective.

        Args:
            raw_points: Raw 26-element position array from XG binary
            on_roll: Player who is on roll (currently unused, kept for compatibility)

        Returns:
            Position object with signs inverted (still from O's perspective)
        """
        position = Position()

        # XG binary uses opposite sign convention - invert all signs
        position.points = [-count for count in raw_points]

        # Calculate borne-off checkers (each player starts with 15)
        total_x = sum(count for count in position.points if count > 0)
        total_o = sum(abs(count) for count in position.points if count < 0)

        position.x_off = 15 - total_x
        position.o_off = 15 - total_o

        # Validate position
        XGBinaryParser._validate_position(position)

        return position

    @staticmethod
    def _validate_position(position: Position) -> None:
        """
        Validate position to catch inversions and corruption.

        Args:
            position: Position to validate

        Raises:
            ValueError: If position is invalid
        """
        # Count checkers
        total_x = sum(count for count in position.points if count > 0)
        total_o = sum(abs(count) for count in position.points if count < 0)

        # Each player should have at most 15 checkers on board
        if total_x > 15:
            raise ValueError(f"Invalid position: X has {total_x} checkers on board (max 15)")
        if total_o > 15:
            raise ValueError(f"Invalid position: O has {total_o} checkers on board (max 15)")

        # Total checkers (on board + borne off) should be exactly 15 per player
        if total_x + position.x_off != 15:
            raise ValueError(
                f"Invalid position: X has {total_x} on board + {position.x_off} off = "
                f"{total_x + position.x_off} (expected 15)"
            )
        if total_o + position.o_off != 15:
            raise ValueError(
                f"Invalid position: O has {total_o} on board + {position.o_off} off = "
                f"{total_o + position.o_off} (expected 15)"
            )

        # Check bar constraints (should be <= 2 per player in normal positions)
        x_bar = position.points[0]
        o_bar = abs(position.points[25])
        if x_bar > 15:  # Relaxed constraint - theoretically up to 15
            raise ValueError(f"Invalid position: X has {x_bar} checkers on bar")
        if o_bar > 15:
            raise ValueError(f"Invalid position: O has {o_bar} checkers on bar")

    @staticmethod
    def _parse_move_entry(
        move_entry: xgstruct.MoveEntry,
        match_length: int,
        score_x: int,
        score_o: int,
        crawford: bool
    ) -> Optional[Decision]:
        """
        Convert MoveEntry to Decision object.

        Args:
            move_entry: MoveEntry from xgstruct
            match_length: Match length (0 for money game)
            score_x: Player X score
            score_o: Player O score
            crawford: Crawford game flag

        Returns:
            Decision object or None if invalid
        """
        # Determine player on roll
        # XG uses ActiveP: 1 or 2
        # Map to AnkiGammon: Player.O (bottom) or Player.X (top)
        on_roll = Player.O if move_entry.ActiveP == 1 else Player.X

        # Create position from XG position array
        # XG binary format ALWAYS stores positions from O's (Player 1's) perspective
        # We need to flip to X's perspective when X is on roll
        position = XGBinaryParser._transform_position(
            list(move_entry.PositionI),
            on_roll
        )

        # Flip position if X is on roll (since XG stores from O's perspective)
        if on_roll == Player.X:
            # Flip the position by reversing points and swapping signs
            flipped_points = [0] * 26
            flipped_points[0] = -position.points[25]  # X's bar = O's bar (negated)
            flipped_points[25] = -position.points[0]  # O's bar = X's bar (negated)
            for i in range(1, 25):
                flipped_points[i] = -position.points[25 - i]
            position.points = flipped_points
            position.x_off, position.o_off = position.o_off, position.x_off

        # Get dice
        dice = tuple(move_entry.Dice) if move_entry.Dice else None

        # Parse cube state
        cube_value = abs(move_entry.CubeA) if move_entry.CubeA != 0 else 1
        if move_entry.CubeA > 0:
            cube_owner = CubeState.X_OWNS  # Player X owns
        elif move_entry.CubeA < 0:
            cube_owner = CubeState.O_OWNS  # Player O owns
        else:
            cube_owner = CubeState.CENTERED

        # Parse candidate moves from analysis
        moves = []
        if hasattr(move_entry, 'DataMoves') and move_entry.DataMoves:
            data_moves = move_entry.DataMoves
            n_moves = min(move_entry.NMoveEval, data_moves.NMoves)

            for i in range(n_moves):
                # Parse move notation with compound move combination and hit detection
                notation = XGBinaryParser._convert_move_notation(
                    data_moves.Moves[i],
                    position,
                    on_roll
                )

                # Get equity (7-element tuple from XG)
                # XG Format: [Lose_BG, Lose_G, Lose_S, Win_S, Win_G, Win_BG, Equity]
                # Indices:   [0]      [1]     [2]     [3]    [4]    [5]     [6]
                #
                # IMPORTANT: Despite the naming, these are CUMULATIVE probabilities:
                #   Lose_S (index 2) = TOTAL losses (all types: normal + gammon + backgammon)
                #   Lose_G (index 1) = Gammon + backgammon losses (subset of Lose_S)
                #   Lose_BG (index 0) = Backgammon losses only (subset of Lose_G)
                #   Win_S (index 3) = TOTAL wins (all types: normal + gammon + backgammon)
                #   Win_G (index 4) = Gammon + backgammon wins (subset of Win_S)
                #   Win_BG (index 5) = Backgammon wins only (subset of Win_G)
                #   Equity (index 6) = Overall equity value
                #
                # Note: Lose_S + Win_S = 1.0 (or very close to 1.0)
                equity_tuple = data_moves.Eval[i]
                equity = equity_tuple[6]  # Overall equity at index 6

                # Extract winning chances (convert from decimals to percentages)
                # Store cumulative values as displayed by XG/GnuBG:
                #   "Player: 50.41% (G:15.40% B:2.03%)" means:
                #     50.41% total wins, of which 15.40% are gammon or better,
                #     of which 2.03% are backgammon
                opponent_win_pct = equity_tuple[2] * 100  # Total opponent wins (index 2 = Lose_S)
                opponent_gammon_pct = equity_tuple[1] * 100  # Opp gammon+BG (index 1 = Lose_G)
                opponent_backgammon_pct = equity_tuple[0] * 100  # Opp BG only (index 0 = Lose_BG)
                player_win_pct = equity_tuple[3] * 100  # Total player wins (index 3 = Win_S)
                player_gammon_pct = equity_tuple[4] * 100  # Player gammon+BG (index 4 = Win_G)
                player_backgammon_pct = equity_tuple[5] * 100  # Player BG only (index 5 = Win_BG)

                move = Move(
                    notation=notation,
                    equity=equity,
                    error=0.0,  # Will be calculated based on best move
                    rank=i + 1,  # Temporary rank
                    xg_rank=i + 1,
                    xg_error=0.0,
                    xg_notation=notation,
                    from_xg_analysis=True,
                    player_win_pct=player_win_pct,
                    player_gammon_pct=player_gammon_pct,
                    player_backgammon_pct=player_backgammon_pct,
                    opponent_win_pct=opponent_win_pct,
                    opponent_gammon_pct=opponent_gammon_pct,
                    opponent_backgammon_pct=opponent_backgammon_pct
                )
                moves.append(move)

        # Mark which move was actually played
        if hasattr(move_entry, 'Moves') and move_entry.Moves:
            played_notation = XGBinaryParser._convert_move_notation(
                move_entry.Moves,
                position,
                on_roll
            )
            # Normalize by sorting sub-moves for comparison
            played_normalized = XGBinaryParser._normalize_move_notation(played_notation)

            for move in moves:
                move_normalized = XGBinaryParser._normalize_move_notation(move.notation)
                if move_normalized == played_normalized:
                    move.was_played = True
                    break

        # Sort moves by equity (highest first) and assign ranks
        if moves:
            moves.sort(key=lambda m: m.equity, reverse=True)
            best_equity = moves[0].equity

            for i, move in enumerate(moves):
                move.rank = i + 1
                move.error = abs(best_equity - move.equity)
                move.xg_error = move.equity - best_equity  # Negative for worse moves

        # Generate XGID for the position
        crawford_jacoby = 1 if crawford else 0
        xgid = position.to_xgid(
            cube_value=cube_value,
            cube_owner=cube_owner,
            dice=dice,
            on_roll=on_roll,
            score_x=score_x,
            score_o=score_o,
            match_length=match_length,
            crawford_jacoby=crawford_jacoby
        )

        # Create Decision
        decision = Decision(
            position=position,
            on_roll=on_roll,
            dice=dice,
            score_x=score_x,
            score_o=score_o,
            match_length=match_length,
            crawford=crawford,
            cube_value=cube_value,
            cube_owner=cube_owner,
            decision_type=DecisionType.CHECKER_PLAY,
            candidate_moves=moves,
            xgid=xgid
        )

        return decision

    @staticmethod
    def _parse_cube_entry(
        cube_entry: xgstruct.CubeEntry,
        match_length: int,
        score_x: int,
        score_o: int,
        crawford: bool
    ) -> Optional[Decision]:
        """
        Convert CubeEntry to Decision object.

        XG binary files contain cube entries for all cube decisions in a game,
        but not all of them are analyzed. This method filters out unanalyzed
        cube decisions and extracts equity values from analyzed ones.

        Unanalyzed cube decisions are identified by:
        - FlagDouble == -100 or -1000 (indicates not analyzed)
        - All equities are 0.0 and position is empty

        Analyzed cube decisions contain:
        - equB: Equity for "No Double"
        - equDouble: Equity for "Double/Take"
        - equDrop: Equity for "Double/Pass" (typically -1.0 for opponent)
        - Eval: Win probabilities for "No Double" scenario
        - EvalDouble: Win probabilities for "Double/Take" scenario

        IMPORTANT: For cube decisions, we always need to show the position from the
        doubler's perspective (the player who has the cube decision), regardless of
        whether the error was made by the doubler or the responder. This is critical
        for score matrix generation and consistent position display.

        Args:
            cube_entry: CubeEntry from xgstruct
            match_length: Match length (0 for money game)
            score_x: Player X score
            score_o: Player O score
            crawford: Crawford game flag

        Returns:
            Decision object with 5 cube options, or None if unanalyzed
        """
        # Determine player on roll from ActiveP
        # IMPORTANT: ActiveP may represent the responder for take/pass errors,
        # but we always need to show cube decisions from the doubler's perspective
        active_player = Player.O if cube_entry.ActiveP == 1 else Player.X

        # Create position with perspective transformation (using active_player)
        position = XGBinaryParser._transform_position(
            list(cube_entry.Position),
            active_player
        )

        # Parse cube state
        cube_value = abs(cube_entry.CubeB) if cube_entry.CubeB != 0 else 1
        if cube_entry.CubeB > 0:
            cube_owner = CubeState.X_OWNS
        elif cube_entry.CubeB < 0:
            cube_owner = CubeState.O_OWNS
        else:
            cube_owner = CubeState.CENTERED

        # Parse cube decisions from Doubled analysis
        moves = []
        if hasattr(cube_entry, 'Doubled') and cube_entry.Doubled:
            doubled = cube_entry.Doubled

            # Check if cube decision was analyzed
            # FlagDouble -100 or -1000 indicates unanalyzed position
            flag_double = doubled.get('FlagDouble', -100)
            if flag_double in (-100, -1000):
                logger.debug("Skipping unanalyzed cube decision (FlagDouble=%d)", flag_double)
                return None

            # Extract equities
            eq_no_double = doubled.get('equB', 0.0)
            eq_double_take = doubled.get('equDouble', 0.0)
            eq_double_drop = doubled.get('equDrop', -1.0)

            # Validate that we have actual analysis data
            # If all equities are zero and position is empty, skip this decision
            if (eq_no_double == 0.0 and eq_double_take == 0.0 and
                abs(eq_double_drop - (-1.0)) < 0.001):
                # Check if position has any checkers
                pos = doubled.get('Pos', None)
                if pos and all(v == 0 for v in pos):
                    logger.debug("Skipping cube decision with no analysis data")
                    return None

            # Extract winning chances
            eval_no_double = doubled.get('Eval', None)
            eval_double = doubled.get('EvalDouble', None)

            # Create 5 cube options (similar to XGTextParser)
            cube_options = []

            # 1. No double
            if eval_no_double:
                cube_options.append({
                    'notation': 'No Double/Take',
                    'equity': eq_no_double,
                    'xg_notation': 'No double',
                    'from_xg': True,
                    'eval': eval_no_double
                })

            # 2. Double/Take
            if eval_double:
                cube_options.append({
                    'notation': 'Double/Take',
                    'equity': eq_double_take,
                    'xg_notation': 'Double/Take',
                    'from_xg': True,
                    'eval': eval_double
                })

            # 3. Double/Pass
            cube_options.append({
                'notation': 'Double/Pass',
                'equity': eq_double_drop,
                'xg_notation': 'Double/Pass',
                'from_xg': True,
                'eval': None
            })

            # 4 & 5. Too good options (synthetic)
            cube_options.append({
                'notation': 'Too good/Take',
                'equity': eq_double_drop,
                'xg_notation': None,
                'from_xg': False,
                'eval': None
            })

            cube_options.append({
                'notation': 'Too good/Pass',
                'equity': eq_double_drop,
                'xg_notation': None,
                'from_xg': False,
                'eval': None
            })

            # Create Move objects
            for i, opt in enumerate(cube_options):
                eval_data = opt.get('eval')

                # Extract winning chances if available
                player_win_pct = None
                player_gammon_pct = None
                player_backgammon_pct = None
                opponent_win_pct = None
                opponent_gammon_pct = None
                opponent_backgammon_pct = None

                if eval_data and len(eval_data) >= 7:
                    # Same format as MoveEntry: [Lose_BG, Lose_G, Lose_S, Win_S, Win_G, Win_BG, Equity]
                    # Cumulative probabilities where Lose_S and Win_S are totals
                    opponent_win_pct = eval_data[2] * 100  # Total opponent wins (Lose_S)
                    opponent_gammon_pct = eval_data[1] * 100  # Opp gammon+BG (Lose_G)
                    opponent_backgammon_pct = eval_data[0] * 100  # Opp BG only (Lose_BG)
                    player_win_pct = eval_data[3] * 100  # Total player wins (Win_S)
                    player_gammon_pct = eval_data[4] * 100  # Player gammon+BG (Win_G)
                    player_backgammon_pct = eval_data[5] * 100  # Player BG only (Win_BG)

                move = Move(
                    notation=opt['notation'],
                    equity=opt['equity'],
                    error=0.0,
                    rank=0,  # Will be assigned later
                    xg_rank=i + 1 if opt['from_xg'] else None,
                    xg_error=None,
                    xg_notation=opt['xg_notation'],
                    from_xg_analysis=opt['from_xg'],
                    player_win_pct=player_win_pct,
                    player_gammon_pct=player_gammon_pct,
                    player_backgammon_pct=player_backgammon_pct,
                    opponent_win_pct=opponent_win_pct,
                    opponent_gammon_pct=opponent_gammon_pct,
                    opponent_backgammon_pct=opponent_backgammon_pct
                )
                moves.append(move)

        # Mark which cube action was actually played
        # Double: 0=no double, 1=doubled
        # Take: 0=pass, 1=take, 2=beaver
        if hasattr(cube_entry, 'Double') and hasattr(cube_entry, 'Take'):
            if cube_entry.Double == 0:
                # No double was the action taken
                played_action = 'No Double/Take'
            elif cube_entry.Double == 1:
                if cube_entry.Take == 1:
                    # Doubled and taken
                    played_action = 'Double/Take'
                else:
                    # Doubled and passed
                    played_action = 'Double/Pass'
            else:
                played_action = None

            if played_action:
                for move in moves:
                    if move.notation == played_action:
                        move.was_played = True
                        break

        # Determine best move and assign ranks
        # Cube decision logic must account for perfect opponent response.
        # Key insight: equDouble represents equity if opponent TAKES, but opponent
        # will only take if it's correct for them.
        #
        # Algorithm:
        # 1. Determine opponent's correct response: take or pass?
        #    - If equDouble > equDrop: opponent should PASS (taking is worse for them)
        #    - If equDouble < equDrop: opponent should TAKE (taking is better for them)
        # 2. Compare equB (No Double) vs the correct doubling equity
        #    - If opponent passes: compare equB vs equDrop (Double/Pass)
        #    - If opponent takes: compare equB vs equDouble (Double/Take)
        if moves:
            # Find the three main cube options
            no_double_move = None
            double_take_move = None
            double_pass_move = None

            for move in moves:
                if move.notation == "No Double/Take":
                    no_double_move = move
                elif move.notation == "Double/Take":
                    double_take_move = move
                elif move.notation == "Double/Pass":
                    double_pass_move = move

            if no_double_move and double_take_move and double_pass_move:
                # Step 1: Determine opponent's correct response
                # If equDouble > equDrop, opponent should pass (taking gives them worse equity)
                if double_take_move.equity > double_pass_move.equity:
                    # Opponent should PASS
                    # Compare No Double vs Double/Pass
                    if no_double_move.equity >= double_pass_move.equity:
                        best_move_notation = "No Double/Take"
                        best_equity = no_double_move.equity
                    else:
                        best_move_notation = "Double/Pass"
                        best_equity = double_pass_move.equity
                else:
                    # Opponent should TAKE
                    # Compare No Double vs Double/Take
                    if no_double_move.equity >= double_take_move.equity:
                        best_move_notation = "No Double/Take"
                        best_equity = no_double_move.equity
                    else:
                        best_move_notation = "Double/Take"
                        best_equity = double_take_move.equity
            elif no_double_move:
                best_move_notation = "No Double/Take"
                best_equity = no_double_move.equity
            elif double_take_move:
                best_move_notation = "Double/Take"
                best_equity = double_take_move.equity
            else:
                # Fallback: sort by equity
                moves.sort(key=lambda m: m.equity, reverse=True)
                best_move_notation = moves[0].notation
                best_equity = moves[0].equity

            # Assign rank 1 to best move
            for move in moves:
                if move.notation == best_move_notation:
                    move.rank = 1
                    move.error = 0.0
                    if move.from_xg_analysis:
                        move.xg_error = 0.0

            # Assign ranks 2-5 to other moves based on equity
            other_moves = [m for m in moves if m.notation != best_move_notation]
            other_moves.sort(key=lambda m: m.equity, reverse=True)

            for i, move in enumerate(other_moves):
                move.rank = i + 2  # Ranks 2, 3, 4, 5
                move.error = abs(best_equity - move.equity)
                if move.from_xg_analysis:
                    move.xg_error = move.equity - best_equity

        # Extract decision-level winning chances from "No Double" evaluation
        # This represents the current position's winning chances
        decision_player_win_pct = None
        decision_player_gammon_pct = None
        decision_player_backgammon_pct = None
        decision_opponent_win_pct = None
        decision_opponent_gammon_pct = None
        decision_opponent_backgammon_pct = None

        if eval_no_double and len(eval_no_double) >= 7:
            # Same format as MoveEntry: [Lose_BG, Lose_G, Lose_S, Win_S, Win_G, Win_BG, Equity]
            decision_opponent_win_pct = eval_no_double[2] * 100  # Total opponent wins
            decision_opponent_gammon_pct = eval_no_double[1] * 100  # Opp gammon+BG
            decision_opponent_backgammon_pct = eval_no_double[0] * 100  # Opp BG only
            decision_player_win_pct = eval_no_double[3] * 100  # Total player wins
            decision_player_gammon_pct = eval_no_double[4] * 100  # Player gammon+BG
            decision_player_backgammon_pct = eval_no_double[5] * 100  # Player BG only

        # Extract cube and take errors from XG binary data
        # ErrCube: error made by doubler on double/no double decision
        # ErrTake: error made by responder on take/pass decision
        # Value of -1000 indicates not analyzed
        cube_error = None
        take_error = None
        if hasattr(cube_entry, 'ErrCube'):
            err_cube_raw = cube_entry.ErrCube
            if err_cube_raw != -1000:
                cube_error = err_cube_raw
        if hasattr(cube_entry, 'ErrTake'):
            err_take_raw = cube_entry.ErrTake
            if err_take_raw != -1000:
                take_error = err_take_raw

        # Determine who the doubler is (the player making the cube decision)
        # For cube decisions, we ALWAYS want to show the position from the doubler's perspective,
        # even if the error was made by the responder on the take/pass decision.
        #
        # CRITICAL UNDERSTANDING:
        # - ActiveP = the player who had the cube decision (on roll)
        # - cube_error = error made by ActiveP on the double/no double decision
        # - take_error = error made by the OPPONENT of ActiveP on the take/pass decision
        #
        # Therefore, ActiveP is ALWAYS the potential doubler (the player who had access to the cube).
        # The doubler is determined by:
        # 1. If cube is owned by X: only X can redouble (X is the doubler)
        # 2. If cube is owned by O: only O can redouble (O is the doubler)
        # 3. If cube is centered: ActiveP is the doubler (had the cube decision)

        # Check the actual cube action taken in the game
        doubled_in_game = hasattr(cube_entry, 'Double') and cube_entry.Double == 1

        if doubled_in_game:
            # A double occurred in the game - determine who doubled
            if cube_owner == CubeState.X_OWNS:
                # X owns cube and redoubled
                doubler = Player.X
            elif cube_owner == CubeState.O_OWNS:
                # O owns cube and redoubled
                doubler = Player.O
            else:
                # Cube is centered - ActiveP is the doubler
                doubler = active_player
        else:
            # No double occurred - determine who had the cube decision
            if cube_owner == CubeState.X_OWNS:
                # X owns cube - X had the decision (chose not to redouble)
                doubler = Player.X
            elif cube_owner == CubeState.O_OWNS:
                # O owns cube - O had the decision (chose not to redouble)
                doubler = Player.O
            else:
                # Cube is centered - ActiveP had the cube decision (chose not to double)
                doubler = active_player

        # Always use doubler as on_roll for cube decisions
        on_roll = doubler

        # CRITICAL: XG binary ALWAYS stores positions from O's (Player 1's) perspective
        # If the doubler is X, we need to flip the position to show it from X's perspective
        if doubler == Player.X:
            logger.debug(
                f"Flipping position from O's perspective to X's perspective (doubler is X)"
            )
            # Flip the position by reversing points and swapping signs
            flipped_points = [0] * 26
            # Swap the bars
            flipped_points[0] = -position.points[25]  # X's bar = O's bar (negated)
            flipped_points[25] = -position.points[0]  # O's bar = X's bar (negated)
            # Reverse and negate board points
            for i in range(1, 25):
                flipped_points[i] = -position.points[25 - i]

            position.points = flipped_points
            # Swap borne-off counts
            position.x_off, position.o_off = position.o_off, position.x_off

        # Generate XGID for the position
        crawford_jacoby = 1 if crawford else 0
        xgid = position.to_xgid(
            cube_value=cube_value,
            cube_owner=cube_owner,
            dice=None,  # No dice for cube decisions
            on_roll=on_roll,
            score_x=score_x,
            score_o=score_o,
            match_length=match_length,
            crawford_jacoby=crawford_jacoby
        )

        # Create Decision
        decision = Decision(
            position=position,
            on_roll=on_roll,
            dice=None,  # No dice for cube decisions
            score_x=score_x,
            score_o=score_o,
            match_length=match_length,
            crawford=crawford,
            cube_value=cube_value,
            cube_owner=cube_owner,
            decision_type=DecisionType.CUBE_ACTION,
            candidate_moves=moves,
            cube_error=cube_error,
            take_error=take_error,
            xgid=xgid,
            player_win_pct=decision_player_win_pct,
            player_gammon_pct=decision_player_gammon_pct,
            player_backgammon_pct=decision_player_backgammon_pct,
            opponent_win_pct=decision_opponent_win_pct,
            opponent_gammon_pct=decision_opponent_gammon_pct,
            opponent_backgammon_pct=decision_opponent_backgammon_pct
        )

        return decision

    @staticmethod
    def _normalize_move_notation(notation: str) -> str:
        """
        Normalize move notation by sorting sub-moves.

        This handles cases where "7/6 12/8" and "12/8 7/6" represent the same move
        but with sub-moves in different order.

        Args:
            notation: Move notation string (e.g., "12/8 7/6")

        Returns:
            Normalized notation with sub-moves sorted (e.g., "7/6 12/8")
        """
        if not notation or notation == "Cannot move":
            return notation

        # Split into sub-moves
        parts = notation.split()

        # Sort sub-moves for consistent comparison
        # Sort by from point (descending), then by to point
        parts.sort(reverse=True)

        return " ".join(parts)

    @staticmethod
    def _convert_move_notation(
        xg_moves: Tuple[int, ...],
        position: Optional[Position] = None,
        on_roll: Optional[Player] = None
    ) -> str:
        """
        Convert XG move notation to readable format with compound move combination and hit detection.

        IMPORTANT: XG binary uses 0-based indexing for board points in move notation.
        - XG binary: 0-23 for board points
        - Standard notation: 1-24 for board points
        - Therefore, we add 1 to convert board point numbers to standard notation

        XG binary stores compound moves as separate sub-moves (e.g., 20/16 16/15)
        but standard notation combines them (e.g., 20/15*). This function:
        1. Converts 0-based to 1-based point numbering
        2. Combines consecutive sub-moves into compound moves
        3. Detects and marks hits with *
        4. Detects duplicate moves and uses (2), (3), (4) notation for doublets

        XG format: [from1, to1, from2, to2, from3, to3, from4, to4]
        Special values:
        - -1: End of move list OR bearing off (when used as destination)
        - 24: Bar (both players when entering)
        - 0-23: Board points (0-based, must add 1 for standard notation)

        Args:
            xg_moves: Tuple of 8 integers
            position: Position object for hit detection (optional)
            on_roll: Player making the move (optional)

        Returns:
            Move notation string (e.g., "20/15*", "bar/22", "15/9(2)")
            Returns "Cannot move" for illegal/blocked positions (all zeros)
        """
        if not xg_moves or len(xg_moves) < 2:
            return ""

        # Check for illegal/blocked move (all zeros)
        if all(x == 0 for x in xg_moves):
            return "Cannot move"

        # Pass 1: Parse all sub-moves
        sub_moves = []
        for i in range(0, len(xg_moves), 2):
            from_point = xg_moves[i]

            # -1 indicates end of move
            if from_point == -1:
                break

            if i + 1 >= len(xg_moves):
                break

            to_point = xg_moves[i + 1]
            sub_moves.append((from_point, to_point))

        if not sub_moves:
            return ""

        # Pass 2: Build adjacency map for chain detection
        # Map from to_point -> list of indices that start from that point
        from_point_map = {}
        for idx, (from_point, to_point) in enumerate(sub_moves):
            if from_point not in from_point_map:
                from_point_map[from_point] = []
            from_point_map[from_point].append(idx)

        # Pass 3: Greedily build maximal chains
        used = [False] * len(sub_moves)
        combined_moves = []

        # Sort sub-moves by from_point descending to process in order
        sorted_indices = sorted(range(len(sub_moves)),
                               key=lambda i: sub_moves[i][0],
                               reverse=True)

        for start_idx in sorted_indices:
            if used[start_idx]:
                continue

            # Start a new chain
            from_point, to_point = sub_moves[start_idx]
            used[start_idx] = True

            # Extend the chain as far as possible
            while to_point in from_point_map:
                # Find an unused move that starts from current to_point
                extended = False
                for next_idx in from_point_map[to_point]:
                    if not used[next_idx]:
                        _, next_to = sub_moves[next_idx]
                        to_point = next_to
                        used[next_idx] = True
                        extended = True
                        break

                if not extended:
                    break

            # Check for hit if position is available
            hit = False
            if position and on_roll and 0 <= to_point <= 23:
                # Convert 0-based to 1-based for position lookup
                checker_count = position.points[to_point + 1]
                # Hit occurs if opponent has exactly 1 checker at destination
                if on_roll == Player.X and checker_count == -1:
                    hit = True  # X hitting O
                elif on_roll == Player.O and checker_count == 1:
                    hit = True  # O hitting X

            combined_moves.append((from_point, to_point, hit))

        # Pass 4: Count duplicates and format
        from collections import Counter

        # Count occurrences of each move (excluding hit marker for counting)
        move_counts = Counter((from_point, to_point) for from_point, to_point, _ in combined_moves)

        # Track how many of each move we've seen (for numbering)
        move_seen = {}

        # Sort combined moves for consistent output
        combined_moves.sort(key=lambda m: m[0], reverse=True)

        # Format as notation strings
        parts = []
        for from_point, to_point, hit in combined_moves:
            move_key = (from_point, to_point)
            count = move_counts[move_key]

            # Track this occurrence
            if move_key not in move_seen:
                move_seen[move_key] = 0
            move_seen[move_key] += 1
            occurrence = move_seen[move_key]

            # Convert special values to standard backgammon notation
            # Handle from_point
            if from_point == 24:
                from_str = "bar"  # Bar for both players
            else:
                from_str = str(from_point + 1)  # Convert 0-based to 1-based (0→1, 23→24)

            # Handle to_point
            if to_point == -1:
                to_str = "off"  # Bearing off
            elif to_point == 24:
                to_str = "bar"  # Opponent hit and sent to bar
            else:
                to_str = str(to_point + 1)  # Convert 0-based to 1-based (0→1, 23→24)

            # Build notation
            notation = f"{from_str}/{to_str}"
            if hit:
                notation += "*"

            # Add doublet notation if this is the first occurrence and count > 1
            if occurrence == 1 and count > 1:
                notation += f"({count})"
            elif occurrence > 1:
                # Skip duplicate occurrences (already counted in first one)
                continue

            parts.append(notation)

        return " ".join(parts) if parts else ""
