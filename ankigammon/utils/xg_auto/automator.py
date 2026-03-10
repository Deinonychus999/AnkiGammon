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


def _try_import_hooks():
    try:
        from .hooks import XGEventHooks, EventType
        return XGEventHooks, EventType
    except (ImportError, Exception):
        return None, None

CLASS_NAME = "TMainX"

# Win32 constants
WM_COMMAND = 0x0111
WM_CLOSE = 0x0010
WM_GETTEXT = 0x000D
WM_GETTEXTLENGTH = 0x000E
BM_CLICK = 0x00F5
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

PostMessageW = user32.PostMessageW
PostMessageW.argtypes = [wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM]
PostMessageW.restype = wt.BOOL

SendMessageW = user32.SendMessageW
SendMessageW.argtypes = [wt.HWND, ctypes.c_uint, wt.WPARAM, wt.LPARAM]
SendMessageW.restype = wt.LPARAM

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

    # XG analysis level indices (in the TComboBox dropdown)
    ANALYSIS_LEVELS = {
        "none": 0,
        "very quick": 1,
        "fast": 2,
        "deep": 3,
        "thorough": 4,
        "world class": 5,
        "extensive": 6,
    }

    def __init__(
        self,
        xg_path: Path | None = None,
        backend: str = "win32",
        poll_interval: float = 3.0,
        timeout: float = 600.0,
        use_memory_reader: bool = False,
        use_hooks: bool = False,
        address_map_path: Optional[Path | str] = None,
        hook_timeout: float = 5.0,
        analysis_level: Optional[str] = None,
        headless: bool = False,
    ):
        self.xg_path = xg_path
        self.backend = backend
        self.poll_interval = poll_interval
        self.timeout = timeout
        self.use_memory_reader = use_memory_reader
        self.use_hooks = use_hooks
        self.headless = headless
        if headless:
            self.use_hooks = True  # Headless requires Frida hooks
        self.address_map_path = address_map_path
        self.hook_timeout = hook_timeout
        self.analysis_level = analysis_level
        self.app: Application | None = None
        self._main = None
        self._hwnd: int = 0
        self._cmd: XGCommandProfile | None = None
        self._xg_base_title: str = ""
        self._memory = None   # Optional[XGMemoryReader]
        self._hooks = None    # Optional[XGEventHooks]
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
            self._setup_hooks()

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

    def _connect_headless(self) -> None:
        """Connect via pure Win32 and hide the window (headless mode).

        Always launches a new hidden XG instance to avoid hijacking any
        user-visible XG window. XG supports multiple instances.

        Attaches Frida hooks as early as possible so the in-process
        ShowWindow(SW_HIDE) hook catches startup dialogs at creation time.
        """
        if not self.xg_path or not self.xg_path.exists():
            raise XGAutomationError(
                "eXtreme Gammon 2 exe path is not set or does not exist."
            )

        # Collect existing XG window handles so we can identify our new one
        existing_hwnds = set()

        def _collect_existing(hwnd, _lparam):
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, cls, 64)
            if cls.value == CLASS_NAME:
                existing_hwnds.add(int(hwnd))
            return True

        user32.EnumWindows(WNDENUMPROC(_collect_existing), 0)

        if existing_hwnds:
            log.info(
                "Found %d existing XG instance(s) — launching a new one.",
                len(existing_hwnds),
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

        # Attach hooks BEFORE waiting so the in-process
        # CreateWindowExW hook hides startup dialogs at creation time.
        self._setup_memory_reader()
        self._setup_hooks()

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

    def _setup_hooks(self) -> None:
        """Initialize Frida event hooks if requested and available."""
        if not self.use_hooks:
            return

        HooksClass, _ = _try_import_hooks()
        if HooksClass is None:
            log.info("frida not installed. Event hooks disabled.")
            return

        try:
            pid = wt.DWORD()
            user32.GetWindowThreadProcessId(self._hwnd, ctypes.byref(pid))

            self._hooks = HooksClass(headless=self.headless)
            if self._hooks.attach(pid.value):
                log.info("Frida hooks attached successfully.")
            else:
                log.warning("Frida hooks failed to attach. Falling back to polling.")
                self._hooks = None
        except Exception as e:
            log.warning("Frida hooks setup failed: %s", e)
            self._hooks = None

    def disconnect(self) -> None:
        """Clean up optional subsystems."""
        if self.headless and self._hwnd:
            # Close XG entirely — no reason to leave a hidden process running
            PostMessageW(self._hwnd, WM_CLOSE, 0, 0)
            time.sleep(1.0)
            # Dismiss any "save changes?" dialogs
            self._dismiss_unexpected_dialogs(accept=False)
            log.info("XG closed (headless cleanup).")
        if self._hooks:
            try:
                self._hooks.detach()
            except Exception:
                pass
            self._hooks = None
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

        # Set analysis level if configured
        if self.analysis_level:
            level_idx = self.ANALYSIS_LEVELS.get(
                self.analysis_level.lower()
            )
            if level_idx is not None:
                self._set_analysis_level(dlg_hwnd, level_idx)
            else:
                log.warning(
                    "Unknown analysis level %r, using default",
                    self.analysis_level,
                )

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

    def _set_analysis_level(self, dlg_hwnd: int, level_idx: int) -> None:
        """Set both player ComboBoxes in the analysis dialog to a level."""
        CB_SETCURSEL = 0x014E
        combos = []

        def _enum_cb(hwnd, _lparam):
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, cls, 64)
            if cls.value == "TComboBox":
                combos.append(hwnd)
            return True

        user32.EnumChildWindows(dlg_hwnd, WNDENUMPROC(_enum_cb), 0)

        for combo_hwnd in combos:
            SendMessageW(combo_hwnd, CB_SETCURSEL, level_idx, 0)

        level_name = next(
            (k for k, v in self.ANALYSIS_LEVELS.items() if v == level_idx),
            str(level_idx),
        )
        log.info(
            "Set analysis level to %r for %d player(s)",
            level_name,
            len(combos),
        )

    def _wait_for_analysis(self) -> None:
        """Wait for analysis completion using a hybrid approach.

        Combines hooks (if available) with UI polling in a single loop.
        Every poll_interval, checks: hook events, completion dialog,
        menu state, and status bar. This avoids blocking exclusively
        on hooks that may miss certain dialog creation patterns.
        """
        _, EventType = _try_import_hooks()
        start = time.time()
        use_hooks = bool(
            self._hooks and self._hooks.is_attached and EventType
        )

        if use_hooks:
            # Drain stale events, but check if analysis already completed
            # (happens for very short matches that finish before we start polling)
            for event in self._hooks.drain_events():
                if event.event_type == EventType.ANALYSIS_COMPLETE:
                    log.info("Analysis already complete (event in queue)")
                    time.sleep(1.0)
                    self._dismiss_unexpected_dialogs()
                    return

        log.info(
            "Waiting for analysis (timeout: %.0fs, poll: %.1fs, hooks: %s)...",
            self.timeout,
            self.poll_interval,
            use_hooks,
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
            # Check hook events (non-blocking, wait up to poll_interval)
            if use_hooks:
                event = self._hooks.wait_for_event(
                    EventType.ANALYSIS_COMPLETE,
                    timeout=self.poll_interval,
                )
                if event is not None:
                    log.info(
                        "Analysis complete (hook: %s)",
                        event.data.get("trigger", "unknown"),
                    )
                    time.sleep(1.0)
                    self._dismiss_unexpected_dialogs()
                    return

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

            if not use_hooks:
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

        self._click_button(_HwndWrap(dlg_hwnd), ["No", "OK", "Close", "Yes"])
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
        """
        self.send_command(cmd_id)

        deadline = time.time() + 10.0
        while time.time() < deadline:
            dlg_hwnd = self._find_file_dialog_win32()
            if dlg_hwnd:
                user32.ShowWindow(dlg_hwnd, 0)  # SW_HIDE
                non_block = dialog_type == "save"
                self._autofill_file_dialog_win32(
                    dlg_hwnd, filepath, non_blocking=non_block,
                )
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

        # Strategy 1: Find the filename ComboBoxEx32 by control ID (0x047C),
        # then get the Edit inside it.
        GetDlgItem = user32.GetDlgItem
        GetDlgItem.restype = wt.HWND
        combo_ex = GetDlgItem(dlg_hwnd, 0x047C)
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

        # Press Enter in the Edit control instead of clicking the button.
        # IFileDialog processes Enter differently from BM_CLICK: it reads
        # the Edit text, parses it as a path, and navigates/opens/saves.
        # BM_CLICK reads the dialog's internal COM state which WM_CHAR
        # doesn't update.
        if edit_hwnd:
            WM_KEYDOWN = 0x0100
            WM_KEYUP = 0x0101
            VK_RETURN = 0x0D
            if non_blocking:
                log.debug("Pressing Enter in file dialog (PostMessage)")
                PostMessageW(edit_hwnd, WM_KEYDOWN, VK_RETURN, 0x001C0001)
                PostMessageW(edit_hwnd, WM_KEYUP, VK_RETURN, 0xC01C0001)
            else:
                log.debug("Pressing Enter in file dialog (SendMessage)")
                SendMessageW(edit_hwnd, WM_KEYDOWN, VK_RETURN, 0x001C0001)
                SendMessageW(edit_hwnd, WM_KEYUP, VK_RETURN, 0xC01C0001)
        else:
            # Fallback: click the button directly
            class _HwndWrap:
                def __init__(self, h):
                    self.handle = h

            self._click_button(
                _HwndWrap(dlg_hwnd),
                ["Open", "Save", "OK", "&Open", "&Save"],
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
        self._click_button(dialog, ["Open", "Save", "OK", "&Open", "&Save"])

    def _click_button(self, dialog, button_names: list[str]) -> None:
        """Try to click one of the named buttons in a dialog.

        Uses Win32 EnumChildWindows + BM_CLICK to reliably click buttons,
        even for Delphi dialogs with &-prefixed labels (e.g. '&Yes').
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
        accept_names = ["OK", "Yes", "Continue", "Close"]
        reject_names = ["Cancel", "No", "Close"]
        btn_names = accept_names if accept else reject_names

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

            class _HwndWrap:
                def __init__(self, h):
                    self.handle = h
            self._click_button(_HwndWrap(dlg_hwnd), btn_names)
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
            log.debug("Dismissing lingering dialog: %s", title.value)

            targets = ["OK", "Yes", "Open", "&Open", "&Yes", "Close"]
            target_set = {n.replace("&", "").lower() for n in targets}
            clicked = False
            for btn_hwnd, btn_text in buttons:
                if btn_text.replace("&", "").lower() in target_set:
                    log.debug("Clicking button %r via BM_CLICK", btn_text)
                    # Use PostMessage to avoid blocking on modal dialogs
                    # (e.g. clicking Save triggers an overwrite confirmation
                    # which would deadlock SendMessageW)
                    PostMessageW(btn_hwnd, BM_CLICK, 0, 0)
                    clicked = True
                    break
            if not clicked:
                # No matching target button — skip this dialog instead of
                # clicking a random button (which could trigger modal dialogs
                # and deadlock via SendMessageW).
                log.debug("No target button found in %r, skipping", title.value)
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
