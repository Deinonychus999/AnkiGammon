"""Cube options keep their logical order, so the answer is not always A.

GitHub issue #59: "I've only added 4 notes to my cube study deck and so far
the correct answer is always A."

Cube cards deliberately are not shuffled - the five actions read as a set and
belong in a fixed order. The XG parser ended with `moves.sort(key=rank)`,
which put the best action first every time, so the MCQ answer was slot A on
every XG-analyzed cube card. The GnuBG parser has no such re-sort and was
always correct.

Both engines must emit the same canonical order:
    No Double/Take, Double/Take, Double/Pass, Too good/Take, Too good/Pass
"""

import pytest

from ankigammon.parsers.xg_text_parser import XGTextParser


def _canonical(double_term="Double"):
    return [
        f"No {double_term}/Take",
        f"{double_term}/Take",
        f"{double_term}/Pass",
        "Too good/Take",
        "Too good/Pass",
    ]


def _cube_export(best_action, nd_eq, dt_eq, dp_eq="+1.0000", cube=1):
    """An XG cube export whose best action we control.

    XGID fields: position:cubeLog2:cubeOwner:turn:dice:scoreO:scoreX:...
    A redouble needs the cube already owned by the player on roll.
    """
    cube_log2 = 0 if cube == 1 else 1
    cube_owner = 0 if cube == 1 else -1
    # XG says "redouble" throughout the equities block once the cube is up,
    # and that block is what the parser reads the terminology from.
    term = "Double" if cube == 1 else "Redouble"
    return f"""XGID=-b----E-C--AeD---bAdb---A-:{cube_log2}:{cube_owner}:1:00:0:0:3:0:10

X:Player 1   O:Player 2
Score is X:0 O:0. Unlimited Game, Jacoby Beaver
Pip count  X: 159  O: 163 X-O: 0-0
Cube: {cube}
X on roll, cube action

Cubeless Equities: No Double={nd_eq}, Double={dt_eq}

Cubeful Equities:
       No {term.lower()}:     {nd_eq}
       {term}/Take:   {dt_eq}
       {term}/Pass:   {dp_eq}

Best Cube action: {best_action}

eXtreme Gammon Version: 2.19
"""


def _parse(best_action, nd_eq="-0.0861", dt_eq="-0.0769", dp_eq="+1.0000"):
    text = _cube_export(best_action, nd_eq, dt_eq, dp_eq)
    decisions = XGTextParser.parse_string(text)
    assert len(decisions) == 1
    return decisions[0].candidate_moves


def _answer_index(moves):
    return next(i for i, m in enumerate(moves) if m.rank == 1)


class TestCanonicalOrder:
    def test_options_are_in_logical_order(self):
        moves = _parse("Double / Take")

        assert [m.notation for m in moves] == _canonical()

    def test_order_is_the_same_when_no_double_is_best(self):
        moves = _parse("No double", nd_eq="-0.0500", dt_eq="-0.0900")

        assert [m.notation for m in moves] == _canonical()

    def test_redouble_wording_keeps_the_same_shape(self):
        text = _cube_export("Redouble / Take", "-0.0861", "-0.0769", cube=2)
        moves = XGTextParser.parse_string(text)[0].candidate_moves

        assert [m.notation for m in moves] == _canonical("Redouble")


class TestAnswerIsNotAlwaysFirst:
    """The reported symptom."""

    def test_double_take_best_lands_on_option_b(self):
        moves = _parse("Double / Take", nd_eq="-0.0861", dt_eq="-0.0769")

        assert _answer_index(moves) == 1, "Double/Take is the second option"

    def test_no_double_best_lands_on_option_a(self):
        moves = _parse("No double", nd_eq="-0.0500", dt_eq="-0.0900")

        assert _answer_index(moves) == 0

    def test_double_pass_best_lands_on_option_c(self):
        moves = _parse("Double / Pass", nd_eq="-0.5000", dt_eq="-0.4000", dp_eq="+1.0000")

        assert _answer_index(moves) == 2

    def test_the_answer_moves_between_positions(self):
        """The whole point: slot A must not be the answer every time."""
        seen = {
            _answer_index(_parse("No double", nd_eq="-0.0500", dt_eq="-0.0900")),
            _answer_index(_parse("Double / Take", nd_eq="-0.0861", dt_eq="-0.0769")),
            _answer_index(_parse("Double / Pass", nd_eq="-0.5000", dt_eq="-0.4000")),
        }

        assert len(seen) > 1, f"the answer sat in the same slot every time: {seen}"


class TestRanksAndErrorsSurvive:
    """Ordering is presentation; the analysis data must be unaffected."""

    def test_every_option_still_has_a_rank(self):
        moves = _parse("Double / Take")

        assert sorted(m.rank for m in moves) == [1, 2, 3, 4, 5]

    def test_exactly_one_option_is_rank_one(self):
        moves = _parse("Double / Take")

        assert sum(1 for m in moves if m.rank == 1) == 1

    def test_the_best_action_is_the_one_ranked_first(self):
        moves = _parse("Double / Take", nd_eq="-0.0861", dt_eq="-0.0769")

        assert next(m for m in moves if m.rank == 1).notation == "Double/Take"

    def test_the_best_option_has_no_error(self):
        moves = _parse("Double / Take")

        assert next(m for m in moves if m.rank == 1).error == 0.0

    def test_other_options_carry_an_error(self):
        moves = _parse("Double / Take", nd_eq="-0.0861", dt_eq="-0.0769")

        no_double = next(m for m in moves if m.notation == "No Double/Take")
        assert no_double.error == pytest.approx(0.0092, abs=1e-4)


class TestMatchesTheGnubgParser:
    def test_both_parsers_agree_on_the_option_list(self):
        """GnuBG was already right; XG has to produce the same shape."""
        from ankigammon.parsers.gnubg_parser import GNUBGParser

        assert hasattr(GNUBGParser, "_parse_cube_decision")
        xg_notations = [m.notation for m in _parse("Double / Take")]

        assert xg_notations == _canonical()
