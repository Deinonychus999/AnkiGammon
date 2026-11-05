"""Reads a JellyFish position file (.pos), the format BGBlitz saves positions
in: one position, with no analysis.

The layout follows GnuBG's importer (ParseJF in import.c). Little-endian
16-bit values, except strings, which have a one-byte length:

    version (124, 125 or 126); 126 adds two values, 125 and 126 then hold
        cube in use, Jacoby, beavers
    cube value, cube owner (0 centered, 1 player 1, 2 player 2)
    on roll (0 opening, 1 or 2 that player, 3 or 4 that player before
        rolling; BGBlitz also writes 1 or 2 with dice 1, -1 before rolling)
    moves left, moves right, unused, game or match (1 match, 3 single game),
        opponent, level, match length, player 1's score, player 2's score
    player 1's name, player 2's name
    swap dice, Crawford (2 Crawford game, 3 post-Crawford), JellyFish played
        last, the move it played (string), die, die
    26 board values plus 20, each followed by the same point on the undo
        board (the position before the last move)

Player 1 is BGBlitz's green and the board is laid out as in a .bgf match.
"""

import struct
from pathlib import Path
from typing import List, NamedTuple, Optional

from ankigammon.models import Decision, DecisionType
from ankigammon.parsers.bgf_parser import GREEN, RED, BgfError, board_decision

VERSIONS = (124, 125, 126)
SINGLE_GAME = 3
CRAWFORD_GAME = 2
_ON_ROLL = {1: GREEN, 2: RED, 3: GREEN, 4: RED}
_OWNERS = {0: 0, 1: GREEN, 2: RED}


class JellyFishPosition(NamedTuple):
    jacoby: bool
    beavers: bool
    cube: int
    owner: int
    on_roll: int
    match_length: int
    scores: tuple
    names: tuple
    crawford: int
    dice: Optional[tuple]
    board: List[int]


class _Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.at = 0

    def short(self) -> int:
        if self.at + 2 > len(self.data):
            raise BgfError("Position file is truncated")
        value = struct.unpack_from("<h", self.data, self.at)[0]
        self.at += 2
        return value

    def text(self) -> str:
        if self.at >= len(self.data):
            raise BgfError("Position file is truncated")
        end = self.at + 1 + self.data[self.at]
        if end > len(self.data):
            raise BgfError("Position file is truncated")
        value = self.data[self.at + 1:end].decode("utf-8", errors="replace")
        self.at = end
        return value


def read_position(data: bytes) -> JellyFishPosition:
    reader = _Reader(data)
    version = reader.short()
    if version not in VERSIONS:
        raise BgfError("Not a JellyFish position file")
    jacoby = beavers = False
    if version == 126:
        reader.short()
        reader.short()
    if version >= 125:
        reader.short()
        jacoby = bool(reader.short())
        beavers = bool(reader.short())
    cube, owner, on_roll = reader.short(), reader.short(), reader.short()
    for _ in range(3):
        reader.short()
    game_or_match = reader.short()
    reader.short()
    reader.short()
    match_length = reader.short()
    scores = (reader.short(), reader.short())
    names = (reader.text(), reader.text())
    reader.short()
    crawford = reader.short()
    reader.short()
    reader.text()
    dice = (abs(reader.short()), reader.short())
    values = [reader.short() for _ in range(52)]
    board = [values[2 * i] - 20 for i in range(26)]
    if sum(c for c in board if c > 0) > 15 or sum(-c for c in board if c < 0) > 15:
        raise BgfError("Position file holds more than 15 checkers a side")
    return JellyFishPosition(
        jacoby=jacoby, beavers=beavers, cube=max(cube, 1), owner=owner, on_roll=on_roll,
        match_length=0 if game_or_match == SINGLE_GAME else match_length,
        scores=scores, names=names, crawford=crawford,
        dice=dice if on_roll in (1, 2) and all(1 <= d <= 6 for d in dice) else None,
        board=board,
    )


def is_bgblitz_position(data: bytes) -> bool:
    try:
        read_position(data)
    except BgfError:
        return False
    return True


def parse_position_bytes(data: bytes, source_description: str) -> Decision:
    position = read_position(data)
    if position.on_roll == 0:
        raise BgfError(
            "This position has nobody on roll (the opening position). Set who is "
            "on roll in BGBlitz and save it again."
        )
    if position.on_roll not in _ON_ROLL or position.owner not in _OWNERS:
        raise BgfError("Position file is damaged")
    decision = board_decision(
        position.board, _ON_ROLL[position.on_roll], position.dice, position.cube,
        _OWNERS[position.owner], position.scores, position.match_length,
        position.crawford == CRAWFORD_GAME,
        DecisionType.CHECKER_PLAY if position.dice else DecisionType.CUBE_ACTION,
        position.jacoby, source_description, position.beavers,
    )
    decision.original_position_format = "POS"
    return decision


def parse_position_file(path: str) -> List[Decision]:
    return [parse_position_bytes(Path(path).read_bytes(), f"Position from BGBlitz file '{Path(path).name}'")]
