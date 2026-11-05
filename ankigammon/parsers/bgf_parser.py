"""Turns a BGBlitz match file (.bgf) into Decisions.

A .bgf file is one JSON header line, then the match as JSON, usually gzipped
Smile. BGBlitz calls its players green (player -1, read here as O) and red
(player 1, X). The board lists points 1-24 as green numbers them, so it maps
onto the Position model directly; moves are numbered by their mover, 25 being
the bar and 0 off.

In match play BGBlitz stores cubeful equities as match winning chances. Cards
show normalized equity (losing the cube = -1, cashing it = +1), which needs
BGBlitz's own match equity table: its cubeless MWC is exactly the outcome
probabilities weighted by that table, so the entries are solved for from the
file's evaluations. The bundled table fills any entry the file does not pin.
"""

import gzip
import json
import logging
import zlib
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from ankigammon.models import CubeState, Decision, DecisionType, GameRules, Move, Player, Position
from ankigammon.parsers import hedgehog_parser
from ankigammon.parsers.xg_binary_parser import XGBinaryParser
from ankigammon.utils import smile
from ankigammon.utils.met import get_met

logger = logging.getLogger(__name__)

GREEN, RED = -1, 1
SPECIAL = 7
DOUBLE, TAKE, PASS, WIN, DANCE = 1, 2, 3, 4, 5
NOT_ANALYZED = -99.0

_OUTCOMES = ("myWins", "myGammon", "myBackGammon", "oppWins", "oppGammon", "oppBackGammon")


class BgfError(ValueError):
    """A BGBlitz file (.bgf match or .pos position) that cannot be read."""


def is_bgf(data: bytes) -> bool:
    header = _header(data)
    return header is not None and header.get("format") == "BGF"


def _header(data: bytes) -> Optional[dict]:
    end = data.find(b"\n", 0, 4096)
    if end < 0 or not data.startswith(b"{"):
        return None
    try:
        header = json.loads(data[:end].decode("utf-8"))
    except ValueError:
        return None
    return header if isinstance(header, dict) else None


def read_bgf(data: bytes) -> dict:
    header = _header(data)
    if header is None or header.get("format") != "BGF":
        raise BgfError("Not a BGBlitz match file")
    payload = data[data.index(b"\n") + 1:]
    try:
        if payload[:2] == b"\x1f\x8b":
            payload = gzip.decompress(payload)
        elif payload[:1] == b"\x78":
            payload = zlib.decompress(payload)
        match = smile.decode(payload) if payload[:3] == smile.MAGIC else json.loads(payload.decode("utf-8"))
    except (OSError, EOFError, zlib.error, ValueError) as e:
        raise BgfError(f"BGBlitz file is damaged: {e}") from e
    if not isinstance(match, dict) or not isinstance(match.get("games"), list):
        raise BgfError("BGBlitz file holds no games")
    return match


def extract_player_names(path: str) -> Tuple[Optional[str], Optional[str]]:
    """(player 1, player 2) as the import dialog numbers them: green (O), then red (X)."""
    match = read_bgf(Path(path).read_bytes())
    return match.get("nameGreen") or None, match.get("nameRed") or None


def parse_bgf_file(path: str) -> List[Decision]:
    name = Path(path).name
    return parse_bgf_bytes(Path(path).read_bytes(), source_description=f"BGBlitz file '{name}'")


def parse_bgf_bytes(data: bytes, source_description: Optional[str] = None) -> List[Decision]:
    match = read_bgf(data)
    if not has_analysis(match):
        raise BgfError("This BGBlitz match has no analysis. Analyze it in BGBlitz, save it, and import it again.")
    return _Converter(match, source_description or "BGBlitz analysis").decisions()


def has_analysis(match: dict) -> bool:
    """Whether BGBlitz analyzed any move. Each game's first record carries a
    placeholder evaluation even in a match nobody analyzed, so that counts
    only with candidate moves or a cube analysis."""
    return any(
        isinstance(record, dict)
        and (record.get("moveAnalysis") or (record.get("equity") or {}).get("cubeDecision"))
        for game in match["games"] if isinstance(game, dict)
        for record in game.get("moves") or []
    )


STANDARD_START = [2, 0, 0, 0, 0, -5, 0, -3, 0, 0, 0, 5, -5, 0, 0, 0, 3, 0, 5, 0, 0, 0, 0, -2]
_MAT_COLUMN = 36


def to_mat(match: dict) -> str:
    """The match as a .mat match file, for an engine to analyze.

    .mat has no portable way to start a game from a set-up position, so a
    match with such a game is refused.
    """
    for game in match["games"]:
        initial = game.get("initial") or {}
        if ((initial.get("points") or STANDARD_START)[:24] != STANDARD_START
                or int(initial.get("cube") or 1) != 1 or initial.get("cubeOwner")):
            raise BgfError(
                "This BGBlitz match starts from a set-up position, which only "
                "BGBlitz can analyze. Analyze it in BGBlitz, save it, and import it again."
            )
    converter = _Converter(match, "")
    green = _mat_name(match.get("nameGreen")) or "Player 1"
    red = _mat_name(match.get("nameRed")) or "Player 2"
    lines = [
        f'; [Player 1 "{green}"]',
        f'; [Player 2 "{red}"]',
        '; [Crawford "{}"]'.format("On" if match.get("useCrawford", True) else "Off"),
        "",
        f" {converter.match_length} point match",
        "",
    ]
    for game_index, game in enumerate(match["games"]):
        lines += [
            f" Game {game_index + 1}",
            f" {green} : {game.get('scoreGreen') or 0}".ljust(40) + f"{red} : {game.get('scoreRed') or 0}",
        ]
        rows: List[List[str]] = []
        for turn in converter.turns:
            if turn.game_index != game_index:
                continue
            text = converter.mat_entry(turn)
            if text is None:
                continue
            column = 0 if turn.player == GREEN else 1
            if not rows or rows[-1][column] or (column == 0 and rows[-1][1]):
                rows.append(["", ""])
            rows[-1][column] = text
        for number, (left, right) in enumerate(rows, 1):
            lines.append(f"{number:>3}) {left:<{_MAT_COLUMN}} {right}".rstrip())
        lines.append("")
    return "\n".join(lines)


def _mat_name(name: Optional[str]) -> str:
    """A player name .mat readers can split: the header quotes it and the score
    line ends it at a colon."""
    return " ".join((name or "").replace('"', "'").replace(":", " ").split())


def _num(value: object) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _player(player: int) -> Player:
    return Player.O if player == GREEN else Player.X


def _probabilities(evaluation: dict) -> Optional[dict]:
    values = [_num(evaluation.get(key)) for key in _OUTCOMES]
    if None in values:
        return None
    win, gammon, backgammon, _, gammon_loss, backgammon_loss = values
    return {"win": win, "gammon_win": gammon, "bg_win": backgammon,
            "gammon_loss": gammon_loss, "bg_loss": backgammon_loss}


def _xg_steps(move: dict) -> Tuple[int, ...]:
    """A move's checker steps as XG binary numbers them (0-based, 24 bar, -1 off)."""
    steps = []
    for start, end in zip(move.get("from") or [], move.get("to") or []):
        if start < 0:
            break
        steps += [24 if start == 25 else start - 1, -1 if end <= 0 else end - 1]
    return tuple(steps)


def _solve_least_squares(rows: List[List[float]], targets: List[float]) -> Optional[List[float]]:
    """Householder QR; None when the columns do not pin every unknown."""
    a = [row[:] + [t] for row, t in zip(rows, targets)]
    m, n = len(a), len(rows[0])
    for j in range(n):
        norm = sum(a[i][j] ** 2 for i in range(j, m)) ** 0.5
        if norm < 1e-9:
            return None
        alpha = -norm if a[j][j] > 0 else norm
        v = [0.0] * j + [a[j][j] - alpha] + [a[i][j] for i in range(j + 1, m)]
        vv = sum(x * x for x in v)
        for k in range(j, n + 1):
            s = sum(v[i] * a[i][k] for i in range(j, m)) * 2 / vv
            for i in range(j, m):
                a[i][k] -= s * v[i]
    x = [0.0] * n
    for j in reversed(range(n)):
        x[j] = (a[j][n] - sum(a[j][k] * x[k] for k in range(j + 1, n))) / a[j][j]
    return x


class _MatchEquities:
    """BGBlitz's match equity table, as far as the file's evaluations pin it.

    Entries are MWC needing x points against y; `post` marks post-Crawford
    entries where one side is 1-away.
    """

    _FIT_TOLERANCE = 1e-6

    def __init__(self):
        self.pools: Dict[tuple, List[Tuple[List[float], float]]] = {}
        self.single: Dict[tuple, float] = {}
        self.multiple: Dict[tuple, float] = {}

    @staticmethod
    def key(x: int, y: int, post: bool) -> tuple:
        return x, y, post and 1 in (x, y)

    def add(self, aways: Tuple[int, int], cube: int, evaluation: Optional[dict]) -> None:
        probs = _probabilities(evaluation) if evaluation else None
        mwc = _num(evaluation.get("matchEquity")) if evaluation else None
        if probs is None or mwc is None:
            return
        row = [
            probs["win"] - probs["gammon_win"], probs["gammon_win"] - probs["bg_win"], probs["bg_win"],
            1 - probs["win"] - probs["gammon_loss"], probs["gammon_loss"] - probs["bg_loss"], probs["bg_loss"],
        ]
        self.pools.setdefault((aways, cube), []).append((row, mwc))

    def solve(self) -> None:
        for ((my_away, opp_away), cube), samples in self.pools.items():
            post = 1 in (my_away, opp_away)
            used = [j for j in range(6) if max(row[j] for row, _ in samples) > 1e-7]
            rows = [[row[j] for j in used] for row, _ in samples]
            targets = [mwc for _, mwc in samples]
            solution = _solve_least_squares(rows, targets) if len(rows) > len(used) else None
            residual = None if solution is None else max(
                abs(sum(r * s for r, s in zip(row, solution)) - t) for row, t in zip(rows, targets)
            )
            if residual is None or residual > self._FIT_TOLERANCE:
                logger.warning(
                    "BGBlitz match equities at %d-away/%d-away, cube %d: no fit from %d evaluations "
                    "(residual %s); using the bundled table there",
                    my_away, opp_away, cube, len(rows), residual,
                )
                continue
            for j, value in zip(used, solution):
                points = cube * (j % 3 + 1)
                if j < 3:
                    x, y = my_away - points, opp_away
                else:
                    x, y = my_away, opp_away - points
                if x <= 0 or y <= 0:
                    continue
                table = self.single if j % 3 == 0 else self.multiple
                table[self.key(x, y, post)] = value
                table[self.key(y, x, post)] = 1 - value

    def get(self, x: int, y: int, post: bool) -> float:
        if x <= 0:
            return 1.0
        if y <= 0:
            return 0.0
        key = self.key(x, y, post)
        for table in (self.single, self.multiple):
            if key in table:
                return table[key]
        return get_met().get_mwc(x, y, post_crawford=key[2])

    def normalizer(self, my_away: int, opp_away: int, cube: int) -> Optional[Callable[[float], float]]:
        post = 1 in (my_away, opp_away)
        win = self.get(my_away - cube, opp_away, post)
        lose = self.get(my_away, opp_away - cube, post)
        span = win - lose
        if span <= 1e-9:
            return None
        return lambda mwc: (mwc - lose) / span * 2 - 1


class _Turn:
    """One record replayed: the state before it and what it did."""

    def __init__(self, game_index: int, index: int, record: dict, board: List[int],
                 cube: int, owner: int, score: Tuple[int, int], crawford: bool):
        self.game_index = game_index
        self.index = index
        self.record = record
        self.board = list(board)
        self.cube = cube
        self.owner = owner
        self.green_score, self.red_score = score
        self.crawford = crawford
        self.player = record.get("player")
        dice = (record.get("green"), record.get("red"))
        self.action = dice[1] if dice[0] == SPECIAL else None
        self.dice = None if self.action is not None else tuple(dice)

    @property
    def is_roll(self) -> bool:
        return self.dice is not None or self.action == DANCE

    def aways(self, match_length: int, player: Optional[int] = None) -> Tuple[int, int]:
        player = self.player if player is None else player
        mine, theirs = ((self.green_score, self.red_score) if player == GREEN
                        else (self.red_score, self.green_score))
        return match_length - mine, match_length - theirs


def board_decision(board: List[int], player: int, dice: Optional[Tuple[int, int]], cube: int,
                   owner: int, score: Tuple[int, int], match_length: int, crawford: bool,
                   decision_type: DecisionType, jacoby: bool, source: str,
                   beavers: bool = False) -> Decision:
    """A Decision on a BGBlitz board (X positive from bar 0, O negative from bar 25),
    with `player`, `owner` and the (green, red) `score` in BGBlitz's terms."""
    position = Position(
        points=list(board),
        x_off=15 - sum(c for c in board if c > 0),
        o_off=15 - sum(-c for c in board if c < 0),
    )
    on_roll = _player(player)
    if on_roll == Player.X:
        position = position.flipped()
    cube_owner = {GREEN: CubeState.O_OWNS, RED: CubeState.X_OWNS}.get(owner, CubeState.CENTERED)
    green_score, red_score = score
    unlimited = match_length == 0
    rules = GameRules(match_length=match_length, crawford=crawford and not unlimited,
                      jacoby=jacoby and unlimited, beavers_allowed=beavers and unlimited)
    decision = Decision(
        position=position,
        on_roll=on_roll,
        dice=dice,
        score_x=red_score,
        score_o=green_score,
        match_length=match_length,
        crawford=rules.crawford,
        cube_value=cube,
        cube_owner=cube_owner,
        decision_type=decision_type,
        jacoby=rules.jacoby,
        beavers_allowed=rules.beavers_allowed,
        source_description=source,
    )
    decision.xgid = position.to_xgid(
        cube_value=cube, cube_owner=cube_owner, dice=dice, on_roll=on_roll,
        score_x=red_score, score_o=green_score, match_length=match_length,
        crawford_jacoby=rules.to_xgid_field(),
    )
    return decision


def _comments(turns: List[_Turn]) -> Optional[str]:
    texts = [t.record.get("comment") for t in turns]
    return "\n\n".join(t.strip() for t in texts if isinstance(t, str) and t.strip()) or None


def _apply(board: List[int], player: int, move: dict) -> None:
    """Play a move on an absolute board (X positive from bar 0, O negative from bar 25)."""
    sign = 1 if player == RED else -1
    for start, end in zip(move.get("from") or [], move.get("to") or []):
        if start < 0:
            break
        source = start if player == GREEN else 25 - start
        board[source] -= sign
        if end <= 0:
            continue
        target = end if player == GREEN else 25 - end
        if board[target] == -sign:
            board[target] = 0
            board[25 if player == RED else 0] -= sign
        board[target] += sign


class _Converter:
    def __init__(self, match: dict, source: str):
        self.match = match
        self.source = source
        self.match_length = int(match.get("matchlen") or 0)
        self.jacoby = bool(match.get("useJacoby")) and self.match_length == 0
        self.beavers = bool(match.get("useBeaver")) and self.match_length == 0
        self.turns = self._replay()
        self.table = _MatchEquities()
        if self.match_length > 0:
            for turn in self.turns:
                aways = turn.aways(self.match_length)
                record = turn.record
                self.table.add(aways, turn.cube, record.get("equity"))
                self.table.add(aways, turn.cube, record.get("dancingEquity"))
                for alternative in record.get("moveAnalysis") or []:
                    self.table.add(aways, turn.cube, alternative.get("eq"))
            self.table.solve()

    def _replay(self) -> List[_Turn]:
        turns = []
        for game_index, game in enumerate(self.match["games"]):
            initial = game.get("initial") or {}
            board = [0] * 26
            for i, count in enumerate((initial.get("points") or [])[:24]):
                board[i + 1] = count
            cube = int(initial.get("cube") or 1)
            owner = int(initial.get("cubeOwner") or 0)
            score = (int(game.get("scoreGreen") or 0), int(game.get("scoreRed") or 0))
            crawford = bool(game.get("isCrawford"))
            for index, record in enumerate(game.get("moves") or []):
                turn = _Turn(game_index, index, record, board, cube, owner, score, crawford)
                turns.append(turn)
                if turn.dice is not None:
                    _apply(board, turn.player, record)
                elif turn.action == TAKE:
                    cube *= 2
                    owner = turn.player
        return turns

    def decisions(self) -> List[Decision]:
        out: List[Decision] = []
        for i, turn in enumerate(self.turns):
            if turn.is_roll and self._may_double(turn):
                decision = self._cube_decision(turn, turn.record, None)
                if decision is not None:
                    out.append(decision)
            elif turn.action == DOUBLE:
                following = self.turns[i + 1] if i + 1 < len(self.turns) else None
                response = following if following and following.action in (TAKE, PASS) else None
                decision = self._cube_decision(turn, turn.record, response)
                if decision is not None:
                    out.append(decision)
            if turn.dice is not None and len(turn.record.get("moveAnalysis") or []) >= 2:
                decision = self._checker_decision(turn)
                if decision is not None:
                    out.append(decision)
        return out

    def mat_entry(self, turn: _Turn) -> Optional[str]:
        """What the turn reads as in a .mat file; None for nothing to write."""
        record = turn.record
        if turn.dice is not None:
            decision = self._base(turn, DecisionType.CHECKER_PLAY, dice=turn.dice)
            notation = self._notation(record, decision)
            return f"{turn.dice[0]}{turn.dice[1]}: {notation}".rstrip()
        if turn.action == DANCE:
            return f"{record['from'][0]}{record['to'][0]}: Cannot Move"
        if turn.action == DOUBLE:
            return f" Doubles => {turn.cube * 2}"
        if turn.action == TAKE:
            return " Takes"
        if turn.action == PASS:
            return " Drops"
        if turn.action == WIN:
            game = self.match["games"][turn.game_index]
            points = int(game.get("wonPoints") or 1)
            return f" Wins {points} point{'s' if points > 1 else ''}"
        return None

    def _may_double(self, turn: _Turn) -> bool:
        return not turn.crawford and turn.owner in (0, turn.player)

    def _normalizer(self, turn: _Turn, player: int) -> Optional[Callable[[float], float]]:
        if self.match_length <= 0:
            return lambda equity: equity
        my_away, opp_away = turn.aways(self.match_length, player)
        return self.table.normalizer(my_away, opp_away, turn.cube)

    def _base(self, turn: _Turn, decision_type: DecisionType,
              dice: Optional[Tuple[int, int]] = None) -> Decision:
        decision = board_decision(
            turn.board, turn.player, dice, turn.cube, turn.owner,
            (turn.green_score, turn.red_score), self.match_length, turn.crawford,
            decision_type, self.jacoby, self.source, self.beavers,
        )
        decision.game_number = turn.game_index + 1
        decision.move_number = turn.index + 1
        return decision

    def _checker_decision(self, turn: _Turn) -> Optional[Decision]:
        normalize = self._normalizer(turn, turn.player)
        if normalize is None:
            return None
        decision = self._base(turn, DecisionType.CHECKER_PLAY, dice=turn.dice)
        level = f"{turn.record['ply']}-ply" if turn.record.get("ply") else "BGBlitz"
        alternatives = [(a, a.get("eq") or {}) for a in turn.record["moveAnalysis"]]
        # Ranking cubeful against cubeless equities would be meaningless, so one
        # alternative without a cubeful equity puts them all on cubeless.
        cubeful = all(_num((e.get("cubeDecision") or {}).get("eqCubeFul")) is not None
                      for _, e in alternatives)
        scored = []
        for alternative, evaluation in alternatives:
            equity = (_num(evaluation["cubeDecision"]["eqCubeFul"]) if cubeful
                      else _num(evaluation.get("matchEquity")))
            if equity is None:
                return None
            scored.append((normalize(equity), alternative, evaluation))
        scored.sort(key=lambda item: item[0], reverse=True)
        best = scored[0][0]
        moves = []
        for rank, (equity, alternative, evaluation) in enumerate(scored, 1):
            notation = self._notation(alternative.get("move") or {}, decision)
            move = Move(
                notation=notation, equity=equity, error=best - equity, rank=rank, xg_rank=rank,
                xg_error=equity - best, xg_notation=notation,
                was_played=bool(alternative.get("played")), analysis_level=level,
            )
            hedgehog_parser.set_probabilities(move, _probabilities(evaluation))
            move.cubeless_equity = hedgehog_parser.cubeless_equity(move, decision)
            moves.append(move)
        played = next((m for m in moves if m.was_played), None)
        loss = _num((turn.record.get("pr") or {}).get("checkerError"))
        if played is None and loss is not None and loss != NOT_ANALYZED:
            notation = self._notation(turn.record, decision)
            played = Move(
                notation=notation, equity=best + loss, error=-loss, rank=len(moves) + 1,
                xg_rank=len(moves) + 1, xg_error=loss, xg_notation=notation,
                was_played=True, analysis_level=level,
            )
            moves.append(played)
        decision.candidate_moves = moves
        if played is not None:
            decision.xg_error_move = played.error
        decision.note = _comments([turn])
        return decision

    @staticmethod
    def _notation(move: dict, decision: Decision) -> str:
        return XGBinaryParser._convert_move_notation(
            _xg_steps(move), decision.position, decision.on_roll
        )

    def _cube_triple(self, turn: _Turn, record: dict, doubler: int) -> Optional[Tuple[float, float, float]]:
        cube = (record.get("equity") or {}).get("cubeDecision") or {}
        values = [_num(cube.get(key)) for key in ("eqNoDouble", "eqDoubleTake", "eqDoublePass")]
        if None in values:
            return None
        if record.get("player") != doubler:
            values = [1 - v if self.match_length > 0 else -v for v in values]
        normalize = self._normalizer(turn, doubler)
        if normalize is None:
            return None
        return tuple(normalize(v) for v in values)

    def _cube_decision(self, turn: _Turn, offer: dict, response: Optional[_Turn]) -> Optional[Decision]:
        doubler = turn.player
        analyzed = offer
        triple = self._cube_triple(turn, offer, doubler)
        if triple is None and response is not None:
            analyzed = response.record
            triple = self._cube_triple(turn, analyzed, doubler)
        if triple is None:
            return None
        no_double, double_take, double_pass = triple

        double = min(double_take, double_pass)
        if double > no_double:
            best = "double_take" if double_take <= double_pass else "double_pass"
        elif no_double >= double_pass:
            best = "too_good"
        else:
            best = "no_double"

        decision = self._base(turn, DecisionType.CUBE_ACTION)
        decision.candidate_moves = hedgehog_parser.cube_moves(
            turn.cube, no_double, double_take, double_pass, best
        )
        word = "Redouble" if turn.cube > 1 else "Double"
        if turn.action != DOUBLE:
            played = f"No {word}/Take"
        elif response is not None and response.action == PASS:
            played = f"{word}/Pass"
        else:
            played = f"{word}/Take"
        for move in decision.candidate_moves:
            move.was_played = move.notation == played

        right = max(no_double, double)
        decision.cube_error = right - (no_double if turn.action != DOUBLE else double)
        if response is not None:
            answered = double_pass if response.action == PASS else double_take
            decision.take_error = answered - double
        # A roll's own comment is about its move, so only a double's go on the cube card.
        if turn.action == DOUBLE:
            decision.note = _comments([turn, response] if response else [turn])

        probs = _probabilities(analyzed.get("equity") or {})
        if analyzed.get("player") != doubler:
            probs = hedgehog_parser.swap_sides(probs)
        hedgehog_parser.set_probabilities(decision, probs)
        decision.cubeless_equity = hedgehog_parser.cubeless_equity(decision, decision)
        if decision.match_length > 0:
            decision.double_cubeless_equity = hedgehog_parser.cubeless_equity(
                decision, decision, decision.cube_value * 2
            )
        elif decision.cubeless_equity is not None:
            decision.double_cubeless_equity = decision.cubeless_equity * 2
        return decision
