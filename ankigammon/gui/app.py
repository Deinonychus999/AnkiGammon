"""
Application entry point for GUI mode.
"""

import sys
import os
from pathlib import Path
from PySide6.QtWidgets import QApplication, QSplashScreen, QGraphicsDropShadowEffect
from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont, QLinearGradient, QPainterPath, QPen

from ankigammon.gui.main_window import MainWindow
from ankigammon.gui.resources import get_resource_path
from ankigammon.settings import get_settings


def set_windows_app_id():
    """
    Set Windows AppUserModelID to display custom icon in taskbar.

    On Windows, this enables the application's icon to appear in the taskbar
    instead of the default Python icon.
    """
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('AnkiGammon.GUI.1.0')
        except Exception:
            pass


def create_splash_screen(icon_path: Path) -> QSplashScreen:
    """
    Create a splash screen with modern styling.

    Features rounded corners, gradient background, branded border,
    drop shadow, and antialiased rendering.

    Args:
        icon_path: Path to the application icon

    Returns:
        QSplashScreen: Configured splash screen
    """
    # Create pixmap with margin for drop shadow
    splash_pix = QPixmap(440, 340)
    splash_pix.fill(Qt.transparent)

    # Initialize painter with antialiasing
    painter = QPainter(splash_pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    painter.setRenderHint(QPainter.TextAntialiasing)

    # Define rounded rectangle with 20px margin for shadow
    rect = QRectF(20, 20, 400, 300)
    corner_radius = 12

    path = QPainterPath()
    path.addRoundedRect(rect, corner_radius, corner_radius)

    # Apply gradient background
    gradient = QLinearGradient(20, 20, 20, 320)
    gradient.setColorAt(0.0, QColor("#1e1e2e"))
    gradient.setColorAt(0.3, QColor("#262637"))
    gradient.setColorAt(0.7, QColor("#262637"))
    gradient.setColorAt(1.0, QColor("#1e1e2e"))
    painter.fillPath(path, gradient)

    # Load and draw application icon
    if icon_path.exists():
        icon_pixmap = QPixmap(str(icon_path))
        icon_size = 120
        scaled_icon = icon_pixmap.scaled(icon_size, icon_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        icon_x = 20 + (400 - scaled_icon.width()) // 2
        icon_y = 20 + 40

        painter.drawPixmap(icon_x, icon_y, scaled_icon)

    # Draw border
    border_pen = QPen(QColor("#89b4fa"), 2.5)
    border_pen.setJoinStyle(Qt.RoundJoin)
    border_pen.setCapStyle(Qt.RoundCap)
    painter.setPen(border_pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(path)

    # Draw application name
    painter.setPen(QColor("#f5e0dc"))
    title_font = QFont("Segoe UI", 24, QFont.Bold)
    title_font.setLetterSpacing(QFont.AbsoluteSpacing, 0.5)
    painter.setFont(title_font)
    painter.drawText(20, 20 + 170, 400, 40, Qt.AlignCenter, "AnkiGammon")

    # Draw tagline
    painter.setPen(QColor("#b4befe"))
    tagline_font = QFont("Segoe UI", 10)
    painter.setFont(tagline_font)
    painter.drawText(20, 20 + 215, 400, 20, Qt.AlignCenter, "Backgammon Analysis to Flashcards")

    # Draw loading indicator
    painter.setPen(QColor("#a6adc8"))
    loading_font = QFont("Segoe UI", 11)
    painter.setFont(loading_font)
    painter.drawText(20, 20 + 240, 400, 30, Qt.AlignCenter, "Loading...")

    painter.end()

    # Create frameless splash screen
    splash = QSplashScreen(splash_pix, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)

    # Add drop shadow effect
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(30)
    shadow.setColor(QColor(0, 0, 0, 140))
    shadow.setOffset(0, 6)
    splash.setGraphicsEffect(shadow)

    return splash


def main():
    """
    Launch the GUI application.

    Returns:
        int: Application exit code
    """
    import multiprocessing
    import logging
    from logging.handlers import RotatingFileHandler

    # CRITICAL: Required for PyInstaller + multiprocessing on Windows
    # Without this, worker processes will spawn new GUI windows when using ProcessPoolExecutor
    multiprocessing.freeze_support()

    # Configure logging: DEBUG to file, INFO to console
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    log_file = Path.home() / ".ankigammon" / "ankigammon.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        str(log_file), maxBytes=1_000_000, backupCount=3, encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    set_windows_app_id()

    # High DPI scaling configuration
    # Note: AA_EnableHighDpiScaling and AA_UseHighDpiPixmaps are deprecated in Qt6
    # (enabled by default), so we only set the rounding policy
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("AnkiGammon")
    app.setOrganizationName("AnkiGammon")
    app.setOrganizationDomain("github.com/Deinonychus999/AnkiGammon")

    # Use Fusion style for consistent cross-platform appearance
    app.setStyle('Fusion')

    # Set platform-specific application icon
    # macOS: .icns, Windows: .ico, Linux: .png
    if sys.platform == 'darwin':
        icon_file = "ankigammon/gui/resources/icon.icns"
    elif sys.platform == 'win32':
        icon_file = "ankigammon/gui/resources/icon.ico"
    else:
        icon_file = "ankigammon/gui/resources/icon.png"

    icon_path = get_resource_path(icon_file)
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # PyInstaller's bootloader native splash is injected as the `pyi_splash`
    # module on Windows/Linux frozen builds. When present it has been visible
    # since onefile extraction began, so we skip the Qt splash to avoid a
    # visible swap. macOS bundles and dev runs fall through to the Qt splash.
    try:
        import pyi_splash  # type: ignore[import-not-found]
        native_splash_active = pyi_splash.is_alive()
    except (ImportError, ModuleNotFoundError):
        pyi_splash = None
        native_splash_active = False

    splash = None
    if not native_splash_active:
        splash_icon_path = get_resource_path("ankigammon/gui/resources/icon.png")
        splash = create_splash_screen(splash_icon_path)
        splash.show()
        app.processEvents()

    # Load and apply stylesheet
    style_path = get_resource_path("ankigammon/gui/resources/style.qss")
    if style_path.exists():
        with open(style_path, encoding='utf-8') as f:
            app.setStyleSheet(f.read())

    settings = get_settings()
    window = MainWindow(settings)

    if splash is not None:
        splash.finish(window)
    window.show()

    if native_splash_active and pyi_splash is not None:
        pyi_splash.close()

    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
