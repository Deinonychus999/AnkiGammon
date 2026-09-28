"""The browser version's HedgeHog and .ogxm entry points (ankigammon.web).

The page makes HedgeHog's requests; these functions prepare them and parse
the answers, which the saved live answers in tests/data/hedgehog stand in for.
"""

import json
from pathlib import Path

import pytest

from ankigammon import settings as settings_module
from ankigammon import web

DATA = Path(__file__).parent / "data" / "hedgehog"
OGXM = DATA / "analysis.ogxm"
CHECKER = json.loads((DATA / "position_checker.json").read_text())["result"]
CUBE = json.loads((DATA / "position_cube.json").read_text())["result"]

CHECKER_OGID = "99cchhiijjjkkmm:223334455666ddo:N0N:16:B:R:2:1:3C:13"
CUBE_XGID = "XGID=-BBB--CC----eA--bc-e-B----:0:0:1:00:0:0:0:3:8"
MONEY_JACOBY_XGID = "XGID=-BBB--CC----eA--bc-e-B----:0:0:1:00:0:0:1:0:8"


@pytest.fixture
def session(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module, "_settings", None)
    web.start(str(tmp_path / "work"))
    return tmp_path


def _copy(tmp_path, name, data):
    path = tmp_path / name
    path.write_bytes(data)
    return str(path)


def test_ogxm_files_load_and_filter_like_xg(session):
    path = _copy(session, "rchoicebug.ogxm", OGXM.read_bytes())
    assert json.loads(web.read_player_names(path)) == {"o": "Jezebel", "x": "rchoice"}
    loaded = json.loads(web.load_file(path, 0.08, 0.08, True, True))
    assert loaded["total"] == 170
    assert len(loaded["positions"]) == 11
    only_x = json.loads(web.load_file(path, 0.08, 0.08, True, False))
    assert 0 < len(only_x["positions"]) < 11


def test_a_hedgehog_analysis_names_its_source_on_the_card(session):
    path = _copy(session, "rchoicebug.mat.ogxm", OGXM.read_bytes())
    web.load_file(path, source_description="HedgeHog analysis (Colossus v1.0, 3-ply) from 'rchoicebug.mat'")
    assert "HedgeHog analysis (Colossus" in json.loads(web.preview(0))["back"]


@pytest.mark.parametrize("name, data, expected", [
    ("m.ogxm", b"OGXM....", {"analyzed": True, "import": None, "text": False}),
    ("m.xg", b"RGMH....", {"analyzed": True, "import": None, "text": False}),
    ("m.mat", b" 7 point match", {"analyzed": False, "import": "mat", "text": False}),
    ("5179402", b" 15 point match", {"analyzed": False, "import": "mat", "text": False}),
    ("m.txt", b"; [Site \"OpenGammon\"]", {"analyzed": False, "import": "mat", "text": False}),
    ("m.sgf", b"(;FF[4]GM[6]", {"analyzed": False, "import": "sgf", "text": False}),
])
def test_analysis_kind_routes_files(session, name, data, expected):
    assert json.loads(web.analysis_kind(_copy(session, name, data))) == expected


def test_pasted_ids_become_batched_requests(session):
    requests = json.loads(web.position_requests(
        f"{CHECKER_OGID}\nwatch the blot\n{CUBE_XGID}\n{MONEY_JACOBY_XGID}\nXGID=garbage", "2ply"))
    assert (requests["analyzed"], requests["pending"]) == (0, 3)
    assert len(requests["rejected"]) == 1
    by_rule = {batch["jacoby"]: batch for batch in requests["batches"]}
    assert by_rule[False]["indices"] == [0, 1]
    assert by_rule[True]["indices"] == [2]
    assert by_rule[False]["ogids"][0].startswith("99cchhiijjjkkmm:223334455666ddo:N0N:16:B:R:2:1:3C")


def test_answers_become_cards_with_notes_and_failures_reported(session):
    web.position_requests(f"{CHECKER_OGID}\nwatch the blot\n{CUBE_XGID}\n{MONEY_JACOBY_XGID}", "2ply")
    failure = {"success": False, "ogid": "x", "error": {"message": "Try a lower preset."}}
    loaded = json.loads(web.apply_position_analysis(json.dumps([CHECKER, CUBE, failure]), "3-ply"))
    assert loaded["failed"] == ["Try a lower preset."]
    assert [p["type"] for p in loaded["positions"]] == ["checker", "cube"]
    assert loaded["positions"][0]["has_note"] is True
    back = json.loads(web.preview(0))["back"]
    assert "13/7 6/5" in back
    assert "Analyzed with HedgeHog (3-ply) from OGID" in back


def test_answers_must_match_the_paste(session):
    web.position_requests(CUBE_XGID, "2ply")
    with pytest.raises(ValueError, match="paste them again"):
        web.apply_position_analysis(json.dumps([CUBE, CUBE]))


def test_a_paste_of_analyzed_text_needs_no_requests(session):
    from tests.test_web_entry import ANALYZED
    requests = json.loads(web.position_requests(ANALYZED))
    assert (requests["analyzed"], requests["pending"], requests["batches"]) == (1, 0, [])


def _answers_for(requests):
    """Stand-in HedgeHog answers for `matrix_requests`, in its "xgids" order."""
    order = [None] * len(requests["xgids"])
    for batch in requests["batches"]:
        for i, ogid in zip(batch["indices"], batch["ogids"]):
            order[i] = ogid
    return [dict(CHECKER if ogid.split(":")[3] else CUBE, ogid=ogid) for ogid in order]


def _apply(requests, answers, preset="2ply"):
    return json.loads(web.apply_matrix_analysis(json.dumps(requests["xgids"]), json.dumps(answers), preset))


@pytest.fixture
def pasted(session):
    web.position_requests(f"{CHECKER_OGID}\n{CUBE_7PT}", "2ply")
    web.apply_position_analysis(json.dumps([CHECKER, CUBE]), "3-ply")
    web.configure(json.dumps({"generate_score_matrix": True, "hedgehog_preset": "2ply"}))
    return session


CUBE_7PT = "XGID=-BBB--CC----eA--bc-e-B----:0:0:1:00:2:1:0:7:10"


def _matrix(indices="[]", preset="2ply"):
    return json.loads(web.matrix_requests(indices, preset))


def test_matrices_ask_for_every_score_once_and_count_by_batch(pasted):
    requests = _matrix()
    assert len(requests["xgids"]) == 38  # 36 scores, plus the unlimited game with and without Jacoby
    assert requests["cost"] == len(requests["batches"]) == 5
    assert _matrix("[1]", "3ply")["cost"] == 38


def test_fetched_answers_put_the_matrix_on_the_card(pasted):
    requests = _matrix()
    assert _apply(requests, _answers_for(requests)) == {"stored": 38, "failed": []}
    assert _matrix()["xgids"] == []
    preview = json.loads(web.preview(1))
    assert "score-matrix" in preview["back"]
    assert preview["warnings"] == []
    pack = json.loads(web.export_pack("[1]", "Deck"))
    assert "score_matrix" in pack["positions"][0]["extras"]


def test_a_card_whose_matrix_was_not_fetched_is_still_made_and_says_so(pasted):
    preview = json.loads(web.preview(1))
    assert "score-matrix" not in preview["back"]
    assert preview["warnings"] and json.loads(web.generation_warnings()) == preview["warnings"]


def test_no_matrix_settings_means_nothing_to_fetch(session):
    web.position_requests(CUBE_7PT, "2ply")
    web.apply_position_analysis(json.dumps([CUBE]), "3-ply")
    assert _matrix() == {"xgids": [], "batches": [], "cost": 0}


def test_matrix_answers_must_match_the_request(pasted):
    requests = _matrix()
    with pytest.raises(ValueError, match="try again"):
        _apply(requests, [CUBE])


def test_answers_for_another_request_are_not_stored_under_these_positions(pasted):
    """Two overlapping fetches: the second request's answers arrive for the first's XGIDs."""
    first = _matrix("[1]")
    web.position_requests("XGID=-BBB--CC----eA--bc-e-B----:0:0:-1:00:2:1:0:7:10", "2ply")
    web.apply_position_analysis(json.dumps([CUBE]), "3-ply")
    other = _matrix("[0]")
    assert first["xgids"] != other["xgids"]
    result = _apply(first, _answers_for(other))
    assert result["stored"] < len(first["xgids"])
    assert any("different position" in message for message in result["failed"])


def test_failed_answers_are_asked_again(pasted):
    requests = _matrix()
    answers = _answers_for(requests)
    answers[0] = {"success": False, "error": {"message": "You've used today's free position analyses."}}
    result = _apply(requests, answers)
    assert result["failed"] == ["You've used today's free position analyses."]
    assert _matrix()["xgids"] == [requests["xgids"][0]]


def test_answers_are_kept_per_depth(pasted):
    requests = _matrix()
    _apply(requests, _answers_for(requests))
    assert len(_matrix(preset="3ply")["xgids"]) == 38
    web.configure(json.dumps({"hedgehog_preset": "3ply"}))
    assert "score-matrix" not in json.loads(web.preview(1))["back"]


def test_a_paste_answered_after_a_newer_paste_is_refused(session):
    first = json.loads(web.position_requests(CUBE_XGID, "2ply"))
    web.position_requests(MONEY_JACOBY_XGID, "2ply")
    with pytest.raises(ValueError, match="paste them again"):
        web.apply_position_analysis(json.dumps([CUBE]), "3-ply", first["request"])


def test_an_unreadable_answer_is_one_failure_not_a_lost_paste(session):
    requests = json.loads(web.position_requests(f"{CUBE_XGID}\n{CHECKER_OGID}", "2ply"))
    loaded = json.loads(web.apply_position_analysis(json.dumps([CUBE, None]), "3-ply", requests["request"]))
    assert len(loaded["positions"]) == 1
    assert loaded["failed"] == ["HedgeHog's answer could not be read."]


@pytest.mark.parametrize("name, data, expected", [
    ("photo.png", bytes([0x89]) + b"PNG" + bytes(8), {"analyzed": False, "import": None, "text": False}),
    ("position.txt", b"XGID=-b----E-C--:0:0:1:52:0:0:3:0:10\n  1. XG Roller++ 18/11  eq:-0.0026",
     {"analyzed": True, "import": None, "text": True}),
    ("renamed", b"OGXM" + bytes(12), {"analyzed": True, "import": None, "text": False}),
])
def test_analysis_kind_tells_other_files_apart(session, name, data, expected):
    assert json.loads(web.analysis_kind(_copy(session, name, data))) == expected


def test_an_ogxm_file_without_its_extension_loads(session):
    path = _copy(session, "renamed-analysis", OGXM.read_bytes())
    assert json.loads(web.load_file(path))["total"] == 170
