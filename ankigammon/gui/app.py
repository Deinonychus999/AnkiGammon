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
    Set Windows AppUserModelID to show custom icon in taskbar.

    This fixes the issue where Python scripts show the Python icon
    in the Windows taskbar instead of the application's custom icon.
    """
    if sys.platform == 'win32':
        try:
            import ctypes
            # Set unique AppUserModelID for this application
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('AnkiGammon.GUI.1.0')
        except Exception:
            # Silently fail if setting AppUserModelID doesn't work
            pass


def create_splash_screen(icon_path: Path) -> QSplashScreen:
    """
    Create a beautiful splash screen with modern styling.

    Features:
    - Rounded corners for modern appearance
    - Gradient background for depth
    - Fancy border with brand color
    - Drop shadow for elevation
    - High-quality antialiasing

    Args:
        icon_path: Path to the application icon

    Returns:
        QSplashScreen: Configured splash screen with modern styling
    """
    # Create larger pixmap to accommodate drop shadow margin
    splash_pix = QPixmap(440, 340)
    splash_pix.fill(Qt.transparent)  # Transparent background for rounded corners

    # Initialize painter with high-quality rendering
    painter = QPainter(splash_pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    painter.setRenderHint(QPainter.TextAntialiasing)

    # Define rounded rectangle with margin for shadow (20px margin on all sides)
    rect = QRectF(20, 20, 400, 300)
    corner_radius = 12

    # Create path for rounded rectangle
    path = QPainterPath()
    path.addRoundedRect(rect, corner_radius, corner_radius)

    # Apply elegant gradient background (subtle top-to-bottom variation)
    gradient = QLinearGradient(20, 20, 20, 320)
    gradient.setColorAt(0.0, QColor("#1e1e2e"))  # Dark blue-gray at top
    gradient.setColorAt(0.3, QColor("#262637"))  # Slightly lighter in middle
    gradient.setColorAt(0.7, QColor("#262637"))  # Maintain middle tone
    gradient.setColorAt(1.0, QColor("#1e1e2e"))  # Return to dark at bottom
    painter.fillPath(path, gradient)

    # Load and draw the dice icon from the icon file
    if icon_path.exists():
        icon_pixmap = QPixmap(str(icon_path))
        # Scale to a good size for the splash screen (120px width)
        icon_size = 120
        scaled_icon = icon_pixmap.scaled(icon_size, icon_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        # Center the icon in the upper portion
        icon_x = 20 + (400 - scaled_icon.width()) // 2
        icon_y = 20 + 40  # Position higher on the splash screen

        painter.drawPixmap(icon_x, icon_y, scaled_icon)

    # Draw fancy border with brand color (blue from Catppuccin palette)
    border_pen = QPen(QColor("#89b4fa"), 2.5)  # 2.5px blue border
    border_pen.setJoinStyle(Qt.RoundJoin)  # Smooth corner joins
    border_pen.setCapStyle(Qt.RoundCap)    # Smooth line caps
    painter.setPen(border_pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(path)

    # Draw application name with elegant typography
    painter.setPen(QColor("#f5e0dc"))  # Warm white text
    title_font = QFont("Segoe UI", 24, QFont.Bold)
    title_font.setLetterSpacing(QFont.AbsoluteSpacing, 0.5)  # Slight letter spacing
    painter.setFont(title_font)
    painter.drawText(20, 20 + 170, 400, 40, Qt.AlignCenter, "AnkiGammon")

    # Draw subtle tagline
    painter.setPen(QColor("#b4befe"))  # Lighter blue for accent
    tagline_font = QFont("Segoe UI", 10)
    painter.setFont(tagline_font)
    painter.drawText(20, 20 + 215, 400, 20, Qt.AlignCenter, "Backgammon Analysis to Flashcards")

    # Draw loading indicator
    painter.setPen(QColor("#a6adc8"))  # Muted gray-blue
    loading_font = QFont("Segoe UI", 11)
    painter.setFont(loading_font)
    painter.drawText(20, 20 + 240, 400, 30, Qt.AlignCenter, "Loading...")

    painter.end()

    # Create frameless splash screen for clean appearance
    splash = QSplashScreen(splash_pix, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)

    # Add professional drop shadow for depth and elevation
    shadow = QGraphicsDropShadowEffect()
    shadow.setBlurRadius(30)               # Soft, diffused shadow
    shadow.setColor(QColor(0, 0, 0, 140))  # Semi-transparent black
    shadow.setOffset(0, 6)                 # Slight downward offset
    splash.setGraphicsEffect(shadow)

    return splash


def main():
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
    app.setApplicationName("AnkiGammon")
    app.setOrganizationName("AnkiGammon")
    app.setOrganizationDomain("github.com/Deinonychus999/AnkiGammon")

    # Set application style (modern, consistent across platforms)
    app.setStyle('Fusion')

    # Set application icon (use platform-specific format for best compatibility)
    # macOS requires .icns, Windows prefers .ico, Linux uses .png
    if sys.platform == 'darwin':
        icon_file = "ankigammon/gui/resources/icon.icns"
    elif sys.platform == 'win32':
        icon_file = "ankigammon/gui/resources/icon.ico"
    else:
        icon_file = "ankigammon/gui/resources/icon.png"

    icon_path = get_resource_path(icon_file)
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # Show splash screen (always use PNG for high-quality rendering at larger sizes)
    splash_icon_path = get_resource_path("ankigammon/gui/resources/icon.png")
    splash = create_splash_screen(splash_icon_path)
    splash.show()
    app.processEvents()  # Ensure splash screen is rendered

    # Load and apply stylesheet (use resource path helper for PyInstaller compatibility)
    style_path = get_resource_path("ankigammon/gui/resources/style.qss")
    if style_path.exists():
        with open(style_path, encoding='utf-8') as f:
            app.setStyleSheet(f.read())

    # Load settings
    settings = get_settings()

    # Create main window (but don't show it yet)
    window = MainWindow(settings)

    # Close splash screen and show main window after a minimum display time
    # This ensures users see the splash screen even if loading is fast
    def show_main_window():
        splash.finish(window)  # Close splash and show window
        window.show()

    # Minimum splash screen display: 1 second
    # Adjust this value as needed (1000ms = 1 second)
    QTimer.singleShot(1000, show_main_window)

    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())
