"""Parser for XG text exports with ASCII board diagrams.

This parser handles the text format that XG exports with:
- XGID line
- ASCII board diagram
- Move analysis with equities and rollout data
"""

import re
from typing import List, Optional, Tuple

from ankigammon.models import Decision, Move, Position, Player, CubeState, DecisionType
from ankigammon.utils.xgid import parse_xgid
from ankigammon.utils.ogid import parse_ogid
from ankigammon.utils.gnuid import parse_gnuid


class XGTextParser:
    """Parse XG text export format."""

    @staticmethod
    def parse_file(file_path: str) -> List[Decision]:
        """
        Parse an XG text export file.

        Args:
            file_path: Path to XG text file

        Returns:
            List of Decision objects
        """
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        return XGTextParser.parse_string(content)

    @staticmethod
    def parse_string(content: str) -> List[Decision]:
        """
        Parse XG text export from string.

        Args:
            content: Full text content

        Returns:
            List of Decision objects
        """
        decisions = []

        # Split into sections by XGID, OGID, or GNUID patterns
        # Pattern matches XGID=, OGID (base-26 format), or GNUID (base64 format)
        sections = re.split(r'(XGID=[^\n]+|^[0-9a-p]+:[0-9a-p]+:[A-Z0-9]{3}[^\n]*|^[A-Za-z0-9+/]{14}:[A-Za-z0-9+/]{12})', content, flags=re.MULTILINE)

        for i in range(1, len(sections), 2):
            if i + 1 >= len(sections):
                break

            position_id_line = sections[i].strip()
            analysis_section = sections[i + 1]

            decision = XGTextParser._parse_decision_section(position_id_line, analysis_section)
            if decision:
                decisions.append(decision)

        return decisions

    @staticmethod
    def _parse_decision_section(position_id_line: str, analysis_section: str) -> Optional[Decision]:
        """Parse a single decision section."""
        # Detect and parse position ID (XGID, OGID, or GNUID)
        try:
            # Check if it's XGID format
            if position_id_line.startswith('XGID='):
                position, metadata = parse_xgid(position_id_line)
                position_id = position_id_line
            # Check if it's OGID format (base-26 encoding)
            elif re.match(r'^[0-9a-p]+:[0-9a-p]+:[A-Z0-9]{3}', position_id_line):
                position, metadata = parse_ogid(position_id_line)
                position_id = position_id_line
            # Check if it's GNUID format (base64 encoding)
            elif re.match(r'^[A-Za-z0-9+/]{14}:[A-Za-z0-9+/]{12}$', position_id_line):
                position, metadata = parse_gnuid(position_id_line)
                position_id = position_id_line
            else:
                raise ValueError(f"Unknown position ID format: {position_id_line}")
        except Exception as e:
            print(f"Error parsing position ID '{position_id_line}': {e}")
            return None

        # Parse game info (players, score, cube, etc.)
        game_info = XGTextParser._parse_game_info(analysis_section)
        if game_info:
            # Update metadata with parsed info. XGID data takes precedence where it exists
            # since it correctly accounts for perspective in all position encodings.
            for key, value in game_info.items():
                if key not in metadata or key == 'decision_type':
                    # Add values not present in XGID metadata
                    # decision_type can only come from text parsing
                    metadata[key] = value

        # Parse move analysis
        moves = XGTextParser._parse_moves(analysis_section)
        # Note: Allow empty moves for XGID-only positions (gnubg can analyze them later)
        # if not moves:
        #     return None

        # Parse global winning chances (for cube decisions)
        winning_chances = XGTextParser._parse_winning_chances(analysis_section)

        # Determine decision type from metadata or dice presence
        if 'decision_type' in metadata:
            decision_type = metadata['decision_type']
        elif 'dice' not in metadata or metadata.get('dice') is None:
            decision_type = DecisionType.CUBE_ACTION
        else:
            decision_type = DecisionType.CHECKER_PLAY

        # Determine Crawford status from multiple sources
        # The crawford_jacoby field indicates Crawford rule for matches or Jacoby rule for money games
        match_length = metadata.get('match_length', 0)
        crawford = False

        if match_length > 0:
            if 'crawford' in metadata and metadata['crawford']:
                crawford = True
            elif 'crawford_jacoby' in metadata and metadata['crawford_jacoby'] > 0:
                crawford = True
            elif 'match_modifier' in metadata and metadata['match_modifier'] == 'C':
                crawford = True

        # Create decision
        decision = Decision(
            position=position,
            xgid=position_id,  # Store original position ID (XGID or OGID)
            on_roll=metadata.get('on_roll', Player.O),
            dice=metadata.get('dice'),
            score_x=metadata.get('score_x', 0),
            score_o=metadata.get('score_o', 0),
            match_length=metadata.get('match_length', 0),
            crawford=crawford,
            cube_value=metadata.get('cube_value', 1),
            cube_owner=metadata.get('cube_owner', CubeState.CENTERED),
            decision_type=decision_type,
            candidate_moves=moves,
            player_win_pct=winning_chances.get('player_win_pct'),
            player_gammon_pct=winning_chances.get('player_gammon_pct'),
            player_backgammon_pct=winning_chances.get('player_backgammon_pct'),
            opponent_win_pct=winning_chances.get('opponent_win_pct'),
            opponent_gammon_pct=winning_chances.get('opponent_gammon_pct'),
            opponent_backgammon_pct=winning_chances.get('opponent_backgammon_pct'),
        )

        return decision

    @staticmethod
    def _parse_winning_chances(text: str) -> dict:
        """
        Parse global winning chances from text section.

        Format:
            Player Winning Chances:   52.68% (G:14.35% B:0.69%)
            Opponent Winning Chances: 47.32% (G:12.42% B:0.55%)

        Returns dict with keys: player_win_pct, player_gammon_pct, player_backgammon_pct,
                                opponent_win_pct, opponent_gammon_pct, opponent_backgammon_pct
        """
        chances = {}

        # Parse player winning chances
        player_match = re.search(
            r'Player Winning Chances:\s*(\d+\.?\d*)%\s*\(G:(\d+\.?\d*)%\s*B:(\d+\.?\d*)%\)',
            text,
            re.IGNORECASE
        )
        if player_match:
            chances['player_win_pct'] = float(player_match.group(1))
            chances['player_gammon_pct'] = float(player_match.group(2))
            chances['player_backgammon_pct'] = float(player_match.group(3))

        # Parse opponent winning chances
        opponent_match = re.search(
            r'Opponent Winning Chances:\s*(\d+\.?\d*)%\s*\(G:(\d+\.?\d*)%\s*B:(\d+\.?\d*)%\)',
            text,
            re.IGNORECASE
        )
        if opponent_match:
            chances['opponent_win_pct'] = float(opponent_match.group(1))
            chances['opponent_gammon_pct'] = float(opponent_match.group(2))
            chances['opponent_backgammon_pct'] = float(opponent_match.group(3))

        return chances

    @staticmethod
    def _parse_move_winning_chances(move_text: str) -> dict:
        """
        Parse winning chances from a move's analysis section.

        Format:
              Player:   53.81% (G:17.42% B:0.87%)
              Opponent: 46.19% (G:12.99% B:0.64%)

        Returns dict with keys: player_win_pct, player_gammon_pct, player_backgammon_pct,
                                opponent_win_pct, opponent_gammon_pct, opponent_backgammon_pct
        """
        chances = {}

        # Parse player chances
        player_match = re.search(
            r'Player:\s*(\d+\.?\d*)%\s*\(G:(\d+\.?\d*)%\s*B:(\d+\.?\d*)%\)',
            move_text,
            re.IGNORECASE
        )
        if player_match:
            chances['player_win_pct'] = float(player_match.group(1))
            chances['player_gammon_pct'] = float(player_match.group(2))
            chances['player_backgammon_pct'] = float(player_match.group(3))

        # Parse opponent chances
        opponent_match = re.search(
            r'Opponent:\s*(\d+\.?\d*)%\s*\(G:(\d+\.?\d*)%\s*B:(\d+\.?\d*)%\)',
            move_text,
            re.IGNORECASE
        )
        if opponent_match:
            chances['opponent_win_pct'] = float(opponent_match.group(1))
            chances['opponent_gammon_pct'] = float(opponent_match.group(2))
            chances['opponent_backgammon_pct'] = float(opponent_match.group(3))

        return chances

    @staticmethod
    def _parse_game_info(text: str) -> dict:
        """
        Parse game information from text section.

        Extracts:
        - Players (X:Player 2   O:Player 1)
        - Score (Score is X:3 O:4 5 pt.(s) match.)
        - Cube info (Cube: 2, O own cube)
        - Turn info (X to play 63)
        """
        info = {}

        # Parse player designation and map to internal model
        # Player 1 = BOTTOM player = Player.O
        # Player 2 = TOP player = Player.X
        xo_to_player = {}
        player_designation = re.search(
            r'([XO]):Player\s+(\d+)',
            text,
            re.IGNORECASE
        )
        if player_designation:
            label = player_designation.group(1).upper()  # 'X' or 'O'
            player_num = int(player_designation.group(2))  # 1 or 2

            # Map player number to internal representation
            if player_num == 1:
                xo_to_player[label] = Player.O
            else:
                xo_to_player[label] = Player.X

            # Parse the other player
            other_label = 'O' if label == 'X' else 'X'
            other_player_designation = re.search(
                rf'{other_label}:Player\s+(\d+)',
                text,
                re.IGNORECASE
            )
            if other_player_designation:
                other_num = int(other_player_designation.group(1))
                if other_num == 1:
                    xo_to_player[other_label] = Player.O
                else:
                    xo_to_player[other_label] = Player.X

        # Parse score and match length
        # "Score is X:3 O:4 5 pt.(s) match."
        score_match = re.search(
            r'Score is X:(\d+)\s+O:(\d+)\s+(\d+)\s+pt',
            text,
            re.IGNORECASE
        )
        if score_match:
            info['score_x'] = int(score_match.group(1))
            info['score_o'] = int(score_match.group(2))
            info['match_length'] = int(score_match.group(3))

        # Check for Crawford game indicator in pip count line
        # Format: "Pip count  X: 156  O: 167 X-O: 1-4/5 Crawford"
        crawford_match = re.search(
            r'Pip count.*Crawford',
            text,
            re.IGNORECASE
        )
        if crawford_match:
            info['crawford'] = True

        # Check for money game
        if 'money game' in text.lower():
            info['match_length'] = 0

        # Parse cube info
        cube_match = re.search(
            r'Cube:\s*(\d+)(?:,\s*([XO])\s+own\s+cube)?',
            text,
            re.IGNORECASE
        )
        if cube_match:
            info['cube_value'] = int(cube_match.group(1))
            owner_label = cube_match.group(2)
            if owner_label:
                owner_label = owner_label.upper()
                if owner_label in xo_to_player:
                    owner_player = xo_to_player[owner_label]
                    if owner_player == Player.X:
                        info['cube_owner'] = CubeState.X_OWNS
                    else:
                        info['cube_owner'] = CubeState.O_OWNS
                else:
                    # Fallback if player mapping not found
                    if owner_label == 'X':
                        info['cube_owner'] = CubeState.X_OWNS
                    elif owner_label == 'O':
                        info['cube_owner'] = CubeState.O_OWNS
            else:
                info['cube_owner'] = CubeState.CENTERED

        # Parse turn info
        turn_match = re.search(
            r'([XO])\s+(?:to\s+play|to\s+roll|on\s+roll)(?:\s+(\d)(\d))?',
            text,
            re.IGNORECASE
        )
        if turn_match:
            player_label = turn_match.group(1).upper()

            if player_label in xo_to_player:
                info['on_roll'] = xo_to_player[player_label]
            else:
                # Fallback if player mapping not found
                info['on_roll'] = Player.X if player_label == 'X' else Player.O

            dice1 = turn_match.group(2)
            dice2 = turn_match.group(3)
            if dice1 and dice2:
                info['dice'] = (int(dice1), int(dice2))

        # Check for cube actions
        if any(word in text.lower() for word in ['double', 'take', 'drop', 'pass', 'beaver']):
            # Look for cube decision indicators
            if 'double' in text.lower() and 'to play' not in text.lower():
                info['decision_type'] = DecisionType.CUBE_ACTION

        return info

    @staticmethod
    def _parse_moves(text: str) -> List[Move]:
        """
        Parse move analysis from text.

        Format:
            1. XG Roller+  11/8 11/5                    eq:+0.589
              Player:   79.46% (G:17.05% B:0.67%)
              Opponent: 20.54% (G:2.22% B:0.06%)

            2. XG Roller+  9/3* 6/3                     eq:+0.529 (-0.061)
              Player:   76.43% (G:24.10% B:1.77%)
              Opponent: 23.57% (G:3.32% B:0.12%)

        Or for cube decisions:
            1. XG Roller+  Double, take                 eq:+0.678
            2. XG Roller+  Double, drop                 eq:+0.645 (-0.033)
            3. XG Roller+  No double                    eq:+0.623 (-0.055)
        """
        moves = []

        # Find all move entries
        # Pattern: rank. [engine] notation eq:[equity] [(error)]
        move_pattern = re.compile(
            r'^\s*(\d+)\.\s+(?:[\w\s+-]+?)\s+(.*?)\s+eq:\s*([+-]?\d+\.\d+)(?:\s*\(([+-]\d+\.\d+)\))?',
            re.MULTILINE | re.IGNORECASE
        )

        # Split text into lines to extract following lines after each move
        lines = text.split('\n')
        move_matches = list(move_pattern.finditer(text))

        for i, match in enumerate(move_matches):
            rank = int(match.group(1))
            notation = match.group(2).strip()
            equity = float(match.group(3))
            error_str = match.group(4)

            # Parse error if present
            if error_str:
                xg_error = float(error_str)
                error = abs(xg_error)
            else:
                xg_error = 0.0
                error = 0.0

            # Clean up notation
            notation = XGTextParser._clean_move_notation(notation)

            # Extract winning chances from the lines following this move
            # Get the text between this match and the next move (or end)
            start_pos = match.end()
            if i + 1 < len(move_matches):
                end_pos = move_matches[i + 1].start()
            else:
                end_pos = len(text)

            move_section = text[start_pos:end_pos]
            winning_chances = XGTextParser._parse_move_winning_chances(move_section)

            moves.append(Move(
                notation=notation,
                equity=equity,
                error=error,
                rank=rank,
                xg_error=xg_error,
                xg_notation=notation,
                player_win_pct=winning_chances.get('player_win_pct'),
                player_gammon_pct=winning_chances.get('player_gammon_pct'),
                player_backgammon_pct=winning_chances.get('player_backgammon_pct'),
                opponent_win_pct=winning_chances.get('opponent_win_pct'),
                opponent_gammon_pct=winning_chances.get('opponent_gammon_pct'),
                opponent_backgammon_pct=winning_chances.get('opponent_backgammon_pct'),
            ))

        # If we didn't find moves with the standard pattern, try alternative patterns
        if not moves:
            moves = XGTextParser._parse_moves_fallback(text)

        # If still no moves, try parsing as cube decision
        if not moves:
            moves = XGTextParser._parse_cube_decision(text)

        # Calculate errors if not already set
        if moves and len(moves) > 1:
            best_equity = moves[0].equity
            for move in moves[1:]:
                if move.error == 0.0:
                    move.error = abs(best_equity - move.equity)

        return moves

    @staticmethod
    def _parse_moves_fallback(text: str) -> List[Move]:
        """Fallback parser for alternative move formats."""
        moves = []

        # Try simpler pattern without engine name
        # "1. 11/8 11/5   eq:+0.589"
        pattern = re.compile(
            r'^\s*(\d+)\.\s+(.*?)\s+eq:\s*([+-]?\d+\.\d+)',
            re.MULTILINE | re.IGNORECASE
        )

        for match in pattern.finditer(text):
            rank = int(match.group(1))
            notation = match.group(2).strip()
            equity = float(match.group(3))

            notation = XGTextParser._clean_move_notation(notation)

            moves.append(Move(
                notation=notation,
                equity=equity,
                error=0.0,
                rank=rank
            ))

        return moves

    @staticmethod
    def _parse_cube_decision(text: str) -> List[Move]:
        """
        Parse cube decision analysis from text.

        Format:
            Cubeful Equities:
                   No redouble:     +0.172
                   Redouble/Take:   -0.361 (-0.533)
                   Redouble/Pass:   +1.000 (+0.828)

            Best Cube action: No redouble / Take
                         OR: Too good to redouble / Pass

        Generates all 5 cube options:
        - No double/redouble
        - Double/Take (Redouble/Take)
        - Double/Pass (Redouble/Pass)
        - Too good/Take
        - Too good/Pass
        """
        moves = []

        # Look for "Cubeful Equities:" section
        if 'Cubeful Equities:' not in text:
            return moves

        # Parse the 3 equity values from "Cubeful Equities:" section
        # Pattern to match cube decision lines:
        # "       No redouble:     +0.172"
        # "       Redouble/Take:   -0.361 (-0.533)"
        # "       Redouble/Pass:   +1.000 (+0.828)"
        pattern = re.compile(
            r'^\s*(No (?:redouble|double)|(?:Re)?[Dd]ouble/(?:Take|Pass|Drop)):\s*([+-]?\d+\.\d+)(?:\s*\(([+-]\d+\.\d+)\))?',
            re.MULTILINE | re.IGNORECASE
        )

        # Store parsed equities in order they appear
        xg_moves_data = []
        for i, match in enumerate(pattern.finditer(text), 1):
            notation = match.group(1).strip()
            equity = float(match.group(2))
            error_str = match.group(3)

            xg_error = float(error_str) if error_str else 0.0

            # Normalize notation
            normalized = XGTextParser._clean_move_notation(notation)
            xg_moves_data.append((normalized, equity, xg_error, i))

        if not xg_moves_data:
            return moves

        # Build equity map for easy lookup
        equity_map = {data[0]: data[1] for data in xg_moves_data}

        # Parse "Best Cube action:" to determine which is actually best
        best_action_match = re.search(
            r'Best Cube action:\s*(.+?)(?:\n|$)',
            text,
            re.IGNORECASE
        )

        best_action_text = None
        if best_action_match:
            best_action_text = best_action_match.group(1).strip()

        # Determine if we're using "double" or "redouble" terminology
        # Check if any parsed notation contains "redouble"
        use_redouble = any('redouble' in match.group(1).lower()
                          for match in pattern.finditer(text))

        # Generate all 5 cube options with appropriate terminology
        double_term = "Redouble" if use_redouble else "Double"

        # Define all 5 possible cube options
        # All options should show opponent's recommended response
        all_options = [
            f"No {double_term}/Take",
            f"{double_term}/Take",
            f"{double_term}/Pass",
            f"Too good/Take",
            f"Too good/Pass"
        ]

        # Assign equities from XG's analysis
        no_double_eq = equity_map.get("No Double", None)
        double_take_eq = equity_map.get("Double/Take", None)
        double_pass_eq = equity_map.get("Double/Pass", None)

        # Build option list with equities
        option_equities = {}
        if no_double_eq is not None:
            option_equities[f"No {double_term}/Take"] = no_double_eq
        if double_take_eq is not None:
            option_equities[f"{double_term}/Take"] = double_take_eq
        if double_pass_eq is not None:
            option_equities[f"{double_term}/Pass"] = double_pass_eq

        # Assign equities for synthetic "Too good" options
        if double_pass_eq is not None:
            option_equities["Too good/Take"] = double_pass_eq
            option_equities["Too good/Pass"] = double_pass_eq

        # Determine best option from "Best Cube action:" text
        best_notation = None
        if best_action_text:
            text_lower = best_action_text.lower()
            if 'too good' in text_lower:
                if 'take' in text_lower:
                    best_notation = "Too good/Take"
                elif 'pass' in text_lower or 'drop' in text_lower:
                    best_notation = "Too good/Pass"
            elif ('no double' in text_lower or 'no redouble' in text_lower):
                best_notation = f"No {double_term}/Take"
            elif ('double' in text_lower or 'redouble' in text_lower):
                if 'take' in text_lower:
                    best_notation = f"{double_term}/Take"
                elif 'pass' in text_lower or 'drop' in text_lower:
                    best_notation = f"{double_term}/Pass"

        # Build a lookup for XG move data
        xg_data_map = {data[0]: data for data in xg_moves_data}

        # Create Move objects for all 5 options
        for i, option in enumerate(all_options):
            equity = option_equities.get(option, 0.0)
            is_from_xg = not option.startswith("Too good")

            # Get XG metadata for moves from analysis
            xg_error_val = None
            xg_order = None
            xg_notation_val = None
            if is_from_xg:
                base_notation = option.replace(f"No {double_term}/Take", "No Double")
                base_notation = base_notation.replace(f"{double_term}/Take", "Double/Take")
                base_notation = base_notation.replace(f"{double_term}/Pass", "Double/Pass")

                if base_notation in xg_data_map:
                    _, _, xg_error_val, xg_order = xg_data_map[base_notation]
                    if base_notation == "No Double":
                        xg_notation_val = f"No {double_term.lower()}"
                    else:
                        xg_notation_val = base_notation.replace("Double", double_term)

            moves.append(Move(
                notation=option,
                equity=equity,
                error=0.0,
                rank=0,
                xg_rank=xg_order,
                xg_error=xg_error_val,
                xg_notation=xg_notation_val,
                from_xg_analysis=is_from_xg
            ))

        # Sort by equity (highest first) to determine ranking
        moves.sort(key=lambda m: m.equity, reverse=True)

        # Assign ranks based on best move and equity
        if best_notation:
            rank_counter = 1
            for move in moves:
                if move.notation == best_notation:
                    move.rank = 1
                else:
                    if rank_counter == 1:
                        rank_counter = 2
                    move.rank = rank_counter
                    rank_counter += 1
        else:
            for i, move in enumerate(moves):
                move.rank = i + 1

        # Calculate errors relative to best move
        if moves:
            best_move = next((m for m in moves if m.rank == 1), moves[0])
            best_equity = best_move.equity
            for move in moves:
                if move.rank != 1:
                    move.error = abs(best_equity - move.equity)

        # Sort by rank for output
        moves.sort(key=lambda m: m.rank)

        return moves

    @staticmethod
    def _clean_move_notation(notation: str) -> str:
        """Clean up move notation by removing engine names and normalizing cube actions."""
        notation = re.sub(r'^(XG\s+)?(?:Roller\+*|rollout|\d+-ply)\s+', '', notation, flags=re.IGNORECASE)

        # Remove extra whitespace
        notation = re.sub(r'\s+', ' ', notation)
        notation = notation.strip()

        # Handle cube actions
        notation_lower = notation.lower()
        if 'double' in notation_lower and 'take' in notation_lower:
            return "Double/Take"
        elif 'double' in notation_lower and 'drop' in notation_lower:
            return "Double/Drop"
        elif 'double' in notation_lower and 'pass' in notation_lower:
            return "Double/Pass"
        elif 'no double' in notation_lower or 'no redouble' in notation_lower:
            return "No Double"
        elif 'take' in notation_lower:
            return "Take"
        elif 'drop' in notation_lower or 'pass' in notation_lower:
            return "Drop"

        return notation
