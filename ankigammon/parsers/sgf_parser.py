"""SGF (Smart Game Format) parser for backgammon.

SGF is a standard format for recording board games. For backgammon, it uses GM[6].
Specification: https://www.red-bean.com/sgf/backgammon.html

Move notation uses perspective-dependent point encoding:
- Points a-x represent points 1-24
- y = bar, z = off

For White (moving 1→24): a=1, b=2, c=3... x=24
For Black (moving 24→1): a=24, b=23, c=22... x=1

Example: B[52lqac] (Black rolls 5-2)
  - lq: l(13) → q(8) = 13/8
  - ac: a(24) → c(22) = 24/22
"""

import re
from typing import List, Dict, Tuple, Optional
from pathlib import Path


class SGFParser:
    """Parser for SGF backgammon match files."""

    # SGF point letters (a-x = points, y = bar, z = off)
    POINT_LETTERS = 'abcdefghijklmnopqrstuvwxyz'

    @staticmethod
    def sgf_letter_to_point(letter: str, player: str) -> Optional[int]:
        """Convert SGF letter to backgammon point number.

        Args:
            letter: Single letter (a-x=points, y=bar, z=off)
            player: 'W' for White or 'B' for Black

        Returns:
            Point number (1-24) or special values:
            - 0 for bar
            - 25 for off
            - None for invalid letter
        """
        if letter == 'y':
            return 0
        elif letter == 'z':
            return 25
        elif letter in SGFParser.POINT_LETTERS[:24]:
            index = SGFParser.POINT_LETTERS.index(letter)

            if player == 'W':
                return index + 1
            else:
                return 24 - index
        else:
            return None

    @staticmethod
    def parse_sgf_move(move_str: str, player: str) -> Tuple[str, str]:
        """Parse SGF move notation to dice and standard notation.

        Args:
            move_str: SGF move string like "52lqac" or "double"
            player: 'W' for White or 'B' for Black

        Returns:
            Tuple of (dice, move_notation)
            - dice: "52" or "" for special moves
            - move_notation: "13/8 24/22" or "Doubles" etc.
        """
        # Handle special cube actions
        if move_str == 'double':
            return "", "Doubles => 2"
        elif move_str == 'take':
            return "", "Takes"
        elif move_str == 'drop':
            return "", "Drops"

        if len(move_str) < 2:
            return "", ""

        dice = move_str[:2]
        if not dice.isdigit():
            return "", ""

        move_part = move_str[2:]
        if len(move_part) % 2 != 0:
            return dice, ""

        moves = []
        for i in range(0, len(move_part), 2):
            from_letter = move_part[i]
            to_letter = move_part[i + 1]

            from_point = SGFParser.sgf_letter_to_point(from_letter, player)
            to_point = SGFParser.sgf_letter_to_point(to_letter, player)

            if from_point is None or to_point is None:
                continue

            from_str = 'bar' if from_point == 0 else str(from_point)
            to_str = 'off' if to_point == 25 else str(to_point)

            moves.append(f"{from_str}/{to_str}")

        move_notation = " ".join(moves) if moves else ""
        return dice, move_notation

    @staticmethod
    def parse_sgf_file(file_path: str) -> Dict:
        """Parse SGF file and extract match information.

        Args:
            file_path: Path to .sgf file

        Returns:
            Dictionary with:
            - player_white: White player name
            - player_black: Black player name
            - match_length: Match length (0 for unlimited game)
            - games: List of game dictionaries
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        games_raw = re.findall(r'\(([^()]+)\)', content)

        games = []
        player_white = None
        player_black = None
        match_length = 0

        for game_raw in games_raw:
            game_data = SGFParser._parse_game(game_raw)

            if player_white is None:
                player_white = game_data.get('player_white', 'White')
            if player_black is None:
                player_black = game_data.get('player_black', 'Black')
            if match_length == 0:
                match_length = game_data.get('match_length', 0)

            games.append(game_data)

        return {
            'player_white': player_white,
            'player_black': player_black,
            'match_length': match_length,
            'games': games
        }

    @staticmethod
    def _parse_game(game_str: str) -> Dict:
        """Parse a single SGF game.

        Args:
            game_str: SGF game string (content between parentheses)

        Returns:
            Dictionary with game metadata and moves
        """
        game_data = {
            'moves': []
        }

        parts = game_str.split(';')

        for part in parts:
            part = part.strip()
            if not part:
                continue

            props = re.findall(r'([A-Z]+)\[([^\]]*)\]', part)

            for prop_name, prop_value in props:
                if prop_name == 'PW':
                    game_data['player_white'] = prop_value
                elif prop_name == 'PB':
                    game_data['player_black'] = prop_value
                elif prop_name == 'RE':
                    game_data['result'] = prop_value
                elif prop_name == 'RU':
                    game_data['rules'] = prop_value
                elif prop_name == 'MI':
                    mi_match = re.search(r'length:(\d+)', prop_value)
                    if mi_match:
                        game_data['match_length'] = int(mi_match.group(1))

                    game_match = re.search(r'game:(\d+)', prop_value)
                    if game_match:
                        game_data['game_number'] = int(game_match.group(1))

                    bs_match = re.search(r'bs:(\d+)', prop_value)
                    if bs_match:
                        game_data['black_score'] = int(bs_match.group(1))

                    ws_match = re.search(r'ws:(\d+)', prop_value)
                    if ws_match:
                        game_data['white_score'] = int(ws_match.group(1))

            move_match = re.match(r'^([BW])\[([^\]]+)\]', part)
            if move_match:
                player = move_match.group(1)
                move_str = move_match.group(2)

                dice, notation = SGFParser.parse_sgf_move(move_str, player)

                game_data['moves'].append({
                    'player': player,
                    'dice': dice,
                    'notation': notation,
                    'raw': move_str
                })

        return game_data

    @staticmethod
    def convert_to_mat_format(sgf_data: Dict) -> str:
        """Convert parsed SGF data to .mat (match text) format.

        Args:
            sgf_data: Parsed SGF data from parse_sgf_file()

        Returns:
            String in .mat format compatible with GnuBG
        """
        lines = []

        player_white = sgf_data.get('player_white', 'White')
        player_black = sgf_data.get('player_black', 'Black')
        match_length = sgf_data.get('match_length', 0)

        lines.append(f" {match_length} point match")
        lines.append("")

        for game_idx, game in enumerate(sgf_data['games'], start=1):
            white_score = game.get('white_score', 0)
            black_score = game.get('black_score', 0)

            lines.append(f" Game {game_idx}")
            lines.append(f" {player_black} : {black_score}                        {player_white} : {white_score}")

            move_num = 0
            for move in game['moves']:
                player_name = player_white if move['player'] == 'W' else player_black
                dice = move['dice']
                notation = move['notation']

                if 'Doubles' in notation:
                    lines.append(f" {move_num})  Doubles => 2")
                elif 'Takes' in notation:
                    lines.append(f" {move_num})  Takes")
                elif 'Drops' in notation:
                    lines.append(f" {move_num})  Drops")
                else:
                    if dice:
                        move_num += 1
                        lines.append(f" {move_num}) {dice}: {notation}")

            result = game.get('result', '')
            if result:
                result_match = re.match(r'([WB])\+(\d+)', result)
                if result_match:
                    winner = 'White' if result_match.group(1) == 'W' else 'Black'
                    points = result_match.group(2)
                    lines.append(f"      Wins {points} point{'s' if points != '1' else ''}")

            lines.append("")

        return "\n".join(lines)


def extract_player_names_from_sgf(sgf_file_path: str) -> Tuple[str, str]:
    """Extract player names from SGF file.

    Args:
        sgf_file_path: Path to .sgf file

    Returns:
        Tuple of (player1_name, player2_name) where:
        - player1 goes to top checkbox (Player.O filter)
        - player2 goes to bottom checkbox (Player.X filter)
    """
    try:
        data = SGFParser.parse_sgf_file(sgf_file_path)
        return (
            data.get('player_white', 'Player 1'),
            data.get('player_black', 'Player 2')
        )
    except Exception:
        return ('Player 1', 'Player 2')


def is_sgf_position_file(sgf_file_path: str) -> bool:
    """Detect if SGF file is a position file vs a match file.

    Position files contain a board setup but no actual move sequence.
    They typically have:
    - MI[game:0] (game number 0)
    - Position setup nodes (AE, AW, AB)
    - Dice indication (DI) but no actual moves (B[...] or W[...] with move notation)

    Args:
        sgf_file_path: Path to .sgf file

    Returns:
        True if this is a position file, False if it's a match/game file
    """
    try:
        with open(sgf_file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Parse the file
        data = SGFParser.parse_sgf_file(sgf_file_path)

        if not data.get('games'):
            return True  # No games = position file

        # Check first game for actual moves
        first_game = data['games'][0]
        moves = first_game.get('moves', [])

        # Position files may have DI (dice) tags but no actual move nodes
        # or only cube actions (double/take/drop) but no checker play moves
        has_checker_moves = any(
            move.get('dice') and move.get('notation') and
            move.get('notation') not in ['Doubles => 2', 'Takes', 'Drops']
            for move in moves
        )

        return not has_checker_moves

    except Exception:
        # If we can't parse it, assume it's a match file and let normal error handling deal with it
        return False
