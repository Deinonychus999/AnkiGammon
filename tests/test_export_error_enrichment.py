"""Regression test for export error enrichment.

When card generation fails mid-export, the user previously saw a bare
"Invalid point number: -3" with no source context. The enriched RuntimeError
must include position index, XGID, dice, and decision type so bug reports
ship with everything needed to reproduce.
"""

import tempfile
from pathlib import Path

import pytest

from ankigammon.anki.apkg_exporter import ApkgExporter
from ankigammon.models import Decision, DecisionType, Player
from ankigammon.utils.xgid import parse_xgid


XGID_CHECKER = "XGID=-a----E-C---eE---c-e----B-:0:0:1:55:1:0:0:5:10"


def _make_decision(xgid: str, dice=(5, 5)) -> Decision:
    position, _ = parse_xgid(xgid)
    return Decision(
        position=position,
        xgid=xgid,
        on_roll=Player.X,
        dice=dice,
        decision_type=DecisionType.CHECKER_PLAY,
        match_length=5,
    )


class TestExportErrorEnrichment:
    def test_card_generation_failure_is_enriched_with_position_context(self, monkeypatch):
        from ankigammon.anki import card_generator as cg_mod

        def boom(self, decision, card_id=None):
            raise ValueError("Invalid point number: -3")

        monkeypatch.setattr(cg_mod.CardGenerator, "generate_card", boom)

        decisions = [_make_decision(XGID_CHECKER) for _ in range(12)]

        with tempfile.TemporaryDirectory() as tmp:
            exporter = ApkgExporter(output_dir=Path(tmp))
            with pytest.raises(RuntimeError) as exc_info:
                exporter.export(decisions=decisions, output_file="t.apkg")

        msg = str(exc_info.value)
        # Position index relative to total — answers "which card?"
        assert "1/12" in msg
        # XGID — full reproducer
        assert XGID_CHECKER in msg
        # Dice — narrows to the specific roll
        assert "(5, 5)" in msg
        # Decision type — distinguishes checker from cube failures
        assert "CHECKER_PLAY" in msg
        # Original error preserved in the enriched message
        assert "Invalid point number: -3" in msg

    def test_original_exception_is_chained(self, monkeypatch):
        """`from e` must preserve the original traceback for debugging."""
        from ankigammon.anki import card_generator as cg_mod

        original = ValueError("Invalid point number: -3")

        def boom(self, decision, card_id=None):
            raise original

        monkeypatch.setattr(cg_mod.CardGenerator, "generate_card", boom)

        with tempfile.TemporaryDirectory() as tmp:
            exporter = ApkgExporter(output_dir=Path(tmp))
            with pytest.raises(RuntimeError) as exc_info:
                exporter.export(decisions=[_make_decision(XGID_CHECKER)], output_file="t.apkg")

        assert exc_info.value.__cause__ is original

    def test_failure_at_position_10_of_12_reports_correct_index(self, monkeypatch):
        """HerJe's bug report screenshot — failure at position 10/12. The
        enriched message must surface that index, not just the first."""
        from ankigammon.anki import card_generator as cg_mod

        call_count = {"n": 0}

        def fail_on_tenth(self, decision, card_id=None):
            call_count["n"] += 1
            if call_count["n"] == 10:
                raise ValueError("Invalid point number: -3")
            return {"front": "", "back": "", "tags": [], "xgid": decision.xgid, "analysis_data": ""}

        monkeypatch.setattr(cg_mod.CardGenerator, "generate_card", fail_on_tenth)

        decisions = [_make_decision(XGID_CHECKER) for _ in range(12)]

        with tempfile.TemporaryDirectory() as tmp:
            exporter = ApkgExporter(output_dir=Path(tmp))
            with pytest.raises(RuntimeError) as exc_info:
                exporter.export(decisions=decisions, output_file="t.apkg")

        assert "10/12" in str(exc_info.value)
