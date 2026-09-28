"""Warning before a HedgeHog run would go past the free plan's daily allowance."""

from types import SimpleNamespace
from unittest import mock

import pytest

from ankigammon.models import DecisionType
from ankigammon.parsers.hedgehog_parser import decision_from_xgid, estimated_cost, plan_batches
from ankigammon.settings import Settings
from ankigammon.utils.prefetch_analyzer import estimate_hedgehog_cost

CUBE_7PT = "XGID=-BBB--CC----eA--bc-e-B----:0:0:1:00:2:1:0:7:10"


def test_cost_counts_batches_at_shallow_presets_and_positions_deeper():
    batches, _ = plan_batches([CUBE_7PT] * 30, "2ply")
    assert estimated_cost(batches, "2ply") == 3
    batches, _ = plan_batches([CUBE_7PT] * 30, "3ply")
    assert estimated_cost(batches, "3ply") == 30


@pytest.fixture
def settings(tmp_path, monkeypatch):
    s = Settings(config_path=tmp_path / "config.json")
    monkeypatch.setattr("ankigammon.anki.card_generator.get_settings", lambda: s)
    return s


def test_estimate_includes_the_score_matrix(settings, tmp_path):
    decision = decision_from_xgid(CUBE_7PT, DecisionType.CUBE_ACTION)
    assert estimate_hedgehog_cost([decision], "2ply", tmp_path) == 1
    settings.generate_score_matrix = True
    assert estimate_hedgehog_cost([decision], "2ply", tmp_path) == 1 + 5


def _dialog(settings, decisions):
    settings.analyzer_type = "hedgehog"
    settings.set_hedgehog_account("u1", None)
    return SimpleNamespace(settings=settings, all_decisions=decisions)


def _me(left):
    return {"allowance": {"position": {"used": 5 - left, "limit": 5, "credits": 0}}}


def _check(dialog, me, answer):
    from PySide6.QtWidgets import QMessageBox
    from ankigammon.gui.dialogs.export_dialog import ExportDialog
    with mock.patch("ankigammon.utils.hedgehog_client.HedgehogClient.me", return_value=me), \
            mock.patch("ankigammon.gui.dialogs.export_dialog.silent_messagebox.question",
                       return_value=getattr(QMessageBox.StandardButton, answer)) as asked:
        return ExportDialog._hedgehog_allowance_ok(dialog), asked


def test_asks_when_the_export_would_go_past_the_allowance(qapp, settings):
    settings.generate_score_matrix = True
    dialog = _dialog(settings, [decision_from_xgid(CUBE_7PT, DecisionType.CUBE_ACTION)])
    ok, asked = _check(dialog, _me(2), "No")
    assert not ok
    assert "about 6 HedgeHog position analyses" in asked.call_args.args[2]
    assert "2 left today" in asked.call_args.args[2]
    assert _check(dialog, _me(2), "Yes")[0]


def test_stays_quiet_when_it_fits_or_the_plan_is_paid(qapp, settings):
    dialog = _dialog(settings, [decision_from_xgid(CUBE_7PT, DecisionType.CUBE_ACTION)])
    ok, asked = _check(dialog, _me(3), "No")
    assert ok and not asked.called
    ok, asked = _check(dialog, {"allowance": None, "fair_use": {"guideline": 200}}, "No")
    assert ok and not asked.called


def test_other_engines_are_never_asked(qapp, settings):
    dialog = SimpleNamespace(settings=settings, all_decisions=[])
    assert _check(dialog, _me(0), "No")[0]
