"""
One-shot generator for ankigammon/gui/resources/splash.png.

The PyInstaller native splash is a static PNG drawn by the bootloader (Tk-based)
before Python starts. It cannot use Qt-rendered transparency or rounded corners
across all platforms, so this PNG bakes a solid 400x300 design without alpha.

Run when the splash design changes:
    python scripts/generate_splash_png.py

Then rebuild the bundle. The Qt splash in app.py keeps its own design for the
dev / macOS paths.
"""
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import (
    QColor, QFont, QFontDatabase, QLinearGradient, QPainter,
    QPainterPath, QPen, QPixmap,
)
from PySide6.QtWidgets import QApplication


REPO_ROOT = Path(__file__).resolve().parent.parent
ICON_PATH = REPO_ROOT / "ankigammon" / "gui" / "resources" / "icon.png"
OUT_PATH = REPO_ROOT / "ankigammon" / "gui" / "resources" / "splash.png"

WIDTH, HEIGHT = 400, 300


def render() -> QPixmap:
    pix = QPixmap(WIDTH, HEIGHT)
    pix.fill(QColor("#1e1e2e"))

    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    painter.setRenderHint(QPainter.TextAntialiasing)

    rect = QRectF(0, 0, WIDTH, HEIGHT)
    gradient = QLinearGradient(0, 0, 0, HEIGHT)
    gradient.setColorAt(0.0, QColor("#1e1e2e"))
    gradient.setColorAt(0.3, QColor("#262637"))
    gradient.setColorAt(0.7, QColor("#262637"))
    gradient.setColorAt(1.0, QColor("#1e1e2e"))
    painter.fillRect(rect, gradient)

    if ICON_PATH.exists():
        icon = QPixmap(str(ICON_PATH))
        size = 120
        scaled = icon.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        x = (WIDTH - scaled.width()) // 2
        painter.drawPixmap(x, 52, scaled)

    border = QPainterPath()
    border.addRect(rect.adjusted(1.5, 1.5, -1.5, -1.5))
    pen = QPen(QColor("#89b4fa"), 2.5)
    pen.setJoinStyle(Qt.MiterJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(border)

    families = QFontDatabase.families()
    title_family = next(
        (f for f in ("Segoe UI", "Helvetica Neue", "Arial", "DejaVu Sans") if f in families),
        QFont().defaultFamily(),
    )

    painter.setPen(QColor("#f5e0dc"))
    title_font = QFont(title_family, 24, QFont.Bold)
    title_font.setLetterSpacing(QFont.AbsoluteSpacing, 0.5)
    painter.setFont(title_font)
    painter.drawText(0, 182, WIDTH, 40, Qt.AlignCenter, "AnkiGammon")

    painter.setPen(QColor("#b4befe"))
    painter.setFont(QFont(title_family, 10))
    painter.drawText(0, 227, WIDTH, 20, Qt.AlignCenter, "Backgammon Analysis to Flashcards")

    painter.end()
    return pix


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    pix = render()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not pix.save(str(OUT_PATH), "PNG"):
        print(f"FAILED to write {OUT_PATH}", file=sys.stderr)
        return 1
    print(f"Wrote {OUT_PATH} ({OUT_PATH.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
