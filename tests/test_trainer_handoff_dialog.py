"""Study in Trainer: the dialog opens the trainer and follows the handoff."""

import json
import threading
import time
import urllib.request

import pytest
from PySide6.QtGui import QDesktopServices

from ankigammon.gui.dialogs.trainer_handoff_dialog import TrainerHandoffDialog

PACK = {"format": "ankigammon-position-pack", "version": 1,
        "deck": {"title": "Dialog test"}, "positions": [{"xgid": "XGID=-a"}]}


@pytest.fixture
def opened(monkeypatch):
    urls = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: urls.append(url.toString()) or True)
    return urls


def wait_for(qapp, condition, seconds=5):
    deadline = time.monotonic() + seconds
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("timed out")
        qapp.processEvents()
        time.sleep(0.01)


def fetch(url):
    port, key = url.split("#desktop=")[1].split(".")
    req = urllib.request.Request(f"http://127.0.0.1:{port}/pack/{key}",
                                 headers={"Origin": "https://ankigammon.com"})
    with urllib.request.urlopen(req, timeout=5) as response:
        return json.loads(response.read())


def test_dialog_closes_as_sent_once_the_trainer_fetches(qapp, opened):
    dialog = TrainerHandoffDialog(None, PACK, 1)
    dialog.show()
    assert opened == [dialog.handoff.url()]

    got = {}
    threading.Thread(target=lambda: got.update(pack=fetch(opened[0]))).start()
    wait_for(qapp, lambda: not dialog.isVisible())

    assert got["pack"] == PACK
    assert dialog.outcome == "sent"


def test_timeout_offers_the_file_instead(qapp, opened):
    dialog = TrainerHandoffDialog(None, PACK, 1, timeout=0.2)
    dialog.show()
    wait_for(qapp, lambda: dialog._cancel_btn.text() == "Close")

    assert "Save the positions as a file" in dialog._message.text()
    assert dialog.isVisible()
    dialog._save_btn.click()
    assert dialog.outcome == "save_file"


def test_cancel_stops_serving(qapp, opened, monkeypatch):
    dialog = TrainerHandoffDialog(None, PACK, 1)
    closed = []
    original = dialog.handoff.close
    monkeypatch.setattr(dialog.handoff, "close", lambda: closed.append(True) or original())
    dialog.show()
    dialog._cancel_btn.click()

    assert closed
    assert dialog.outcome == "cancelled"
