"""
Resource path utilities for GUI.
"""
import sys
from pathlib import Path


def get_resource_path(relative_path: str) -> Path:
    """
    Get absolute path to resource, works for dev and PyInstaller.

    Args:
        relative_path: Relative path to resource (e.g., "gui/resources/icon.png")

    Returns:
        Path: Absolute path to resource
    """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = Path(sys._MEIPASS)
    except AttributeError:
        # Running in normal Python environment
        # __file__ is in ankigammon/gui/resources.py, so parent.parent gets us to repo root
        base_path = Path(__file__).parent.parent.parent

    return base_path / relative_path


def load_stylesheet() -> str:
    """Read style.qss with its url() references made absolute.

    Qt resolves relative url() paths in an application stylesheet against the
    process working directory, not the .qss file, so outside a repo-root dev
    run (installed builds, pip installs) the tree arrows and other images
    silently fail to load.
    """
    style_path = get_resource_path("ankigammon/gui/resources/style.qss")
    if not style_path.exists():
        return ""
    qss = style_path.read_text(encoding='utf-8')
    base = get_resource_path("ankigammon").as_posix()
    return qss.replace("url(ankigammon/", f"url({base}/")
