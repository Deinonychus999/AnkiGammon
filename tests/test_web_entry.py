"""ankigammon.web, the API the browser version (ankigammon.com/app) calls.

The browser runs this module under Pyodide; here it runs natively, which is
the same code path. The website's Pyodide parity check compares the two.
"""

import copy
import json
from pathlib import Path

import pytest

from ankigammon import settings as settings_module
from ankigammon import web
from ankigammon.import_filter import filter_decisions
from ankigammon.parsers.xg_binary_parser import XGBinaryParser

from conftest import read_apkg_notes

DATA = Path(__file__).parent / "data"
SAMPLE = str(DATA / "sample_match.xg")

ANALYZED = """XGID=-b----E-C--AeD---bAdb---A-:0:0:1:52:0:0:3:0:10

X:Player 1   O:Player 2
Score is X:0 O:0. Unlimited Game, Jacoby Beaver
Pip count  X: 159  O: 163 X-O: 0-0
Cube: 1
X to play 52

    1. XG Roller++ 18/11                        eq:-0.0026
      Player:   50.64% (G:11.55% B:0.54%)
      Opponent: 49.36% (G:13.95% B:0.42%)

    2. XG Roller++ 24/22 18/13                  eq:-0.1141 (-0.1114)
      Player:   48.27% (G:10.81% B:0.55%)
      Opponent: 51.73% (G:15.83% B:0.49%)

Keep the builder

eXtreme Gammon Version: 2.10
"""

UNANALYZED = """XGID=-b----E-C--AeD---bAdb---A-:0:0:1:00:0:0:3:0:10

X:Player 1   O:Player 2
Score is X:0 O:0. Unlimited Game, Jacoby Beaver
Pip count  X: 159  O: 163 X-O: 0-0
Cube: 1
X on roll, cube action

eXtreme Gammon Version: 2.19.211.pre-release
"""


@pytest.fixture
def session(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module, "_settings", None)
    web.start(str(tmp_path / "work"))
    return tmp_path / "work"


def test_session_settings_never_touch_the_home_config(session):
    web.configure(json.dumps({"max_moves": 3, "color_scheme": "ocean"}))
    active = settings_module.get_settings()
    assert active.config_path == session / "config.json"
    assert json.loads(active.config_path.read_text())["max_moves"] == 3


def test_functions_refuse_to_run_before_start(monkeypatch):
    monkeypatch.setattr(web, "_work_dir", None)
    with pytest.raises(RuntimeError, match="start"):
        web.load_file(SAMPLE)


def test_match_file_is_filtered_like_the_desktop_import(session):
    result = json.loads(web.load_file(SAMPLE, 0.08, 0.08, True, False))
    parsed = XGBinaryParser.parse_file(SAMPLE)
    expected = filter_decisions(copy.deepcopy(parsed), 0.08, 0.08, True, False, 5)

    assert result["total"] == len(parsed)
    assert [p["xgid"] for p in result["positions"]] == [d.xgid for d in expected]
    assert all(p["on_roll"] == "X" for p in result["positions"] if p["type"] == "checker")
    assert all(p["error"] >= 0.08 for p in result["positions"] if p["type"] == "checker")


def test_player_names_come_back_by_side(session):
    names = json.loads(web.read_player_names(SAMPLE))
    player1, player2 = XGBinaryParser.extract_player_names(SAMPLE)
    assert names == {"o": player1, "x": player2}


@pytest.mark.parametrize("name", ["match.mat", "match.sgf", "positions.txt", "noextension"])
def test_formats_that_need_an_engine_are_refused_with_a_pointer(session, tmp_path, name):
    path = tmp_path / name
    path.write_bytes(b"irrelevant")
    with pytest.raises(ValueError, match="desktop app"):
        web.load_file(str(path))


def test_unreadable_xg_file_gets_a_plain_message(session, tmp_path):
    path = tmp_path / "damaged match.xg"
    path.write_bytes(bytes(range(256)) * 16)
    with pytest.raises(ValueError) as excinfo:
        web.load_file(str(path))
    message = str(excinfo.value)
    assert message.startswith("damaged match.xg could not be read as an eXtreme Gammon file")
    assert str(tmp_path) not in message


def test_pasted_xg_text_keeps_analyzed_positions_and_counts_the_rest(session):
    result = json.loads(web.load_text(ANALYZED + "\n" + UNANALYZED))
    assert result["total"] == 2
    assert len(result["positions"]) == 1
    assert result["positions"][0]["played"] is None
    assert result["positions"][0]["has_note"] is True


def test_paste_without_analysis_explains_what_is_needed(session):
    with pytest.raises(ValueError, match="desktop app"):
        web.load_text(UNANALYZED)


def test_unknown_card_setting_is_rejected(session):
    with pytest.raises(ValueError, match="Unknown card setting"):
        web.configure(json.dumps({"colour_scheme": "ocean"}))


def test_color_scheme_reaches_the_rendered_board(session):
    """The prototype wrote a 'color_scheme' key nobody reads (the stored key is
    'default_color_scheme'), so the picker silently did nothing."""
    from ankigammon.renderer.color_schemes import get_scheme

    web.load_file(SAMPLE)
    web.configure(json.dumps({"color_scheme": "ocean"}))
    ocean = json.loads(web.preview(0))["front"]
    web.configure(json.dumps({"color_scheme": "classic"}))
    classic = json.loads(web.preview(0))["front"]

    assert get_scheme("ocean").board_dark in ocean
    assert get_scheme("ocean").board_dark not in classic


def test_preview_is_the_card_an_export_stores(session):
    import random

    web.load_file(SAMPLE)
    random.seed(7)
    card = json.loads(web.preview(2))
    random.seed(7)
    path = web.export_apkg("[2]", "Web entry test")

    [fields] = read_apkg_notes(path)
    assert card["css"]
    assert fields[1] == card["front"].replace("preview_2", "card_0")
    assert fields[2] == card["back"].replace("preview_2", "card_0")


def test_export_writes_the_chosen_positions(session):
    loaded = json.loads(web.load_file(SAMPLE))
    chosen = [0, 3, len(loaded["positions"]) - 1]
    path = web.export_apkg(json.dumps(chosen), "Web entry test", use_subdecks=True)

    xgids = sorted(fields[0] for fields in read_apkg_notes(path))
    assert xgids == sorted(loaded["positions"][i]["xgid"] for i in chosen)
    assert Path(path).parent == session


def test_empty_selection_exports_everything(session):
    loaded = json.loads(web.load_file(SAMPLE))
    notes = read_apkg_notes(web.export_apkg("[]", "Web entry test"))
    assert len(notes) == len(loaded["positions"])
