"""
Application entry point for GUI mode.
"""

import sys
import os
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon

from xg2anki.gui.main_window import MainWindow
from xg2anki.settings import get_settings


def set_windows_app_id():
    """
    Set Windows AppUserModelID to show custom icon in taskbar.

    This fixes the issue where Python scripts show the Python icon
    in the Windows taskbar instead of the application's custom icon.
    """
    if sys.platform == 'win32':
        try:
            import ctypes
            # Set unique AppUserModelID for this application
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('XG2Anki.GUI.1.0')
        except Exception:
            # Silently fail if setting AppUserModelID doesn't work
            pass


def run_gui():
    """
    Launch the GUI application.

    Returns:
        int: Application exit code
    """
    # Set Windows AppUserModelID for custom taskbar icon
    set_windows_app_id()

    # Enable High DPI scaling
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

    app = QApplication(sys.argv)
    app.setApplicationName("XG2Anki")
    app.setOrganizationName("XG2Anki")
    app.setOrganizationDomain("github.com/yourusername/xg2anki")

    # Set application style (modern, consistent across platforms)
    app.setStyle('Fusion')

    # Set application icon
    icon_path = Path(__file__).parent / "resources" / "icon.png"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Load and apply stylesheet
    style_path = Path(__file__).parent / "resources" / "style.qss"
    if style_path.exists():
        with open(style_path) as f:
            app.setStyleSheet(f.read())

    # Load settings
    settings = get_settings()

    # Create and show main window
    window = MainWindow(settings)
    window.show()

    return app.exec()


if __name__ == '__main__':
    sys.exit(run_gui())
