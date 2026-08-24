"""Shared fixtures, plus the gate for tests that drive real XG2 and real Anki.

Live tests are opt-in because they launch applications and, for Anki, write
to the user's actual collection:

    ANKIGAMMON_LIVE_XG=1     real eXtreme Gammon 2 (launches XG, uses clipboard)
    ANKIGAMMON_LIVE_ANKI=1   real Anki via AnkiConnect (creates and deletes a note)
    ANKIGAMMON_LIVE=1        both

They exist because mocked tests have already passed while the real
application misbehaved: XG can decline a WM_CLOSE, so a green
"disconnect posts WM_CLOSE" test coexisted with an XG2 left running.
"""

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest


ANKI_URL = "http://127.0.0.1:8765"
XG_PROCESS_NAME = "extremegammon2.exe"

# Where XG2 tends to live. ANKIGAMMON_XG_EXE overrides.
_XG_CANDIDATES = (
    os.environ.get("ANKIGAMMON_XG_EXE"),
    r"D:/Program Files (x86)/eXtreme Gammon 2.19/eXtremeGammon2.exe",
    r"C:/Program Files (x86)/eXtreme Gammon 2/eXtremeGammon2.exe",
    r"C:/Program Files/eXtreme Gammon 2/eXtremeGammon2.exe",
)

_GNUBG_CANDIDATES = (
    os.environ.get("ANKIGAMMON_GNUBG"),
    r"D:/Program Files (x86)/gnubg/gnubg-cli.exe",
    r"C:/Program Files (x86)/gnubg/gnubg-cli.exe",
    "/usr/bin/gnubg",
)


def _first_existing(candidates):
    return next((c for c in candidates if c and Path(c).exists()), None)


XG_EXE = _first_existing(_XG_CANDIDATES)
GNUBG_EXE = _first_existing(_GNUBG_CANDIDATES)


def _enabled(name: str) -> bool:
    return os.environ.get("ANKIGAMMON_LIVE") == "1" or os.environ.get(name) == "1"


def pytest_configure(config):
    config.addinivalue_line("markers", "live_xg: drives a real eXtreme Gammon 2")
    config.addinivalue_line("markers", "live_anki: writes to a real Anki collection")


# --------------------------------------------------------------------------
# Anki helpers
# --------------------------------------------------------------------------

def anki_call(action: str, timeout: int = 60, **params):
    """Invoke AnkiConnect directly, raising on the API's in-band errors."""
    request = urllib.request.Request(
        ANKI_URL,
        data=json.dumps({"action": action, "version": 6, "params": params}).encode(),
        headers={"Content-Type": "application/json"},
    )
    payload = json.loads(urllib.request.urlopen(request, timeout=timeout).read().decode())
    if payload.get("error"):
        raise RuntimeError(f"AnkiConnect {action} failed: {payload['error']}")
    return payload["result"]


def anki_reachable() -> bool:
    try:
        anki_call("version", timeout=3)
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------
# XG process helpers
# --------------------------------------------------------------------------

def xg_pids() -> set:
    """PIDs of every running XG2 process."""
    import psutil

    found = set()
    for proc in psutil.process_iter(["name"]):
        try:
            if (proc.info["name"] or "").lower() == XG_PROCESS_NAME:
                found.add(proc.pid)
        except psutil.Error:
            pass
    return found


def wait_for_exit(pids: set, timeout: float = 30.0) -> bool:
    """True once none of pids is running."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not (pids & xg_pids()):
            return True
        time.sleep(0.5)
    return not (pids & xg_pids())


def force_kill(pids: set) -> None:
    """Last-resort cleanup so a failed test never strands an XG process."""
    import psutil

    for pid in pids & xg_pids():
        try:
            psutil.Process(pid).kill()
        except psutil.Error:
            pass


# --------------------------------------------------------------------------
# Reading a finished deck back
# --------------------------------------------------------------------------

def read_apkg_notes(apkg_path):
    """Return each note's field list, read out of the packaged collection.

    Checking the .apkg rather than the in-memory Decision is what proves a
    note survived every step, serialization and packaging included.
    """
    import sqlite3
    import tempfile
    import zipfile

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


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def live_xg():
    """Path to a real XG2, or skip."""
    if not _enabled("ANKIGAMMON_LIVE_XG"):
        pytest.skip("live XG tests are opt-in (ANKIGAMMON_LIVE_XG=1)")
    if XG_EXE is None:
        pytest.skip("eXtreme Gammon 2 not found")
    pytest.importorskip("psutil")
    return Path(XG_EXE)


@pytest.fixture
def no_xg_running(live_xg):
    """Require a clean slate, and strand nothing on the way out."""
    before = xg_pids()
    if before:
        pytest.skip(f"XG already running (pids={sorted(before)}); this test needs none")
    yield before
    stragglers = xg_pids() - before
    if stragglers:
        force_kill(stragglers)
        wait_for_exit(stragglers, timeout=10)
        pytest.fail(f"test left XG running: {sorted(stragglers)}")


@pytest.fixture
def live_anki():
    """A reachable AnkiConnect, or skip."""
    if not _enabled("ANKIGAMMON_LIVE_ANKI"):
        pytest.skip("live Anki tests are opt-in (ANKIGAMMON_LIVE_ANKI=1)")
    if not anki_reachable():
        pytest.skip("Anki is not running with AnkiConnect on " + ANKI_URL)
    return ANKI_URL


@pytest.fixture
def anki_collection_guard(live_anki):
    """Fail the test if it touches any pre-existing AnkiGammon note.

    Regenerate queries `tag:ankigammon` across the whole collection, so a
    live test that forgets to scope itself would rewrite the user's real
    cards. This catches that.
    """
    ids = anki_call("findNotes", query="tag:ankigammon")
    before = {n["noteId"]: n["mod"] for n in anki_call("notesInfo", notes=ids)} if ids else {}

    yield set(before)

    if not before:
        return
    still = anki_call("notesInfo", notes=list(before))
    after = {n["noteId"]: n["mod"] for n in still}
    changed = [i for i, mod in before.items() if after.get(i) != mod]
    assert not changed, f"pre-existing notes were modified: {changed}"
