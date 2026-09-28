"""Links opened from the frozen Linux build reach the desktop's own opener.

The AppImage's bootloader points LD_LIBRARY_PATH at its bundled Qt, and a
child like kde-open, built against the system's newer Qt, then fails with
"version `Qt_6.11' not found" (reported on Fedora KDE, HedgeHog Connect).
"""

import sys

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

from ankigammon.gui import url_opener

BUNDLE = "/tmp/_MEI12345"


@pytest.fixture
def frozen_linux(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("LD_LIBRARY_PATH", BUNDLE)
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/usr/local/lib")


@pytest.fixture
def launched(monkeypatch):
    calls = []

    class FakePopen:
        def __init__(self, args, **kwargs):
            calls.append((args, kwargs.get("env")))

    monkeypatch.setattr(url_opener.subprocess, "Popen", FakePopen)
    return calls


@pytest.fixture
def installed(qapp):
    yield
    url_opener.uninstall()


def test_links_open_with_the_systems_library_path(qapp, frozen_linux, launched, installed):
    url_opener.install()
    QDesktopServices.openUrl(QUrl("https://hedgehog-bg.com/oauth/authorize?state=x"))

    (args, env), = launched
    assert args == ["xdg-open", "https://hedgehog-bg.com/oauth/authorize?state=x"]
    assert env["LD_LIBRARY_PATH"] == "/usr/local/lib"
    assert BUNDLE not in env.get("LD_LIBRARY_PATH", "")


def test_folders_open_the_same_way(qapp, frozen_linux, launched, installed):
    url_opener.install()
    QDesktopServices.openUrl(QUrl.fromLocalFile("/home/player"))

    (args, env), = launched
    assert args == ["xdg-open", "/home/player"]
    assert env["LD_LIBRARY_PATH"] == "/usr/local/lib"


def test_left_to_qt_outside_the_frozen_linux_build(qapp, monkeypatch, launched, installed):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "platform", "linux")
    url_opener.install()
    opened = []
    monkeypatch.setattr(url_opener.QDesktopServices, "openUrl", lambda url: opened.append(url) or True)

    url_opener.open_url("https://ankigammon.com/")

    assert launched == []
    assert opened == [QUrl("https://ankigammon.com/")]


def test_falls_back_to_qt_when_xdg_open_is_missing(qapp, frozen_linux, monkeypatch, installed):
    def missing(*args, **kwargs):
        raise FileNotFoundError("xdg-open")

    monkeypatch.setattr(url_opener.subprocess, "Popen", missing)
    url_opener.install()
    fallback = []
    monkeypatch.setattr(url_opener, "_qt_open", lambda url: fallback.append(url.toString()))

    QDesktopServices.openUrl(QUrl("https://ankigammon.com/"))

    assert fallback == ["https://ankigammon.com/"]
