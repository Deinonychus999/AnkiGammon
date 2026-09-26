"""
Render every raster app icon from ankigammon/gui/resources/icon.svg.

Run when the logo changes:
    python scripts/generate_icons.py
    python scripts/generate_splash_png.py
    python scripts/generate_icons.py --website ../xg2anki-website/website/public

Each size is rendered from the vector rather than downscaled from 512px, so
the 16-48px icons keep crisp outlines and pips.
"""
import argparse
import io
import shutil
import sys
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QBuffer, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication


REPO_ROOT = Path(__file__).resolve().parent.parent
RESOURCES = REPO_ROOT / "ankigammon" / "gui" / "resources"
SVG_PATH = RESOURCES / "icon.svg"

ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
FAVICON_SIZES = (16, 32, 48)
ICNS_SIZES = (16, 32, 64, 128, 256, 512, 1024)

# Maskable icons get cropped to a circle as small as 80% of the width, so the
# mark sits inside that zone on the trainer's theme color. iOS only rounds the
# corners of apple-touch-icon and fills transparency with black.
TILE_BG = "#121212"
MASKABLE_SCALE = 0.62
APPLE_TOUCH_SCALE = 0.78


def render(renderer: QSvgRenderer, size: int, scale: float = 1.0, background: str = "") -> Image.Image:
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(QColor(background) if background else Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    inner = size * scale
    offset = (size - inner) / 2
    renderer.render(painter, QRectF(offset, offset, inner, inner))
    painter.end()

    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, "PNG")
    return Image.open(io.BytesIO(bytes(buffer.data()))).convert("RGBA")


def save_ico(renderer: QSvgRenderer, path: Path, sizes: tuple) -> None:
    images = [render(renderer, s) for s in sizes]
    images[-1].save(path, format="ICO", sizes=[(s, s) for s in sizes], append_images=images[:-1])


def write_app_icons(renderer: QSvgRenderer) -> None:
    render(renderer, 512).save(RESOURCES / "icon.png", optimize=True)
    save_ico(renderer, RESOURCES / "icon.ico", ICO_SIZES)
    icns = [render(renderer, s) for s in ICNS_SIZES]
    icns[-1].save(RESOURCES / "icon.icns", format="ICNS", append_images=icns[:-1])
    print(f"Wrote icon.png, icon.ico, icon.icns in {RESOURCES}")


def write_website_icons(renderer: QSvgRenderer, public: Path) -> None:
    images = public / "assets" / "images"
    if not images.is_dir():
        raise SystemExit(f"Not a website public/ folder: {public}")
    shutil.copyfile(SVG_PATH, images / "icon.svg")
    render(renderer, 32).save(images / "icon.png", optimize=True)
    render(renderer, 64).save(images / "icon.webp", lossless=True)
    render(renderer, 100).save(images / "icon-og.webp", lossless=True)
    render(renderer, 192).save(images / "icon-192.png", optimize=True)
    render(renderer, 512).save(images / "icon-512.png", optimize=True)
    for size in (192, 512):
        render(renderer, size, MASKABLE_SCALE, TILE_BG).save(
            images / f"icon-maskable-{size}.png", optimize=True)
    render(renderer, 180, APPLE_TOUCH_SCALE, TILE_BG).save(images / "apple-touch-icon.png", optimize=True)
    save_ico(renderer, public / "favicon.ico", FAVICON_SIZES)
    print(f"Wrote website icons in {images} and {public / 'favicon.ico'}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--website", type=Path, help="website public/ folder to write site icons into")
    args = parser.parse_args()

    app = QApplication.instance() or QApplication(sys.argv)
    renderer = QSvgRenderer(str(SVG_PATH))
    if not renderer.isValid():
        print(f"Could not read {SVG_PATH}", file=sys.stderr)
        return 1

    if args.website:
        write_website_icons(renderer, args.website.resolve())
    else:
        write_app_icons(renderer)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
