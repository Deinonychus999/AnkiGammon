"""End-to-end: a user's comment must reach the finished Anki card.

Runs the real pipeline - format detection, parsing, a real GnuBG analysis,
the real CardGenerator, and a real .apkg written to disk - then reads the
note rows back out of the package's SQLite database and looks for the
comment. Nothing here is mocked except AnkiConnect in the regenerate case,
because that needs a running Anki.

Skipped unless a GnuBG binary is available (ANKIGAMMON_GNUBG or the default
Windows install path).
"""

import json
import os
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from unittest import mock

import pytest
from PySide6.QtWidgets import QApplication

from ankigammon.anki.apkg_exporter import ApkgExporter
from ankigammon.anki.decision_serialize import decision_from_json
from ankigammon.gui.dialogs.export_dialog import AnalysisWorker
from ankigammon.gui.dialogs.input_dialog import InputDialog
from ankigammon.gui.dialogs.regenerate_dialog import MODE_REANALYZE, RegenerateWorker
from ankigammon.gui.format_detector import FormatDetector, InputFormat
from ankigammon.parsers.xg_text_parser import XGTextParser
from ankigammon.settings import Settings


_GNUBG_CANDIDATES = [
    os.environ.get("ANKIGAMMON_GNUBG"),
    r"D:/Program Files (x86)/gnubg/gnubg-cli.exe",
    r"C:/Program Files (x86)/gnubg/gnubg-cli.exe",
    "/usr/bin/gnubg",
]
GNUBG_PATH = next(
    (p for p in _GNUBG_CANDIDATES if p and Path(p).exists()), None
)

pytestmark = pytest.mark.skipif(
    GNUBG_PATH is None, reason="needs a GnuBG binary for a real analysis"
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture(scope="module")
def settings():
    with tempfile.TemporaryDirectory() as tmp:
        s = Settings(config_path=Path(tmp) / "config.json")
        s.gnubg_path = GNUBG_PATH
        s.gnubg_analysis_ply = 0  # fastest real analysis; note handling is ply-agnostic
        s.analyzer_type = "gnubg"
        yield s


XGID = "XGID=-b----E-C--AeD---bAdb---A-:0:0:1:52:0:0:3:0:10"
NOTE_WITH_XGID = (
    "Compare with XGID=-b----E-C--AeD---bAdb---A-:0:0:1:31:0:0:3:0:10 - "
    "race lead = 4 pips, so run."
)

XG_EXPORT = """XGID=-b----E-C--AeD---bAdb---A-:0:0:1:52:0:0:3:0:10

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

{NOTE}

eXtreme Gammon Version: 2.10
"""


def _read_apkg_notes(apkg_path: Path):
    """Return each note's field list, straight out of the packaged collection."""
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(apkg_path) as zf:
            name = next(
                n for n in zf.namelist()
                if n in ("collection.anki2", "collection.anki21")
            )
            zf.extract(name, tmp)
        db = sqlite3.connect(Path(tmp) / name)
        try:
            rows = db.execute("SELECT flds FROM notes").fetchall()
        finally:
            db.close()
    return [row[0].split("\x1f") for row in rows]


def _export(decisions, tmp_path, name="deck.apkg"):
    out = tmp_path / name
    exporter = ApkgExporter(output_dir=tmp_path / "cards", deck_name="E2E Test Deck")
    exporter.export(decisions, output_file=str(out))
    assert out.exists(), "exporter did not write an apkg"
    return _read_apkg_notes(out)


def _analyze(decisions, settings):
    """Run the real export-time analysis worker to completion."""
    worker = AnalysisWorker(decisions, settings)
    result = {}
    worker.finished.connect(
        lambda ok, msg, decs: result.update(ok=ok, msg=msg, decisions=decs)
    )
    worker.run()
    assert result["ok"], result["msg"]
    return result["decisions"]


class TestPastedPositionIdWithComment:
    """The unanalyzed-position case: a bare XGID plus a typed comment."""

    def test_comment_reaches_the_apkg_back_field(self, qapp, settings, tmp_path):
        pasted = f"{XGID}\nRace lead = 4 pips, so run."

        detected = FormatDetector(settings).detect(pasted)
        assert detected.format == InputFormat.POSITION_IDS

        dialog = InputDialog(settings)
        decisions = dialog._parse_input(pasted, detected.format)
        assert len(decisions) == 1
        assert not decisions[0].candidate_moves, "should still need analysis"

        analyzed = _analyze(decisions, settings)
        assert analyzed[0].candidate_moves, "GnuBG returned no moves"

        notes = _export(analyzed, tmp_path)
        assert len(notes) == 1
        xgid_field, front, back, blob = notes[0]

        assert "Race lead = 4 pips, so run." in back
        assert decision_from_json(blob).note == "Race lead = 4 pips, so run."
        assert xgid_field

    def test_comment_containing_an_xgid_survives_the_round_trip(
        self, qapp, settings, tmp_path
    ):
        pasted = f"{XGID}\n{NOTE_WITH_XGID}"

        dialog = InputDialog(settings)
        decisions = dialog._parse_input(pasted, InputFormat.POSITION_IDS)
        assert len(decisions) == 1, "the XGID inside the note must not add a position"

        analyzed = _analyze(decisions, settings)
        notes = _export(analyzed, tmp_path, "deck2.apkg")

        assert len(notes) == 1
        assert "race lead = 4 pips" in notes[0][2]


class TestPastedFullAnalysisWithComment:
    """The analyzed-position case: XG's own text export, no engine needed."""

    def test_note_with_an_embedded_xgid_reaches_the_apkg(self, qapp, settings, tmp_path):
        text = XG_EXPORT.replace("{NOTE}", NOTE_WITH_XGID)

        detected = FormatDetector(settings).detect(text)
        assert detected.format == InputFormat.FULL_ANALYSIS
        assert detected.count == 1, "the XGID inside the note must not split the export"

        decisions = XGTextParser.parse_string(text)
        assert len(decisions) == 1
        assert decisions[0].note == NOTE_WITH_XGID

        notes = _export(decisions, tmp_path, "deck3.apkg")
        assert len(notes) == 1
        assert "race lead = 4 pips" in notes[0][2]


class TestRegenerateAgainstRealAnalysis:
    """Issue #58 with a real engine and the real CardGenerator behind it.

    AnkiConnect is the one stand-in: it needs a running Anki. Everything it
    is handed is what a live Anki would have been handed.
    """

    def test_comment_survives_a_real_reanalysis(self, qapp, settings, tmp_path):
        comment = "Race lead = 4 pips, so run."

        # Build the starting card exactly as an export would have.
        dialog = InputDialog(settings)
        decisions = dialog._parse_input(f"{XGID}\n{comment}", InputFormat.POSITION_IDS)
        analyzed = _analyze(decisions, settings)
        notes = _export(analyzed, tmp_path, "seed.apkg")
        seed_xgid, seed_front, seed_back, seed_blob = notes[0]
        assert comment in seed_back

        stored = {}

        class FakeAnki:
            def test_connection(self):
                return True

            def create_model(self):
                pass

            def invoke(self, action, **kw):
                assert action == "findNotes"
                return [1]

            def notes_info(self, ids):
                return [{
                    "noteId": 1,
                    "fields": {
                        "XGID": {"value": seed_xgid},
                        "Front": {"value": seed_front},
                        "Back": {"value": seed_back},
                        "AnalysisData": {"value": seed_blob},
                    },
                }]

            def update_note_fields(self, note_id, front, back, xgid="", analysis_data=None):
                stored.update(front=front, back=back, xgid=xgid, blob=analysis_data)

            def update_note_tags(self, note_id, tags):
                pass

        worker = RegenerateWorker(settings, MODE_REANALYZE)
        outcome = {}
        worker.finished.connect(lambda ok, msg: outcome.update(ok=ok, msg=msg))
        with mock.patch(
            "ankigammon.gui.dialogs.regenerate_dialog.AnkiConnect",
            return_value=FakeAnki(),
        ):
            worker.run()

        assert outcome["ok"], outcome["msg"]
        assert comment in stored["back"], "regenerate dropped the comment"
        assert decision_from_json(stored["blob"]).note == comment
        assert json.loads(stored["blob"])["decision"]["candidate_moves"], \
            "regenerate should have written fresh analysis"
