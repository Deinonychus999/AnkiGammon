"""Decisions from HedgeHog's position results, and HedgeHog in Settings."""

import json
from pathlib import Path
from unittest import mock

import pytest

from ankigammon.models import DecisionType, Player
from ankigammon.parsers.hedgehog_parser import parse_position_result, xgid_to_ogid
from ankigammon.settings import Settings
from ankigammon.utils.analyzer_base import create_analyzer

DATA = Path(__file__).parent / "data" / "hedgehog"


def _result(name):
    return json.dumps(json.loads((DATA / f"{name}.json").read_text())["result"])


CHECKER_XGID = "XGID=--BCBBC--b--bB---bbcb-b-A-:0:0:-1:16:1:2:1:3:8"
CUBE_XGID = "XGID=-BBB--CC----eA--bc-e-B----:0:0:1:00:0:0:0:3:8"
MONEY_XGID = "XGID=-BBB--CC----eA--bc-e-B----:0:0:1:00:0:0:0:0:8"


def test_the_ogid_sent_is_the_one_hedgehog_reads():
    ogid, decision_type, jacoby = xgid_to_ogid(CHECKER_XGID)
    assert ogid.rsplit(":", 1)[0] == "99cchhiijjjkkmm:223334455666ddo:N0N:16:B:R:2:1:3C"
    assert decision_type == DecisionType.CHECKER_PLAY
    assert not jacoby
    assert xgid_to_ogid(CUBE_XGID)[0].rsplit(":", 1)[0] == "cccccgghhhjjjjj:112233666777dll:N0N::W:C:0:0:3"
    assert xgid_to_ogid("XGID=-BBB--CC----eA--bc-e-B----:0:0:1:00:0:0:1:0:8")[2] is True


def test_checker_result():
    decision = parse_position_result(_result("position_checker"), CHECKER_XGID, DecisionType.CHECKER_PLAY, "3-ply")
    assert decision.on_roll == Player.X
    assert decision.crawford
    assert len(decision.candidate_moves) == 25
    best, second = decision.candidate_moves[:2]
    assert (best.notation, best.equity, best.rank) == ("13/7 6/5", pytest.approx(-0.1159), 1)
    assert second.xg_error == pytest.approx(-0.018)
    assert best.player_win_pct == pytest.approx(58.82)
    assert best.player_gammon_pct == pytest.approx(7.28)
    assert best.analysis_level == "3-ply"


def test_match_cube_result_uses_normalized_equity():
    decision = parse_position_result(_result("position_cube"), CUBE_XGID, DecisionType.CUBE_ACTION, "3-ply")
    moves = {m.notation: m for m in decision.candidate_moves}
    assert moves["No Double/Take"].equity == pytest.approx(0.3266)
    assert moves["Double/Take"].equity == pytest.approx(0.0913)
    assert moves["Double/Pass"].equity == pytest.approx(1.0)
    assert moves["No Double/Take"].rank == 1
    assert not moves["Too good/Pass"].from_xg_analysis
    assert decision.player_win_pct == pytest.approx(58.12)
    assert decision.cubeless_equity is not None and decision.double_cubeless_equity is not None


def test_money_cube_result_uses_money_equity():
    decision = parse_position_result(_result("position_money"), MONEY_XGID, DecisionType.CUBE_ACTION, "3-ply")
    moves = {m.notation: m for m in decision.candidate_moves}
    assert moves["No Double/Take"].equity == pytest.approx(0.3012)
    assert moves["Double/Pass"].equity == pytest.approx(1.0)
    assert decision.double_cubeless_equity == pytest.approx(decision.cubeless_equity * 2)


def test_a_dead_cube_is_reported():
    with pytest.raises(ValueError, match="dead"):
        parse_position_result(json.dumps({"decision_type": "cube", "cube_decision": None, "cube_disabled": True}),
                              CUBE_XGID, DecisionType.CUBE_ACTION, "3-ply")


def test_a_failed_position_is_reported():
    with pytest.raises(ValueError, match="Try a lower preset"):
        parse_position_result(json.dumps({"success": False, "error": {"message": "Try a lower preset."}}),
                              CUBE_XGID, DecisionType.CUBE_ACTION, "3-ply")


@pytest.fixture
def settings(tmp_path):
    return Settings(config_path=tmp_path / "config.json")


def test_hedgehog_settings(settings):
    settings.analyzer_type = "hedgehog"
    assert not settings.is_engine_available()
    settings.set_hedgehog_account("u1", "frank")
    assert settings.is_engine_available()
    settings.hedgehog_preset = "3ply"
    assert settings.engine_description() == "HedgeHog (4-ply)"
    settings.set("hedgehog_preset_labels", {"3ply": "Deep"})
    assert settings.engine_label() == "Deep"
    assert "token" not in settings.config_path.read_text()
    with pytest.raises(ValueError):
        settings.analyzer_type = "bogus"


def test_every_engine_has_a_name_and_label(settings):
    assert settings.engine_description() == "GnuBG (3-ply)"
    settings.analyzer_type = "xg"
    assert settings.engine_description() == "eXtreme Gammon (World Class)"


def test_factory_builds_the_hedgehog_analyzer(settings):
    settings.analyzer_type = "hedgehog"
    settings.hedgehog_preset = "1ply"
    analyzer = create_analyzer(settings)
    assert (type(analyzer).__name__, analyzer.preset, analyzer.preset_label) == ("HedgehogAnalyzer", "1ply", "2-ply")


def test_factory_refuses_unknown_engines():
    with pytest.raises(ValueError, match="Unknown analysis engine"):
        create_analyzer(mock.Mock(analyzer_type="bogus"))


@pytest.fixture
def dialog(qapp, settings):
    with mock.patch("ankigammon.utils.xg_auto.registry.read_custom_analysis_levels", return_value=[]):
        from ankigammon.gui.dialogs.settings_dialog import SettingsDialog
        dlg = SettingsDialog(settings)
    yield dlg
    dlg.reject()


def _select(dialog, engine):
    dialog.cmb_analyzer_type.setCurrentIndex(dialog.cmb_analyzer_type.findData(engine))


def test_settings_dialog_shows_the_hedgehog_rows_only_for_hedgehog(dialog):
    _select(dialog, "hedgehog")
    assert dialog.btn_hedgehog_connect.isVisibleTo(dialog)
    assert not dialog.txt_gnubg_path.isVisibleTo(dialog)
    assert dialog.lbl_hedgehog_status_text.text() == "Not connected"
    _select(dialog, "gnubg")
    assert not dialog.btn_hedgehog_connect.isVisibleTo(dialog)
    assert dialog.txt_gnubg_path.isVisibleTo(dialog)


def test_settings_dialog_saves_the_hedgehog_preset(dialog, settings):
    _select(dialog, "hedgehog")
    dialog.cmb_hedgehog_preset.setCurrentIndex(dialog.cmb_hedgehog_preset.findData("1ply"))
    dialog.accept()
    assert (settings.analyzer_type, settings.hedgehog_preset) == ("hedgehog", "1ply")


def test_account_answer_limits_the_presets_on_offer(dialog, settings):
    settings.set_hedgehog_account("u1", "frank")
    dialog._on_hedgehog_me({
        "username": "frank", "presets": {"position": ["1ply", "2ply"]},
        "preset_labels": {"1ply": "2-ply", "2ply": "3-ply"},
        "allowance": {"position": {"used": 2, "limit": 5, "credits": 0}},
    })
    assert [dialog.cmb_hedgehog_preset.itemData(i) for i in range(dialog.cmb_hedgehog_preset.count())] == ["1ply", "2ply"]
    assert "3 free position analyses left today" in dialog.lbl_hedgehog_status_text.text()
