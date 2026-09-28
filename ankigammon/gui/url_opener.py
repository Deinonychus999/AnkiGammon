"""Open links and folders with the desktop's own opener.

In the frozen Linux build, Qt would start xdg-open with the bootloader's
LD_LIBRARY_PATH, and a system opener like kde-open then loads the bundled Qt
instead of the system's and fails. A URL handler for the common schemes runs
xdg-open with the original environment, which also covers the links Qt
opens by itself (the About box, release notes).
"""

import subprocess
import sys

from PySide6.QtCore import QObject, QUrl, Slot
from PySide6.QtGui import QDesktopServices

from ankigammon.utils.subprocess_env import external_subprocess_env

SCHEMES = ("http", "https", "file")

_handler = None


class _SystemOpener(QObject):
    @Slot(QUrl)
    def open(self, url: QUrl) -> None:
        target = url.toLocalFile() if url.isLocalFile() else bytes(url.toEncoded()).decode()
        try:
            subprocess.Popen(["xdg-open", target], env=external_subprocess_env())
        except OSError:
            _qt_open(url)


def _qt_open(url: QUrl) -> None:
    # Qt would hand the URL straight back to our handler while it is set.
    uninstall()
    try:
        QDesktopServices.openUrl(url)
    finally:
        install()


def install() -> None:
    global _handler
    if not (getattr(sys, "frozen", False) and sys.platform.startswith("linux")):
        return
    if _handler is None:
        _handler = _SystemOpener()
    for scheme in SCHEMES:
        QDesktopServices.setUrlHandler(scheme, _handler, "open")


def uninstall() -> None:
    for scheme in SCHEMES:
        QDesktopServices.unsetUrlHandler(scheme)


def open_url(url: str) -> bool:
    return QDesktopServices.openUrl(QUrl(url))
