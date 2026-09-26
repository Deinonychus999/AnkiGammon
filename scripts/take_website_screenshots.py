"""Regenerate the screenshots in the ankigammon.com "See It In Action" carousel.

Drives the real app and the real Anki, then writes each image as .webp:

    python scripts/take_website_screenshots.py                  # everything
    python scripts/take_website_screenshots.py --skip-anki      # app windows only
    python scripts/take_website_screenshots.py --only settings,edit-note
    python scripts/take_website_screenshots.py --out some/dir   # review before installing

Windows only, and needs GnuBG (score matrix), Anki with AnkiConnect, and the
websocket-client package. App windows are captured from the screen, so each
one is raised on top for a few seconds - leave the desktop alone while it
runs. Anki shots are cropped to the card itself, captured from the page.

The app runs against a throwaway home directory and QSettings store, so the
user's settings, saved decks and window geometry are never read or written.

Anki is driven through AnkiConnect plus Chromium's DevTools port on its main
web view: AnkiConnect's guiDeckReview races Anki's own overview refresh and
leaves the overview page on screen, so review is started the way the Study
Now button does it, by running pycmd('study') in the page. The DevTools port
only exists when Anki starts with QTWEBENGINE_REMOTE_DEBUGGING set, so the
script starts Anki itself; pass --restart-anki to let it close an Anki that
is already running without the port. Cards go into a temporary deck that is
deleted afterwards, and an Anki the script started is closed again.
"""

import argparse
import ctypes
import ctypes.wintypes as wt
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_OUT = REPO.parent / "xg2anki-website" / "website" / "public" / "assets" / "images"
SAMPLE_MATCH = REPO / "tests" / "data" / "sample_match.xg"
GNUBG_EXE = "D:/Program Files (x86)/gnubg/gnubg-cli.exe"

# Indices into sample_match.xg, a 7-point match between "Player One" and
# "Player Two": a 0.433 checker blunder, and a 4-away/3-away double whose
# score falls inside a 5-away score matrix, so its cell is highlighted.
CHECKER_INDEX = 200
CUBE_INDEX = 319

# A study note for the CHECKER_INDEX position, written like a player's own.
CHECKER_NOTE = (
    "Red has two blots in my zone, on my bar point and my ace point. 6/1* 4/1 hits "
    "and closes the ace point: red has to come in against a 3-point board, and the "
    "blot on my 7 is still hanging.\n\n"
    "24/21 13/8 would be a fine quiet play, but here it lets red off the hook: both "
    "red blots survive and red gets a free roll to tidy them up. It also halves my "
    "gammons (26% down to 13%).\n\n"
    "When the opponent has blots in my home board, attack first; the quiet play can wait."
)

TEMP_DECK = "AnkiGammon Screenshots (temp)"
ANKI_DEVTOOLS_PORT = 9229
# Wide enough for the card back's two-column layout: board beside analysis.
ANKI_WINDOW_SIZE = (1500, 1180)
CARD_PADDING = 24

APP_SHOTS = ["main-window", "add-positions", "drag-and-drop", "edit-note", "settings"]
ANKI_SHOTS = ["anki-front", "anki-back", "anki-note", "score-matrix"]

_REAL_ENV = dict(os.environ)
# Must run before ankigammon is imported: Settings and the deck store resolve
# Path.home() on first use.
_TEMP_HOME = tempfile.mkdtemp(prefix="ankigammon-shots-")
os.environ["USERPROFILE"] = os.environ["HOME"] = _TEMP_HOME
sys.path.insert(0, str(REPO))

from PIL import Image, ImageGrab  # noqa: E402
from PySide6.QtCore import QEventLoop, QSettings, Qt, QTimer  # noqa: E402
from PySide6.QtGui import QIcon  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi
user32.SetWindowPos.argtypes = [wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.UINT]
user32.MoveWindow.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.BOOL]
user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
SWP_NOMOVE, SWP_NOSIZE, SWP_SHOWWINDOW = 0x2, 0x1, 0x40
SW_RESTORE = 9
WM_CLOSE = 0x10
DWMWA_EXTENDED_FRAME_BOUNDS = 9


def wait(ms: int) -> None:
    """Let Qt paint and deliver signals while we wait."""
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def wait_until(predicate, timeout_ms: int = 20000, step_ms: int = 150, what: str = "the window") -> None:
    deadline = time.monotonic() + timeout_ms / 1000
    while not predicate():
        if time.monotonic() > deadline:
            raise TimeoutError(f"timed out waiting for {what}")
        wait(step_ms)


def window_rect(hwnd: int) -> tuple:
    """Visible frame bounds; GetWindowRect includes the invisible resize border."""
    rect = wt.RECT()
    dwmapi.DwmGetWindowAttribute(
        wt.HWND(hwnd), DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect), ctypes.sizeof(rect)
    )
    return rect.left, rect.top, rect.right, rect.bottom


def set_topmost(hwnd: int, topmost: bool) -> None:
    after = HWND_TOPMOST if topmost else HWND_NOTOPMOST
    user32.SetWindowPos(hwnd, after, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)


def grab(hwnd: int) -> Image.Image:
    # The outer pixel is Windows' translucent window border, tinted by whatever is behind.
    left, top, right, bottom = window_rect(hwnd)
    return ImageGrab.grab(bbox=(left + 1, top + 1, right - 1, bottom - 1), all_screens=True)


def grab_on_top(hwnd: int, settle_ms: int = 600) -> Image.Image:
    set_topmost(hwnd, True)
    wait(settle_ms)
    try:
        return grab(hwnd)
    finally:
        set_topmost(hwnd, False)


def save_webp(image: Image.Image, out_dir: Path, name: str) -> None:
    path = out_dir / f"{name}.webp"
    image.convert("RGB").save(path, "WEBP", quality=85, method=6)
    print(f"  {path.name} {image.size[0]}x{image.size[1]}")


# --- sample data -----------------------------------------------------------

def load_match():
    from ankigammon.parsers.xg_binary_parser import XGBinaryParser
    return XGBinaryParser.parse_file(str(SAMPLE_MATCH))


def played_move(decision):
    return next(m for m in decision.candidate_moves if m.was_played)


def xg_text_export(decision, note: str) -> str:
    """Render a checker-play decision the way XG's copied analysis text looks.

    Only valid for an XGID with X on roll, where uppercase letters are X's
    checkers and index i is point i.
    """
    xgid = decision.xgid
    fields = xgid.split("=", 1)[1].split(":")
    board = fields[0]
    assert int(fields[3]) == 1, "xg_text_export expects X on roll"

    def count(ch):
        return 0 if ch == "-" else ord(ch.lower()) - ord("a") + 1

    def owner(ch):
        return None if ch == "-" else ("X" if ch.isupper() else "O")

    pip_x = sum(i * count(board[i]) for i in range(1, 25) if owner(board[i]) == "X") + 25 * count(board[25])
    pip_o = sum((25 - i) * count(board[i]) for i in range(1, 25) if owner(board[i]) == "O") + 25 * count(board[0])

    def half(points, row):
        return "  ".join(owner(board[p]) if count(board[p]) > row else " " for p in points)

    lines = [" +13-14-15-16-17-18------19-20-21-22-23-24-+"]
    for row in range(5):
        lines.append(f" | {half(range(13, 19), row)} |   | {half(range(19, 25), row)} |")
    lines.append(" |                  |BAR|                  |")
    for row in reversed(range(5)):
        lines.append(f" | {half(range(12, 6, -1), row)} |   | {half(range(6, 0, -1), row)} |")
    lines.append(" +12-11-10--9--8--7-------6--5--4--3--2--1-+")

    score_x, score_o, length = decision.score_x, decision.score_o, decision.match_length
    text = [
        xgid, "",
        "X:Player Two   O:Player One",
        f"Score is X:{score_x} O:{score_o} {length} pt.(s) match.",
        *lines,
        f"Pip count  X: {pip_x}  O: {pip_o} X-O: {score_x}-{score_o}/{length}",
        f"Cube: {decision.cube_value}",
        f"X to play {''.join(str(d) for d in decision.dice)}", "",
    ]
    moves = sorted(decision.candidate_moves, key=lambda m: m.rank)[:5]
    for i, move in enumerate(moves, 1):
        eq = f"eq:{move.equity:+.3f}"
        if i > 1:
            eq += f" ({move.equity - moves[0].equity:+.3f})"
        text += [
            f"    {i}. {move.analysis_level or 'XG Roller++':<11} {move.notation:<28} {eq}",
            f"      Player:   {move.player_win_pct:.2f}% (G:{move.player_gammon_pct:.2f}% "
            f"B:{move.player_backgammon_pct:.2f}%)",
            f"      Opponent: {move.opponent_win_pct:.2f}% (G:{move.opponent_gammon_pct:.2f}% "
            f"B:{move.opponent_backgammon_pct:.2f}%)",
            "",
        ]
    text += ["", note, "", "eXtreme Gammon Version: 2.19.211", ""]
    return "\n".join(text)


def configure_settings():
    from ankigammon.settings import get_settings
    settings = get_settings()
    settings.check_for_updates = False
    settings.export_method = "apkg"  # no background deck sync with Anki
    settings.deck_name = "AnkiGammon"
    settings.show_options = True
    settings.interactive_moves = True
    if Path(GNUBG_EXE).exists():
        settings.analyzer_type = "gnubg"
        settings.gnubg_path = GNUBG_EXE
    return settings


# --- AnkiGammon windows ----------------------------------------------------

class AppShots:
    def __init__(self, out_dir: Path, settings, match):
        from ankigammon.gui.main_window import MainWindow

        self.out = out_dir
        self.settings = settings
        self.match = match
        self.window = MainWindow(settings)
        self.window.resize(1300, 720)
        self.window.move(80, 60)
        self.window.show()
        self.wait_preview()

    def wait_preview(self) -> None:
        w = self.window
        wait_until(lambda: not w._preview_load_in_flight and w._pending_preview_html is None,
                   what="the board preview")
        wait(900)

    def grab(self, widget, name: str, settle_ms: int = 600) -> None:
        save_webp(grab_on_top(int(widget.winId()), settle_ms), self.out, name)

    def import_match(self) -> None:
        """Import the sample match's mistakes, split into checker and cube subdecks."""
        from ankigammon.models import DecisionType
        w = self.window
        w._in_batch_import = True  # suppresses the "Import Successful" message box
        w._import_file(str(SAMPLE_MATCH), options={
            "checker_threshold": 0.08,
            "cube_threshold": 0.08,
            "selected_player_names": None,
        })
        w._in_batch_import = False
        root = self.settings.deck_name
        imported = w.deck_manager.get_all_decisions()
        for deck, kind in ((f"{root}::Checker Play", DecisionType.CHECKER_PLAY),
                           (f"{root}::Cube Decisions", DecisionType.CUBE_ACTION)):
            w.deck_manager.create_deck(deck)
            w.deck_manager.move_decisions([d for d in imported if d.decision_type == kind], deck)
        w.deck_tree.rebuild_tree()

    def select(self, decision) -> None:
        self.window.deck_tree.select_decision(decision)
        self.window.show_decision(decision)
        self.wait_preview()

    def shot_drag_and_drop(self) -> None:
        self.window._show_drop_overlay()
        wait(300)
        self.grab(self.window, "drag-and-drop")
        self.window._hide_drop_overlay()

    def shot_main_window(self, checker) -> None:
        self.window.change_color_scheme("ocean")
        self.select(checker)
        self.grab(self.window, "main-window")

    def shot_edit_note(self, checker) -> None:
        from ankigammon.gui.dialogs.note_dialog import NoteEditDialog
        self.window.change_color_scheme("forest")
        self.select(checker)
        manager = self.window.deck_manager
        deck = next(name for name, decs in manager.get_grouped_decisions().items()
                    if any(d is checker for d in decs))
        number = next(i for i, d in enumerate(manager.get_deck_decisions(deck), 1) if d is checker)
        dialog = NoteEditDialog(CHECKER_NOTE, f"Note for position #{number}:", self.window)
        dialog.setModal(False)
        dialog.resize(560, 330)
        geo = self.window.frameGeometry()
        dialog.move(geo.x() + 400, geo.y() + 190)
        dialog.show()
        back, front = int(self.window.winId()), int(dialog.winId())
        set_topmost(back, True)
        set_topmost(front, True)
        wait(600)
        try:
            save_webp(grab(back), self.out, "edit-note")
        finally:
            set_topmost(front, False)
            set_topmost(back, False)
        dialog.close()

    def shot_settings(self) -> None:
        from ankigammon.gui.dialogs.settings_dialog import SettingsDialog
        # Show the defaults users see; apkg was only to keep the window off AnkiConnect.
        self.settings.export_method = "ankiconnect"
        self.settings.generate_score_matrix = True
        dialog = SettingsDialog(self.settings, self.window)
        dialog.setModal(False)
        dialog.show()
        wait(1500)  # GnuBG validation runs in a worker thread
        self.grab(dialog, "settings")
        dialog.close()

    def shot_add_positions(self, checker) -> None:
        from ankigammon.gui.dialogs.input_dialog import InputDialog
        self.settings.color_scheme = "desert"
        dialog = InputDialog(self.settings, self.window)
        dialog.setModal(False)
        dialog.show()
        text = xg_text_export(checker, CHECKER_NOTE)
        smart = dialog.input_widget
        smart.text_area.setPlainText(text)
        wait_until(lambda: smart.get_last_result() is not None, what="format detection")
        dialog._on_add_clicked()
        wait_until(lambda: dialog.pending_decisions, what="the pending list")
        # Adding clears the input; paste again so the shot shows the text and its detection.
        smart.last_result = None
        smart.text_area.setPlainText(text)
        wait_until(lambda: smart.get_last_result() is not None, what="format detection")
        wait(1800)
        self.grab(dialog, "add-positions")
        dialog.close()


def run_app_shots(out_dir: Path, only: set, settings, match) -> None:
    shots = AppShots(out_dir, settings, match)
    checker = match[CHECKER_INDEX]
    # Before importing: the drop hint reads best over the empty-state screen.
    if "drag-and-drop" in only:
        shots.shot_drag_and_drop()
    shots.import_match()
    in_tree = next(d for d in shots.window.deck_manager.get_all_decisions() if d.xgid == checker.xgid)
    if "main-window" in only:
        shots.shot_main_window(in_tree)
    if "edit-note" in only:
        shots.shot_edit_note(in_tree)
    if "settings" in only:
        shots.shot_settings()
    if "add-positions" in only:
        shots.shot_add_positions(checker)
    shots.window.hide()


# --- Anki -----------------------------------------------------------------

def anki_exe() -> Path:
    local = Path(_REAL_ENV.get("LOCALAPPDATA", ""))
    candidates = [
        _REAL_ENV.get("ANKI_EXE"),
        local / "AnkiProgramFiles" / ".venv" / "Scripts" / "ankiw.exe",  # 25.x launcher install
        local / "Programs" / "Anki" / "anki.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return Path(candidate)
    raise SystemExit("Anki not found; set ANKI_EXE to its executable")


class Anki:
    def __init__(self):
        from ankigammon.anki.ankiconnect import AnkiConnect
        self.connect = AnkiConnect(deck_name=TEMP_DECK)
        self.started_here = False
        self.hwnd = None
        self.saved_rect = None

    def call(self, action: str, **params):
        return self.connect.invoke(action, **params)

    def connect_up(self) -> bool:
        try:
            return self.connect.test_connection()
        except Exception:
            return False

    def devtools_targets(self):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{ANKI_DEVTOOLS_PORT}/json", timeout=2) as r:
                return json.load(r)
        except OSError:
            return None

    def start(self, restart: bool) -> None:
        if self.connect_up() and self.devtools_targets() is not None:
            self.hwnd = self.find_window()
            return
        if self.connect_up():
            if not restart:
                raise SystemExit(
                    "Anki is running without its DevTools port. Close Anki, or rerun "
                    "with --restart-anki to let this script restart it."
                )
            hwnd = self.find_window()
            user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
            wait_until(lambda: not self.connect_up(), timeout_ms=60000, what="Anki to close")
            wait(2000)
        env = dict(_REAL_ENV, QTWEBENGINE_REMOTE_DEBUGGING=str(ANKI_DEVTOOLS_PORT))
        subprocess.Popen([str(anki_exe())], env=env)
        self.started_here = True
        wait_until(lambda: self.connect_up() and self.devtools_targets(), timeout_ms=90000,
                   what="Anki to start")
        self.hwnd = self.find_window()

    def find_window(self) -> int:
        found = []

        @ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
        def visit(hwnd, _):
            title = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, title, 256)
            if user32.IsWindowVisible(hwnd) and title.value.endswith(" - Anki"):
                found.append(hwnd)
            return True

        user32.EnumWindows(visit, 0)
        if not found:
            raise RuntimeError("Anki's main window not found")
        return found[0]

    def devtools(self, method: str, **params) -> dict:
        """Send one DevTools command to Anki's main web view (reviewer, overview...)."""
        import websocket
        target = next(t for t in self.devtools_targets() if t.get("title") == "main webview")
        ws = websocket.create_connection(target["webSocketDebuggerUrl"], suppress_origin=True, timeout=30)
        try:
            ws.send(json.dumps({"id": 1, "method": method, "params": params}))
            reply = json.loads(ws.recv())
        finally:
            ws.close()
        if "error" in reply:
            raise RuntimeError(f"DevTools {method}: {reply['error']}")
        return reply["result"]

    def page_eval(self, expression: str):
        return self.devtools("Runtime.evaluate", expression=expression,
                             returnByValue=True)["result"].get("value")

    def shot(self, out_dir: Path, name: str, card_selector: str) -> None:
        """Capture only the card: the card's visible children minus the source/XGID footer."""
        import base64
        import io
        box = self.page_eval(f"""(() => {{
            const parts = [...document.querySelector({json.dumps(card_selector)}).children].filter(
                e => e.tagName !== 'SCRIPT' && !e.matches('.source-info')
                     && !e.querySelector('.xgid-container') && e.getBoundingClientRect().height > 0);
            const rects = parts.map(e => e.getBoundingClientRect());
            const left = Math.min(...rects.map(r => r.left)), top = Math.min(...rects.map(r => r.top));
            const right = Math.max(...rects.map(r => r.right)), bottom = Math.max(...rects.map(r => r.bottom));
            return {{x: left + scrollX, y: top + scrollY, width: right - left, height: bottom - top}};
        }})()""")
        pad = CARD_PADDING
        clip = {"x": max(0, box["x"] - pad), "y": max(0, box["y"] - pad),
                "width": box["width"] + 2 * pad, "height": box["height"] + 2 * pad, "scale": 1}
        png = self.devtools("Page.captureScreenshot", format="png", clip=clip,
                            captureBeyondViewport=True)["data"]
        image = Image.open(io.BytesIO(base64.b64decode(png))).convert("RGB")
        save_webp(trim_bottom_padding(image, content_bottom=pad + round(box["height"])), out_dir, name)

    def prepare_window(self) -> None:
        rect = wt.RECT()
        user32.GetWindowRect(self.hwnd, ctypes.byref(rect))
        self.saved_rect = (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)
        user32.ShowWindow(self.hwnd, SW_RESTORE)
        # The window width picks the card layout; on top, Chromium keeps the
        # move animations running instead of throttling a covered window.
        user32.MoveWindow(self.hwnd, 60, 30, *ANKI_WINDOW_SIZE, True)
        set_topmost(self.hwnd, True)

    def restore_window(self) -> None:
        if self.hwnd is None or self.saved_rect is None:
            return
        set_topmost(self.hwnd, False)
        user32.MoveWindow(self.hwnd, *self.saved_rect, True)

    def review(self, deck: str) -> None:
        self.call("guiDeckOverview", name=deck)
        wait(2000)  # the overview renders asynchronously; let it land first
        self.page_eval("pycmd('study')")
        wait_until(lambda: self.page_eval("!!document.querySelector('.card-front')"),
                   what="the card front")
        wait(1500)

    def show_answer(self, choice=None) -> None:
        if choice:
            # The front's click handler stores the pick here before flipping.
            self.page_eval(f"document.body.dataset.ankigammonChoice = '{choice}'")
        self.call("guiShowAnswer")
        wait_until(lambda: self.page_eval("!!document.querySelector('.card-back')"),
                   what="the card back")
        wait(2500)  # the best move animates onto the board

    def stop(self) -> None:
        self.restore_window()
        try:
            self.call("deleteDecks", decks=[TEMP_DECK], cardsToo=True)
            self.call("guiDeckBrowser")
        except Exception as e:
            print(f"  could not delete the temporary deck '{TEMP_DECK}': {e}")
        if self.started_here:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)


def make_card(decision, scheme: str, settings, workdir: Path, score_matrix: bool = False) -> dict:
    from ankigammon.anki.card_generator import CardGenerator
    settings.color_scheme = scheme
    settings.generate_score_matrix = score_matrix
    settings.score_matrix_max_size = 5
    settings.gnubg_analysis_ply = 2
    generator = CardGenerator(output_dir=workdir, show_options=True, interactive_moves=True)
    card = generator.generate_card(decision)
    if generator.generation_warnings:
        print("  warnings:", *generator.generation_warnings, sep="\n    ")
    return card


def trim_bottom_padding(image: Image.Image, content_bottom: int) -> Image.Image:
    """End the bottom padding before whatever follows the card, e.g. the XGID box's border."""
    background = image.getpixel((1, 1))
    # Start a little below the content so its own antialiased bottom border isn't mistaken.
    for y in range(content_bottom + 3, image.height):
        row = (image.getpixel((x, y)) for x in range(image.width))
        if any(sum(abs(a - b) for a, b in zip(pixel, background)) > 24 for pixel in row):
            return image.crop((0, 0, image.width, y - 2))
    return image


def option_letter(front_html: str, notation: str) -> str:
    import html
    import re
    for letter, move in re.findall(r"data-option-letter='([A-E])' data-move-notation='([^']*)'", front_html):
        if html.unescape(move) == notation:
            return letter
    raise ValueError(f"{notation} is not among the card's options")


def run_anki_shots(out_dir: Path, only: set, settings, match, restart: bool) -> None:
    checker, cube = match[CHECKER_INDEX], match[CUBE_INDEX]
    checker.note = CHECKER_NOTE
    workdir = Path(_TEMP_HOME) / "cards"
    print("generating cards (the score matrix runs GnuBG; this takes a minute)")
    cards = {
        "Checker": make_card(checker, "midnight", settings, workdir),
        "Cube": make_card(cube, "sunset", settings, workdir, score_matrix=True),
    }

    anki = Anki()
    anki.start(restart)
    if TEMP_DECK in anki.call("deckNames"):
        anki.call("deleteDecks", decks=[TEMP_DECK], cardsToo=True)  # left over from a failed run
    try:
        anki.connect.create_model()
        for sub, card in cards.items():
            deck = f"{TEMP_DECK}::{sub}"
            anki.connect.create_deck(deck)
            anki.connect.add_note(front=card["front"], back=card["back"], tags=card["tags"],
                                  deck_name=deck, xgid=card.get("xgid", ""),
                                  analysis_data=card.get("analysis_data", ""))
        anki.prepare_window()

        if only & {"anki-front", "anki-back", "anki-note"}:
            anki.review(f"{TEMP_DECK}::Checker")
            if "anki-front" in only:
                anki.shot(out_dir, "anki-front", ".card-front")
            anki.show_answer(option_letter(cards["Checker"]["front"], played_move(checker).notation))
            if "anki-back" in only:
                anki.shot(out_dir, "anki-back", ".card-back")
            if "anki-note" in only:
                anki.page_eval("document.querySelectorAll('.move-row')[1].click()")
                wait(2500)
                anki.shot(out_dir, "anki-note", ".card-back")

        if "score-matrix" in only:
            anki.review(f"{TEMP_DECK}::Cube")
            anki.show_answer()
            anki.shot(out_dir, "score-matrix", ".card-back")
    finally:
        anki.stop()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--only", help="comma-separated shot names: " + ", ".join(APP_SHOTS + ANKI_SHOTS))
    parser.add_argument("--skip-anki", action="store_true")
    parser.add_argument("--restart-anki", action="store_true",
                        help="close a running Anki that lacks the DevTools port and start it with it")
    args = parser.parse_args()

    only = set(args.only.split(",")) if args.only else set(APP_SHOTS + ANKI_SHOTS)
    unknown = only - set(APP_SHOTS + ANKI_SHOTS)
    if unknown:
        parser.error(f"unknown shot(s): {', '.join(sorted(unknown))}")
    if args.skip_anki:
        only -= set(ANKI_SHOTS)
    args.out.mkdir(parents=True, exist_ok=True)

    from ankigammon.gui.app import load_stylesheet, set_windows_app_id, get_resource_path

    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, _TEMP_HOME)
    set_windows_app_id()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("AnkiGammon")
    app.setOrganizationName("AnkiGammon")
    app.setStyle("Fusion")
    # As on a dark-mode desktop: Qt then gives every window a dark title bar.
    app.styleHints().setColorScheme(Qt.ColorScheme.Dark)
    app.setWindowIcon(QIcon(str(get_resource_path("ankigammon/gui/resources/icon.ico"))))
    app.setStyleSheet(load_stylesheet())

    settings = configure_settings()
    match = load_match()
    try:
        if only & set(APP_SHOTS):
            print("AnkiGammon windows")
            run_app_shots(args.out, only, settings, match)
        if only & set(ANKI_SHOTS):
            print("Anki")
            run_anki_shots(args.out, only, settings, match, args.restart_anki)
    finally:
        shutil.rmtree(_TEMP_HOME, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
