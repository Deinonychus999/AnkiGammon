"""QA runner for the split_cube_decisions feature.

Runs every check that can be automated; exits 0 on success, 1 on any failure.

Manual residue (open Anki / inspect by eye):
  1. Settings -> Study Options: confirm "Split cube decisions by player"
     checkbox + tooltip render correctly.
  2. Export an APKG, import into Anki Desktop, eyeball one take card and one
     doubler card to confirm they render natively.

Run from repo root:
    python scripts/qa_split_cube.py
"""

from __future__ import annotations

import glob
import re
import subprocess
import sys
import tempfile
from pathlib import Path

# Force UTF-8 for the console — Windows defaults to cp1252 which can't encode
# the arrows, em-dashes, etc. used in test labels.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from ankigammon.anki.card_generator import CardGenerator
from ankigammon.anki.decision_serialize import decision_from_json, decision_to_json
from ankigammon.models import CubeState, Decision, DecisionType, Player
from ankigammon.parsers.gnubg_parser import GNUBGParser
from ankigammon.parsers.xg_binary_parser import XGBinaryParser
from ankigammon.settings import get_settings
from ankigammon.utils.gnubg_analyzer import GNUBGAnalyzer

# ---------------------------------------------------------------------------
# Fixtures

GNUBG_PATH = r"D:/Program Files (x86)/gnubg/gnubg-cli.exe"
XG_DUMP = REPO / "xg_dump"
TAKE_BLUNDER_FILE = XG_DUMP / "UjOOc8fXTnA.xg"  # Deinonychus (P1=O) take blunder
DOUBLE_BLUNDER_FILE = (
    XG_DUMP / "Deinonychus - deko 9pt Backgammon Studio 2024_01_02 17_26_05.xg"
)  # Deinonychus pure cube blunder
ON_ROLL_O_FILE = XG_DUMP / "-pdm4qfo7Fg.xg"  # responder=X take blunder
BEAVER_XGID = "-acBBBDa-----A---A-cbbBc-A:0:0:-1:00:0:0:3:0:10"
BEAVER_XGP = Path(r"G:\Users\Frank\Documents\eXtremeGammon\Position 505.xgp")

# ---------------------------------------------------------------------------
# Result tracking + rendered-card capture

RESULTS: list[tuple[str, bool, str]] = []
ARTIFACTS: list[tuple[str, str, str, str]] = []  # (label, description, xgid, html)
ARTIFACT_PATH = REPO / "_qa_artifacts.html"


def check(name: str, passed: bool, info: str = "") -> None:
    RESULTS.append((name, passed, info))
    status = "PASS" if passed else "FAIL"
    suffix = f" — {info}" if info else ""
    print(f"  [{status}] {name}{suffix}")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def xgid_for(decision: Decision) -> str:
    """Regenerate XGID from the current decision state (handles forced
    cube_value/score mutations that the stored xgid was captured before).
    Field 7 (Crawford / Jacoby / Beavers) is composed via the GameRules
    value type so the polymorphism lives in exactly one place.
    """
    return decision.position.to_xgid(
        cube_value=decision.cube_value,
        cube_owner=decision.cube_owner,
        dice=decision.dice,
        on_roll=decision.on_roll,
        score_x=decision.score_x,
        score_o=decision.score_o,
        match_length=decision.match_length,
        crawford_jacoby=decision.rules.to_xgid_field(),
    )


def capture(label: str, description: str, xgid: str, card_html: str) -> None:
    """Save a rendered card front for visual inspection in the artifact viewer."""
    ARTIFACTS.append((label, description, xgid, card_html))


def write_artifact_viewer() -> None:
    """Dump all captured cards into one scrollable HTML page."""
    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        "<title>QA artifacts — split_cube_decisions</title>",
        "<style>",
        "  body { background:#1e1e2e; color:#e0e0e0; font-family:system-ui,sans-serif;",
        "         max-width:1100px; margin:24px auto; padding:0 16px; }",
        "  h1 { border-bottom:2px solid #555; padding-bottom:8px; }",
        "  .card { background:#181825; border:1px solid #444; border-radius:8px;",
        "          padding:16px; margin-bottom:32px; }",
        "  .card h2 { margin-top:0; color:#a6e3a1; }",
        "  .card .desc { color:#bbb; margin-bottom:12px; font-size:14px; }",
        "  .card .xgid { font-family:Consolas,Menlo,monospace; font-size:13px;",
        "                background:#11111b; border:1px solid #444; border-radius:4px;",
        "                padding:8px 10px; margin-bottom:14px; user-select:all;",
        "                cursor:text; word-break:break-all; }",
        "  .card .xgid label { display:block; color:#a6adc8; font-size:11px;",
        "                      text-transform:uppercase; letter-spacing:0.5px;",
        "                      margin-bottom:4px; user-select:none; }",
        "  .card-front svg { max-width:100%; height:auto; background:#fff; ",
        "                    border-radius:4px; }",
        "  nav { position:sticky; top:0; background:#181825; padding:8px 0;",
        "        border-bottom:1px solid #555; margin-bottom:24px; z-index:10; }",
        "  nav a { color:#89b4fa; margin-right:14px; text-decoration:none;",
        "          font-size:13px; }",
        "  nav a:hover { text-decoration:underline; }",
        "</style></head><body>",
        "<h1>QA artifacts — split_cube_decisions</h1>",
        f"<p>Generated by <code>scripts/qa_split_cube.py</code>. {len(ARTIFACTS)} cards captured. "
        "XGIDs are click-to-select so you can paste them into XG to verify each position.</p>",
        "<nav>",
    ]
    for i, (label, _, _, _) in enumerate(ARTIFACTS, 1):
        parts.append(f"<a href='#card-{i}'>{i}. {label}</a>")
    parts.append("</nav>")
    for i, (label, description, xgid, html) in enumerate(ARTIFACTS, 1):
        parts.append(f"<div class='card' id='card-{i}'>")
        parts.append(f"<h2>{i}. {label}</h2>")
        parts.append(f"<div class='desc'>{description}</div>")
        parts.append(f"<div class='xgid'><label>XGID (click to select)</label>{xgid}</div>")
        parts.append(html)
        parts.append("</div>")
    parts.append("</body></html>")
    ARTIFACT_PATH.write_text("\n".join(parts), encoding="utf-8")


# ---------------------------------------------------------------------------
# Helpers

def mcq_options(html: str) -> list[str]:
    return [
        m.group(2).strip()
        for m in re.finditer(r"<strong>([A-Z])\.</strong> ([^<\n]+)", html)
    ]


def mcq_correct(decision: Decision, candidates: list) -> str | None:
    """Return the notation of the rank-1 candidate."""
    for m in candidates:
        if m and m.rank == 1:
            return m.notation
    return None


def question_text(html: str) -> str | None:
    m = re.search(r"<h3>([^<]+)</h3>", html)
    return m.group(1) if m else None


def pip_positions(svg: str) -> list[tuple[float, int]]:
    """Return [(y, value)] for each pip-count text element."""
    return [
        (float(m.group(1)), int(m.group(2)))
        for m in re.finditer(
            r'<text class="pip-count"[^>]*y="([^"]+)"[^>]*>Pip: (\d+)</text>', svg
        )
    ]


def cube_offered_pos(svg: str) -> tuple[float, float, int] | None:
    """Return (x, y, value) for the offered cube, or None."""
    m = re.search(
        r'<g class="cube cube-offered">[\s\S]*?<rect[^>]*x="([^"]+)"[^>]*y="([^"]+)"'
        r'[\s\S]*?<text[^>]*>(\d+)</text>',
        svg,
    )
    if not m:
        return None
    return float(m.group(1)), float(m.group(2)), int(m.group(3))


def gen_card(
    decision: Decision,
    *,
    split: bool,
    user_player: Player | None,
    orientation: str = "counter-clockwise",
) -> dict:
    settings = get_settings()
    settings.split_cube_decisions = split
    settings.board_orientation = orientation
    decision.user_player = user_player
    with tempfile.TemporaryDirectory() as td:
        gen = CardGenerator(
            output_dir=Path(td), show_options=True, interactive_moves=False
        )
        return gen.generate_card(decision)


def first_take_blunder(decisions: list[Decision], min_err: float = 0.3) -> Decision:
    return next(
        d
        for d in decisions
        if d.decision_type == DecisionType.CUBE_ACTION
        and d.take_error is not None
        and d.take_error != -1000
        and abs(d.take_error) >= min_err
    )


# ---------------------------------------------------------------------------
# Tests

def test_beaver_detection() -> None:
    section("Beaver detection")

    analyzer = GNUBGAnalyzer(GNUBG_PATH, analysis_ply=2)
    out, dt = analyzer.analyze_position(BEAVER_XGID)
    decision = GNUBGParser.parse_analysis(out, BEAVER_XGID, dt)
    check(
        "GnuBG flags No-double/Beaver position",
        decision.beaverable is True,
        f"beaverable={decision.beaverable}",
    )

    if BEAVER_XGP.exists():
        d = XGBinaryParser.parse_file(str(BEAVER_XGP))[0]
        check("XG binary flags Beaver position via Doubled.isBeaver", d.beaverable is True)
    else:
        check("XG binary flags Beaver position", False, f"missing: {BEAVER_XGP}")


def test_take_blunder_card() -> None:
    section("Receiver take card (UjOOc8fXTnA — Deinonychus take blunder)")

    decisions = XGBinaryParser.parse_file(str(TAKE_BLUNDER_FILE))
    d = first_take_blunder(decisions)
    # Deinonychus = P1; main_window's filter loop sets user_player=Player.O for P1.
    card = gen_card(d, split=True, user_player=Player.O)
    capture(
        "Take card (CCW) — UjOOc8fXTnA",
        "Deinonychus is the receiver (P1). Pip 157 should be at the BOTTOM, "
        "the offered cube ‘2’ should be in the middle of the bottom-LEFT outer "
        "board, and MCQ should be {Take, Pass}.",
        xgid_for(d),
        card["front"],
    )

    opts = mcq_options(card["front"])
    check("MCQ = {Take, Pass}", opts == ["Take", "Pass"], f"got {opts}")
    check(
        "Question text",
        question_text(card["front"]) == "Take or pass?",
        f"got {question_text(card['front'])!r}",
    )

    # Pip 157 belongs to Deinonychus (receiver). Should be at the BOTTOM after the flip.
    pips = pip_positions(card["front"])
    pips_top = [v for y, v in pips if y < 325]
    pips_bot = [v for y, v in pips if y >= 325]
    check(
        "Receiver's pip 157 at BOTTOM, doubler's pip 123 at TOP",
        157 in pips_bot and 123 in pips_top,
        f"top={pips_top}, bottom={pips_bot}",
    )

    cube = cube_offered_pos(card["front"])
    check("Offered cube exists", cube is not None)
    if cube:
        x, y, val = cube
        check("Cube shows doubled value 2", val == 2, f"got {val}")
        check(
            "Cube vertically centered (~y=275)",
            abs(y - 275) < 5,
            f"y={y}",
        )
        check("Cube on LEFT side under counter-clockwise", x < 400, f"x={x}")

    # Clockwise puts the cube on the right
    card_cw = gen_card(d, split=True, user_player=Player.O, orientation="clockwise")
    capture(
        "Take card (CW) — same position",
        "Same take blunder, clockwise orientation. The cube should now be in "
        "the bottom-RIGHT outer board.",
        xgid_for(d),
        card_cw["front"],
    )
    cube_cw = cube_offered_pos(card_cw["front"])
    if cube_cw:
        check(
            "Cube on RIGHT side under clockwise",
            cube_cw[0] > 400,
            f"x={cube_cw[0]}",
        )


def test_doubler_card() -> None:
    section("Doubler card (Deinonychus pure cube blunder)")

    if not DOUBLE_BLUNDER_FILE.exists():
        check("Doubler blunder fixture exists", False, f"missing: {DOUBLE_BLUNDER_FILE}")
        return

    decisions = XGBinaryParser.parse_file(str(DOUBLE_BLUNDER_FILE))
    d = next(
        d
        for d in decisions
        if d.decision_type == DecisionType.CUBE_ACTION
        and d.cube_error is not None
        and d.cube_error != -1000
        and abs(d.cube_error) >= 0.3
        and (
            d.take_error is None
            or d.take_error == -1000
            or abs(d.take_error) < 0.05
        )
        and d.get_cube_error_attribution()["doubler"] == Player.O
    )
    card = gen_card(d, split=True, user_player=Player.O)
    capture(
        "Doubler card — Deinonychus pure cube blunder",
        "Deinonychus made a pure double/roll error. MCQ should be {Roll, Double}, "
        "no offered-cube graphic, default doubler-POV layout (cube remains in the "
        "side-area at its original value).",
        xgid_for(d),
        card["front"],
    )

    opts = mcq_options(card["front"])
    check("MCQ = {Roll, Double}", opts == ["Roll", "Double"], f"got {opts}")
    check(
        "Question text",
        question_text(card["front"]) == "Should you double or roll?",
        f"got {question_text(card['front'])!r}",
    )

    # No offered-cube graphic in the doubler card (the cube hasn't been doubled yet).
    check(
        "Doubler card has NO offered-cube graphic",
        cube_offered_pos(card["front"]) is None,
    )


def test_beaver_mcq() -> None:
    section("Beaver MCQ (unlimited)")

    analyzer = GNUBGAnalyzer(GNUBG_PATH, analysis_ply=2)
    out, dt = analyzer.analyze_position(BEAVER_XGID)
    decision = GNUBGParser.parse_analysis(out, BEAVER_XGID, dt)
    responder = decision.get_cube_error_attribution()["responder"]

    card = gen_card(decision, split=True, user_player=responder)
    capture(
        "Beaver take card (unlimited)",
        "GnuBG flagged this as a No-double/Beaver position. Unlimited game so "
        "MCQ should be {Take, Pass, Beaver}, with Beaver as the correct answer.",
        xgid_for(decision),
        card["front"],
    )
    opts = mcq_options(card["front"])
    check(
        "Unlimited + beaverable -> MCQ has {Take, Pass, Beaver}",
        opts == ["Take", "Pass", "Beaver"],
        f"got {opts}",
    )
    check(
        "Question text mentions beaver",
        question_text(card["front"]) == "Take, pass, or beaver?",
    )

    # Verify Beaver is rank 1 by re-running the variant builder directly.
    settings = get_settings()
    settings.split_cube_decisions = True
    decision.user_player = responder
    with tempfile.TemporaryDirectory() as td:
        gen = CardGenerator(output_dir=Path(td), show_options=True, interactive_moves=False)
        variant = gen._maybe_build_cube_variant(decision)
    check("Variant built", variant is not None)
    if variant:
        candidates, _ = variant
        correct = mcq_correct(decision, candidates)
        check("Beaver is the correct answer", correct == "Beaver", f"correct={correct}")


def test_no_beaver_in_match_play() -> None:
    section("Beaver excluded for match play")

    decisions = XGBinaryParser.parse_file(str(TAKE_BLUNDER_FILE))
    d = first_take_blunder(decisions)
    assert d.match_length > 0
    card = gen_card(d, split=True, user_player=Player.O)
    opts = mcq_options(card["front"])
    check(
        "Match play take card has 2 options (no Beaver)",
        opts == ["Take", "Pass"],
        f"got {opts}",
    )


def test_beavers_allowed_flag_respected() -> None:
    """XGID field 7 bit 1 controls whether beavers are legal in the game.
    The MCQ should hide the Beaver option when the rule is off, even in an
    unlimited game on a position that would otherwise be beaverable."""
    section("Beavers-allowed flag (XGID field 7 bit 1)")

    analyzer = GNUBGAnalyzer(GNUBG_PATH, analysis_ply=2)
    base_pos = "-acBBBDa-----A---A-cbbBc-A"

    # crawford_jacoby = 2 → unlimited, Jacoby off, Beavers ON
    on_xgid = f"{base_pos}:0:0:-1:00:0:0:2:0:10"
    out_on, dt_on = analyzer.analyze_position(on_xgid)
    d_on = GNUBGParser.parse_analysis(out_on, on_xgid, dt_on)
    check("XGID with bit 1 set → beavers_allowed=True", d_on.beavers_allowed is True)
    check("XGID with bit 1 set → beaverable=True", d_on.beaverable is True)
    responder_on = d_on.get_cube_error_attribution()["responder"]
    card_on = gen_card(d_on, split=True, user_player=responder_on)
    capture(
        "Take card — Beavers ALLOWED (XGID cj=2)",
        "Same beaverable position with the Beavers-allowed flag ON. MCQ should "
        "include Beaver and Beaver should be the correct answer.",
        xgid_for(d_on),
        card_on["front"],
    )
    check(
        "Beavers ALLOWED → MCQ has 3 options",
        mcq_options(card_on["front"]) == ["Take", "Pass", "Beaver"],
        f"got {mcq_options(card_on['front'])}",
    )

    # crawford_jacoby = 1 → unlimited, Jacoby on, Beavers OFF
    off_xgid = f"{base_pos}:0:0:-1:00:0:0:1:0:10"
    out_off, dt_off = analyzer.analyze_position(off_xgid)
    d_off = GNUBGParser.parse_analysis(out_off, off_xgid, dt_off)
    check("XGID with bit 1 clear → beavers_allowed=False", d_off.beavers_allowed is False)
    check("XGID with bit 1 clear → beaverable=False", d_off.beaverable is False)
    responder_off = d_off.get_cube_error_attribution()["responder"]
    card_off = gen_card(d_off, split=True, user_player=responder_off)
    capture(
        "Take card — Beavers DISALLOWED (XGID cj=1)",
        "Same position but with Beavers-allowed OFF. MCQ should be {Take, Pass} "
        "only — Beaver must NOT appear, even though the position is otherwise "
        "beaverable.",
        xgid_for(d_off),
        card_off["front"],
    )
    check(
        "Beavers DISALLOWED → MCQ is just {Take, Pass}",
        mcq_options(card_off["front"]) == ["Take", "Pass"],
        f"got {mcq_options(card_off['front'])}",
    )

    # Regenerated XGID must keep field 7 bit 1 set when beavers are allowed,
    # otherwise re-parsing or pasting into XG would lose the rule.
    regen = xgid_for(d_on)
    field7 = int(regen.split(":")[7])
    check(
        "Regenerated XGID keeps Beavers-allowed bit (field 7 bit 1)",
        bool(field7 & 2),
        f"field7={field7} in {regen}",
    )
    regen_off = xgid_for(d_off)
    field7_off = int(regen_off.split(":")[7])
    check(
        "Regenerated XGID clears Beavers-allowed bit when off",
        not (field7_off & 2),
        f"field7={field7_off} in {regen_off}",
    )

    # cj=3 → both Jacoby and Beavers must round-trip
    both_xgid = f"{base_pos}:0:0:-1:00:0:0:3:0:10"
    out_both, dt_both = analyzer.analyze_position(both_xgid)
    d_both = GNUBGParser.parse_analysis(out_both, both_xgid, dt_both)
    check("Jacoby flag parsed from cj=3", d_both.jacoby is True)
    check("Beavers flag parsed from cj=3", d_both.beavers_allowed is True)
    regen_both = xgid_for(d_both)
    field7_both = int(regen_both.split(":")[7])
    check(
        "Regenerated XGID keeps Jacoby + Beavers (field 7 == 3)",
        field7_both == 3,
        f"field7={field7_both} in {regen_both}",
    )

    # cj=1 → Jacoby only
    jonly_xgid = f"{base_pos}:0:0:-1:00:0:0:1:0:10"
    out_j, dt_j = analyzer.analyze_position(jonly_xgid)
    d_j = GNUBGParser.parse_analysis(out_j, jonly_xgid, dt_j)
    check("Jacoby-only: jacoby=True, beavers_allowed=False",
          d_j.jacoby is True and d_j.beavers_allowed is False)
    regen_j = xgid_for(d_j)
    check(
        "Regenerated XGID with cj=1 round-trips as field 7 == 1",
        int(regen_j.split(":")[7]) == 1,
        f"got {regen_j.split(':')[7]} in {regen_j}",
    )


def test_setting_off_and_no_user_player() -> None:
    section("Setting OFF / no user_player fall through to 5-option card")

    decisions = XGBinaryParser.parse_file(str(TAKE_BLUNDER_FILE))
    d = first_take_blunder(decisions)

    card_off = gen_card(d, split=False, user_player=None)
    capture(
        "Existing 5-option card (setting OFF)",
        "Same UjOOc8fXTnA take blunder rendered with split_cube_decisions=OFF. "
        "Use as a baseline to compare against the take card above.",
        xgid_for(d),
        card_off["front"],
    )
    check(
        "Setting OFF -> 5-option card",
        len(mcq_options(card_off["front"])) == 5,
        f"opts={mcq_options(card_off['front'])}",
    )

    card_pure = gen_card(d, split=True, user_player=None)
    check(
        "Setting ON + user_player=None -> 5-option card",
        len(mcq_options(card_pure["front"])) == 5,
        f"opts={mcq_options(card_pure['front'])}",
    )


def test_receiver_x_case() -> None:
    section("Receiver=X case (on_roll=O fixture)")

    if not ON_ROLL_O_FILE.exists():
        check("Receiver=X fixture exists", False, f"missing: {ON_ROLL_O_FILE}")
        return

    decisions = XGBinaryParser.parse_file(str(ON_ROLL_O_FILE))
    d = first_take_blunder(decisions, min_err=0.3)
    # on_roll=O -> doubler=O, responder=X. user_player=Player.X simulates the
    # filter loop selecting the responder.
    assert d.on_roll == Player.O
    card = gen_card(d, split=True, user_player=Player.X)
    capture(
        "Take card with receiver=Player.X",
        "Different fixture file where the doubler is on roll as Player.O and the "
        "receiver is Player.X. The take card should still flip the position so "
        "the receiver ends up at the bottom — the codepath is symmetric.",
        xgid_for(d),
        card["front"],
    )
    opts = mcq_options(card["front"])
    check("MCQ = {Take, Pass}", opts == ["Take", "Pass"], f"got {opts}")
    cube = cube_offered_pos(card["front"])
    check("Offered cube drawn for receiver=X case", cube is not None)


def test_position_flip_helper() -> None:
    section("Position-flip helper")

    decisions = XGBinaryParser.parse_file(str(TAKE_BLUNDER_FILE))
    d = first_take_blunder(decisions)
    flipped = CardGenerator._flip_position_for_pov(d.position)

    points_match = all(
        flipped.points[i] == -d.position.points[25 - i] for i in range(1, 25)
    )
    bars_match = (
        flipped.points[0] == -d.position.points[25]
        and flipped.points[25] == -d.position.points[0]
    )
    bears_swapped = (
        flipped.x_off == d.position.o_off and flipped.o_off == d.position.x_off
    )
    check("Flipped points are reversed-and-negated", points_match)
    check("Flipped bars are swapped-and-negated", bars_match)
    check("Bear-off counts swapped", bears_swapped)

    # Flipping twice is a no-op.
    re_flipped = CardGenerator._flip_position_for_pov(flipped)
    check(
        "Flip is its own inverse",
        re_flipped.points == d.position.points
        and re_flipped.x_off == d.position.x_off
        and re_flipped.o_off == d.position.o_off,
    )


def test_serialization_round_trip() -> None:
    section("Decision serialize round-trip")

    decisions = XGBinaryParser.parse_file(str(TAKE_BLUNDER_FILE))
    d = first_take_blunder(decisions)
    d.user_player = Player.O
    d.beaverable = True

    restored = decision_from_json(decision_to_json(d))
    check("user_player round-trips", restored.user_player == Player.O)
    check("beaverable=True round-trips", restored.beaverable is True)

    d.user_player = None
    d.beaverable = False
    restored2 = decision_from_json(decision_to_json(d))
    check("user_player=None round-trips", restored2.user_player is None)
    check("beaverable=False round-trips", restored2.beaverable is False)


def test_card_back_full_analysis() -> None:
    section("Card back keeps full 5-option analysis")

    decisions = XGBinaryParser.parse_file(str(TAKE_BLUNDER_FILE))
    d = first_take_blunder(decisions)
    card = gen_card(d, split=True, user_player=Player.O)

    back = card["back"].lower()
    # Back analysis pulls xg_notation; the three from-XG cube notations always
    # appear (Too good options have from_xg_analysis=False so are filtered).
    cube_terms = ["no double", "double/take", "double/pass"]
    found = sum(back.count(term) for term in cube_terms)
    check(
        "Back HTML mentions all 3 XG cube notations",
        found >= 3,
        f"total occurrences={found}",
    )


def test_already_doubled_cube_value() -> None:
    """A redouble being offered: pre-redouble the cube is already at value > 1
    and owned by the player who's about to redouble. The take card should
    display the *new* (doubled) value as the offered cube. Tested in an
    unlimited game so an 8-cube is legal (a 3-point match would cap at 4)."""
    import dataclasses

    section("Already-doubled cube doubles its value on the take card")

    decisions = XGBinaryParser.parse_file(str(TAKE_BLUNDER_FILE))
    base = first_take_blunder(decisions)
    # Switch to an unlimited game with the cube at 4 already and owned by the
    # doubler. Only the cube owner can offer a (re)double, so for a redouble-
    # being-offered scenario the cube must belong to the on-roll player —
    # which is `decision.on_roll` (here Player.X). Using dataclasses.replace
    # so the GameRules invariant is re-validated post-mutation.
    d = dataclasses.replace(
        base,
        cube_value=4,
        cube_owner=CubeState.X_OWNS,  # matches on_roll = Player.X = doubler
        match_length=0,
        crawford=False,
        beavers_allowed=False,
        jacoby=False,
        user_player=Player.O,
    )
    card = gen_card(d, split=True, user_player=Player.O)
    capture(
        "Take card with already-doubled cube (unlimited, cube=4 -> offered as 8)",
        "Mutated (via dataclasses.replace) to: unlimited match, cube=4 owned by "
        "the doubler. The cube graphic on the take card should show '8' (doubled "
        "value), positioned inside the playing area on the receiver's side.",
        xgid_for(d),
        card["front"],
    )
    cube = cube_offered_pos(card["front"])
    check(
        "Offered cube shows 4 * 2 = 8",
        cube is not None and cube[2] == 8,
        f"cube={cube}",
    )


def test_doubler_card_with_8_cube() -> None:
    """Doubler card variant where the cube is already at 8 — i.e., the
    on-roll player owns the cube and is considering whether to redouble it
    to 16. Tested in an unlimited game (an 8-cube would be near the cap in
    most matches). Rendered from the existing doubler-POV convention (no
    position flip) so the doubler sits at the bottom of the board."""
    import dataclasses

    section("Doubler card with cube at 8 (unlimited)")

    decisions = XGBinaryParser.parse_file(str(TAKE_BLUNDER_FILE))
    base = first_take_blunder(decisions)
    # Cube=8 owned by the on-roll player (the doubler). user_player matches
    # decision.on_roll so the variant builder produces a doubler card.
    d = dataclasses.replace(
        base,
        cube_value=8,
        cube_owner=CubeState.X_OWNS,  # matches on_roll = Player.X = doubler
        match_length=0,
        crawford=False,
        beavers_allowed=False,
        jacoby=False,
        user_player=base.on_roll,  # Player.X — owner-of-cube, considering redouble
    )
    card = gen_card(d, split=True, user_player=d.user_player)
    capture(
        "Doubler card with cube at 8 (unlimited, considering redouble to 16)",
        "Cube already at 8 and owned by the doubler. MCQ should be {Roll, Double}, "
        "no offered-cube graphic (the cube isn't being offered yet — the doubler "
        "is deciding whether to redouble it to 16). Standard doubler-POV layout: "
        "doubler's pip count and cube on the BOTTOM of the board.",
        xgid_for(d),
        card["front"],
    )

    opts = mcq_options(card["front"])
    check("MCQ = {Roll, Double}", opts == ["Roll", "Double"], f"got {opts}")
    check(
        "Doubler card with 8-cube has NO offered-cube graphic",
        cube_offered_pos(card["front"]) is None,
    )

    # Verify XGID encodes a legal redouble-from-8 scenario.
    xgid = xgid_for(d)
    parts = xgid.replace("XGID=", "").split(":")
    check("XGID cube field encodes value 8 (2^3)", parts[1] == "3", f"field 1 = {parts[1]}")
    # cube_position must match turn — the on-roll player must own the cube
    # to be able to (re)double.
    check(
        "XGID cube position matches the on-roll player",
        parts[2] == parts[3],
        f"cube_position={parts[2]}, turn={parts[3]} (must match)",
    )


def test_preview_matches_export() -> None:
    """The deck-tree preview should produce the same SVG positions as the
    exported card front."""
    section("Preview render matches export render")

    decisions = XGBinaryParser.parse_file(str(TAKE_BLUNDER_FILE))
    d = first_take_blunder(decisions)
    d.user_player = Player.O

    # Export path
    settings = get_settings()
    settings.split_cube_decisions = True
    settings.board_orientation = "counter-clockwise"
    with tempfile.TemporaryDirectory() as td:
        gen = CardGenerator(output_dir=Path(td), show_options=True, interactive_moves=False)
        export_card = gen.generate_card(d)
    export_svg = re.search(r"<svg[\s\S]*?</svg>", export_card["front"]).group(0)

    # Preview path: replicate main_window.show_decision's prep logic and call
    # the same renderer the GUI uses.
    from ankigammon.renderer.svg_board_renderer import SVGBoardRenderer
    from ankigammon.renderer.color_schemes import get_scheme

    scheme = get_scheme(settings.color_scheme)
    if settings.swap_checker_colors:
        scheme = scheme.with_swapped_checkers()
    renderer = SVGBoardRenderer(
        color_scheme=scheme, orientation=settings.board_orientation
    )

    position = d.position
    on_roll = d.on_roll
    cube_value = d.cube_value
    cube_owner = d.cube_owner
    score_x = d.score_x
    score_o = d.score_o
    cube_offered = False
    doubler = d.on_roll
    responder = Player.X if doubler == Player.O else Player.O
    if d.user_player == responder:
        position = CardGenerator._flip_position_for_pov(position)
        score_x, score_o = score_o, score_x
        on_roll = Player.O if on_roll == Player.X else Player.X
        if cube_owner == CubeState.X_OWNS:
            cube_owner = CubeState.O_OWNS
        elif cube_owner == CubeState.O_OWNS:
            cube_owner = CubeState.X_OWNS
        cube_value = d.cube_value * 2
        cube_offered = True

    preview_svg = renderer.render_svg(
        position,
        dice=d.dice,
        on_roll=on_roll,
        cube_value=cube_value,
        cube_owner=cube_owner,
        score_x=score_x,
        score_o=score_o,
        match_length=d.match_length,
        score_format=settings.score_format,
        cube_offered=cube_offered,
    )

    # Compare key positional elements (full SVG can differ in whitespace/IDs).
    def positions_in(svg: str) -> tuple:
        return (
            sorted(pip_positions(svg)),
            cube_offered_pos(svg),
        )

    check("Preview SVG pip positions match export", positions_in(preview_svg)[0] == positions_in(export_svg)[0])
    check("Preview SVG cube position matches export", positions_in(preview_svg)[1] == positions_in(export_svg)[1])


def test_pytest_still_passes() -> None:
    section("pytest")
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--no-header"],
        capture_output=True,
        text=True,
        cwd=str(REPO),
    )
    last = next((l for l in reversed(r.stdout.splitlines()) if l.strip()), "")
    check("Test suite passes", r.returncode == 0, last)


# ---------------------------------------------------------------------------
# Main

def main() -> int:
    test_beaver_detection()
    test_take_blunder_card()
    test_doubler_card()
    test_beaver_mcq()
    test_no_beaver_in_match_play()
    test_beavers_allowed_flag_respected()
    test_setting_off_and_no_user_player()
    test_receiver_x_case()
    test_position_flip_helper()
    test_serialization_round_trip()
    test_card_back_full_analysis()
    test_already_doubled_cube_value()
    test_doubler_card_with_8_cube()
    test_preview_matches_export()
    test_pytest_still_passes()

    write_artifact_viewer()

    total = len(RESULTS)
    failed = [(n, i) for n, p, i in RESULTS if not p]
    print(f"\n{'-' * 60}")
    print(f"Total: {total}, Passed: {total - len(failed)}, Failed: {len(failed)}")
    print(f"Artifact viewer: {ARTIFACT_PATH}  ({len(ARTIFACTS)} cards)")
    if failed:
        print("\nFailures:")
        for name, info in failed:
            print(f"  - {name}{(' — ' + info) if info else ''}")
        return 1
    print("All checks passed. Open the artifact viewer to eyeball the cards.")
    print("Manual residue: open Settings dialog + import APKG into Anki.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
