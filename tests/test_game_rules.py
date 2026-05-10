"""Unit tests for the GameRules value type.

GameRules encapsulates the polymorphic XGID field 7 ("Crawford / Jacoby")
together with match_length, since the meaning of the bits depends on whether
the game is match play or unlimited.
"""
import pytest

from ankigammon.models import (
    CubeState,
    Decision,
    DecisionType,
    GameRules,
    Player,
    Position,
)


# ---------------------------------------------------------------------------
# Construction & invariants

class TestConstruction:
    def test_default_is_money_no_rules(self):
        r = GameRules()
        assert r.match_length == 0
        assert r.crawford is False
        assert r.jacoby is False
        assert r.beavers_allowed is False

    def test_match_play_with_crawford(self):
        r = GameRules(match_length=7, crawford=True)
        assert r.match_length == 7 and r.crawford is True

    def test_unlimited_with_jacoby_and_beavers(self):
        r = GameRules(match_length=0, jacoby=True, beavers_allowed=True)
        assert r.jacoby is True and r.beavers_allowed is True

    def test_crawford_in_unlimited_is_rejected(self):
        with pytest.raises(ValueError, match="crawford"):
            GameRules(match_length=0, crawford=True)

    def test_jacoby_in_match_is_rejected(self):
        with pytest.raises(ValueError, match="jacoby|beavers"):
            GameRules(match_length=5, jacoby=True)

    def test_beavers_in_match_is_rejected(self):
        with pytest.raises(ValueError, match="jacoby|beavers"):
            GameRules(match_length=5, beavers_allowed=True)

    def test_negative_match_length_is_rejected(self):
        with pytest.raises(ValueError):
            GameRules(match_length=-1)

    def test_is_frozen(self):
        r = GameRules(match_length=3, crawford=True)
        with pytest.raises(Exception):  # FrozenInstanceError
            r.crawford = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# XGID field 7 round-trip

class TestXgidFieldRoundtrip:
    @pytest.mark.parametrize("ml,cj,expected", [
        (3, 0, dict(match_length=3, crawford=False)),
        (3, 1, dict(match_length=3, crawford=True)),
        (0, 0, dict(match_length=0, jacoby=False, beavers_allowed=False)),
        (0, 1, dict(match_length=0, jacoby=True,  beavers_allowed=False)),
        (0, 2, dict(match_length=0, jacoby=False, beavers_allowed=True)),
        (0, 3, dict(match_length=0, jacoby=True,  beavers_allowed=True)),
    ])
    def test_from_xgid_field(self, ml, cj, expected):
        r = GameRules.from_xgid_field(match_length=ml, cj=cj)
        for key, value in expected.items():
            assert getattr(r, key) == value

    @pytest.mark.parametrize("ml,cj", [
        (3, 0), (3, 1),
        (0, 0), (0, 1), (0, 2), (0, 3),
    ])
    def test_round_trip(self, ml, cj):
        r = GameRules.from_xgid_field(match_length=ml, cj=cj)
        assert r.to_xgid_field() == cj

    def test_match_play_ignores_higher_bits(self):
        # In match play only bit 0 is meaningful; bit 1 (Beavers) doesn't apply.
        r = GameRules.from_xgid_field(match_length=5, cj=3)
        assert r.crawford is True
        # Re-encoded value drops the spurious bit 1.
        assert r.to_xgid_field() == 1

    def test_invalid_cj_value_rejected(self):
        with pytest.raises(ValueError):
            GameRules.from_xgid_field(match_length=0, cj=4)
        with pytest.raises(ValueError):
            GameRules.from_xgid_field(match_length=0, cj=-1)


# ---------------------------------------------------------------------------
# Equality / replace semantics

class TestValueSemantics:
    def test_equal_rules_compare_equal(self):
        assert GameRules(match_length=0, jacoby=True) == GameRules(match_length=0, jacoby=True)

    def test_different_rules_compare_unequal(self):
        assert GameRules(match_length=0, jacoby=True) != GameRules(match_length=0, jacoby=False)

    def test_dataclasses_replace_works(self):
        import dataclasses
        r = GameRules(match_length=0, jacoby=True, beavers_allowed=True)
        flipped = dataclasses.replace(r, beavers_allowed=False)
        assert flipped.beavers_allowed is False and flipped.jacoby is True


# ---------------------------------------------------------------------------
# Decision integration

class TestDecisionRules:
    def _basic(self, **overrides):
        kwargs = dict(
            position=Position(),
            on_roll=Player.O,
            decision_type=DecisionType.CUBE_ACTION,
            cube_value=1,
            cube_owner=CubeState.CENTERED,
        )
        kwargs.update(overrides)
        return Decision(**kwargs)

    def test_decision_rejects_crawford_in_unlimited(self):
        with pytest.raises(ValueError, match="crawford"):
            self._basic(match_length=0, crawford=True)

    def test_decision_rejects_jacoby_in_match(self):
        with pytest.raises(ValueError, match="jacoby|beavers"):
            self._basic(match_length=5, jacoby=True)

    def test_decision_rejects_beavers_in_match(self):
        with pytest.raises(ValueError, match="jacoby|beavers"):
            self._basic(match_length=5, beavers_allowed=True)

    def test_decision_rules_property_reflects_fields(self):
        d = self._basic(match_length=0, jacoby=True, beavers_allowed=True)
        assert d.rules == GameRules(
            match_length=0, jacoby=True, beavers_allowed=True
        )

    def test_default_decision_is_valid(self):
        # All flags default to False / match_length=0 — should construct fine.
        self._basic()
