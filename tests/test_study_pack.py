"""Study packs, the JSON the AnkiGammon trainer (ankigammon.com/train) studies.

The trainer reads packs made here and packs the website builds out of an
.apkg (js/apkg-reader.js: XGID field, note tags, AnalysisData field), so a
position must come out the same either way.
"""

import dataclasses
import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path

import pytest

from ankigammon import settings as settings_module
from ankigammon import web
from ankigammon.anki.apkg_exporter import ApkgExporter
from ankigammon.anki.decision_serialize import decision_from_json
from ankigammon.import_filter import filter_decisions
from ankigammon.parsers.xg_binary_parser import XGBinaryParser
from ankigammon.study_pack import PACK_FORMAT, build_pack, decision_tags, write_pack

SAMPLE = str(Path(__file__).parent / "data" / "sample_match.xg")


@pytest.fixture(scope="module")
def decisions():
    return filter_decisions(XGBinaryParser.parse_file(SAMPLE), 0.02, 0.02, True, True, 5)


@pytest.fixture
def session(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module, "_settings", None)
    web.start(str(tmp_path / "work"))
    return tmp_path / "work"


def _apkg_notes(path):
    """(xgid, tags, analysis) per note, the three things apkg-reader.js reads."""
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(path) as zf:
            name = next(n for n in zf.namelist() if n in ("collection.anki2", "collection.anki21"))
            zf.extract(name, tmp)
        db = sqlite3.connect(Path(tmp) / name)
        try:
            rows = db.execute("SELECT flds, tags FROM notes").fetchall()
        finally:
            db.close()
    notes = []
    for flds, tags in rows:
        fields = flds.split("\x1f")
        notes.append((fields[0], tags.split(), json.loads(fields[3])))
    return notes


def test_pack_holds_every_analyzed_position_whole(decisions):
    pack = build_pack(decisions, "Sample")
    assert pack["format"] == PACK_FORMAT
    assert pack["version"] == 1
    assert pack["deck"] == {"title": "Sample"}
    assert [p["xgid"] for p in pack["positions"]] == [d.xgid for d in decisions]
    for position, decision in zip(pack["positions"], decisions):
        assert decision_from_json(json.dumps(position["analysis"])) == decision


def test_pack_matches_what_the_website_reads_out_of_an_apkg(decisions, tmp_path, monkeypatch):
    monkeypatch.setattr(settings_module, "_settings", settings_module.Settings(config_path=tmp_path / "config.json"))
    apkg = ApkgExporter(tmp_path, "Sample").export(decisions, output_file="sample.apkg", show_options=True)
    from_apkg = {xgid: (sorted(tags), analysis) for xgid, tags, analysis in _apkg_notes(apkg)}
    pack = build_pack(decisions, "Sample")

    assert len(from_apkg) == len(pack["positions"])
    for position in pack["positions"]:
        tags, analysis = from_apkg[position["xgid"]]
        assert sorted(position["tags"]) == tags
        assert position["analysis"] == analysis


def test_positions_the_trainer_cannot_use_are_left_out(decisions):
    no_xgid = dataclasses.replace(decisions[0], xgid=None)
    unanalyzed = dataclasses.replace(decisions[1], candidate_moves=[])
    pack = build_pack([no_xgid, unanalyzed, decisions[2]], "Sample")
    assert [p["xgid"] for p in pack["positions"]] == [decisions[2].xgid]


def test_tags_name_the_decision_and_the_game(decisions):
    cube = next(d for d in decisions if d.decision_type.value == "cube_action")
    assert decision_tags(cube)[:3] == ["ankigammon", "backgammon", "cube_action"]
    assert "match_7pt" in decision_tags(cube)


def test_write_pack_returns_the_position_count(decisions, tmp_path):
    path = tmp_path / "sample.json"
    assert write_pack(decisions, path, "Sample") == len(decisions)
    assert json.loads(path.read_text(encoding="utf-8"))["format"] == PACK_FORMAT


def test_browser_exports_the_chosen_positions_as_a_pack(session):
    loaded = json.loads(web.load_file(SAMPLE))
    chosen = [0, 3, len(loaded["positions"]) - 1]
    pack = json.loads(web.export_pack(json.dumps(chosen), "My matches"))
    assert pack["deck"]["title"] == "My matches"
    assert [p["xgid"] for p in pack["positions"]] == [loaded["positions"][i]["xgid"] for i in chosen]
    assert len(json.loads(web.export_pack("[]", "All"))["positions"]) == len(loaded["positions"])


def test_browser_pack_export_needs_positions(session):
    with pytest.raises(ValueError, match="No positions"):
        web.export_pack("[]", "Empty")


def test_browser_pack_export_refuses_to_run_before_start(monkeypatch):
    monkeypatch.setattr(web, "_work_dir", None)
    with pytest.raises(RuntimeError, match="start"):
        web.export_pack("[]", "Nothing")


class _Window:
    """What MainWindow.on_export_pack_clicked reads, without building the window."""

    def __init__(self, settings, decks):
        from ankigammon.gui.deck_manager import DeckManager
        self.settings = settings
        self.deck_manager = DeckManager("AnkiGammon")
        for name, decisions in decks.items():
            self.deck_manager.add_decisions(decisions, name)


def _export_pack(window, monkeypatch, save_to, answer):
    from PySide6.QtWidgets import QFileDialog, QMessageBox
    from ankigammon.gui import main_window, silent_messagebox

    opened = []
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(save_to), "")))
    monkeypatch.setattr(silent_messagebox, "question", lambda *a, **k: answer(QMessageBox))
    monkeypatch.setattr(main_window.QDesktopServices, "openUrl", lambda url: opened.append(url.toString()))
    main_window.MainWindow.on_export_pack_clicked(window)
    return opened


def test_desktop_exports_every_deck_into_one_pack_named_after_the_file(decisions, tmp_path, monkeypatch):
    settings = settings_module.Settings(config_path=tmp_path / "config.json")
    window = _Window(settings, {"AnkiGammon": decisions[:3], "AnkiGammon::Cube": decisions[3:5]})
    target = tmp_path / "Tuesday club.json"

    opened = _export_pack(window, monkeypatch, target, lambda mb: mb.StandardButton.Yes)

    pack = json.loads(target.read_text(encoding="utf-8"))
    assert pack["deck"]["title"] == "Tuesday club"
    assert sorted(p["xgid"] for p in pack["positions"]) == sorted(d.xgid for d in decisions[:5])
    assert opened == ["https://ankigammon.com/train/"]


def test_desktop_export_with_nothing_loaded_saves_nothing(tmp_path, monkeypatch):
    from ankigammon.gui import silent_messagebox
    shown = []
    monkeypatch.setattr(silent_messagebox, "information", lambda parent, title, text: shown.append(title))
    window = _Window(settings_module.Settings(config_path=tmp_path / "config.json"), {})
    target = tmp_path / "empty.json"

    _export_pack(window, monkeypatch, target, lambda mb: mb.StandardButton.No)

    assert shown == ["Nothing to Export"]
    assert not target.exists()
