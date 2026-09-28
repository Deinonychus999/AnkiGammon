"""Reader for OGXM v2, HedgeHog's binary match and analysis format.

The spec is docs/OGXM_FORMAT_SPEC.md in gitlab.com/eranlambooij/hedgehog-public.
This reads what flashcards need: the match, every ply replayed into its board,
cube and score, and the checker and cube decisions of the first analysis block.
Boards use OGXM's absolute numbering: positive is White, index 0 White's bar,
25 Black's bar; White moves up the board and Black down.
"""

import struct
import zlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

WHITE, BLACK, CENTRED = 0, 1, 2

DOUBLE, TAKE, DROP = 21, 22, 23
CHECKER_KIND, CUBE_KIND = 0, 1                   # decision kind, 9.12
PLY_SCOPE, DECISION_SCOPE, ALTERNATIVE_SCOPE = 2, 3, 4  # annotation scope, 9.20
MARKERS = (24, 25, 26, 30)
RESIGN_GAME, RESIGN_MATCH = 27, 28
SET_POSITION, BEAVER, RACCOON, CUBE_SET, ESCAPE = 31, 32, 33, 36, 63
RESPONSES = (TAKE, DROP, BEAVER, RACCOON)

# Cube verdicts (9.13)
NO_DOUBLE, VERDICT_DOUBLE, VERDICT_TAKE, VERDICT_PASS, TOO_GOOD = 0, 1, 2, 3, 4

_DICE = []
for _a in range(1, 7):
    for _b in range(_a, 7):
        _DICE.append((_a, _b))

OPENING = [0] * 26
for _point, _count in ((1, 2), (12, 5), (17, 3), (19, 5)):
    OPENING[_point] = _count
for _point, _count in ((24, 2), (13, 5), (8, 3), (6, 5)):
    OPENING[_point] = -_count


class OgxmError(ValueError):
    """The file is not an OGXM v2 file this reader can use."""


@dataclass
class Alternative:
    steps: List[Tuple[int, int]]
    equity: float
    probs: Optional[Dict[str, float]] = None
    is_played: bool = False


@dataclass
class CheckerRecord:
    alternatives: List[Alternative] = field(default_factory=list)
    equity_loss: Optional[float] = None

    @property
    def played(self) -> Optional[Alternative]:
        return next((a for a in self.alternatives if a.is_played), None)

    @property
    def loss(self) -> Optional[float]:
        """The played move's equity loss, stored or derived (7.1 bit 3)."""
        played = self.played
        if played is not None and self.alternatives:
            return max(0.0, self.alternatives[0].equity - played.equity)
        return self.equity_loss


@dataclass
class CubeRecord:
    verdict: int
    no_double: Optional[float] = None
    double_take: Optional[float] = None
    double_pass: Optional[float] = None
    probs: Optional[Dict[str, float]] = None
    equity_loss: Optional[float] = None
    take_point: Optional[float] = None


@dataclass
class Ply:
    ply_ref: int
    game_index: int
    index_in_game: int
    action: int
    seat: int
    steps: List[Tuple[int, int]]
    extras: Dict[str, object]
    board: Optional[List[int]] = None       # before the ply; None once replay failed
    cube_value: int = 1                     # before the ply
    cube_owner: int = CENTRED
    score: Tuple[int, int] = (0, 0)         # (White, Black) at the start of the game
    crawford: bool = False
    unplayed_roll: bool = False

    @property
    def dice(self) -> Optional[Tuple[int, int]]:
        return _DICE[self.action] if self.action <= 20 else None


@dataclass
class Game:
    index: int
    winner: Optional[int] = None
    points_won: Optional[int] = None
    initial_board: Optional[List[int]] = None
    initial_cube_value: int = 1               # auto-doubles applied
    initial_cube_owner: int = CENTRED
    plies: List[Ply] = field(default_factory=list)


@dataclass
class Annotation:
    scope: int
    ref: int
    value: str
    key: Optional[str] = None
    kind: Optional[int] = None
    alt_index: Optional[int] = None
    analysis_id: Optional[bytes] = None


@dataclass
class Analysis:
    analysis_id: bytes = b""
    model_name: Optional[str] = None
    checker_ply: Optional[int] = None
    preset: Optional[str] = None
    met_id: Optional[str] = None
    checker: Dict[int, CheckerRecord] = field(default_factory=dict)
    cube: Dict[int, CubeRecord] = field(default_factory=dict)


@dataclass
class Match:
    match_length: int
    white_name: str = "White"
    black_name: str = "Black"
    crawford_rule: bool = False
    jacoby: bool = False
    score_start: Tuple[int, int] = (0, 0)     # (White, Black)
    crawford_before_start: bool = False
    games: List[Game] = field(default_factory=list)
    analysis: Optional[Analysis] = None
    annotations: List[Annotation] = field(default_factory=list)

    @property
    def plies(self) -> List[Ply]:
        return [ply for game in self.games for ply in game.plies]


class _Bytes:
    def __init__(self, data: bytes, pos: int = 0, end: Optional[int] = None):
        self.data = data
        self.pos = pos
        self.end = len(data) if end is None else end

    def take(self, n: int) -> bytes:
        if self.pos + n > self.end:
            raise OgxmError("OGXM file is truncated")
        chunk = self.data[self.pos:self.pos + n]
        self.pos += n
        return chunk

    def u8(self) -> int:
        return self.take(1)[0]

    def u16(self) -> int:
        return struct.unpack("<H", self.take(2))[0]

    def i32(self) -> int:
        return struct.unpack("<i", self.take(4))[0]

    def u32(self) -> int:
        return struct.unpack("<I", self.take(4))[0]

    def varint(self) -> int:
        value = shift = 0
        while True:
            byte = self.u8()
            value |= (byte & 0x7F) << shift
            if not byte & 0x80:
                return value
            shift += 7
            if shift > 63:
                raise OgxmError("OGXM varint is too long")

    def string(self) -> str:
        return self.take(self.varint()).decode("utf-8")

    def equity(self) -> float:
        return self.i32() / 1e6

    def equity_loss(self) -> float:
        return self.u32() / 1e6

    def probability(self) -> float:
        return self.u16() / 1e4

    def probabilities(self) -> Dict[str, float]:
        keys = ("win", "gammon_win", "bg_win", "gammon_loss", "bg_loss")
        return {key: self.probability() for key in keys}

    def steps(self, count: int) -> List[Tuple[int, int]]:
        return [_step(self.u8()) for _ in range(count)]

    def record(self) -> Tuple[int, int]:
        """Opens a framed record (3.2): its presence mask and end offset."""
        length = self.varint()
        end = self.pos + length
        if end > self.end:
            raise OgxmError("OGXM record runs past its section")
        return self.varint(), end

    def skip_record(self) -> None:
        length = self.varint()
        self.pos += length


def _step(byte: int) -> Tuple[int, int]:
    point, pips = byte & 0x1F, byte >> 5
    if point > 25 or not 1 <= pips <= 6:
        raise OgxmError("OGXM step is out of range")
    return point, pips


def _bit(mask: int, bit: int) -> bool:
    return bool(mask >> bit & 1)


def read_ogxm(data: bytes) -> Match:
    """Decode an OGXM v2 file and replay its games."""
    if len(data) < 20 or data[:4] != b"OGXM":
        raise OgxmError("Not an OGXM file")
    major, minor, reader_major, reader_minor, size = struct.unpack("<HHHHI", data[4:16])
    if major < 2:
        raise OgxmError(
            f"This is an OGXM v{major} file. Only OGXM v2 is supported; open it in "
            "HedgeHog and export it again."
        )
    if (reader_major, reader_minor) > (2, 0):
        raise OgxmError(f"This OGXM file needs a newer reader (v{reader_major}.{reader_minor}).")
    if size > len(data) or data[size - 4:size] != b"END!":
        raise OgxmError("OGXM file is truncated or has no end marker")

    match: Optional[Match] = None
    games: List[Game] = []
    analysis: Optional[Analysis] = None
    annotations: List[Annotation] = []
    reading_first_block = False
    pos = 16
    while pos < size - 4:
        if pos + 9 > size - 4:
            raise OgxmError("OGXM section header is truncated")
        kind = data[pos:pos + 4].decode("ascii", "replace")
        length = struct.unpack("<I", data[pos + 4:pos + 8])[0]
        critical = data[pos + 8] & 1
        start, end = pos + 9, pos + 9 + length
        if end > size - 4:
            raise OgxmError(f"OGXM section {kind} runs past the end of the file")
        section = _Bytes(data, start, end)
        if kind == "MTCH":
            match = _read_match(section)
        elif kind == "GAME":
            games.append(_read_game(section, len(games)))
        elif kind == "ANAL":
            reading_first_block = analysis is None
            if reading_first_block:
                analysis = _read_analysis(section)
        elif kind == "DECS":
            if reading_first_block and analysis is not None:
                _read_decisions(section, analysis)
        elif kind == "ANNO":
            annotations = _read_annotations(section)
        elif kind == "CSUM":
            _check_checksum(section, data[:pos])
        elif kind not in ("SIGN", "CLCK", "VIDO", "MSIG") and critical:
            raise OgxmError(f"OGXM file has a critical section this reader does not know: {kind}")
        pos = end

    if match is None:
        raise OgxmError("OGXM file has no match (only an analysis stored apart from it)")
    match.games = games
    match.analysis = analysis
    match.annotations = annotations
    _replay(match)
    return match


def _check_checksum(section: _Bytes, covered: bytes) -> None:
    mask, end = section.record()
    algorithm = section.varint()
    digest = section.take(section.varint())
    if algorithm == 0 and struct.unpack("<I", digest)[0] != zlib.crc32(covered) & 0xFFFFFFFF:
        raise OgxmError("OGXM file is damaged (checksum mismatch)")


def _read_match(section: _Bytes) -> Match:
    mask, end = section.record()
    match = Match(match_length=section.varint())
    section.varint()  # variant: only backgammon's opening is modelled below
    if _bit(mask, 0):
        match.white_name = section.string()
    if _bit(mask, 1):
        match.black_name = section.string()
    if _bit(mask, 2):
        rules = section.varint()
        match.crawford_rule = bool(rules & 1)
        match.jacoby = bool(rules & 2)
    if _bit(mask, 3):
        section.varint()
    if _bit(mask, 4):
        match.score_start = (section.varint(), section.varint())
    if _bit(mask, 5):
        section.varint(), section.varint()
    for bit in range(6, 11):
        if _bit(mask, bit):
            section.varint()
    match.crawford_before_start = _bit(mask, 11)
    section.pos = end
    return match


def _read_game(section: _Bytes, index: int) -> Game:
    mask, end = section.record()
    game = Game(index=index)
    if _bit(mask, 0):
        game.winner = section.varint()
    if _bit(mask, 1):
        game.points_won = section.varint()
    if _bit(mask, 3):
        game.initial_board = list(struct.unpack("<26b", section.take(26)))
    cube_value = section.varint() if _bit(mask, 4) else 1
    if _bit(mask, 5):
        game.initial_cube_owner = section.varint()
    auto_doubles = section.varint() if _bit(mask, 6) else 0
    game.initial_cube_value = cube_value << auto_doubles
    section.pos = end

    while section.pos < section.end:
        b0 = section.u8()
        action, seat, has_extras = b0 & 0x3F, b0 >> 6 & 1, b0 >> 7
        steps: List[Tuple[int, int]] = []
        if action <= 20:
            move_bytes = 4 if _DICE[action][0] == _DICE[action][1] else 2
            for _ in range(move_bytes):
                byte = section.u8()
                if byte == 0:
                    break
                steps.append(_step(byte))
        extras = _read_extras(section) if has_extras else {}
        if action == ESCAPE:
            action = extras.get("action_ext", ESCAPE)
        game.plies.append(Ply(
            ply_ref=0, game_index=index, index_in_game=len(game.plies),
            action=action, seat=seat, steps=steps, extras=extras,
        ))
    return game


def _read_extras(section: _Bytes) -> Dict[str, object]:
    mask, end = section.record()
    extras: Dict[str, object] = {}
    if _bit(mask, 0):
        extras["dice"] = (section.u8(), section.u8())
    if _bit(mask, 1):
        extras["resign_value"] = section.varint()
    if _bit(mask, 2):
        extras["cube_value"] = section.varint()
    if _bit(mask, 3):
        extras["illegal"] = True
    if _bit(mask, 4):
        extras["settle_value"] = section.equity()
    if _bit(mask, 5):
        extras["steps"] = section.steps(section.varint())
    if _bit(mask, 6):
        extras["board"] = list(struct.unpack("<26b", section.take(26)))
    if _bit(mask, 7):
        extras["action_ext"] = section.varint()
    if _bit(mask, 8):
        extras["cube_owner"] = section.varint()
    section.pos = end
    return extras


def _read_level(section: _Bytes) -> Tuple[Optional[str], Optional[int]]:
    mask, end = section.record()
    preset = section.string() if _bit(mask, 0) else None
    checker_ply = section.varint() if _bit(mask, 1) else None
    section.pos = end
    return preset, checker_ply


def _read_analysis(section: _Bytes) -> Analysis:
    mask, end = section.record()
    analysis = Analysis(analysis_id=section.take(16))
    if _bit(mask, 0):
        section.take(32)
    if _bit(mask, 1):
        section.varint()
    if _bit(mask, 2):
        analysis.preset, analysis.checker_ply = _read_level(section)
    if _bit(mask, 4):
        for _ in range(section.varint()):
            section.varint()
    if _bit(mask, 5):
        section.string()
    if _bit(mask, 6):
        analysis.model_name = section.string()
    if _bit(mask, 7):
        section.take(32)
    if _bit(mask, 8):
        section.string()
    if _bit(mask, 9):
        section.varint()
    if _bit(mask, 10):
        section.u16()
    if _bit(mask, 11):
        analysis.met_id = section.string()
    section.pos = end
    return analysis


def _read_annotations(section: _Bytes) -> List[Annotation]:
    annotations = []
    while section.pos < section.end:
        mask, end = section.record()
        annotation = Annotation(scope=section.varint(), ref=section.varint(), value=section.string())
        if _bit(mask, 0):
            annotation.key = section.string()
        if _bit(mask, 1):
            annotation.kind = section.varint()
        if _bit(mask, 2):
            annotation.alt_index = section.varint()
        if _bit(mask, 3):
            section.string()  # lang
        if _bit(mask, 4):
            section.string()  # author
        if _bit(mask, 5):
            section.varint()  # at
        if _bit(mask, 6):
            for _ in range(section.varint()):
                section.skip_record()
        if _bit(mask, 7):
            annotation.analysis_id = section.take(16)
        annotations.append(annotation)
        section.pos = end
    return annotations


def _read_decisions(section: _Bytes, analysis: Analysis) -> None:
    while section.pos < section.end:
        mask, end = section.record()
        ply_ref = section.varint()
        kind = section.varint()
        if kind == CHECKER_KIND:
            analysis.checker[ply_ref] = _read_checker(section, mask)
        elif kind == CUBE_KIND:
            analysis.cube[ply_ref] = _read_cube(section, mask)
        section.pos = end


def _read_checker(section: _Bytes, mask: int) -> CheckerRecord:
    record = CheckerRecord()
    if _bit(mask, 0):
        for _ in range(section.varint()):
            alt_mask, alt_end = section.record()
            steps = section.steps(section.varint())
            alternative = Alternative(steps=steps, equity=section.equity())
            if _bit(alt_mask, 0):
                alternative.probs = section.probabilities()
            if _bit(alt_mask, 1):
                section.skip_record()
            alternative.is_played = _bit(alt_mask, 2)
            section.pos = alt_end
            record.alternatives.append(alternative)
    if _bit(mask, 1):
        section.varint()
    if _bit(mask, 2):
        section.equity()
    if _bit(mask, 3):
        record.equity_loss = section.equity_loss()
    return record


def _read_cube(section: _Bytes, mask: int) -> CubeRecord:
    record = CubeRecord(verdict=section.varint())
    if _bit(mask, 0):
        record.no_double = section.equity()
    if _bit(mask, 1):
        record.double_take = section.equity()
    if _bit(mask, 2):
        record.double_pass = section.equity()
    if _bit(mask, 3):
        record.probs = section.probabilities()
    if _bit(mask, 4):
        record.equity_loss = section.equity_loss()
    if _bit(mask, 5):
        record.take_point = section.probability()
    return record


def _apply_steps(board: List[int], seat: int, steps: List[Tuple[int, int]]) -> bool:
    """Move checkers in place (5.4.3); False when a step is impossible."""
    sign = 1 if seat == WHITE else -1
    opponent_bar = 25 if seat == WHITE else 0
    for point, pips in steps:
        if board[point] * sign <= 0:
            return False
        dest = point + pips if seat == WHITE else point - pips
        board[point] -= sign
        if dest >= 25 or dest <= 0:
            continue
        if board[dest] * sign < -1:
            return False
        if board[dest] == -sign:
            board[dest] = 0
            board[opponent_bar] -= sign
        board[dest] += sign
    return True


def _replay(match: Match) -> None:
    """Reconstruct each ply's board, cube, score and Crawford status (5.4)."""
    white_score, black_score = match.score_start
    crawford_used = match.crawford_before_start
    ply_ref = 0
    for game in match.games:
        crawford = False
        if match.match_length > 0 and match.crawford_rule and not crawford_used:
            if match.match_length - 1 in (white_score, black_score):
                crawford = crawford_used = True
        board: Optional[List[int]] = list(game.initial_board or OPENING)
        cube_value, cube_owner = game.initial_cube_value, game.initial_cube_owner
        pre_double_value = cube_value
        for i, ply in enumerate(game.plies):
            ply.ply_ref = ply_ref
            ply_ref += 1
            ply.board = list(board) if board is not None else None
            ply.cube_value, ply.cube_owner = cube_value, cube_owner
            ply.score = (white_score, black_score)
            ply.crawford = crawford
            action = ply.action
            if action <= 20:
                following = game.plies[i + 1] if i + 1 < len(game.plies) else None
                if not ply.steps and following is not None and \
                        following.action in (RESIGN_GAME, RESIGN_MATCH) and following.seat == ply.seat:
                    ply.unplayed_roll = True
                elif board is not None and not _apply_steps(board, ply.seat, ply.steps):
                    board = None
            elif action == DOUBLE:
                pre_double_value = cube_value
            elif action == TAKE:
                cube_value, cube_owner = pre_double_value * 2, ply.seat
            elif action == BEAVER:
                cube_value, cube_owner = pre_double_value * 4, ply.seat
            elif action == RACCOON:
                cube_value, cube_owner = pre_double_value * 8, ply.seat
            elif action == CUBE_SET:
                cube_value = int(ply.extras.get("cube_value", cube_value))
                cube_owner = int(ply.extras.get("cube_owner", CENTRED))
            elif action == SET_POSITION and "board" in ply.extras:
                board = list(ply.extras["board"])
        if game.winner is not None and game.points_won:
            if match.match_length > 0:
                if game.winner == WHITE:
                    white_score += min(game.points_won, match.match_length - white_score)
                else:
                    black_score += min(game.points_won, match.match_length - black_score)
            elif game.winner == WHITE:
                white_score += game.points_won
            else:
                black_score += game.points_won
