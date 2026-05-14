"""Core UI automation for eXtreme Gammon 2.

Drives XG via Win32 WM_COMMAND messages (PostMessage) using command IDs
extracted from its Delphi DFM resources. This bypasses the owner-drawn
menus that pywinauto/UIA cannot read.

pywinauto is still used for: window connection, dialog handling, and
reading standard Windows controls (edit boxes, buttons, etc.).
"""

import ctypes
import ctypes.wintypes as wt
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import pyautogui
sys.coinit_flags = 2  # COINIT_APARTMENTTHREADED — must precede pywinauto import
from pywinauto import Application
from pywinauto.findwindows import ElementNotFoundError

log = logging.getLogger(__name__)


# Lazy imports for optional dependencies
def _try_import_memory():
    try:
        from .memory import XGMemoryReader
        return XGMemoryReader
    except (ImportError, Exception):
        return None



CLASS_NAME = "TMainX"

# Win32 constants
WM_COMMAND = 0x0111
WM_CLOSE = 0x0010
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
BM_CLICK = 0x00F5
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

# Standard dialog button IDs
IDOK = 1

# Process access rights
PROCESS_TERMINATE = 0x0001

# SetWindowPos flags
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004

# ShowWindow command
SW_HIDE = 0

# Off-screen sentinel coordinate (matches Windows' own minimized-window pos)
OFFSCREEN_X = -32000
OFFSCREEN_Y = -32000

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

PostMessageW = user32.PostMessageW
PostMessageW.argtypes = [wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM]
PostMessageW.restype = wt.BOOL

SendMessageW = user32.SendMessageW
SendMessageW.argtypes = [wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM]
SendMessageW.restype = wt.LPARAM

user32.GetDlgItem.argtypes = [wt.HWND, ctypes.c_int]
user32.GetDlgItem.restype = wt.HWND

user32.SetWindowPos.argtypes = [
    wt.HWND, wt.HWND, ctypes.c_int, ctypes.c_int,
    ctypes.c_int, ctypes.c_int, ctypes.c_uint,
]
user32.SetWindowPos.restype = wt.BOOL

user32.IsWindow.argtypes = [wt.HWND]
user32.IsWindow.restype = wt.BOOL

user32.IsWindowVisible.argtypes = [wt.HWND]
user32.IsWindowVisible.restype = wt.BOOL

kernel32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel32.OpenProcess.restype = wt.HANDLE

kernel32.TerminateProcess.argtypes = [wt.HANDLE, ctypes.c_uint]
kernel32.TerminateProcess.restype = wt.BOOL

kernel32.CloseHandle.argtypes = [wt.HANDLE]
kernel32.CloseHandle.restype = wt.BOOL

kernel32.GetLastError.restype = wt.DWORD

# Clipboard API
_OpenClipboard = user32.OpenClipboard
_OpenClipboard.argtypes = [wt.HWND]
_OpenClipboard.restype = wt.BOOL
_EmptyClipboard = user32.EmptyClipboard
_CloseClipboard = user32.CloseClipboard
_SetClipboardData = user32.SetClipboardData
_SetClipboardData.argtypes = [ctypes.c_uint, wt.HANDLE]
_SetClipboardData.restype = wt.HANDLE
_GetClipboardData = user32.GetClipboardData
_GetClipboardData.argtypes = [ctypes.c_uint]
_GetClipboardData.restype = wt.HANDLE

_GlobalAlloc = kernel32.GlobalAlloc
_GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
_GlobalAlloc.restype = wt.HGLOBAL
_GlobalLock = kernel32.GlobalLock
_GlobalLock.argtypes = [wt.HGLOBAL]
_GlobalLock.restype = ctypes.c_void_p
_GlobalUnlock = kernel32.GlobalUnlock
_GlobalUnlock.argtypes = [wt.HGLOBAL]
_GlobalFree = kernel32.GlobalFree
_GlobalFree.argtypes = [wt.HGLOBAL]

WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)

# Safety: prevent PyAutoGUI from shooting off-screen
pyautogui.FAILSAFE = True


# ------------------------------------------------------------------
# XG Menu Command IDs (extracted from Delphi TMenuItem.Command)
# ------------------------------------------------------------------
# These are the wID values for WM_COMMAND, version-specific.
# Discovered by walking the VCL component tree via pymem and reading
# TMenuItem.FCommand at object offset +0x54.
#
# IDs differ between XG versions because the developer added new menu
# items, shifting the auto-assigned Delphi command IDs.

from dataclasses import dataclass


@dataclass(frozen=True)
class XGCommandProfile:
    """WM_COMMAND IDs for a specific eXtreme Gammon version."""

    version: str

    # File menu
    NEW_MATCH: int
    NEW_MONEY: int
    NEW_SETUP: int
    NEW_TRANSCRIPTION: int
    REMATCH: int
    OPEN: int
    SAVE: int
    SAVE_AS: int
    CLOSE: int

    # File > Import submenu
    IMPORT_GNUBG: int
    IMPORT_JELLYFISH: int
    IMPORT_OTHERS: int
    IMPORT_POS_CLIPBOARD: int
    IMPORT_LAST_PLAYED: int
    BATCH_IMPORT: int
    IMPORT_POS_TEXT: int

    # File > Export submenu
    EXPORT_POS_CLIPBOARD: int
    EXPORT_POS_CLIPBOARD_DLG: int
    EXPORT_XGID_CLIPBOARD: int
    EXPORT_POS_XGP: int
    EXPORT_POS_TEXT: int
    EXPORT_POS_IMAGE: int
    EXPORT_HTML: int
    EXPORT_JELLYFISH: int
    EXPORT_TEXT: int

    EXIT: int

    # Analyze menu
    ANALYZE_DOUBLE: int
    ANALYZE_POSITION: int
    ANALYZE_GAME: int
    ANALYZE_MATCH: int
    GENERATE_COMMENT: int
    SET_ANALYZE_LEVEL: int
    CLEAR_ANALYZE: int
    BATCH_ANALYZE: int


XG_PROFILES: dict[str, XGCommandProfile] = {
    "2.10": XGCommandProfile(
        version="2.10",
        NEW_MATCH=64, NEW_MONEY=65, NEW_SETUP=66, NEW_TRANSCRIPTION=67,
        REMATCH=69, OPEN=70, SAVE=92, SAVE_AS=93, CLOSE=94,
        IMPORT_GNUBG=119, IMPORT_JELLYFISH=120, IMPORT_OTHERS=121,
        IMPORT_POS_CLIPBOARD=123, IMPORT_LAST_PLAYED=124, BATCH_IMPORT=128,
        IMPORT_POS_TEXT=126,
        EXPORT_POS_CLIPBOARD=130, EXPORT_POS_CLIPBOARD_DLG=131,
        EXPORT_XGID_CLIPBOARD=132, EXPORT_POS_XGP=134,
        EXPORT_POS_TEXT=135, EXPORT_POS_IMAGE=136,
        EXPORT_HTML=138, EXPORT_JELLYFISH=139, EXPORT_TEXT=140,
        EXIT=143,
        ANALYZE_DOUBLE=265, ANALYZE_POSITION=266,
        ANALYZE_GAME=267, ANALYZE_MATCH=268,
        GENERATE_COMMENT=269, SET_ANALYZE_LEVEL=271,
        CLEAR_ANALYZE=272, BATCH_ANALYZE=281,
    ),
    "2.19": XGCommandProfile(
        version="2.19",
        NEW_MATCH=65, NEW_MONEY=66, NEW_SETUP=67, NEW_TRANSCRIPTION=68,
        REMATCH=70, OPEN=71, SAVE=93, SAVE_AS=94, CLOSE=95,
        IMPORT_GNUBG=120, IMPORT_JELLYFISH=121, IMPORT_OTHERS=122,
        IMPORT_POS_CLIPBOARD=124, IMPORT_LAST_PLAYED=125, BATCH_IMPORT=129,
        IMPORT_POS_TEXT=127,
        EXPORT_POS_CLIPBOARD=131, EXPORT_POS_CLIPBOARD_DLG=132,
        EXPORT_XGID_CLIPBOARD=133, EXPORT_POS_XGP=135,
        EXPORT_POS_TEXT=136, EXPORT_POS_IMAGE=137,
        EXPORT_HTML=139, EXPORT_JELLYFISH=140, EXPORT_TEXT=141,
        EXIT=149,
        ANALYZE_DOUBLE=268, ANALYZE_POSITION=269,
        ANALYZE_GAME=270, ANALYZE_MATCH=271,
        GENERATE_COMMENT=272, SET_ANALYZE_LEVEL=274,
        CLEAR_ANALYZE=275, BATCH_ANALYZE=284,
    ),
}

# Backward-compatible module-level alias (defaults to 2.10)
XGCmd = XG_PROFILES["2.10"]


class XGAutomationError(Exception):
    """Raised when a UI automation step fails."""


class XGAutomator:
    """Drive eXtreme Gammon 2 through its GUI."""

    # Button labels across XG's 7 supported languages:
    # English, German, French, Spanish, Japanese, Greek, Russian
    # Verified from XGLanguage/*/STRINGS.TXT (MSG DIALOG IDs 440-443)
    # and Windows common dialog locale strings.
    _BTN_OK = {"ok"}
    _BTN_YES = {
        "yes", "ja", "oui", "sí", "si", "はい", "ναι", "да",
    }
    _BTN_NO = {
        "no", "nein", "non", "いいえ", "όχι", "нет",
    }
    _BTN_CANCEL = {
        "cancel", "abbrechen", "annuler", "cancelar",
        "キャンセル", "ακύρωση",
        "отменить",  # XG custom dialog (STRINGS.TXT ID 443)
        "отмена",    # Windows common dialog
    }
    _BTN_OPEN = {
        "open", "öffnen", "ouvrir", "abrir",
        "開く", "άνοιγμα", "открыть",
    }
    _BTN_CLOSE = {
        "close", "schließen", "fermer", "cerrar",
        "閉じる", "κλείσιμο", "закрыть",
    }
    _BTN_SAVE = {
        "save", "speichern", "enregistrer", "guardar",
        "保存", "αποθήκευση", "сохранить",
    }
    _BTN_IMPORT = {
        "import", "importieren", "importer", "importar",
        "インポート", "εισαγωγή", "импорт",
    }
    _BTN_CONTINUE = {
        "continue", "weiter", "continuer", "continuar",
        "続行", "συνέχεια", "продолжить",
    }
    _BTN_HELP = {
        "help", "hilfe", "aide", "ayuda",
        "ヘルプ", "βοήθεια", "справка",
    }
    _BTN_LOAD = {
        "load", "laden", "charger", "cargar",
        "読み込む", "φόρτωση", "загрузить",
    }

    _ACCEPT_BUTTONS = (
        _BTN_OK | _BTN_YES | _BTN_OPEN | _BTN_CLOSE | _BTN_CONTINUE
        | _BTN_IMPORT | _BTN_LOAD
    )
    _REJECT_BUTTONS = _BTN_CANCEL | _BTN_NO | _BTN_CLOSE | _BTN_HELP

    # Built-in XG analysis levels, in dropdown order. Custom profiles
    # (registry slots 1..5) are appended by XG after these and are
    # discovered at runtime via CB_GETLBTEXT rather than indexed.
    BUILTIN_ANALYSIS_LEVELS = (
        "none",
        "very quick",
        "fast",
        "deep",
        "thorough",
        "world class",
        "extensive",
    )

    def __init__(
        self,
        xg_path: Path | None = None,
        backend: str = "win32",
        poll_interval: float = 3.0,
        timeout: float = 600.0,
        use_memory_reader: bool = False,
        address_map_path: Optional[Path | str] = None,
        analysis_level: Optional[str] = None,
        headless: bool = False,
    ):
        self.xg_path = xg_path
        self.backend = backend
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.use_memory_reader = use_memory_reader
        self.headless = headless
        self.address_map_path = address_map_path
        self.analysis_level = analysis_level
        self.app: Application | None = None
        self._main = None
        self._hwnd: int = 0
        self._cmd: XGCommandProfile | None = None
        self._xg_base_title: str = ""
        self._memory = None   # Optional[XGMemoryReader]
        self._current_file: Path | None = None
        # Persistent set of window handles that have no buttons and should
        # be skipped in dialog dismissal (e.g. GameDLg, Message, etc.)
        self._skip_hwnds: set[int] = set()

    @property
    def cmd(self) -> XGCommandProfile:
        """Active command profile for the connected XG version."""
        if self._cmd is None:
            return XGCmd  # fallback to 2.10 default before connect()
        return self._cmd

    def _detect_xg_version(self) -> XGCommandProfile:
        """Detect XG version from window title and return the matching profile.

        Retries briefly if the title doesn't contain a version number yet
        (XG shows a placeholder title like "eXtreme Gammon IDE" during init).
        Falls back to 2.10 if detection fails after retries.
        """
        for attempt in range(6):
            title = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(self._hwnd, title, 256)

            for version_key, profile in XG_PROFILES.items():
                if f"eXtreme Gammon {version_key}" in title.value:
                    self._xg_base_title = title.value
                    log.info(
                        "Detected XG version %s (title: %r)",
                        version_key, title.value,
                    )
                    return profile

            if attempt < 5:
                time.sleep(1.0)

        # Store whatever title we have as the base title
        self._xg_base_title = title.value
        log.warning(
            "Unknown XG version from title %r — using 2.10 profile", title.value
        )
        return XG_PROFILES["2.10"]

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Connect to a running XG instance, or launch it."""
        if self.headless:
            self._connect_headless()
            # Dismiss startup dialogs (TStartDlg, TMessageDlgG, etc.)
            # Use a settling loop — dialogs can appear after the main
            # message loop is idle, so a single pass isn't enough.
            self._wait_for_dialogs_cleared(max_wait=10.0, settle=2.0)
        else:
            self._connect_gui()
            # Initialize optional subsystems after connection
            self._setup_memory_reader()

    def _connect_gui(self) -> None:
        """Connect via pywinauto (normal GUI mode)."""
        try:
            self.app = Application(backend=self.backend).connect(
                class_name=CLASS_NAME
            )
            log.info("Connected to existing XG instance.")
        except ElementNotFoundError:
            if self.xg_path and self.xg_path.exists():
                log.info("Launching XG: %s", self.xg_path)
                subprocess.Popen([str(self.xg_path)])
                self.app = Application(backend=self.backend).connect(
                    class_name=CLASS_NAME, timeout=30
                )
                log.info("XG launched and connected.")
            else:
                raise XGAutomationError(
                    "eXtreme Gammon 2 is not running and xg_path is not set."
                )
        self._main = self.app.top_window()
        self._hwnd = self._main.handle
        self._cmd = self._detect_xg_version()

    def _kill_stale_xg_instances(self, hwnds: set[int]) -> None:
        """Terminate hidden XG instances; leave visible ones alone.

        Hidden XG windows are stale headless instances orphaned by a
        prior crashed run. Visible instances belong to the user.

        Each hwnd's class is re-validated immediately before termination
        because hwnds can be recycled to other processes between
        enumeration and the kill call.
        """
        my_pid = os.getpid()
        for stale_hwnd in hwnds:
            try:
                if user32.IsWindowVisible(stale_hwnd):
                    continue
                # Re-verify class — guards against hwnd recycling.
                cls = ctypes.create_unicode_buffer(64)
                if (user32.GetClassNameW(stale_hwnd, cls, 64) == 0
                        or cls.value != CLASS_NAME):
                    log.debug(
                        "hwnd 0x%08X no longer an XG window — skip",
                        stale_hwnd,
                    )
                    continue
                stale_pid = wt.DWORD()
                tid = user32.GetWindowThreadProcessId(
                    stale_hwnd, ctypes.byref(stale_pid)
                )
                if tid == 0 or stale_pid.value == 0:
                    log.warning(
                        "Cannot resolve PID for stale hwnd 0x%08X "
                        "(window gone?) — skipping",
                        stale_hwnd,
                    )
                    continue
                if stale_pid.value == my_pid:
                    log.error(
                        "Refusing to terminate own process (pid=%d)",
                        stale_pid.value,
                    )
                    continue
                log.info(
                    "Killing stale hidden XG: hwnd=0x%08X pid=%d",
                    stale_hwnd, stale_pid.value,
                )
                hp = kernel32.OpenProcess(
                    PROCESS_TERMINATE, False, stale_pid.value
                )
                if not hp:
                    log.warning(
                        "OpenProcess(pid=%d) failed: GetLastError=%d "
                        "— stale instance left running",
                        stale_pid.value, kernel32.GetLastError(),
                    )
                    continue
                try:
                    if not kernel32.TerminateProcess(hp, 1):
                        log.warning(
                            "TerminateProcess(pid=%d) failed: "
                            "GetLastError=%d",
                            stale_pid.value, kernel32.GetLastError(),
                        )
                finally:
                    if not kernel32.CloseHandle(hp):
                        log.warning(
                            "CloseHandle leaked for pid=%d: "
                            "GetLastError=%d",
                            stale_pid.value, kernel32.GetLastError(),
                        )
            except OSError as exc:
                log.exception(
                    "Error killing stale XG hwnd=0x%08X: %s",
                    stale_hwnd, exc,
                )

    def _connect_headless(self) -> None:
        """Connect via pure Win32 and hide the window (headless mode).

        Always launches a new hidden XG instance to avoid hijacking any
        user-visible XG window. XG supports multiple instances.

        """
        if not self.xg_path or not self.xg_path.exists():
            raise XGAutomationError(
                "eXtreme Gammon 2 exe path is not set or does not exist."
            )

        # Collect existing XG window handles so we can identify our new one
        existing_hwnds: set[int] = set()

        def _enum_xg_main(hwnd, _lparam):
            try:
                cls = ctypes.create_unicode_buffer(64)
                user32.GetClassNameW(hwnd, cls, 64)
                if cls.value == CLASS_NAME:
                    existing_hwnds.add(int(hwnd))
            except Exception:
                pass
            return True

        user32.EnumWindows(WNDENUMPROC(_enum_xg_main), 0)

        if existing_hwnds:
            log.info(
                "Found %d existing XG instance(s) — launching a new one.",
                len(existing_hwnds),
            )
            self._kill_stale_xg_instances(existing_hwnds)
            existing_hwnds.clear()
            time.sleep(1.0)
            user32.EnumWindows(WNDENUMPROC(_enum_xg_main), 0)
            if existing_hwnds:
                visible = sum(
                    1 for h in existing_hwnds if user32.IsWindowVisible(h)
                )
                hidden = len(existing_hwnds) - visible
                if hidden:
                    log.warning(
                        "%d hidden XG instance(s) survived kill — "
                        "automation may conflict",
                        hidden,
                    )
                if visible:
                    log.info(
                        "%d visible XG instance(s) left alone "
                        "(user's own XG)",
                        visible,
                    )

        log.info("Launching XG (headless): %s", self.xg_path)
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        subprocess.Popen([str(self.xg_path)], startupinfo=si)

        # Wait for a NEW XG window (not one of the pre-existing ones)
        hwnd = 0
        deadline = time.time() + 30
        while time.time() < deadline:
            new_hwnds = []

            def _find_new(h, _lparam):
                cls = ctypes.create_unicode_buffer(64)
                user32.GetClassNameW(h, cls, 64)
                if cls.value == CLASS_NAME and int(h) not in existing_hwnds:
                    new_hwnds.append(int(h))
                return True

            user32.EnumWindows(WNDENUMPROC(_find_new), 0)
            if new_hwnds:
                hwnd = new_hwnds[0]
                break
            time.sleep(0.5)

        if not hwnd:
            raise XGAutomationError(
                "XG did not create main window within 30s."
            )

        self._hwnd = hwnd
        self.app = None
        self._main = None

        # Hide the new window immediately
        user32.ShowWindow(self._hwnd, 0)  # SW_HIDE

        self._setup_memory_reader()

        # Wait for XG to finish initialization using WaitForInputIdle
        # (blocks until the process message loop is idle, rather than
        # guessing with a fixed sleep).
        self._wait_for_process_idle()

        # Re-hide in case VCL restored WS_VISIBLE during init
        user32.ShowWindow(self._hwnd, 0)  # SW_HIDE

        # Detect version AFTER init — the window title is a placeholder
        # ("eXtreme Gammon IDE") until initialization completes.
        self._cmd = self._detect_xg_version()

        log.info("Connected (headless). hwnd=0x%08X, window hidden.", self._hwnd)

    def _wait_for_process_idle(self, timeout_ms: int = 30000) -> None:
        """Wait for XG's process to finish initialization.

        Uses WaitForInputIdle which blocks until the process message loop
        is idle — the standard Win32 way to know a GUI app is ready.
        """
        PROCESS_SYNCHRONIZE = 0x00100000
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(self._hwnd, ctypes.byref(pid))
        h_process = kernel32.OpenProcess(
            PROCESS_SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION,
            False,
            pid.value,
        )
        if not h_process:
            log.debug("OpenProcess failed — falling back to 3s sleep")
            time.sleep(3.0)
            return

        try:
            result = user32.WaitForInputIdle(h_process, timeout_ms)
            if result == 0:
                log.debug("WaitForInputIdle: process is idle")
            else:
                log.debug("WaitForInputIdle returned %d — continuing", result)
        finally:
            kernel32.CloseHandle(h_process)

    def _setup_memory_reader(self) -> None:
        """Initialize the memory reader if requested and available."""
        if not self.use_memory_reader:
            return

        MemoryReaderClass = _try_import_memory()
        if MemoryReaderClass is None:
            log.info("pymem not installed. Memory reading disabled.")
            return

        try:
            self._memory = MemoryReaderClass(self.address_map_path)
            if self._memory.attach(self._hwnd):
                log.info("Memory reader attached successfully.")
            else:
                log.warning("Memory reader failed to attach. Falling back to polling.")
                self._memory = None
        except Exception as e:
            log.warning("Memory reader setup failed: %s", e)
            self._memory = None

    def disconnect(self) -> None:
        """Clean up optional subsystems."""
        if self.headless and self._hwnd:
            # Close XG entirely — no reason to leave a hidden process running
            PostMessageW(self._hwnd, WM_CLOSE, 0, 0)
            time.sleep(1.0)
            # Dismiss any "save changes?" dialogs
            self._dismiss_unexpected_dialogs(accept=False)
            log.info("XG closed (headless cleanup).")
        if self._memory:
            try:
                self._memory.detach()
            except Exception:
                pass
            self._memory = None

    @property
    def main_window(self):
        if self.headless:
            raise XGAutomationError(
                "main_window not available in headless mode."
            )
        if self._main is None:
            raise XGAutomationError("Not connected. Call connect() first.")
        return self._main

    # ------------------------------------------------------------------
    # Low-level command dispatch
    # ------------------------------------------------------------------

    def send_command(self, cmd_id: int) -> None:
        """Send a WM_COMMAND to XG's main window."""
        # Re-hide main window if it became visible (Delphi can restore it
        # when showing/closing modal dialogs)
        if self.headless and user32.IsWindowVisible(self._hwnd):
            user32.ShowWindow(self._hwnd, 0)  # SW_HIDE
        log.debug("Sending WM_COMMAND wID=%d (0x%04X)", cmd_id, cmd_id)
        PostMessageW(self._hwnd, WM_COMMAND, cmd_id, 0)

    def focus(self) -> None:
        """Bring XG to the foreground (no-op in headless mode)."""
        if self.headless:
            return
        win = self.main_window
        if win.has_style(0x20000000):  # WS_MINIMIZE
            win.restore()
        win.set_focus()
        time.sleep(0.3)

    # ------------------------------------------------------------------
    # File operations
    # ------------------------------------------------------------------

    def _get_import_cmd(self, ext: str) -> Optional[int]:
        """Get the import command ID for a file extension.

        Only .xg/.xgp use File > Open; everything else uses Import > Others.
        Returns None for native XG formats (handled by File > Open).
        """
        if ext in (".xg", ".xgp"):
            return None
        return self.cmd.IMPORT_OTHERS

    def open_file(self, filepath: Path) -> None:
        """Open a match file via File > Open or File > Import."""
        filepath = Path(filepath).resolve()
        if not filepath.exists():
            raise FileNotFoundError(f"Match file not found: {filepath}")

        ext = filepath.suffix.lower()
        import_cmd = self._get_import_cmd(ext)
        cmd_id = import_cmd if import_cmd else self.cmd.OPEN

        log.info("Opening file: %s", filepath)

        if self.headless:
            self._headless_file_operation(filepath, cmd_id, "open")
            # Wait until all dialogs are fully closed before returning.
            self._wait_for_dialogs_cleared(max_wait=8.0)
            self._current_file = filepath
            log.info("File opened (headless): %s", filepath.name)
            return

        self.focus()

        if import_cmd:
            log.debug("Using Import (wID=%d) for %s file", import_cmd, ext)
            self.send_command(import_cmd)
        else:
            self.send_command(self.cmd.OPEN)

        time.sleep(1.0)

        # Handle the file dialog (Open or Import)
        open_dlg = self._wait_for_dialog(
            title_re=r".*[Oo]pen.*|.*[Gg]ame.*|.*[Ii]mport.*", timeout=10
        )
        self._fill_file_dialog(open_dlg, filepath)

        # Wait for file to load
        time.sleep(2.0)
        self._dismiss_unexpected_dialogs()
        self._current_file = filepath
        log.info("File opened: %s", filepath.name)

    def close_match(self) -> None:
        """Close the current match (wID=94)."""
        if not self.headless:
            self.focus()
        self.send_command(self.cmd.CLOSE)
        time.sleep(0.5)
        self._dismiss_unexpected_dialogs()

    # ------------------------------------------------------------------
    # Clipboard & XGID import
    # ------------------------------------------------------------------

    def set_clipboard_text(self, text: str) -> None:
        """Set text on the Windows clipboard (CF_UNICODETEXT)."""
        encoded = text.encode("utf-16-le") + b"\x00\x00"
        hMem = _GlobalAlloc(GMEM_MOVEABLE, len(encoded))
        if not hMem:
            raise XGAutomationError("GlobalAlloc failed for clipboard")
        ptr = _GlobalLock(hMem)
        if not ptr:
            _GlobalFree(hMem)
            raise XGAutomationError("GlobalLock failed for clipboard")
        ctypes.memmove(ptr, encoded, len(encoded))
        _GlobalUnlock(hMem)

        if not _OpenClipboard(0):
            _GlobalFree(hMem)
            raise XGAutomationError("OpenClipboard failed")
        _EmptyClipboard()
        if not _SetClipboardData(CF_UNICODETEXT, hMem):
            _CloseClipboard()
            raise XGAutomationError("SetClipboardData failed")
        _CloseClipboard()
        log.debug("Clipboard set: %s", text[:80])

    def get_clipboard_text(self) -> str:
        """Read text from the Windows clipboard (CF_UNICODETEXT)."""
        if not _OpenClipboard(0):
            raise XGAutomationError("OpenClipboard failed")
        try:
            handle = _GetClipboardData(CF_UNICODETEXT)
            if not handle:
                return ""
            ptr = _GlobalLock(handle)
            if not ptr:
                return ""
            try:
                return ctypes.wstring_at(ptr)
            finally:
                _GlobalUnlock(handle)
        finally:
            _CloseClipboard()

    def get_clipboard_text_validated(self, max_retries: int = 3) -> str:
        """Read XG analysis text from clipboard with validation and retry.

        Verifies the clipboard content looks like XG analysis output
        (starts with 'XGID='). Retries on failure to handle cases
        where user clipboard activity temporarily overwrites the data.
        """
        for attempt in range(max_retries):
            text = self.get_clipboard_text()
            if text and "XGID=" in text:
                return text
            if attempt < max_retries - 1:
                log.warning(
                    "Clipboard validation failed (attempt %d/%d): "
                    "content does not look like XG analysis",
                    attempt + 1, max_retries,
                )
                time.sleep(0.5)
                # Re-trigger export in case clipboard was overwritten
                self.send_command(self.cmd.EXPORT_POS_CLIPBOARD)
                time.sleep(1.0)
        raise XGAutomationError(
            "Clipboard does not contain valid XG analysis after "
            f"{max_retries} attempts. Ensure no other application "
            "is modifying the clipboard during analysis."
        )

    def import_xgid(self, xgid: str) -> None:
        """Import a position from an XGID string via clipboard.

        Validates the XGID, places it on the clipboard, sends
        Import > Position from Clipboard (wID=120), and waits
        for the position to load.
        """
        xgid = self._validate_xgid(xgid)
        log.info("Importing XGID: %s", xgid[:60])

        self.set_clipboard_text(xgid)

        if not self.headless:
            self.focus()
        self.send_command(self.cmd.IMPORT_POS_CLIPBOARD)

        self._wait_for_position_loaded()
        log.info("Position loaded from XGID.")

    def import_xgid_from_file(self, xgid: str) -> None:
        """Import a position from an XGID string via a temp text file.

        Writes the XGID to a temporary .txt file, then uses
        Import > Position from text... to load it. This avoids
        the clipboard, preventing interference from user copy/paste.
        """
        import tempfile

        xgid = self._validate_xgid(xgid)
        log.info("Importing XGID from file: %s", xgid[:60])

        # Write XGID to a temp file with a short path (avoid IFileDialog issues)
        temp_dir = Path(tempfile.gettempdir()) / "ankigammon"
        temp_dir.mkdir(exist_ok=True)
        temp_file = temp_dir / "xgid_import.txt"
        temp_file.write_text(xgid, encoding="utf-8")

        try:
            if not self.headless:
                self.focus()
            self._headless_file_operation(
                temp_file, self.cmd.IMPORT_POS_TEXT, "open"
            )
            self._wait_for_dialogs_cleared(max_wait=5.0)
            self._wait_for_position_loaded()
            log.info("Position loaded from text file.")
        finally:
            try:
                temp_file.unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def _validate_xgid(xgid: str) -> str:
        """Validate and normalize an XGID string.

        Ensures the XGID= prefix is present and the format has the
        required colon-separated fields with a 26-char position string.
        """
        xgid = xgid.strip()
        if not xgid.startswith("XGID="):
            xgid = f"XGID={xgid}"

        body = xgid[5:]  # after "XGID="
        parts = body.split(":")
        if len(parts) < 9:
            raise XGAutomationError(
                f"Invalid XGID: expected at least 9 colon-separated fields, "
                f"got {len(parts)}"
            )

        position_str = parts[0]
        if len(position_str) != 26:
            raise XGAutomationError(
                f"Invalid XGID: position must be 26 chars, "
                f"got {len(position_str)}"
            )

        valid_chars = set("-abcdefghijklmnopABCDEFGHIJKLMNOP")
        invalid = set(position_str) - valid_chars
        if invalid:
            raise XGAutomationError(
                f"Invalid XGID: unexpected position characters: {invalid}"
            )

        return xgid

    def _wait_for_position_loaded(self, timeout: float = 10.0) -> None:
        """Wait for XG to finish loading a position after clipboard import.

        Polls for window title change and dismisses any error dialogs.
        """
        time.sleep(1.0)  # initial settle time for XG to process the command

        deadline = time.time() + timeout
        while time.time() < deadline:
            # Dismiss error dialogs (e.g. invalid clipboard content)
            self._dismiss_unexpected_dialogs(accept=True)

            # Check if XG's title changed (indicates content loaded)
            title = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(self._hwnd, title, 256)
            if title.value and title.value != self._xg_base_title:
                log.debug("Position loaded — title: %s", title.value)
                return

            time.sleep(0.5)

        # Even if title didn't change, the position may still have loaded
        # (XG doesn't always update the title for clipboard imports).
        log.debug("Position load wait timed out — proceeding anyway.")

    def save_as(self, output_path: Path) -> None:
        """Save the current match as .xg via File > Save As (wID=93)."""
        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        log.info("Saving as: %s", output_path)

        if self.headless:
            # Use Save As dialog directly — File > Save doesn't work for
            # imported files (.mat, .sgf) because XG has no associated path
            # and would trigger its own Save As dialog, creating conflicts.
            self._headless_file_operation(
                output_path, self.cmd.SAVE_AS, "save"
            )
            # Wait for the file dialog to process Enter and for any overwrite
            # confirmation to appear before we start dismissing dialogs.
            time.sleep(2.0)
            self._wait_for_dialogs_cleared(max_wait=8.0)
            log.info("Saved (headless): %s", output_path.name)
            return

        self.focus()
        self.send_command(self.cmd.SAVE_AS)
        time.sleep(1.0)

        save_dlg = self._wait_for_dialog(
            title_re=r".*[Ss]ave.*", timeout=10
        )
        self._fill_file_dialog(save_dlg, output_path)
        time.sleep(1.0)
        # Handle "Confirm Save As" overwrite prompt (click Yes)
        self._dismiss_unexpected_dialogs(accept=True)
        log.info("Saved: %s", output_path.name)

    def export_text(self, output_path: Path) -> None:
        """Export analysis as text file via Export > Match to Text File (wID=140)."""
        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        log.info("Exporting text to: %s", output_path)

        if self.headless:
            log.warning("export_text in headless mode: IFileDialog path "
                        "control is limited — file will save to XG's "
                        "default export location.")
            self._headless_file_operation(
                output_path, self.cmd.EXPORT_TEXT, "save"
            )
            self._wait_for_dialogs_cleared(max_wait=5.0)
            log.info("Text export complete (headless): %s", output_path.name)
            return

        self.focus()
        self.send_command(self.cmd.EXPORT_TEXT)
        time.sleep(1.0)

        save_dlg = self._wait_for_dialog(
            title_re=r".*[Ss]ave.*|.*[Ee]xport.*|.*[Tt]ext.*", timeout=10
        )
        self._fill_file_dialog(save_dlg, output_path)
        time.sleep(1.0)
        self._dismiss_unexpected_dialogs()
        log.info("Text export complete: %s", output_path.name)

    def export_html(self, output_path: Path) -> None:
        """Export analysis as HTML via Export > Game or Match to HTML (wID=138)."""
        output_path = Path(output_path).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        log.info("Exporting HTML to: %s", output_path)

        if self.headless:
            log.warning("export_html in headless mode: IFileDialog path "
                        "control is limited — file will save to XG's "
                        "default export location.")
            self._headless_file_operation(
                output_path, self.cmd.EXPORT_HTML, "save"
            )
            self._wait_for_dialogs_cleared(max_wait=5.0)
            log.info("HTML export complete (headless): %s", output_path.name)
            return

        self.focus()
        self.send_command(self.cmd.EXPORT_HTML)
        time.sleep(1.0)

        save_dlg = self._wait_for_dialog(
            title_re=r".*[Ss]ave.*|.*[Ee]xport.*|.*HTML.*", timeout=10
        )
        self._fill_file_dialog(save_dlg, output_path)
        time.sleep(1.0)
        self._dismiss_unexpected_dialogs()
        log.info("HTML export complete: %s", output_path.name)

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def run_analysis(self) -> None:
        """Trigger Analyse > Match (wID=268) and wait for completion."""
        log.info("Starting match analysis...")
        if not self.headless:
            self.focus()

        # In headless mode, dismiss any lingering startup dialogs first
        if self.headless:
            self._dismiss_unexpected_dialogs(accept=True)

        self.send_command(self.cmd.ANALYZE_MATCH)

        # Handle the "Analyze Session" settings dialog
        time.sleep(1.5)
        self._handle_analyze_session_dialog()

        # Wait for analysis to complete
        self._wait_for_analysis()

        # Dismiss any remaining post-analysis dialogs
        time.sleep(0.5)
        self._dismiss_unexpected_dialogs(accept=False)
        log.info("Analysis complete.")

    def _handle_analyze_session_dialog(self) -> None:
        """Set analysis level and click OK on the 'Analyze Session' dialog.

        If analysis_level is configured, sets both player ComboBoxes to that
        level. Otherwise just clicks OK to accept defaults.
        """
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(self._hwnd, ctypes.byref(pid))
        xg_pid = pid.value

        dlg_hwnd = 0
        # Look for the Analyze Session dialog (TAnalyzeLevelDlg).
        # Must validate it's the RIGHT dialog — not a lingering file dialog
        # or persistent window like "Analyze Queue & Rollout".
        # Build a local skip set so rejected candidates aren't re-found.
        local_skip = set(self._skip_hwnds)
        for _ in range(15):
            candidate = self._find_xg_dialog(
                xg_pid, self._hwnd, skip=local_skip
            )
            if candidate:
                # Check if it has TComboBox children (analysis dialog signature)
                if self._find_child_by_class(candidate, ["TComboBox"]):
                    dlg_hwnd = candidate
                    break
                # Accept if title contains "analy" AND it has clickable buttons
                # (filters out persistent windows like "Analyze Queue & Rollout")
                # BUT reject completion dialogs ("Analyze completed") — these
                # must be handled by _wait_for_analysis, not consumed here.
                title_buf = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(candidate, title_buf, 256)
                title_lower = title_buf.value.lower()
                if ("analy" in title_lower
                        and "complete" not in title_lower
                        and self._find_buttons(candidate)):
                    dlg_hwnd = candidate
                    break
                log.debug(
                    "Skipping non-analysis dialog: %s", title_buf.value
                )
                local_skip.add(candidate)
            time.sleep(0.3)

        if not dlg_hwnd:
            log.debug("No Analyze Session dialog found")
            return

        title = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(dlg_hwnd, title, 256)
        log.debug("Found analysis dialog: %s", title.value)

        # Hide in headless mode
        if self.headless:
            user32.ShowWindow(dlg_hwnd, 0)  # SW_HIDE

        # Set analysis level if configured (matched by name against the
        # live dropdown items, which include both built-ins and custom
        # profiles XG loaded from its registry).
        if self.analysis_level:
            self._set_analysis_level(dlg_hwnd, self.analysis_level)

        # Tick "Override Previous Analyze" checkbox
        self._tick_checkbox(dlg_hwnd, "Override Previous Analyze")

        # Click OK
        class _HwndWrap:
            def __init__(self, h):
                self.handle = h

        self._click_button(_HwndWrap(dlg_hwnd), ["OK", "Ok"])
        time.sleep(0.5)

    def _tick_checkbox(self, dlg_hwnd: int, label: str) -> None:
        """Ensure a checkbox in a dialog is checked (ticked).

        Finds a TCheckBox child with matching text and sends BM_CLICK
        if it's currently unchecked.
        """
        BM_GETCHECK = 0x00F0
        BST_CHECKED = 1

        checkboxes = []

        def _enum_cb(hwnd, _lparam):
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, cls, 64)
            if cls.value in ("TCheckBox", "Button"):
                txt = ctypes.create_unicode_buffer(128)
                user32.GetWindowTextW(hwnd, txt, 128)
                if txt.value and label.lower() in txt.value.lower():
                    checkboxes.append((hwnd, txt.value))
            return True

        user32.EnumChildWindows(dlg_hwnd, WNDENUMPROC(_enum_cb), 0)

        if not checkboxes:
            log.debug("Checkbox %r not found in dialog", label)
            return

        cb_hwnd, cb_text = checkboxes[0]
        state = SendMessageW(cb_hwnd, BM_GETCHECK, 0, 0)
        if state != BST_CHECKED:
            log.info("Ticking checkbox: %s", cb_text)
            SendMessageW(cb_hwnd, BM_CLICK, 0, 0)
        else:
            log.debug("Checkbox already checked: %s", cb_text)

    def _set_analysis_level(self, dlg_hwnd: int, level_name: str) -> None:
        """Set both player ComboBoxes to the analysis level with this name.

        Resolves the dropdown index at runtime by scraping items via
        CB_GETLBTEXT and matching case-insensitively. This works for both
        built-in levels and user-defined custom profiles, and is robust
        against XG version changes that shift the built-in count.
        """
        CB_SETCURSEL = 0x014E
        CB_GETCOUNT = 0x0146
        CB_GETLBTEXTLEN = 0x0149
        CB_GETLBTEXT = 0x0148

        combos = []

        def _enum_cb(hwnd, _lparam):
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, cls, 64)
            if cls.value == "TComboBox":
                combos.append(hwnd)
            return True

        user32.EnumChildWindows(dlg_hwnd, WNDENUMPROC(_enum_cb), 0)
        if not combos:
            log.warning("No TComboBox found in analysis dialog")
            return

        target = level_name.strip().lower()
        # Resolve the index from the first combo; XG keeps both player
        # combos in sync structurally so the index applies to both.
        # Note: XG's TComboBox stores each item as a colon-delimited
        # "<DisplayName>:<param1>:<param2>:..." string and renders only
        # the first token visually via owner-draw. Match against that
        # first token, not the whole text.
        items = self._read_combo_items(combos[0], CB_GETCOUNT,
                                       CB_GETLBTEXTLEN, CB_GETLBTEXT)
        display_names = [text.split(":", 1)[0].strip() for text in items]
        log.debug("Analysis dropdown items: %s", display_names)
        match_idx = next(
            (i for i, name in enumerate(display_names) if name.lower() == target),
            None,
        )

        if match_idx is None:
            log.warning(
                "Analysis level %r not found in dropdown (available: %s); "
                "leaving XG default",
                level_name,
                display_names,
            )
            return

        for combo_hwnd in combos:
            SendMessageW(combo_hwnd, CB_SETCURSEL, match_idx, 0)

        log.info(
            "Set analysis level to %r (index %d) for %d player(s)",
            display_names[match_idx], match_idx, len(combos),
        )

    @staticmethod
    def _read_combo_items(
        combo_hwnd: int,
        cb_getcount: int,
        cb_getlbtextlen: int,
        cb_getlbtext: int,
    ) -> list[str]:
        """Read all items of a combobox via CB_GETLBTEXT."""
        count = SendMessageW(combo_hwnd, cb_getcount, 0, 0)
        items: list[str] = []
        for i in range(count):
            length = SendMessageW(combo_hwnd, cb_getlbtextlen, i, 0)
            if length < 0:
                items.append("")
                continue
            buf = ctypes.create_unicode_buffer(length + 1)
            SendMessageW(combo_hwnd, cb_getlbtext, i, ctypes.addressof(buf))
            items.append(buf.value)
        return items

    def _wait_for_analysis(self) -> None:
        """Wait for analysis completion via UI polling.

        Every poll_interval, checks: completion dialog, menu state,
        and status bar.
        """
        start = time.time()

        log.info(
            "Waiting for analysis (timeout: %.0fs, poll: %.1fs)...",
            self.timeout,
            self.poll_interval,
        )

        # Wait for analysis to actually START first (menu item becomes disabled)
        analysis_started = False
        for _ in range(10):
            if self._check_for_completion_dialog():
                return  # Already done (very fast analysis)
            if not self._check_menu_item_enabled(self.cmd.ANALYZE_MATCH):
                analysis_started = True
                log.debug("Analysis started (menu item disabled)")
                break
            time.sleep(0.5)

        if not analysis_started:
            log.warning(
                "Analyze menu item never became disabled — "
                "analysis may not have started. Continuing to poll..."
            )

        last_status = ""
        while time.time() - start < self.timeout:
            # Check for the "Analyze completed" dialog (most reliable signal)
            if self._check_for_completion_dialog():
                return

            # Check if the Analyze > Match menu item is enabled again.
            # Also check when analysis_started is False — analysis may have
            # completed before we began polling (fast single-position analysis).
            if self._check_menu_item_enabled(self.cmd.ANALYZE_MATCH):
                if not analysis_started:
                    # Analysis completed before we could observe the start.
                    # Brief confirmation to avoid false positives.
                    time.sleep(1.0)
                    if self._check_menu_item_enabled(self.cmd.ANALYZE_MATCH):
                        log.info("Analysis complete (menu re-enabled, fast completion)")
                        self._dismiss_unexpected_dialogs(accept=False)
                        return
                else:
                    time.sleep(2.0)
                    if self._check_menu_item_enabled(self.cmd.ANALYZE_MATCH):
                        return

            if self._check_status_bar():
                return

            # Dismiss any stray dialogs (startup dialogs, error popups)
            # that could block the completion dialog from appearing.
            # Only do this in headless mode where unexpected dialogs
            # can silently block the UI thread.
            if self.headless:
                self._dismiss_unexpected_dialogs(accept=True)

            # Log progress from status bar and/or window title
            status = self._read_progress()
            if status and status != last_status:
                elapsed = int(time.time() - start)
                log.info("  [%ds] %s", elapsed, status)
                last_status = status

            time.sleep(self.poll_interval)

        raise XGAutomationError(
            f"Analysis did not complete within {self.timeout}s timeout."
        )

    def _check_for_completion_dialog(self) -> bool:
        """Look for an analysis completion dialog via Win32.

        XG shows 'Analyze completed' (with &Yes/&No buttons) when done.
        Also checks for other completion-related dialog titles.
        """
        import re

        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(self._hwnd, ctypes.byref(pid))
        xg_pid = pid.value

        pattern = re.compile(
            r"[Cc]omplete|[Ff]inish|[Dd]one|[Rr]esult|[Aa]nalyze completed"
        )

        dialogs = []

        headless = self.headless

        def _enum_cb(hwnd, _lparam):
            # In headless mode, skip visibility check — owned dialogs may be
            # hidden along with the main window.
            if not headless and not user32.IsWindowVisible(hwnd):
                return True
            p = wt.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
            if p.value != xg_pid:
                return True
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            if buf.value and pattern.search(buf.value):
                dialogs.append((hwnd, buf.value))
            return True

        user32.EnumWindows(WNDENUMPROC(_enum_cb), 0)

        if not dialogs:
            return False

        dlg_hwnd, title = dialogs[0]
        log.debug("Found completion dialog: %s", title)

        # Hide before interacting so it doesn't flash on screen
        if self.headless:
            user32.ShowWindow(dlg_hwnd, 0)  # SW_HIDE

        class _HwndWrap:
            def __init__(self, h):
                self.handle = h

        self._click_button(
            _HwndWrap(dlg_hwnd),
            list(self._BTN_NO | self._BTN_OK | self._BTN_CLOSE | self._BTN_YES),
        )
        time.sleep(0.5)
        # Dismiss any follow-up dialogs (e.g. "Add Results to Profile")
        self._dismiss_unexpected_dialogs(accept=False)
        return True

    def _check_menu_item_enabled(self, cmd_id: int) -> bool:
        """Check if a menu item is enabled via Win32 GetMenuState."""
        try:
            hmenu = user32.GetMenu(self._hwnd)
            if not hmenu:
                return False
            # MF_BYCOMMAND = 0x0000, MF_GRAYED = 0x0001, MF_DISABLED = 0x0002
            state = user32.GetMenuState(hmenu, cmd_id, 0x0000)
            if state == -1:
                # Item not found at top level — search submenus
                return self._check_submenu_item_enabled(hmenu, cmd_id)
            return (state & 0x0003) == 0  # not grayed/disabled
        except Exception:
            return False

    def _check_submenu_item_enabled(self, hmenu: int, cmd_id: int) -> bool:
        """Recursively search submenus for a command ID and check its state."""
        count = user32.GetMenuItemCount(hmenu)
        for i in range(count):
            sub = user32.GetSubMenu(hmenu, i)
            if sub:
                state = user32.GetMenuState(sub, cmd_id, 0x0000)
                if state != -1:
                    return (state & 0x0003) == 0
                # Recurse into deeper submenus
                result = self._check_submenu_item_enabled(sub, cmd_id)
                if result is not None:
                    return result
        return None

    def _check_status_bar(self) -> bool:
        """Check status bar for completion indicators."""
        if self.headless:
            return False
        try:
            status = self.main_window.StatusBar
            text = status.window_text()
            if text:
                text_lower = text.lower()
                if any(
                    kw in text_lower
                    for kw in ["complete", "done", "finished", "ready"]
                ):
                    log.debug("Status bar indicates completion: %s", text)
                    return True
        except Exception:
            pass
        return False

    def _read_progress(self) -> str:
        """Read current analysis progress from XG's UI.

        Checks the status bar and window title for progress info.
        Returns a short string, or empty if nothing useful.
        """
        parts = []

        # Try memory reader first (fastest)
        if self._memory and self._memory.is_attached:
            try:
                text = self._memory.get_status_text()
                if text:
                    parts.append(text)
            except Exception:
                pass

        # Try status bar via pywinauto (skip in headless mode)
        if not parts and not self.headless:
            try:
                status = self.main_window.StatusBar
                text = status.window_text()
                if text and text.strip():
                    parts.append(text.strip())
            except Exception:
                pass

        # Check window title for progress info
        try:
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(self._hwnd, buf, 256)
            title = buf.value
            # XG sometimes puts progress in the title bar
            if title and "%" in title:
                parts.append(title)
        except Exception:
            pass

        return " | ".join(parts) if parts else ""

    # ------------------------------------------------------------------
    # Headless file dialog handling
    # ------------------------------------------------------------------

    WM_SETTEXT = 0x000C

    def _headless_file_operation(
        self,
        filepath: Path,
        cmd_id: int,
        dialog_type: str = "open",
    ) -> None:
        """Perform a file operation in headless mode.

        Sends the WM_COMMAND, waits for the IFileDialog to appear,
        then auto-fills it via Win32 messages.

        The dialog's WS_VISIBLE state is preserved (it is moved
        off-screen rather than hidden via SW_HIDE) because Windows 11's
        IFileDialog only updates its COM state from WM_CHAR
        notifications while the window is technically visible. SW_HIDE
        is applied only after the confirmation attempt.
        """
        self.send_command(cmd_id)

        deadline = time.time() + 10.0
        while time.time() < deadline:
            dlg_hwnd = self._find_file_dialog_win32()
            if dlg_hwnd:
                ok = user32.SetWindowPos(
                    dlg_hwnd, 0,
                    OFFSCREEN_X, OFFSCREEN_Y,
                    0, 0,
                    SWP_NOSIZE | SWP_NOZORDER,
                )
                if not ok:
                    log.warning(
                        "SetWindowPos off-screen failed for hwnd=0x%08X "
                        "(GetLastError=%d) — dialog may flash on screen",
                        dlg_hwnd, kernel32.GetLastError(),
                    )
                non_block = dialog_type == "save"
                self._autofill_file_dialog_win32(
                    dlg_hwnd, filepath, non_blocking=non_block,
                )
                # Autofill+confirm usually destroys the dialog already;
                # apply SW_HIDE only if the hwnd is still alive so we
                # leave a consistent visibility state for the next op.
                if user32.IsWindow(dlg_hwnd):
                    user32.ShowWindow(dlg_hwnd, SW_HIDE)
                return
            time.sleep(0.3)

        raise XGAutomationError(
            f"Headless file {dialog_type} timed out for {filepath}"
        )

    def _find_file_dialog_win32(self) -> int:
        """Find an open file dialog belonging to XG's process.

        Validates the dialog has an Edit control (filename input) to
        distinguish real file dialogs from message boxes (both use #32770).
        """
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(self._hwnd, ctypes.byref(pid))
        xg_pid = pid.value
        candidates = []
        headless = self.headless
        skip = self._skip_hwnds

        def _enum_cb(hwnd, _lparam):
            h = int(hwnd)
            if h in skip or h == self._hwnd:
                return True
            if not headless and not user32.IsWindowVisible(hwnd):
                return True
            p = wt.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
            if p.value != xg_pid:
                return True

            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, cls, 64)
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            title = buf.value.lower()

            if cls.value == "#32770" or any(
                kw in title
                for kw in ("open", "save", "export", "import")
            ):
                candidates.append(h)
            return True  # Continue — collect all candidates

        user32.EnumWindows(WNDENUMPROC(_enum_cb), 0)

        # Return the first candidate that has an Edit control (filename input).
        # This filters out message boxes which are also #32770 but have no Edit.
        for hwnd in candidates:
            combo_ex = user32.GetDlgItem(hwnd, 0x047C)
            if combo_ex:
                return hwnd
            edit = self._find_child_by_class(hwnd, ["Edit", "TEdit"])
            if edit:
                return hwnd

        return 0

    # Win32 Edit control messages
    EM_SETSEL = 0x00B1
    WM_CLEAR = 0x0303
    WM_CHAR = 0x0102

    def _autofill_file_dialog_win32(
        self, dlg_hwnd: int, filepath: Path, non_blocking: bool = False
    ) -> None:
        """Fill a file dialog with a path and click OK via pure Win32.

        IFileDialog layout: ComboBoxEx32(id=0x047C) > ComboBox > Edit.
        Uses keyboard simulation (WM_CHAR) instead of WM_SETTEXT so that
        the IFileDialog COM object updates its internal filename state.

        When non_blocking=True, uses PostMessage for the button click so it
        doesn't block if the dialog shows a confirmation prompt (e.g.
        overwrite). This is critical for headless save operations.
        """
        edit_hwnd = 0

        cls_buf = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(dlg_hwnd, cls_buf, 64)
        title_buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(dlg_hwnd, title_buf, 256)
        log.info("File dialog hwnd=0x%08X class=%r title=%r",
                 dlg_hwnd, cls_buf.value, title_buf.value)

        # Strategy 1: Find the filename ComboBoxEx32 by control ID (0x047C),
        # then get the Edit inside it.
        combo_ex = user32.GetDlgItem(dlg_hwnd, 0x047C)
        if combo_ex:
            edit_hwnd = self._find_child_by_class(int(combo_ex), ["Edit"])

        # Strategy 2: Fallback for classic Delphi dialogs (TEdit)
        if not edit_hwnd:
            edit_hwnd = self._find_child_by_class(
                dlg_hwnd, ["TEdit", "Edit"]
            )

        if edit_hwnd:
            # Clear existing text: select all → delete
            SendMessageW(edit_hwnd, self.EM_SETSEL, 0, -1)
            SendMessageW(edit_hwnd, self.WM_CLEAR, 0, 0)
            # Verify text was cleared; fall back to WM_SETTEXT if not.
            # Some Delphi TEdit controls ignore EM_SETSEL+WM_CLEAR when
            # the control doesn't have focus.
            length = SendMessageW(edit_hwnd, WM_GETTEXTLENGTH, 0, 0)
            if length > 0:
                log.debug(
                    "WM_CLEAR did not clear edit; "
                    "using WM_SETTEXT fallback (%d chars remaining)", length
                )
                empty = ctypes.create_unicode_buffer(1)
                SendMessageW(
                    edit_hwnd, self.WM_SETTEXT, 0,
                    ctypes.addressof(empty),
                )
            # Type path via WM_CHAR so the IFileDialog processes each
            # character and updates its internal COM state.
            path_str = str(filepath)
            for ch in path_str:
                SendMessageW(edit_hwnd, self.WM_CHAR, ord(ch), 0)
            # Read back the text to verify it was entered correctly
            length = SendMessageW(edit_hwnd, WM_GETTEXTLENGTH, 0, 0)
            verify_buf = ctypes.create_unicode_buffer(length + 1)
            SendMessageW(
                edit_hwnd, WM_GETTEXT, length + 1,
                ctypes.addressof(verify_buf),
            )
            log.debug("File dialog text set (%d chars): %s",
                       length, verify_buf.value)
            if verify_buf.value != path_str:
                log.warning(
                    "Edit text mismatch after WM_CHAR! "
                    "Got: %s  Expected: %s",
                    verify_buf.value, path_str,
                )
                # Last resort: force-set via WM_SETTEXT. This works
                # because we confirm with Enter (reads Edit text), not
                # BM_CLICK (reads IFileDialog COM state).
                path_buf = ctypes.create_unicode_buffer(path_str)
                SendMessageW(
                    edit_hwnd, self.WM_SETTEXT, 0,
                    ctypes.addressof(path_buf),
                )
                log.debug("Forced path via WM_SETTEXT fallback")
        else:
            log.warning("Could not find Edit control in file dialog")

        time.sleep(0.3)

        # Confirm the file dialog.  We use three strategies in order:
        #
        # 1. WM_COMMAND IDOK to the dialog — this is how the dialog's own
        #    button handler works internally and is the most reliable across
        #    Windows versions (10, 11) and dialog types (IFileDialog, old
        #    GetOpenFileName, Delphi TOpenDialog).
        #
        # 2. VK_RETURN to the Edit control — IFileDialog processes Enter in
        #    the filename edit by reading the text and navigating/opening.
        #    This may do a two-step navigate (dir → file) so we retry.
        #
        # 3. BM_CLICK on the Open/Save button — last resort fallback.
        #
        # Some file dialogs need a two-step confirm: first Enter navigates
        # to the directory, second Enter opens the file.  We retry up to 3
        # times with a brief pause between attempts.

        send = PostMessageW if non_blocking else SendMessageW

        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(dlg_hwnd, ctypes.byref(pid))
        xg_pid = pid.value

        def _dismiss_error_popups() -> int:
            """Dismiss XG-process MessageBox popups blocking the dialog.

            A real error popup is a #32770 window without an Edit
            control (an Edit would mean it's another file dialog, not a
            MessageBox). Loops until no more popups remain so cascading
            errors don't get partially handled.

            Returns the number of popups dismissed.
            """
            dismissed = 0
            for _ in range(5):
                found = [0]

                def _cb(hwnd, _lp):
                    try:
                        h = int(hwnd)
                        if h == dlg_hwnd:
                            return True
                        p = wt.DWORD()
                        user32.GetWindowThreadProcessId(
                            hwnd, ctypes.byref(p)
                        )
                        if p.value != xg_pid:
                            return True
                        cls = ctypes.create_unicode_buffer(64)
                        user32.GetClassNameW(hwnd, cls, 64)
                        if cls.value != "#32770":
                            return True
                        # Skip if it has an Edit — that's a file dialog,
                        # not an error popup.
                        if (user32.GetDlgItem(hwnd, 0x047C)
                                or self._find_child_by_class(
                                    h, ["Edit", "TEdit"])):
                            return True
                        found[0] = h
                        return False
                    except Exception:
                        return True

                user32.EnumWindows(WNDENUMPROC(_cb), 0)
                if not found[0]:
                    break
                ebuf = ctypes.create_unicode_buffer(256)
                user32.GetWindowTextW(found[0], ebuf, 256)
                log.warning(
                    "Dismissing XG error popup: hwnd=0x%08X title=%r",
                    found[0], ebuf.value,
                )
                PostMessageW(found[0], WM_COMMAND, IDOK, 0)
                time.sleep(0.5)
                dismissed += 1
            return dismissed

        def _log_edit_text(when: str) -> None:
            if not edit_hwnd:
                return
            rl = SendMessageW(edit_hwnd, WM_GETTEXTLENGTH, 0, 0)
            rb = ctypes.create_unicode_buffer(rl + 1)
            SendMessageW(
                edit_hwnd, WM_GETTEXT, rl + 1, ctypes.addressof(rb),
            )
            log.warning("Edit text %s: %r", when, rb.value)

        total_popups_dismissed = 0
        WM_KEYDOWN = 0x0100
        WM_KEYUP = 0x0101
        VK_RETURN = 0x0D

        for attempt in range(3):
            log.debug(
                "Confirming file dialog via WM_COMMAND IDOK (attempt %d)",
                attempt + 1,
            )
            send(dlg_hwnd, WM_COMMAND, IDOK, 0)
            time.sleep(1.0)

            if not user32.IsWindow(dlg_hwnd):
                log.debug("File dialog closed after WM_COMMAND IDOK")
                return

            n = _dismiss_error_popups()
            if n:
                total_popups_dismissed += n
                _log_edit_text("after IDOK error popup")

            if edit_hwnd:
                log.debug(
                    "Pressing Enter in file dialog edit (attempt %d)",
                    attempt + 1,
                )
                send(edit_hwnd, WM_KEYDOWN, VK_RETURN, 0x001C0001)
                send(edit_hwnd, WM_KEYUP, VK_RETURN, 0xC01C0001)
                time.sleep(1.0)

                if not user32.IsWindow(dlg_hwnd):
                    log.debug("File dialog closed after VK_RETURN")
                    return

                n = _dismiss_error_popups()
                if n:
                    total_popups_dismissed += n
                    _log_edit_text("after VK_RETURN error popup")

        # XG repeatedly rejected the path — fail loudly rather than
        # silently falling through to a button click that will trigger
        # the same error.
        if total_popups_dismissed >= 2:
            raise XGAutomationError(
                f"XG rejected the filename for {filepath} "
                f"({total_popups_dismissed} error popups dismissed). "
                f"The file may not exist, be in an unsupported format, "
                f"or be locked by another process."
            )

        log.debug("Falling back to BM_CLICK on Open/Save button")

        class _HwndWrap:
            def __init__(self, h):
                self.handle = h

        self._click_button(
            _HwndWrap(dlg_hwnd),
            list(self._BTN_OPEN | self._BTN_SAVE | self._BTN_OK),
        )

    @staticmethod
    def _find_child_by_class(
        parent_hwnd: int, class_names: list[str]
    ) -> int:
        """Find the first child window matching one of the class names."""
        found = [0]

        def _enum_cb(hwnd, _lparam):
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, cls, 64)
            if cls.value in class_names:
                found[0] = int(hwnd)
                return False
            return True

        user32.EnumChildWindows(parent_hwnd, WNDENUMPROC(_enum_cb), 0)
        return found[0]

    # ------------------------------------------------------------------
    # Dialog helpers
    # ------------------------------------------------------------------

    def _wait_for_dialog(self, title_re: str, timeout: float = 10) -> object:
        """Wait for a dialog window to appear."""
        import re

        start = time.time()
        while time.time() - start < timeout:
            # First try pywinauto's built-in search
            try:
                dlg = self.app.window(title_re=title_re, timeout=1)
                dlg.wait("visible", timeout=2)
                return dlg
            except Exception:
                pass

            # Fallback: scan all top-level windows via Win32 directly
            # (handles 32/64-bit mismatch cases where pywinauto misses dialogs)
            try:
                for w in self.app.windows():
                    title = w.window_text()
                    if title and re.search(title_re, title) and w.is_visible():
                        log.debug("Found dialog via fallback scan: %r", title)
                        return w
            except Exception:
                pass

            time.sleep(0.5)
        raise XGAutomationError(
            f"Dialog matching {title_re!r} did not appear within {timeout}s."
        )

    def _fill_file_dialog(self, dialog, filepath: Path) -> None:
        """Type a file path into a file dialog and confirm."""
        try:
            edit = dialog.Edit
            edit.set_text("")
            edit.type_keys(str(filepath), with_spaces=True)
        except Exception:
            log.debug("Could not find Edit control, typing directly")
            pyautogui.hotkey("ctrl", "a")
            time.sleep(0.1)
            pyautogui.typewrite(str(filepath), interval=0.02)

        time.sleep(0.5)
        self._click_button(
            dialog, list(self._BTN_OPEN | self._BTN_SAVE | self._BTN_OK),
        )

    @staticmethod
    def _send_button_click(
        btn_hwnd: int, dlg_hwnd: int, *, non_blocking: bool = False
    ) -> None:
        """Click a button using WM_COMMAND (most reliable for Delphi).

        Sends a BN_CLICKED WM_COMMAND to the parent dialog, which is what
        Windows does internally when a button is pressed. This works on
        Delphi TButton which may ignore BM_CLICK messages.

        Falls back to BM_CLICK if the control ID cannot be retrieved.
        """
        ctrl_id = user32.GetDlgCtrlID(btn_hwnd)
        send = PostMessageW if non_blocking else SendMessageW
        if ctrl_id:
            # BN_CLICKED = 0 → HIWORD(wParam)=0, LOWORD(wParam)=ctrl_id
            send(dlg_hwnd, WM_COMMAND, ctrl_id, btn_hwnd)
        else:
            send(btn_hwnd, BM_CLICK, 0, 0)

    def _click_button(self, dialog, button_names: list[str]) -> None:
        """Try to click one of the named buttons in a dialog.

        Uses BM_CLICK which works for standard Delphi TButton controls
        (Analyze Session, completion dialogs, etc.).  For dialogs where
        BM_CLICK doesn't work, use _send_button_click (WM_COMMAND) instead.
        """
        dlg_hwnd = dialog.handle if hasattr(dialog, "handle") else int(dialog)
        buttons = self._find_buttons(dlg_hwnd)

        # Normalize target names: strip '&' for matching
        targets = [n.replace("&", "").lower() for n in button_names]

        for btn_hwnd, btn_text in buttons:
            clean = btn_text.replace("&", "").lower()
            if clean in targets:
                log.debug("Clicking button %r via BM_CLICK", btn_text)
                SendMessageW(btn_hwnd, BM_CLICK, 0, 0)
                return

        # Fallback: click the first button found
        if buttons:
            btn_hwnd, btn_text = buttons[0]
            log.debug("No target button found, clicking first: %r", btn_text)
            SendMessageW(btn_hwnd, BM_CLICK, 0, 0)
            return

        # Last resort: send Enter to the dialog
        log.debug("No buttons found, sending Enter to dialog")
        PostMessageW(dlg_hwnd, 0x0100, 0x0D, 0)  # WM_KEYDOWN VK_RETURN

    @staticmethod
    def _find_buttons(hwnd: int) -> list[tuple[int, str]]:
        """Find all button controls in a window via Win32."""
        buttons = []

        def _enum_cb(child_hwnd, _lparam):
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(child_hwnd, cls, 64)
            if cls.value in ("Button", "TButton", "TBitBtn"):
                txt = ctypes.create_unicode_buffer(64)
                user32.GetWindowTextW(child_hwnd, txt, 64)
                if txt.value:
                    buttons.append((child_hwnd, txt.value))
            return True

        user32.EnumChildWindows(hwnd, WNDENUMPROC(_enum_cb), 0)
        return buttons

    def _dismiss_unexpected_dialogs(self, accept: bool = True) -> None:
        """Try to dismiss any popup dialogs (save prompts, errors, etc.).

        Uses Win32 EnumWindows to find ALL dialogs belonging to XG's process,
        including Delphi dialogs (TAddToProfileDlg, TAnalyzeLevelDlg, etc.)
        that pywinauto cannot see.

        For windows with buttons: click the appropriate one.
        For buttonless windows (e.g. TStartDlg): hide + WM_CLOSE in headless,
        or skip in non-headless mode.
        """
        main_handle = self._hwnd

        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(main_handle, ctypes.byref(pid))
        xg_pid = pid.value

        # Re-hide main window if Delphi restored it
        if self.headless and user32.IsWindowVisible(main_handle):
            user32.ShowWindow(main_handle, 0)  # SW_HIDE

        for _ in range(8):
            dlg_hwnd = self._find_xg_dialog(
                xg_pid, main_handle, skip=self._skip_hwnds
            )
            if not dlg_hwnd:
                break

            title = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(dlg_hwnd, title, 256)

            buttons = self._find_buttons(dlg_hwnd)
            if not buttons:
                if self.headless:
                    user32.ShowWindow(dlg_hwnd, 0)  # SW_HIDE
                    log.debug("Closing buttonless dialog: %s", title.value)
                    PostMessageW(dlg_hwnd, WM_CLOSE, 0, 0)
                    time.sleep(0.3)
                self._skip_hwnds.add(dlg_hwnd)
                continue

            if self.headless:
                user32.ShowWindow(dlg_hwnd, 0)  # SW_HIDE

            log.debug("Dismissing dialog: %s", title.value)

            # Stuck file dialogs (Edit control + Open/Save/Import title)
            # are closed via WM_CLOSE rather than clicking the accept
            # button: at this point the dialog is in an error state
            # (file-not-found from a prior failed attempt) and clicking
            # the accept button just retriggers the error popup.
            # Multilingual: matches the same _BTN_* sets used elsewhere
            # in this file for XG's 7 supported locales.
            _has_edit = bool(
                user32.GetDlgItem(dlg_hwnd, 0x047C)
                or self._find_child_by_class(
                    dlg_hwnd, ["Edit", "TEdit"]
                )
            )
            _file_dialog_kw = (
                self._BTN_OPEN | self._BTN_SAVE | self._BTN_IMPORT
            )
            title_lower = title.value.lower()
            _is_file_dlg = _has_edit and any(
                kw in title_lower for kw in _file_dialog_kw
            )
            if _is_file_dlg:
                log.debug(
                    "Stuck file dialog %r — sending WM_CLOSE",
                    title.value,
                )
                PostMessageW(dlg_hwnd, WM_CLOSE, 0, 0)
                time.sleep(0.5)
                if user32.IsWindow(dlg_hwnd):
                    log.warning(
                        "WM_CLOSE ignored — file dialog %r still "
                        "alive; adding to skip set",
                        title.value,
                    )
                    self._skip_hwnds.add(dlg_hwnd)
                continue

            btn_targets = self._ACCEPT_BUTTONS if accept else self._REJECT_BUTTONS

            # Try matching a target button, fall back to first button
            clicked = False
            for btn_hwnd, btn_text in buttons:
                if btn_text.replace("&", "").lower() in btn_targets:
                    log.debug("Clicking button %r via BM_CLICK", btn_text)
                    SendMessageW(btn_hwnd, BM_CLICK, 0, 0)
                    clicked = True
                    break
            if not clicked:
                btn_hwnd = buttons[0][0]
                log.debug("Clicking first button via BM_CLICK")
                SendMessageW(btn_hwnd, BM_CLICK, 0, 0)
            time.sleep(0.5)

    def _wait_for_dialogs_cleared(
        self, max_wait: float = 5.0, settle: float = 1.5
    ) -> None:
        """Wait until no XG dialogs exist, dismissing any found.

        After the last dialog is dismissed, waits an additional `settle`
        seconds to catch late-arriving dialogs (e.g. "Confirm Save As"
        that appears after the Save dialog closes).
        """
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(self._hwnd, ctypes.byref(pid))
        xg_pid = pid.value
        deadline = time.time() + max_wait
        last_dismiss_time = time.time()

        while time.time() < deadline:
            dlg_hwnd = self._find_xg_dialog(
                xg_pid, self._hwnd, skip=self._skip_hwnds
            )
            if not dlg_hwnd:
                if time.time() - last_dismiss_time >= settle:
                    return  # Settled — truly clear
                time.sleep(0.3)
                continue

            # Check if this window has buttons we can click
            buttons = self._find_buttons(dlg_hwnd)
            if not buttons:
                if self.headless:
                    user32.ShowWindow(dlg_hwnd, 0)  # SW_HIDE
                    PostMessageW(dlg_hwnd, WM_CLOSE, 0, 0)
                self._skip_hwnds.add(dlg_hwnd)
                time.sleep(0.3)
                continue

            last_dismiss_time = time.time()

            if self.headless:
                user32.ShowWindow(dlg_hwnd, 0)  # SW_HIDE

            title = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(dlg_hwnd, title, 256)
            title_lower = title.value.lower()
            log.debug("Dismissing lingering dialog: %s", title.value)

            # For file dialogs (Open/Save/Import), try WM_COMMAND IDOK
            # first — this is the most reliable way to confirm a Windows
            # Common File Dialog across all Windows versions and locales.
            # Uses translation sets to match all 7 XG languages.
            _file_dialog_kw = self._BTN_OPEN | self._BTN_SAVE | self._BTN_IMPORT
            if any(kw in title_lower for kw in _file_dialog_kw):
                log.debug("Trying WM_COMMAND IDOK for file dialog %r",
                           title.value)
                PostMessageW(dlg_hwnd, WM_COMMAND, IDOK, 0)
                time.sleep(0.5)
                if not user32.IsWindow(dlg_hwnd):
                    log.debug("File dialog closed via IDOK")
                    last_dismiss_time = time.time()
                    continue
                # IDOK didn't close it — clicking the accept button now
                # would just retrigger the same error popup. Force-close
                # via WM_CLOSE; if even that fails, blacklist the hwnd
                # so we stop targeting it.
                log.debug(
                    "File dialog %r did not close via IDOK — "
                    "sending WM_CLOSE", title.value,
                )
                PostMessageW(dlg_hwnd, WM_CLOSE, 0, 0)
                time.sleep(0.5)
                if user32.IsWindow(dlg_hwnd):
                    log.warning(
                        "WM_CLOSE ignored for file dialog %r — "
                        "blacklisting hwnd",
                        title.value,
                    )
                    self._skip_hwnds.add(dlg_hwnd)
                continue

            # Click the first non-reject button via WM_COMMAND.
            reject = self._REJECT_BUTTONS
            btn_texts = [t for _, t in buttons]
            target = next(
                ((h, t) for h, t in buttons
                 if t.replace("&", "").lower() not in reject),
                None,
            )
            if target:
                btn_hwnd, btn_text = target
                log.debug(
                    "Clicking %r in %r (all: %s)",
                    btn_text, title.value, btn_texts,
                )
                self._send_button_click(
                    btn_hwnd, dlg_hwnd, non_blocking=True,
                )
            else:
                log.debug(
                    "Only reject buttons in %r (all: %s), skipping",
                    title.value, btn_texts,
                )
                self._skip_hwnds.add(dlg_hwnd)
            time.sleep(0.5)

        log.debug("Dialogs still present after %.1fs wait", max_wait)

    # Window classes that are never actionable dialogs
    _SKIP_CLASSES = {"TApplication", "IME", "MSCTFIME UI"}

    def _find_xg_dialog(
        self, xg_pid: int, main_handle: int, skip: set | None = None
    ) -> int:
        """Find a dialog window belonging to XG's process.

        In headless mode, finds dialogs regardless of visibility
        (since we hide dialogs to prevent screen flashing).

        Args:
            skip: Set of hwnds to ignore (e.g. buttonless windows already seen).
        """
        found = [0]
        headless = self.headless
        skip_set = skip or set()
        skip_classes = self._SKIP_CLASSES

        def _enum_cb(hwnd, _lparam):
            h = int(hwnd)
            if h in skip_set or h == main_handle:
                return True
            # In headless mode, find dialogs even if hidden (we hide them ourselves)
            if not headless and not user32.IsWindowVisible(hwnd):
                return True
            # Check if this window belongs to XG's process
            pid = wt.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value != xg_pid:
                return True
            # Skip system/helper window classes
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, cls, 64)
            if cls.value in skip_classes:
                return True
            # Check it has a title
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            if not buf.value:
                return True
            found[0] = h
            return False  # Stop enumeration

        user32.EnumWindows(WNDENUMPROC(_enum_cb), 0)
        return found[0]
