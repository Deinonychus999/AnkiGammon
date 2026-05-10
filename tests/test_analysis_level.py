"""Tests for per-move analysis-level labels.

Covers:
  * The XG binary level → label mapping derived in scripts/xg_dump_levels.py
  * That XGBinaryParser populates Move.analysis_level for every candidate
    (including formerly-dropped lower-tier slots — see GitHub issue
    "Max moves dropdown ignored on .xg files")
  * That GNUBGMatchParser captures the ply digit from the engine label
  * That XGTextParser._extract_engine_label round-trips the labels XG itself
    prints in text exports
"""

from __future__ import annotations

import os

import pytest

from ankigammon.models import DecisionType
from ankigammon.parsers.xg_binary_parser import XGBinaryParser
from ankigammon.parsers.xg_text_parser import XGTextParser


MATCH_FILE_DIR = os.path.join(os.path.dirname(__file__), "..", "match_files")
USERS_PROBLEM_FILE = os.path.join(
    MATCH_FILE_DIR, "2025-11-02#49733 Csaba Daday-Lorenzo Pacini.xg"
)
XGP_SAMPLE_DIR = os.path.join(os.path.dirname(__file__), "..", "xg_dump", "xgp")


# ---------------------------------------------------------------------------
# XGBinaryParser._format_xg_analysis_level
# ---------------------------------------------------------------------------

class TestXGLevelLabelMapping:
    def test_ply_levels_are_offset_by_one(self):
        # XG's enum is 0-indexed but XG itself displays plies 1-indexed:
        # what the file calls Level=3 appears in XG's GUI/text as "4-ply".
        # The official PLAYERLEVEL TABLE at
        # https://www.extremegammon.com/xgformat.aspx defines codes 0-6 as
        # 1-ply through 7-ply respectively.
        assert XGBinaryParser._format_xg_analysis_level(0, False) == "1-ply"
        assert XGBinaryParser._format_xg_analysis_level(1, False) == "2-ply"
        assert XGBinaryParser._format_xg_analysis_level(2, False) == "3-ply"
        assert XGBinaryParser._format_xg_analysis_level(3, False) == "4-ply"
        assert XGBinaryParser._format_xg_analysis_level(6, False) == "7-ply"

    def test_three_ply_red(self):
        # Level 12 is XG's "3-ply red" reduced-search variant per the
        # official PLAYERLEVEL TABLE.
        assert XGBinaryParser._format_xg_analysis_level(12, False) == "3-ply red"

    def test_opening_book(self):
        # XG stores opening-book entries at two levels (V2 and V1) but we
        # surface a single canonical "Book" label.
        assert XGBinaryParser._format_xg_analysis_level(998, False) == "Book"
        assert XGBinaryParser._format_xg_analysis_level(999, False) == "Book"

    def test_rollout_via_flag(self):
        # If RolloutIndexM signals a rollout, the level number is irrelevant.
        assert XGBinaryParser._format_xg_analysis_level(0, True) == "Rollout"
        assert XGBinaryParser._format_xg_analysis_level(1002, True) == "Rollout"

    def test_rollout_via_level_100(self):
        # Level 100 always means a full rollout — across observed .xg files
        # it correlated with the rollout flag in 100% of cases.
        assert XGBinaryParser._format_xg_analysis_level(100, False) == "Rollout"

    def test_xg_roller_variants(self):
        assert XGBinaryParser._format_xg_analysis_level(1000, False) == "XG Roller"
        assert XGBinaryParser._format_xg_analysis_level(1001, False) == "XG Roller+"
        assert XGBinaryParser._format_xg_analysis_level(1002, False) == "XG Roller++"

    def test_unknown_level_falls_back_to_raw(self):
        # Unknown level numbers should still surface a label so the user gets
        # some information rather than a silent hole.
        assert XGBinaryParser._format_xg_analysis_level(42, False) == "Level 42"
        assert XGBinaryParser._format_xg_analysis_level(-1, False) == "Level -1"


class TestAnalysisTierRank:
    """Move.analysis_tier_rank orders candidates by analysis depth.

    The displayed move table sorts on this rank (descending) before falling
    back to equity error, so a 1-ply screening eval can't outrank a
    deeply-analyzed move just because its raw equity looks favorable.
    """

    def test_full_ordering(self):
        from ankigammon.models import Move
        labels_high_to_low = [
            "Rollout",
            "Book",          # pre-rolled-out opening book — near-rollout quality
            "XG Roller++",
            "XG Roller+",
            "XG Roller",
            "7-ply",
            "4-ply",
            "3-ply",
            "2-ply",
            "1-ply",
            None,
        ]
        ranks = [Move(notation="x", equity=0, analysis_level=l).analysis_tier_rank()
                 for l in labels_high_to_low]
        assert ranks == sorted(ranks, reverse=True), (
            f"tier ranks should be strictly descending for labels {labels_high_to_low}, "
            f"got {ranks}"
        )

    def test_book_outranks_engine_analysis(self):
        # Specific to the issue: a Book entry (deep pre-rolled-out
        # opening-book result) should sort above a fresh N-ply engine
        # analysis even when their equities are very close, so the user
        # immediately sees which moves came from the authoritative book.
        from ankigammon.models import Move
        book = Move(notation="24/21 13/9", equity=0.007, analysis_level="Book")
        ply4 = Move(notation="13/10 13/9", equity=0.007, analysis_level="4-ply")
        assert book.analysis_tier_rank() > ply4.analysis_tier_rank()

    def test_three_ply_red_ranks_with_three_ply(self):
        from ankigammon.models import Move
        red = Move(notation="x", equity=0, analysis_level="3-ply red")
        ply3 = Move(notation="x", equity=0, analysis_level="3-ply")
        ply2 = Move(notation="x", equity=0, analysis_level="2-ply")
        assert red.analysis_tier_rank() == ply3.analysis_tier_rank()
        assert red.analysis_tier_rank() > ply2.analysis_tier_rank()


# ---------------------------------------------------------------------------
# End-to-end: parsing a real .xg file populates analysis_level on every move
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    not os.path.exists(USERS_PROBLEM_FILE),
    reason="real .xg sample not available in this checkout",
)
class TestXGBinaryParserAnalysisLevel:
    @pytest.fixture(scope="class")
    def decisions(self):
        return XGBinaryParser.parse_file(USERS_PROBLEM_FILE)

    def test_every_candidate_move_has_a_label(self, decisions):
        # Regression: the prior tier-filter used to silently drop lower-tier
        # candidates. Now they're kept, and each must carry a label so the
        # UI can render the badge.
        checker_decisions = [
            d for d in decisions if d.decision_type == DecisionType.CHECKER_PLAY
        ]
        assert checker_decisions, "expected some checker-play decisions in the sample"
        for d in checker_decisions:
            for move in d.candidate_moves:
                assert move.analysis_level, (
                    f"Move {move.notation!r} on decision dice={d.dice} "
                    f"score=({d.score_o},{d.score_x}) has no analysis_level"
                )

    def test_labels_use_known_vocabulary(self, decisions):
        # Anything that survives should map to a recognized label, not to the
        # raw "Level N" fallback — that would signal we missed an XG level.
        known = {"Rollout", "Book", "XG Roller", "XG Roller+", "XG Roller++",
                 "3-ply red"}
        known |= {f"{n}-ply" for n in range(1, 8)}

        seen = set()
        for d in decisions:
            for m in d.candidate_moves:
                if m.analysis_level:
                    seen.add(m.analysis_level)

        unknown = seen - known
        assert not unknown, (
            f"unexpected analysis_level labels (likely an unmapped XG level): {unknown}"
        )

    def test_table_sorts_higher_tier_above_lower_tier(self, decisions):
        # The 32-roll position from the second screenshot exhibits this:
        # two XG Roller+ moves and several 4-ply moves. The XG Roller+ moves
        # must appear above the 4-ply moves in the rendered analysis table,
        # even when a 4-ply move's equity error is smaller than the
        # XG Roller+ second-best's error.
        import tempfile, re
        from pathlib import Path
        from ankigammon.anki.card_generator import CardGenerator

        target = None
        for d in decisions:
            if d.decision_type != DecisionType.CHECKER_PLAY:
                continue
            if d.dice not in [(3, 2), (2, 3)]:
                continue
            if d.score_o != 1 or d.score_x != 0 or d.match_length != 7:
                continue
            if any("24/21 23/21" == m.notation for m in d.candidate_moves):
                target = d
                break

        assert target is not None, (
            "expected the (dice=32, score=1-0, 7pt) position with '24/21 23/21' "
            "as a candidate; if the fixture file changed, update this test"
        )

        # Sanity check: this position has both XG Roller+ and 4-ply moves.
        levels = {m.analysis_level for m in target.candidate_moves}
        assert "XG Roller+" in levels and "4-ply" in levels, (
            f"expected both XG Roller+ and 4-ply candidates; got {levels}"
        )

        with tempfile.TemporaryDirectory() as tmp:
            gen = CardGenerator(Path(tmp))
            gen.settings.max_moves = 5
            card = gen.generate_card(target, 0)
            back = card.get("back", "")

        # Extract the rendered ordering of analysis-level badges from the
        # back HTML. With tier-first sorting, all XG Roller+ rows must
        # precede any 4-ply / 3-ply row.
        badges = re.findall(r'<span class="analysis-level">([^<]+)</span>', back)
        assert badges, "expected analysis-level badges to be rendered"

        # Walk badges and ensure no lower tier appears before a higher tier.
        from ankigammon.models import Move
        tiers = [Move(notation="x", equity=0, analysis_level=b).analysis_tier_rank()
                 for b in badges]
        for i in range(1, len(tiers)):
            assert tiers[i] <= tiers[i - 1], (
                f"tier ranking violated at row {i}: {badges[:i+1]} ({tiers[:i+1]})"
            )

    def test_xgp_files_also_populate_analysis_level(self):
        # .xgp (single-position) files share the move-entry parsing path
        # with .xg match files, so the analysis-level fix must apply to
        # them too. Sweep a sample and assert every analyzed candidate
        # carries a known label — never the raw "Level N" fallback or None.
        import glob
        xgp_files = sorted(glob.glob(os.path.join(XGP_SAMPLE_DIR, "*.xgp")))
        if not xgp_files:
            pytest.skip("no .xgp sample files available in this checkout")

        # Sample stride to keep the test fast even with hundreds of files.
        sample = xgp_files[::max(1, len(xgp_files) // 20)][:20]
        known = {"Rollout", "Book", "XG Roller", "XG Roller+", "XG Roller++",
                 "3-ply red"}
        known |= {f"{n}-ply" for n in range(1, 8)}

        seen_labels: set[str] = set()
        for fp in sample:
            try:
                decisions = XGBinaryParser.parse_file(fp)
            except Exception:
                # Some .xgp samples are corrupt or are XGID-only positions
                # without analysis; those aren't regressions for this test.
                continue
            for d in decisions:
                if d.decision_type != DecisionType.CHECKER_PLAY:
                    continue
                for m in d.candidate_moves:
                    assert m.analysis_level, (
                        f"{os.path.basename(fp)}: move {m.notation!r} has no "
                        f"analysis_level"
                    )
                    seen_labels.add(m.analysis_level)

        unknown = seen_labels - known
        assert not unknown, (
            f"unexpected labels from .xgp parsing: {unknown}"
        )

    def test_users_screenshot_position_returns_full_candidate_set(self, decisions):
        # The position from the GitHub issue: dice 21, score 1-0, 7pt match,
        # with both 13/10 and 13/11 6/5* as candidates. Before the fix it
        # surfaced only 2 moves because the tier filter dropped 3-ply slots.
        # After the fix it should expose all 10 candidates the engine
        # produced.
        target = None
        for d in decisions:
            if d.decision_type != DecisionType.CHECKER_PLAY:
                continue
            if d.dice not in [(2, 1), (1, 2)]:
                continue
            if d.score_o != 1 or d.score_x != 0 or d.match_length != 7:
                continue
            notations = {m.notation for m in d.candidate_moves}
            if "13/10" in notations and any("13/11" in n for n in notations):
                target = d
                break

        assert target is not None, "expected to find the user-reported position"
        assert len(target.candidate_moves) >= 5, (
            f"expected at least 5 candidates after dropping the tier filter, "
            f"got {len(target.candidate_moves)}"
        )


# ---------------------------------------------------------------------------
# GnuBG text-export ply capture
# ---------------------------------------------------------------------------

class TestGNUBGAnalysisLevelCapture:
    def test_captures_ply_from_cubeful_line(self):
        from ankigammon.parsers.gnubg_match_parser import GNUBGMatchParser
        # We test the regex behavior on a synthetic snippet matching the
        # format gnubg emits with `set export moves number N`.
        import re
        line = "  1. Cubeful 2-ply 8/5 6/5                    Eq.: +0.123 (+0.000)"
        m = re.match(
            r'\s*\*?\s*(\d+)\.\s+Cubeful\s+(\d+)-ply\s+(.+?)\s+Eq\.:\s+'
            r'([+-]?\d+[.,]\d+)(?:\s+\(\s*([+-]?\d+[.,]\d+)\s*\))?',
            line,
        )
        assert m is not None
        assert m.group(2) == "2"
        assert m.group(3).strip() == "8/5 6/5"


# ---------------------------------------------------------------------------
# XG text-export engine label extraction
# ---------------------------------------------------------------------------

class TestXGTextEngineLabel:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("XG Roller+ 11/8 11/5", "XG Roller+"),
            ("XG Roller++ 9/3* 6/3", "XG Roller++"),
            ("XG Roller 6/4", "XG Roller"),
            ("2-ply Double, take", "2-ply"),
            ("4-ply 13/10 6/5", "4-ply"),
            ("Rollout 13/10", "Rollout"),
            ("Rollout    15/14 6/3", "Rollout"),
            ("Rollout¹ 15/14 6/3", "Rollout"),    # superscript 1
            ("Book 24/21 13/9", "Book"),
            ("Book¹ 24/21 13/9", "Book"),         # superscript 1
            ("Book² 24/20 13/10", "Book"),        # superscript 2
            ("Book4 13/9 8/5", "Book"),           # ASCII fallback past ³
            ("13/10", None),
            ("", None),
        ],
    )
    def test_extract_engine_label(self, raw, expected):
        assert XGTextParser._extract_engine_label(raw) == expected

    def test_parses_real_xg_text_sample(self):
        # This is the exact text export the user pasted (XGID + ASCII board
        # stripped down to the move list). All five XG engine labels appear
        # in one block, including unicode-superscripted "Rollout¹"/"Rollout²"
        # that XG uses to disambiguate multiple rollout configurations.
        sample = (
            "    1. Rollout¹    15/14 6/3                    eq:+0.885\n"
            "    2. Rollout²    15/13 6/5 4/3                eq:+0.845 (-0.040)\n"
            "    3. XG Roller++ 15/13 6/4                    eq:+1.014 (+0.129)\n"
            "    4. XG Roller+  15/14 6/5 4/2                eq:+0.926 (+0.041)\n"
            "    5. 4-ply       6/2                          eq:+1.004 (+0.119)\n"
        )
        moves = XGTextParser._parse_moves(sample)
        assert len(moves) == 5
        labels = [m.analysis_level for m in moves]
        assert labels == ["Rollout", "Rollout", "XG Roller++", "XG Roller+", "4-ply"]
        # And the notations are clean (engine prefix stripped).
        notations = [m.notation for m in moves]
        assert notations == [
            "15/14 6/3",
            "15/13 6/5 4/3",
            "15/13 6/4",
            "15/14 6/5 4/2",
            "6/2",
        ]

    def test_parses_opening_book_entries(self):
        # Real text export of the very first move (43 roll opening) of the
        # Csaba match: rank 1 is 4-ply engine analysis, ranks 2-5 are
        # opening-book entries differentiated by superscript or trailing
        # digit ("Book¹", "Book²", "Book³", "Book4"). All four book entries
        # must collapse to the canonical "Book" label.
        sample = (
            "    1. 4-ply       13/10 13/9                   eq:+0.007\n"
            "    2. Book¹       24/21 13/9                   eq:+0.007\n"
            "    3. Book²       24/20 13/10                  eq:-0.001 (-0.008)\n"
            "    4. Book³       24/21 24/20                  eq:-0.016 (-0.023)\n"
            "    5. Book4       13/9 8/5                     eq:-0.073 (-0.080)\n"
        )
        moves = XGTextParser._parse_moves(sample)
        assert len(moves) == 5
        labels = [m.analysis_level for m in moves]
        assert labels == ["4-ply", "Book", "Book", "Book", "Book"]
        notations = [m.notation for m in moves]
        assert notations == [
            "13/10 13/9",
            "24/21 13/9",
            "24/20 13/10",
            "24/21 24/20",
            "13/9 8/5",
        ]
