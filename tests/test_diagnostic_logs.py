import os
import zipfile
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtWidgets import QFileDialog, QMessageBox

from ankigammon.gui import main_window
from ankigammon.gui.main_window import MainWindow


def test_zip_includes_faulthandler_log_while_app_holds_it_open(qapp, tmp_path, monkeypatch):
    config_dir = tmp_path / ".ankigammon"
    config_dir.mkdir()
    (config_dir / "ankigammon.log").write_text("app log\n", encoding="utf-8")
    zip_path = tmp_path / "diag.zip"

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(zip_path), ""))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "critical", lambda *a, **k: None)
    monkeypatch.setattr(os, "startfile", lambda *a: None, raising=False)
    monkeypatch.setattr(main_window.subprocess, "Popen", lambda *a, **k: None)

    fake_window = SimpleNamespace(
        settings=SimpleNamespace(
            analyzer_type="gnubg", gnubg_path=None,
            xg_exe_path=None, xg_analysis_level="world class",
        ),
        _gnubg_version=lambda: "n/a",
    )

    # Mirrors app.main(), which keeps the fault log open for the process lifetime
    with open(config_dir / "faulthandler.log", "a", buffering=1, encoding="utf-8") as fault_log:
        fault_log.write("Windows fatal exception: code 0xc0000409\n")
        MainWindow.send_diagnostic_logs(fake_window)

    with zipfile.ZipFile(zip_path) as zf:
        assert "faulthandler.log" in zf.namelist()
        assert "0xc0000409" in zf.read("faulthandler.log").decode("utf-8")
