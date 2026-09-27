"""OGID field 5 and board perspective, checked against positions HedgeHog wrote.

Field 5 names the player who reached the position, so the other player acts;
at a pending double it names the doubler. The OGID board is absolute, while a
Position is stored from the view of the player on roll.
"""

import json
from pathlib import Path

import pytest

from ankigammon.models import CubeState, Player, Position
from ankigammon.utils.move_parser import MoveParser
from ankigammon.utils.ogid import encode_ogid, parse_ogid
from ankigammon.utils.xgid import encode_xgid, parse_xgid

BLUNDERS = json.loads(
    (Path(__file__).parent / "data" / "hedgehog" / "blunders.json").read_text()
)["blunders"]


def _is_pending(ogid: str) -> bool:
    return ogid.split(":")[2][2] == "O"


@pytest.mark.parametrize("row", BLUNDERS, ids=lambda r: f"g{r['game_num']}p{r['ply_num']}")
def test_hedgehog_positions_read_the_side_to_act(row):
    _, metadata = parse_ogid(row["position"])
    actor = Player.X if row["color"] == 1 else Player.O
    doubler = Player.O if actor == Player.X else Player.X
    expected = doubler if _is_pending(row["position"]) else actor
    assert metadata["on_roll"] == expected


@pytest.mark.parametrize("row", BLUNDERS, ids=lambda r: f"g{r['game_num']}p{r['ply_num']}")
def test_hedgehog_positions_round_trip_through_xgid(row):
    ogid = row["position"]
    position, metadata = parse_ogid(ogid)
    match_length = metadata["match_length"]
    xgid = encode_xgid(
        position,
        cube_value=metadata["cube_value"],
        cube_owner=metadata["cube_owner"],
        dice=metadata.get("dice"),
        on_roll=metadata["on_roll"],
        score_x=metadata["score_x"],
        score_o=metadata["score_o"],
        match_length=match_length,
    )
    position2, metadata2 = parse_xgid(xgid)
    assert encode_ogid(
        position2,
        cube_value=metadata2["cube_value"],
        cube_owner=metadata2["cube_owner"],
        cube_action=metadata["cube_action"],
        dice=metadata2.get("dice"),
        on_roll=metadata2["on_roll"],
        game_state=metadata["game_state"],
        score_x=metadata2["score_x"],
        score_o=metadata2["score_o"],
        match_length=match_length,
        match_modifier=metadata.get("match_modifier", ""),
        move_id=metadata.get("move_id"),
    ) == ogid


def test_white_to_move_is_flipped_into_the_movers_view():
    # White (X) to play 6-1; HedgeHog says it played 7/6 7/1* in White's own numbering
    position, metadata = parse_ogid("99cchhiijjjkkmm:223334455666ddo:N0N:16:B:R:2:1:3C:13")
    assert metadata["on_roll"] == Player.X
    assert position.points[7] == -2  # White's 7 point, absolute point 18
    assert position.points[1] == 1   # Black's blot on White's ace point, absolute 24
    after = MoveParser.apply_move(position, "7/6 7/1*", Player.O)
    assert after.points[7] == 0
    assert after.points[1] == -1
    assert after.points[0] == 1      # the hit Black checker is on the bar


def test_black_to_move_is_not_flipped():
    position, metadata = parse_ogid("03cccchhhhjjjjj:16666888dddddoo:N0N:33:W:R:0:1:3:3")
    assert metadata["on_roll"] == Player.O
    assert position.points[13] == -5
    assert position.points[0] == 1   # White's checker on its bar


def test_pending_double_names_the_doubler():
    _, metadata = parse_ogid("cccccgghhhjjjjj:112233666777dll:N0O::B:D:0:0:3:11")
    assert metadata["on_roll"] == Player.O
    assert encode_ogid(
        Position.from_ogid("cccccgghhhjjjjj:112233666777dll:N0O"),
        cube_action="O",
        on_roll=Player.O,
        game_state="D",
        match_length=3,
    ).split(":")[4] == "B"


def test_encoding_names_the_player_who_reached_the_position():
    start = Position.from_ogid("11jjjjjhhhccccc:ooddddd88866666:N0N")
    assert encode_ogid(start, on_roll=Player.O).split(":")[4] == "W"
    assert encode_ogid(start.flipped(), on_roll=Player.X).split(":")[4] == "B"
    assert encode_ogid(start.flipped(), on_roll=Player.X, only_position=True) == \
        "11ccccchhhjjjjj:66666888dddddoo:N0N"


def test_borne_off_checkers_may_be_written_as_q():
    position, _ = parse_ogid("11jjjjjhhhccccq:ooddddd88866666:W1N")
    assert position.x_off == 1
    assert sum(c for c in position.points if c > 0) == 14
    assert parse_ogid("11jjjjjhhhccccq:ooddddd88866666:W1N")[1]["cube_owner"] == CubeState.X_OWNS
