"""Cancelling or closing while a worker thread winds down must not abort the app.

Workers report their result by signal, then keep running to shut their
engine down. A dialog that closed on that signal let its worker be destroyed
mid-run, and Qt aborted the whole process ("QThread: Destroyed while thread
is still running"); a Fedora user hit it cancelling a Send to Anki export.
Quitting right after cancelling a match import did the same. Qt aborts
rather than raising, so those scenarios run in their own process.
"""

import os
import subprocess
import sys
import textwrap

import pytest

COMMON = textwrap.dedent("""
    import sys, time
    from pathlib import Path
    from PySide6.QtCore import QThread, QTimer, Signal
    from PySide6.QtWidgets import QApplication, QWidget
    from ankigammon.settings import Settings

    from PySide6.QtCore import QSettings
    QSettings.setDefaultFormat(QSettings.IniFormat)  # keeps window state out of the registry
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, sys.argv[1])
    app = QApplication(sys.argv)
    window = QWidget()
    settings = Settings(config_path=Path(sys.argv[1]) / "config.json")
    settings.check_for_updates = False
    settings.export_method = "apkg"

    def winding_down_worker(signature):
        class Worker(QThread):
            finished = Signal(*signature)
            progress = Signal(float)
            status_message = Signal(str)

            def __init__(self, *args, **kwargs):
                super().__init__()
                self._cancelled = False

            def cancel(self):
                self._cancelled = True

            def run(self):
                while not self._cancelled:
                    time.sleep(0.01)
                self.finished.emit(*CANCELLED[:len(signature)])
                time.sleep(0.5)  # the engine shutting down after the report
        return Worker

    CANCELLED = (False, "Cancelled", [], 0)

    def close_while_running(dialog, start):
        QTimer.singleShot(0, start)
        close = dialog.btn_close.click if sys.argv[2] == "cancel" else dialog.reject
        QTimer.singleShot(200, close)
        dialog.exec()

    def finish():
        deadline = time.monotonic() + 1.5
        while time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        print("survived", flush=True)
""")

DIALOGS = {
    "export": """
        from ankigammon.gui.dialogs import export_dialog
        from ankigammon.models import Decision, Move, Player, Position
        export_dialog.ExportWorker = winding_down_worker((bool, str))
        decision = Decision(position=Position(points=[0] * 26), on_roll=Player.O,
                            candidate_moves=[Move(notation="13/7", equity=0.1, rank=1)])
        def run():
            dialog = export_dialog.ExportDialog({"Deck": [decision]}, settings, window)
            dialog.output_path = None
            close_while_running(dialog, dialog._start_export_worker)
        run()
        finish()
    """,
    "regenerate": """
        from ankigammon.gui.dialogs import regenerate_dialog
        regenerate_dialog.RegenerateWorker = winding_down_worker((bool, str))
        def run():
            dialog = regenerate_dialog.RegenerateDialog(settings, window)
            close_while_running(dialog, dialog.start_regenerate)
        run()
        finish()
    """,
}

MATCH_IMPORT = """
    from PySide6.QtCore import QObject
    from ankigammon.gui.main_window import MainWindow
    Worker = winding_down_worker((bool, str, list, int))
    owner = QObject()
    owner._finishing_workers = []
    owner._analysis_worker = Worker()
    owner._analysis_worker.finished.connect(lambda *a: MainWindow._release_analysis_worker(owner))
    owner._analysis_worker.start()
    QTimer.singleShot(100, owner._analysis_worker.cancel)
    finish()
"""

QUIT_DURING_IMPORT = """
    from ankigammon.gui.main_window import MainWindow
    win = MainWindow(settings)
    win._analysis_worker = winding_down_worker((bool, str, list, int))()
    win._analysis_worker.start()
    QTimer.singleShot(100, win.close)
    QTimer.singleShot(200, app.quit)
    app.exec()
    print("survived", flush=True)
"""


def _run(script, *args):
    result = subprocess.run(
        [sys.executable, "-c", COMMON + textwrap.dedent(script), *args],
        capture_output=True, text=True, timeout=60,
        env=dict(os.environ, QT_QPA_PLATFORM="offscreen"),
    )
    assert result.returncode == 0 and "survived" in result.stdout, (
        f"exit {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )


@pytest.mark.parametrize("close_with", ["cancel", "escape"])
@pytest.mark.parametrize("dialog", sorted(DIALOGS))
def test_closing_a_dialog_while_its_worker_winds_down(dialog, close_with, tmp_path):
    _run(DIALOGS[dialog], str(tmp_path), close_with)


def test_releasing_the_match_import_worker_while_it_winds_down(tmp_path):
    _run(MATCH_IMPORT, str(tmp_path), "cancel")


def test_quitting_while_an_import_worker_still_runs(tmp_path):
    _run(QUIT_DURING_IMPORT, str(tmp_path), "cancel")


def test_a_cancel_before_the_engine_starts_stops_the_import(qapp, tmp_path):
    from unittest import mock
    from ankigammon.gui.main_window import MatchAnalysisWorker
    from ankigammon.settings import Settings

    worker = MatchAnalysisWorker(
        "match.mat", Settings(config_path=tmp_path / "config.json"), 0.0, 0.0, True, True,
        filter_func=lambda decisions, *args: decisions, max_moves=0,
    )
    engine_runs = []

    class Analyzer:
        def analyze_match_file(self, path, max_moves, progress_callback):
            progress_callback("Analyzing match with GnuBG (2-ply)...")
            engine_runs.append(path)
            return []

        def terminate(self):
            pass

    def create_analyzer(settings):
        worker.cancel()  # the user cancels while the engine is being set up
        return Analyzer()

    results = []
    worker.finished.connect(lambda ok, msg, decisions, total: results.append((ok, msg)))
    with mock.patch("ankigammon.utils.analyzer_base.create_analyzer", create_analyzer):
        worker.run()
    assert engine_runs == []
    assert results == [(False, "Cancelled")]
