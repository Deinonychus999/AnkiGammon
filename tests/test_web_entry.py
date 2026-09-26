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


@pytest.mark.parametrize("failed_load", ["paste", "file"])
def test_failed_load_keeps_the_positions_the_page_still_shows(session, tmp_path, failed_load):
    """The page keeps its list when a load fails, so exporting it must still
    work; a paste without analysis used to empty the list first, and the
    export then failed with 'list index out of range'."""
    loaded = json.loads(web.load_file(SAMPLE))
    with pytest.raises(ValueError):
        if failed_load == "paste":
            web.load_text(UNANALYZED)
        else:
            damaged = tmp_path / "damaged.xg"
            damaged.write_bytes(bytes(range(256)) * 16)
            web.load_file(str(damaged))

    last = len(loaded["positions"]) - 1
    [fields] = read_apkg_notes(web.export_apkg(f"[{last}]", "Web entry test"))
    assert fields[0] == loaded["positions"][last]["xgid"]


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


# ---------------------------------------------------------------------------
# What the browser can and cannot import
# ---------------------------------------------------------------------------

def _run_isolated(code, tmp_path):
    import subprocess
    import sys
    script = tmp_path / "probe.py"
    script.write_text(code, encoding="utf-8")
    return subprocess.run([sys.executable, str(script)], capture_output=True, text=True,
                          cwd=str(Path(__file__).resolve().parent.parent))


def test_browser_path_never_imports_desktop_only_modules(tmp_path):
    """The website strips ankigammon/gui and utils/xg_auto from the wheel it
    serves, so nothing the browser calls may import them."""
    result = _run_isolated(f"""
import json, sys, warnings
warnings.filterwarnings("ignore")
from ankigammon import web
web.start({str(tmp_path / 'work')!r})
web.read_player_names({SAMPLE!r})
web.load_file({SAMPLE!r})
web.configure(json.dumps({{"color_scheme": "ocean"}}))
web.preview(0)
web.export_apkg("[]", "probe")
web.load_text({ANALYZED!r})
banned = [m for m in sys.modules if m.startswith(("ankigammon.gui", "ankigammon.utils.xg_auto", "PySide6"))]
print(banned)
sys.exit(1 if banned else 0)
""", tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr


def test_anki_connect_client_loads_without_requests(tmp_path):
    """requests is not installed in the browser; the client must import
    it only where the desktop sends a request."""
    result = _run_isolated("""
import sys
sys.modules["requests"] = None
import ankigammon.anki.ankiconnect
from ankigammon import web
""", tmp_path)
    assert result.returncode == 0, result.stderr[-800:]


# ---------------------------------------------------------------------------
# Send to Anki: the real AnkiConnect client over a swapped transport
# ---------------------------------------------------------------------------

class FakeAnki:
    """Just enough of AnkiConnect's HTTP API, answering like the add-on."""

    def __init__(self):
        self.models = {}
        self.decks = set()
        self.notes = {}
        self.cards = {}
        self.actions = []
        self.keys = []
        self._next = 1000

    def __call__(self, url, payload):
        self.url = url
        self.keys.append(payload.get("key"))
        action, params = payload["action"], payload.get("params", {})
        self.actions.append(action)
        try:
            return {"result": getattr(self, "do_" + action)(**params), "error": None}
        except Exception as e:  # AnkiConnect reports failures in-band
            return {"result": None, "error": str(e)}

    def _id(self):
        self._next += 1
        return self._next

    def do_modelNames(self):
        return list(self.models)

    def do_createModel(self, modelName, inOrderFields, css, cardTemplates):
        self.models[modelName] = {"fields": list(inOrderFields), "css": css}

    def do_updateModelStyling(self, model):
        self.models[model["name"]]["css"] = model["css"]

    def do_modelFieldNames(self, modelName):
        return self.models[modelName]["fields"]

    def do_createDeck(self, deck):
        self.decks.add(deck)

    def do_findNotes(self, query):
        xgid = query.split('"XGID:', 1)[1].split('"', 1)[0].replace('\\"', '"')
        return [nid for nid, n in self.notes.items() if n["fields"]["XGID"] == xgid]

    def do_addNote(self, note):
        if note["deckName"] not in self.decks:
            raise ValueError(f"deck was not found: {note['deckName']}")
        nid, cid = self._id(), self._id()
        self.notes[nid] = {"fields": dict(note["fields"]), "tags": list(note["tags"]), "cards": [cid]}
        self.cards[cid] = note["deckName"]
        return nid

    def do_updateNoteFields(self, note):
        self.notes[note["id"]]["fields"].update(note["fields"])

    def do_notesInfo(self, notes):
        return [{"noteId": n, "tags": self.notes[n]["tags"], "cards": self.notes[n]["cards"]} for n in notes]

    def do_removeTags(self, notes, tags):
        for n in notes:
            self.notes[n]["tags"] = [t for t in self.notes[n]["tags"] if t not in tags.split()]

    def do_addTags(self, notes, tags):
        for n in notes:
            self.notes[n]["tags"] += tags.split()

    def do_changeDeck(self, cards, deck):
        for c in cards:
            self.cards[c] = deck

    def deck_of(self, nid):
        return self.cards[self.notes[nid]["cards"][0]]


def _send(fake, indices="[]", deck="Web send test", **kw):
    return json.loads(web.send_to_anki(indices, deck, transport=fake, **kw))


def test_first_send_adds_every_card_with_the_apkg_fields(session):
    import random

    loaded = json.loads(web.load_file(SAMPLE))
    fake = FakeAnki()
    random.seed(11)
    summary = _send(fake, use_subdecks=True)
    random.seed(11)
    apkg = read_apkg_notes(web.export_apkg("[]", "Web send test", use_subdecks=True))

    total = len(loaded["positions"])
    assert (summary["total"], summary["added"], summary["updated"]) == (total, total, 0)
    assert set(summary["decks"]) == {"Web send test::Checker Play", "Web send test::Cube Decisions"}
    assert set(summary["decks"]) <= fake.decks
    sent = sorted((n["fields"]["XGID"], n["fields"]["Front"], n["fields"]["Back"], n["fields"]["AnalysisData"])
                  for n in fake.notes.values())
    assert sent == sorted(tuple(f) for f in apkg)
    assert "AnkiGammon" in fake.models


def test_sending_again_updates_instead_of_duplicating(session):
    web.load_file(SAMPLE)
    fake = FakeAnki()
    first = _send(fake)
    second = _send(fake)
    assert second["added"] == 0 and second["updated"] == first["total"]
    assert len(fake.notes) == first["total"]


def test_changing_the_deck_moves_existing_cards(session):
    web.load_file(SAMPLE)
    fake = FakeAnki()
    _send(fake, deck="Old deck")
    _send(fake, deck="New deck")
    assert {fake.deck_of(n) for n in fake.notes} == {"New deck"}


def test_selection_and_progress(session):
    web.load_file(SAMPLE)
    fake = FakeAnki()
    seen = []
    summary = _send(fake, indices="[0, 2]", progress=lambda done, total: seen.append((done, total)))
    assert summary["total"] == 2 and len(fake.notes) == 2
    assert seen == [(0, 2), (1, 2), (2, 2)]


def test_api_key_travels_with_every_request(session):
    web.load_file(SAMPLE)
    fake = FakeAnki()
    _send(fake, indices="[0]", api_key="s3cret", url="http://127.0.0.1:8766")
    assert set(fake.keys) == {"s3cret"}
    assert fake.url == "http://127.0.0.1:8766"


def test_anki_errors_reach_the_page(session):
    web.load_file(SAMPLE)

    def broken(url, payload):
        return {"result": None, "error": "collection is not available"}

    with pytest.raises(Exception, match="collection is not available"):
        _send(broken)
