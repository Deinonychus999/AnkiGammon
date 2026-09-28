"""Turns an OGXM v2 match analysis (HedgeHog's format) into Decisions.

In match play HedgeHog stores checker equities as normalized equity and cube
equities as match winning chances; the cube triple is normalized here with
HedgeHog's own match equity table so cards show the numbers HedgeHog shows.
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ankigammon.models import CubeState, Decision, DecisionType, Move, Player, Position
from ankigammon.parsers import hedgehog_parser
from ankigammon.utils.hedgehog_met import normalize_cube_triple
from ankigammon.utils import ogxm_reader as ogxm
from ankigammon.utils.ogxm_reader import BLACK, WHITE, CubeRecord, Match, Ply


def extract_player_names(path: str) -> Tuple[Optional[str], Optional[str]]:
    """(player 1, player 2) as the import dialog numbers them: Black (O), then White (X)."""
    match = ogxm.read_ogxm(Path(path).read_bytes())
    return match.black_name, match.white_name


def parse_ogxm_file(path: str) -> List[Decision]:
    name = Path(path).name
    return parse_ogxm_bytes(Path(path).read_bytes(), source_description=f"OGXM file '{name}'")


def parse_ogxm_bytes(data: bytes, level: Optional[str] = None,
                     source_description: Optional[str] = None) -> List[Decision]:
    match = ogxm.read_ogxm(data)
    if match.analysis is None:
        raise ValueError("This OGXM file has no analysis to make cards from.")
    if level is None:
        # HedgeHog names a depth one ply above its search depth (2ply is "3-ply").
        ply = match.analysis.checker_ply
        level = f"{ply + 1}-ply" if ply is not None else "HedgeHog"
    return _Converter(match, level, source_description).decisions()


def _player(seat: int) -> Player:
    return Player.X if seat == WHITE else Player.O


def _cube_owner(owner: int) -> CubeState:
    return {WHITE: CubeState.X_OWNS, BLACK: CubeState.O_OWNS}.get(owner, CubeState.CENTERED)


def _position(board: List[int], seat: int) -> Position:
    """An absolute OGXM board as a Position seen by the player to act."""
    position = Position(
        points=list(board),
        x_off=15 - sum(c for c in board if c > 0),
        o_off=15 - sum(-c for c in board if c < 0),
    )
    return position.flipped() if seat == WHITE else position


def move_notation(board: List[int], seat: int, steps: List[Tuple[int, int]]) -> str:
    """Steps in the mover's own numbering, with hits marked, e.g. '13/7 6/5*'."""
    board = list(board)
    sign = 1 if seat == WHITE else -1
    own_bar, opponent_bar = (0, 25) if seat == WHITE else (25, 0)
    parts = []
    for point, pips in steps:
        dest = point + pips if seat == WHITE else point - pips
        off = dest >= 25 or dest <= 0
        source = "bar" if point == own_bar else str(25 - point if seat == WHITE else point)
        target = "off" if off else str(25 - dest if seat == WHITE else dest)
        hit = not off and board[dest] == -sign
        parts.append((0 if source == "bar" else int(source), f"{source}/{target}{'*' if hit else ''}"))
        board[point] -= sign
        if not off:
            if hit:
                board[dest] = 0
                board[opponent_bar] -= sign
            board[dest] += sign
    # Standard notation lists sub-moves from the highest point down; bar first.
    parts.sort(key=lambda part: 26 if part[1].startswith("bar") else part[0], reverse=True)
    return " ".join(text for _, text in parts)


class _Converter:
    def __init__(self, match: Match, level: str, source_description: Optional[str]):
        self.match = match
        self.level = level
        self.source = source_description or "HedgeHog analysis"
        self.plies = match.plies
        self.notes = self._index_notes()

    def _index_notes(self) -> Dict[tuple, List[tuple]]:
        """Prose annotations (spec 8.4) by target; notes on another analysis
        block's decisions are left out, since only the first block is read."""
        block = self.match.analysis.analysis_id
        notes: Dict[tuple, List[tuple]] = {}
        for note in self.match.annotations:
            if note.key is not None or not note.value.strip():
                continue
            if note.scope == ogxm.PLY_SCOPE:
                target = ("ply", note.ref)
            elif note.scope in (ogxm.DECISION_SCOPE, ogxm.ALTERNATIVE_SCOPE) and note.analysis_id == block:
                target = ("decision", note.kind, note.ref)
            else:
                continue
            alt_index = note.alt_index if note.scope == ogxm.ALTERNATIVE_SCOPE else None
            notes.setdefault(target, []).append((alt_index, note.value.strip()))
        return notes

    def _note(self, targets: List[tuple], moves: Optional[List[Move]] = None) -> Optional[str]:
        parts = []
        for target in targets:
            for alt_index, text in self.notes.get(target, []):
                if alt_index is None:
                    parts.append(text)
                elif moves is not None and alt_index < len(moves):
                    parts.append(f"{moves[alt_index].notation}: {text}")
        return "\n\n".join(parts) or None

    def decisions(self) -> List[Decision]:
        analysis = self.match.analysis
        out: List[Decision] = []
        for ply in self.plies:
            if ply.board is None:
                continue
            cube = analysis.cube.get(ply.ply_ref)
            if cube is not None and ply.action <= 20:
                out.append(self._cube_decision(ply, cube, None, None))
            elif ply.action == ogxm.DOUBLE:
                response = self._response_to(ply)
                response_record = analysis.cube.get(response.ply_ref) if response else None
                if cube is not None or response_record is not None:
                    out.append(self._cube_decision(ply, cube, response, response_record))
            checker = analysis.checker.get(ply.ply_ref)
            if checker is not None and len(checker.alternatives) >= 2 and not ply.unplayed_roll:
                out.append(self._checker_decision(ply, checker))
        return out

    def _response_to(self, double: Ply) -> Optional[Ply]:
        game = self.match.games[double.game_index]
        following = game.plies[double.index_in_game + 1:double.index_in_game + 2]
        return following[0] if following and following[0].action in ogxm.RESPONSES else None

    def _base(self, ply: Ply, seat: int, decision_type: DecisionType, dice=None) -> Decision:
        white_score, black_score = ply.score
        decision = Decision(
            position=_position(ply.board, seat),
            on_roll=_player(seat),
            dice=dice,
            score_x=white_score,
            score_o=black_score,
            match_length=self.match.match_length,
            crawford=ply.crawford,
            cube_value=ply.cube_value,
            cube_owner=_cube_owner(ply.cube_owner),
            decision_type=decision_type,
            jacoby=self.match.jacoby and self.match.match_length == 0,
            source_description=self.source,
            game_number=ply.game_index + 1,
            move_number=ply.index_in_game + 1,
        )
        decision.xgid = decision.position.to_xgid(
            cube_value=decision.cube_value, cube_owner=decision.cube_owner, dice=dice,
            on_roll=decision.on_roll, score_x=white_score, score_o=black_score,
            match_length=decision.match_length, crawford_jacoby=1 if ply.crawford else 0,
        )
        return decision

    def _checker_decision(self, ply: Ply, record: ogxm.CheckerRecord) -> Decision:
        decision = self._base(ply, ply.seat, DecisionType.CHECKER_PLAY, dice=ply.dice)
        best = record.alternatives[0].equity
        moves = []
        for rank, alternative in enumerate(record.alternatives, 1):
            notation = move_notation(ply.board, ply.seat, alternative.steps)
            move = Move(
                notation=notation, equity=alternative.equity, error=abs(best - alternative.equity),
                rank=rank, xg_rank=rank, xg_error=alternative.equity - best, xg_notation=notation,
                was_played=alternative.is_played, analysis_level=self.level,
            )
            hedgehog_parser.set_probabilities(move, alternative.probs)
            move.cubeless_equity = hedgehog_parser.cubeless_equity(move, decision)
            moves.append(move)
        decision.candidate_moves = moves
        decision.xg_error_move = record.loss
        decision.note = self._note([("ply", ply.ply_ref), ("decision", ogxm.CHECKER_KIND, ply.ply_ref)], moves)
        return decision

    def _cube_decision(self, ply: Ply, offer: Optional[CubeRecord],
                       response: Optional[Ply], response_record: Optional[CubeRecord]) -> Decision:
        doubler = ply.seat
        decision = self._base(ply, doubler, DecisionType.CUBE_ACTION)
        source = offer or response_record
        white_score, black_score = ply.score
        triple = (source.no_double, source.double_take, source.double_pass)
        if self.match.match_length > 0 and None not in triple:
            doubler_score, other_score = (
                (white_score, black_score) if doubler == WHITE else (black_score, white_score)
            )
            normalized = normalize_cube_triple(
                self.match.match_length, doubler_score, other_score, ply.cube_value, *triple
            )
            if normalized is not None:
                triple = normalized
        no_double, double_take, double_pass = (value if value is not None else 0.0 for value in triple)

        if offer is not None and offer.verdict == ogxm.NO_DOUBLE:
            best = "no_double"
        elif offer is not None and offer.verdict == ogxm.TOO_GOOD:
            best = "too_good"
        else:
            best = "double_take" if double_take <= double_pass else "double_pass"
        decision.candidate_moves = hedgehog_parser.cube_moves(
            ply.cube_value, no_double, double_take, double_pass, best
        )

        double = "Redouble" if ply.cube_value > 1 else "Double"
        if ply.action <= 20:
            played = f"No {double}/Take"
        elif response is not None and response.action == ogxm.DROP:
            played = f"{double}/Pass"
        else:
            played = f"{double}/Take"
        for move in decision.candidate_moves:
            move.was_played = move.notation == played

        probs = offer.probs if offer is not None else hedgehog_parser.swap_sides(response_record.probs)
        hedgehog_parser.set_probabilities(decision, probs)
        decision.cubeless_equity = hedgehog_parser.cubeless_equity(decision, decision)
        if decision.match_length > 0:
            decision.double_cubeless_equity = hedgehog_parser.cubeless_equity(
                decision, decision, decision.cube_value * 2
            )
        elif decision.cubeless_equity is not None:
            decision.double_cubeless_equity = decision.cubeless_equity * 2
        decision.cube_error = offer.equity_loss if offer is not None else None
        decision.take_error = response_record.equity_loss if response_record is not None else None
        # A roll's own notes are about the move, so only a double's go on the cube card.
        if ply.action == ogxm.DOUBLE:
            refs = [ply.ply_ref] + ([response.ply_ref] if response is not None else [])
            targets = [t for ref in refs for t in (("ply", ref), ("decision", ogxm.CUBE_KIND, ref))]
        else:
            targets = [("decision", ogxm.CUBE_KIND, ply.ply_ref)]
        decision.note = self._note(targets)
        return decision
