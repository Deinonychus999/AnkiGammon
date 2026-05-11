"""Tests for the new error-message branches in GnuBGValidationWorker.

The fix for the AppImage gnubg detection bug introduced two distinct
verdicts on the validation failure path that used to share one misleading
"Not GNU Backgammon" message: an empty-stderr launch failure (the actual
AppImage symptom) and a non-gnubg binary that did produce output. These
tests pin both branches so a future refactor doesn't silently restore the
original confusing UX.
"""

import subprocess
from pathlib import Path
from unittest import mock

import pytest
from PySide6.QtWidgets import QApplication

from ankigammon.gui.dialogs.settings_dialog import GnuBGValidationWorker


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


def _run_worker_with_subprocess_result(returncode: int, stdout: str, stderr: str):
    """Run the validation worker with a mocked subprocess result and return the emitted (text, type)."""
    worker = GnuBGValidationWorker("/fake/gnubg")
    captured: list = []
    worker.validation_complete.connect(lambda text, kind: captured.append((text, kind)))

    fake_result = subprocess.CompletedProcess(
        args=["/fake/gnubg"],
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )
    with mock.patch.object(Path, 'exists', return_value=True), \
         mock.patch.object(Path, 'is_file', return_value=True), \
         mock.patch('ankigammon.gui.dialogs.settings_dialog.subprocess.run', return_value=fake_result):
        worker.run()

    assert len(captured) == 1, f"Expected exactly one validation_complete emit, got {captured}"
    return captured[0]


def test_empty_output_with_nonzero_exit_reports_launch_failure(qapp):
    """The AppImage LD_LIBRARY_PATH symptom: non-zero exit, empty stdout+stderr.

    Without this branch the user got "Not GNU Backgammon" — misleading
    because the binary IS gnubg, it just failed to link.
    """
    text, kind = _run_worker_with_subprocess_result(returncode=127, stdout="", stderr="")
    assert "Failed to launch" in text
    assert "127" in text
    assert "libraries" in text
    assert kind == "warning"


def test_non_gnubg_output_includes_snippet_in_error(qapp):
    """A non-gnubg binary that did print something — surface what it said."""
    text, kind = _run_worker_with_subprocess_result(
        returncode=1,
        stdout="some other tool v2.3\nUsage: foobar [options]",
        stderr="",
    )
    assert text.startswith("Not GNU Backgammon: ")
    assert "some other tool v2.3" in text
    assert kind == "warning"
