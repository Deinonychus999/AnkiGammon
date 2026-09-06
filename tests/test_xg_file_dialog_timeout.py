"""The three things behind an intermittent "Headless file open timed out".

Version detection read the window title for 6s and silently fell back to the
2.10 command profile. On 2.19 every menu ID differs, and 2.10's
IMPORT_POS_TEXT is an unlisted slot, so the command lands on nothing and the
file dialog never appears. The exe's version resource is deterministic and
now decides the profile; the title loop still runs, but only to capture the
base title, exactly as before.

_skip_hwnds collected buttonless startup dialogs and was never pruned.
Windows recycles HWNDs, so a dead entry could shadow the file dialog that
later reused its handle. Dead entries are now dropped before each search,
and before a file command is sent.

The timeout itself carried nothing but a path. It now records the profile,
the title, the skip set and every top-level window in XG's process.
"""

import ctypes
import itertools
import sys
from pathlib import Path
from unittest import mock

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="XG automation is Windows-only")
pytest.importorskip("pywinauto")

from ankigammon.utils.xg_auto import automator as automator_mod  # noqa: E402
from ankigammon.utils.xg_auto.automator import (  # noqa: E402
    XG_PROFILES,
    XGAutomationError,
    XGAutomator,
)
from tests.conftest import XG_EXE  # noqa: E402

HWND = 0x1234
P210, P219 = XG_PROFILES["2.10"], XG_PROFILES["2.19"]
PLACEHOLDER = "eXtreme Gammon IDE"
VERSIONED = "eXtreme Gammon 2.19.211.pre-release"


def _auto(xg_path=None):
    auto = XGAutomator(xg_path=xg_path, headless=True)
    auto._hwnd = HWND
    return auto


def _titles(sequence):
    """Patch user32 so GetWindowTextW on the main window yields these titles in turn."""
    remaining = list(sequence)

    def get_text(hwnd, buf, n):
        buf.value = remaining.pop(0) if len(remaining) > 1 else remaining[0]
        return len(buf.value)

    fake = mock.MagicMock()
    fake.GetWindowTextW.side_effect = get_text
    return mock.patch.object(automator_mod, "user32", fake)


# ---------------------------------------------------------------------------
# A. Version detection
# ---------------------------------------------------------------------------

class TestExeDecidesTheProfile:
    def test_exe_version_wins_when_the_title_never_carries_one(self):
        """The reported path: placeholder title, silent 2.10, wrong menu IDs."""
        auto = _auto()
        with mock.patch.object(XGAutomator, "_profile_from_exe", return_value=P219), \
             _titles([PLACEHOLDER]), mock.patch.object(automator_mod.time, "sleep"):
            assert auto._detect_xg_version() is P219

    def test_exe_and_title_agreeing_is_the_normal_case(self):
        auto = _auto()
        with mock.patch.object(XGAutomator, "_profile_from_exe", return_value=P219), \
             _titles([PLACEHOLDER, VERSIONED]), mock.patch.object(automator_mod.time, "sleep"):
            assert auto._detect_xg_version() is P219
        assert auto._xg_base_title == VERSIONED

    def test_base_title_is_still_only_taken_from_a_versioned_title(self):
        """Grabbing the placeholder as base would make position-load waits return early."""
        auto = _auto()
        with mock.patch.object(XGAutomator, "_profile_from_exe", return_value=P219), \
             _titles([PLACEHOLDER, PLACEHOLDER, VERSIONED]), \
             mock.patch.object(automator_mod.time, "sleep"):
            auto._detect_xg_version()
        assert auto._xg_base_title == VERSIONED


class TestBehaviourWithoutExeInfoIsUnchanged:
    """Anyone whose setup works today must see no difference."""

    def test_versioned_title_is_still_detected(self):
        auto = _auto()
        with mock.patch.object(XGAutomator, "_profile_from_exe", return_value=None), \
             _titles([PLACEHOLDER, VERSIONED]), mock.patch.object(automator_mod.time, "sleep"):
            assert auto._detect_xg_version() is P219
        assert auto._xg_base_title == VERSIONED

    def test_placeholder_forever_still_falls_back_to_2_10(self):
        auto = _auto()
        with mock.patch.object(XGAutomator, "_profile_from_exe", return_value=None), \
             _titles([PLACEHOLDER]), mock.patch.object(automator_mod.time, "sleep"):
            assert auto._detect_xg_version() is P210
        assert auto._xg_base_title == PLACEHOLDER

    def test_fallback_still_retries_the_title_six_times(self):
        auto = _auto()
        with mock.patch.object(XGAutomator, "_profile_from_exe", return_value=None), \
             _titles([PLACEHOLDER]), \
             mock.patch.object(automator_mod.time, "sleep") as sleep:
            auto._detect_xg_version()
        assert sleep.call_count == 5


class TestProfileFromExe:
    def test_uses_xg_path_when_it_exists(self, tmp_path):
        exe = tmp_path / "eXtremeGammon2.exe"
        exe.write_bytes(b"")
        auto = _auto(xg_path=exe)
        with mock.patch.object(automator_mod, "_read_file_version",
                               return_value="2.19.211.2671") as read:
            assert auto._profile_from_exe() is P219
        read.assert_called_once_with(exe)

    def test_falls_back_to_the_process_path_for_a_users_own_instance(self, tmp_path):
        """GUI mode attaches to an XG we did not launch, so xg_path is None."""
        auto = _auto(xg_path=None)
        with mock.patch.object(automator_mod, "_exe_path_for_hwnd",
                               return_value=Path("C:/xg/eXtremeGammon2.exe")) as by_hwnd, \
             mock.patch.object(automator_mod, "_read_file_version", return_value="2.10.5.0"):
            assert auto._profile_from_exe() is P210
        by_hwnd.assert_called_once_with(HWND)

    def test_a_version_with_no_profile_yields_none(self):
        auto = _auto(xg_path=None)
        with mock.patch.object(automator_mod, "_exe_path_for_hwnd", return_value=Path("x.exe")), \
             mock.patch.object(automator_mod, "_read_file_version", return_value="2.20.0.0"):
            assert auto._profile_from_exe() is None

    def test_an_unreadable_exe_yields_none(self):
        auto = _auto(xg_path=None)
        with mock.patch.object(automator_mod, "_exe_path_for_hwnd", return_value=Path("x.exe")), \
             mock.patch.object(automator_mod, "_read_file_version", return_value=None):
            assert auto._profile_from_exe() is None

    def test_no_path_at_all_yields_none(self):
        auto = _auto(xg_path=None)
        with mock.patch.object(automator_mod, "_exe_path_for_hwnd", return_value=None):
            assert auto._profile_from_exe() is None


class TestReadFileVersion:
    def test_reads_the_real_xg_executable(self):
        if XG_EXE is None:
            pytest.skip("eXtreme Gammon 2 not found")
        version = automator_mod._read_file_version(Path(XG_EXE))

        assert version and version.startswith("2."), version

    def test_missing_file_yields_none_not_an_exception(self, tmp_path):
        assert automator_mod._read_file_version(tmp_path / "nope.exe") is None

    def test_a_file_with_no_version_resource_yields_none(self, tmp_path):
        bare = tmp_path / "bare.exe"
        bare.write_bytes(b"MZ")
        assert automator_mod._read_file_version(bare) is None


# ---------------------------------------------------------------------------
# B. Skip-set pruning
# ---------------------------------------------------------------------------

class TestSkipSetPruning:
    def test_dead_hwnds_are_dropped(self):
        auto = _auto()
        auto._skip_hwnds = {1, 2, 3}
        fake = mock.MagicMock()
        fake.IsWindow.side_effect = lambda h: h != 2
        with mock.patch.object(automator_mod, "user32", fake):
            auto._prune_dead_skip_hwnds()

        assert auto._skip_hwnds == {1, 3}

    def test_live_hwnds_are_kept(self):
        auto = _auto()
        auto._skip_hwnds = {1, 2}
        fake = mock.MagicMock()
        fake.IsWindow.return_value = True
        with mock.patch.object(automator_mod, "user32", fake):
            auto._prune_dead_skip_hwnds()

        assert auto._skip_hwnds == {1, 2}

    def test_pruning_happens_before_the_file_command_is_sent(self):
        """A handle freed by a closed startup dialog must be forgotten before
        the file dialog can be created with that same handle."""
        auto = _auto()
        order = []
        with mock.patch.object(XGAutomator, "_prune_dead_skip_hwnds",
                               side_effect=lambda: order.append("prune")), \
             mock.patch.object(XGAutomator, "send_command",
                               side_effect=lambda cmd: order.append("send")), \
             mock.patch.object(XGAutomator, "_find_file_dialog_win32", return_value=0x50), \
             mock.patch.object(XGAutomator, "_autofill_file_dialog_win32"), \
             mock.patch.object(automator_mod, "user32"):
            auto._headless_file_operation(Path("x.txt"), 127, "open")

        assert order[:2] == ["prune", "send"]

    def test_file_dialog_finder_prunes_before_searching(self):
        auto = _auto()
        auto._skip_hwnds = {0x50}
        fake = mock.MagicMock()
        fake.IsWindow.return_value = False  # 0x50 is dead at search time
        fake.EnumWindows.return_value = 0
        with mock.patch.object(automator_mod, "user32", fake), \
             mock.patch.object(automator_mod, "WNDENUMPROC", lambda f: f):
            auto._find_file_dialog_win32()

        assert auto._skip_hwnds == set()


# ---------------------------------------------------------------------------
# D. Diagnostics on timeout
# ---------------------------------------------------------------------------

def _mock_user32_with_windows(windows, pid=4242):
    """user32 whose EnumWindows yields `windows`: {hwnd: (class, title, visible)}."""
    fake = mock.MagicMock()

    def thread_pid(hwnd, pid_ref):
        pid_ref._obj.value = pid
        return 1

    # The main window (HWND) is queried too, for its title.
    lookup = {HWND: ("TMainX", "eXtreme Gammon 2.19.211", True), **windows}
    fake.GetWindowThreadProcessId.side_effect = thread_pid
    fake.EnumWindows.side_effect = lambda cb, _: [cb(h, 0) for h in windows] and 1
    fake.GetClassNameW.side_effect = lambda h, buf, n: setattr(buf, "value", lookup[h][0])
    fake.GetWindowTextW.side_effect = lambda h, buf, n: setattr(buf, "value", lookup[h][1])
    fake.IsWindowVisible.side_effect = lambda h: lookup[h][2]
    fake.IsWindow.return_value = True
    fake.GetDlgItem.return_value = 0
    return fake


class TestTimeoutDiagnostics:
    def _time_out(self, auto, user32):
        with mock.patch.object(XGAutomator, "send_command"), \
             mock.patch.object(XGAutomator, "_find_file_dialog_win32", return_value=0), \
             mock.patch.object(XGAutomator, "_find_child_by_class", return_value=0), \
             mock.patch.object(automator_mod, "user32", user32), \
             mock.patch.object(automator_mod, "WNDENUMPROC", lambda f: f), \
             mock.patch.object(automator_mod.time, "sleep"), \
             mock.patch.object(automator_mod.time, "time",
                               side_effect=itertools.chain([0.0], itertools.repeat(100.0))):
            with pytest.raises(XGAutomationError) as info:
                auto._headless_file_operation(Path("C:/t/xgid_import.txt"), 127, "open")
        return str(info.value)

    def test_error_names_the_profile_and_lists_xg_windows(self):
        auto = _auto()
        auto._cmd = P219
        auto._skip_hwnds = {0x10}
        user32 = _mock_user32_with_windows({
            0x10: ("TStartDlg", "", False),
            0x20: ("#32770", "Open", True),
        })

        message = self._time_out(auto, user32)

        assert "xgid_import.txt" in message
        assert "2.19" in message
        assert "2 window" in message
        assert "#32770" in message

    def test_a_failing_inventory_never_masks_the_timeout(self):
        auto = _auto()
        auto._cmd = P219
        user32 = mock.MagicMock()
        user32.EnumWindows.side_effect = RuntimeError("enumeration exploded")

        message = self._time_out(auto, user32)

        assert "timed out" in message
        assert "xgid_import.txt" in message
