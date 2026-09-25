"""The match-import filter, shared by the desktop import and the browser version.

`import_filter_golden.json` was recorded from MainWindow's filter before it
moved out of the Qt class, so these tests pin that the move changed nothing.
Regenerate it only for an intended behaviour change.
"""

import copy
import json
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

from ankigammon.import_filter import filter_decisions
from ankigammon.parsers.xg_binary_parser import XGBinaryParser

DATA = Path(__file__).parent / "data"
GOLDEN = json.loads((DATA / "import_filter_golden.json").read_text(encoding="utf-8"))


def _fingerprint(decisions):
    return [
        [
            d.xgid,
            d.decision_type.name,
            d.user_player.name if d.user_player else None,
            next(i for i, m in enumerate(d.candidate_moves) if m.was_played),
            len(d.candidate_moves),
        ]
        for d in decisions
    ]


@pytest.fixture(scope="module")
def sample_decisions():
    return XGBinaryParser.parse_file(str(DATA / "sample_match.xg"))


@pytest.mark.parametrize(
    "combo", GOLDEN["sample_match.xg"],
    ids=lambda c: f"chk{c['checker']}-cube{c['cube']}-x{c['include_x']:d}-o{c['include_o']:d}-n{c['max_moves']}",
)
def test_matches_the_recorded_desktop_filter(sample_decisions, combo):
    kept = filter_decisions(
        copy.deepcopy(sample_decisions), combo["checker"], combo["cube"],
        combo["include_x"], combo["include_o"], combo["max_moves"],
    )
    assert _fingerprint(kept) == combo["kept"]


def test_golden_exercises_every_branch():
    """Guards the golden file itself: a fixture where nothing is kept, or no
    card is tagged for one player, would let a broken filter pass."""
    runs = GOLDEN["sample_match.xg"]
    rows = [row for run in runs for row in run["kept"]]
    assert {r[1] for r in rows} == {"CHECKER_PLAY", "CUBE_ACTION"}
    # Player X never errs on the cube in this match; see test_cube_decision_is_tagged_for_the_single_player.
    assert {"O", None} <= {r[2] for r in rows}
    moved = [r for run in runs for r in run["kept"] if r[3] == run["max_moves"] - 1 and r[4] > run["max_moves"]]
    assert moved, "no played move was injected into the last choice slot"
    assert len({len(run["kept"]) for run in runs}) > 5


def _cube_decision(doubler, responder, doubler_error, responder_error):
    from ankigammon.models import Decision, DecisionType, Move, Position

    decision = Decision(
        position=Position(),
        decision_type=DecisionType.CUBE_ACTION,
        candidate_moves=[Move(notation="No Double", equity=0.0, rank=1),
                         Move(notation="Double/Take", equity=-0.2, rank=2, was_played=True)],
    )
    attribution = {"doubler": doubler, "responder": responder,
                   "doubler_error": doubler_error, "responder_error": responder_error}
    return decision, attribution


@pytest.mark.parametrize("erring_side", ["doubler", "responder"])
@pytest.mark.parametrize("player", ["X", "O"])
def test_cube_decision_is_tagged_for_the_single_player(player, erring_side):
    from ankigammon.models import Decision, Player

    me = Player[player]
    other = Player.O if me == Player.X else Player.X

    def erred_by(who):
        if erring_side == "doubler":
            return _cube_decision(who, other if who == me else me, 0.3, None)
        return _cube_decision(other if who == me else me, who, None, 0.3)

    mine, mine_attr = erred_by(me)
    theirs, theirs_attr = erred_by(other)
    attributions = {id(mine): mine_attr, id(theirs): theirs_attr}
    with mock.patch.object(Decision, "get_cube_error_attribution",
                           lambda self: attributions[id(self)]):
        kept = filter_decisions([mine, theirs], 0.1, 0.1,
                                include_player_x=me == Player.X, include_player_o=me == Player.O,
                                max_options=5)

    assert kept == [mine]
    assert mine.user_player == me
    assert theirs.user_player is None


def test_cube_error_exactly_at_the_threshold_is_kept():
    from ankigammon.models import Decision, Player

    at, at_attr = _cube_decision(Player.X, Player.O, 0.08, None)
    below, below_attr = _cube_decision(Player.X, Player.O, 0.0799, None)
    attributions = {id(at): at_attr, id(below): below_attr}
    with mock.patch.object(Decision, "get_cube_error_attribution",
                           lambda self: attributions[id(self)]):
        kept = filter_decisions([at, below], 1.0, 0.08, True, True, max_options=5)
    assert kept == [at]


def test_checker_error_exactly_at_the_threshold_is_kept():
    from ankigammon.models import Decision, Move, Player, Position

    def checker(error):
        return Decision(position=Position(), on_roll=Player.O, dice=(5, 2), xg_error_move=error,
                        candidate_moves=[Move(notation="13/8 13/11", equity=0.0, rank=1),
                                         Move(notation="24/17", equity=-error, rank=2, was_played=True)])

    at, below = checker(0.08), checker(0.0799)
    assert filter_decisions([at, below], 0.08, 1.0, True, True, max_options=5) == [at]


def test_importing_the_filter_and_web_entry_does_not_load_qt():
    code = (
        "import sys, ankigammon.import_filter, ankigammon.web; "
        "qt = [m for m in sys.modules if m.startswith(('PySide6', 'qtawesome'))]; "
        "print(qt); sys.exit(1 if qt else 0)"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_main_window_uses_the_shared_filter(tmp_path):
    from ankigammon.gui.main_window import MainWindow
    from ankigammon.settings import Settings

    settings = Settings(config_path=tmp_path / "config.json")
    settings.max_moves = 4
    window = mock.Mock(settings=settings)
    with mock.patch("ankigammon.gui.main_window.filter_decisions", return_value=["kept"]) as shared:
        result = MainWindow._filter_decisions_by_import_options(window, ["d"], 0.1, 0.2, True, False)
    assert result == ["kept"]
    shared.assert_called_once_with(["d"], 0.1, 0.2, True, False, 4)
