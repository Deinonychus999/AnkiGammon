"""XG2 must not be left running after AnkiGammon is done with it.

Reported on Reddit: "a background process of xg2 is left after everything is
shutdown."

disconnect() only closed XG on the headless branch, so GUI-mode automation
launched an XG via Popen and then abandoned it. An XG the user already had
open is theirs and must survive - only an instance we started gets closed.
"""

import sys
from pathlib import Path
from unittest import mock

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="XG automation is Windows-only"
)

pytest.importorskip("pywinauto")

from ankigammon.utils.xg_auto import automator as automator_mod  # noqa: E402
from ankigammon.utils.xg_auto.automator import WM_CLOSE, XGAutomator  # noqa: E402


HWND = 0x1234


@pytest.fixture
def win32(tmp_path):
    """Neutralise the Win32 surface and record posted messages."""
    xg_exe = tmp_path / "eXtremeGammon2.exe"
    xg_exe.write_bytes(b"")

    posted = []
    fake_app = mock.MagicMock()
    fake_app.top_window.return_value.handle = HWND

    with mock.patch.object(automator_mod, "PostMessageW",
                           side_effect=lambda h, m, w, l: posted.append((h, m))), \
         mock.patch.object(automator_mod, "Application", return_value=fake_app), \
         mock.patch.object(automator_mod.subprocess, "Popen") as popen, \
         mock.patch.object(automator_mod.time, "sleep"), \
         mock.patch.object(XGAutomator, "_detect_xg_version", return_value=automator_mod.XGCmd), \
         mock.patch.object(XGAutomator, "_dismiss_unexpected_dialogs"):
        yield {"exe": xg_exe, "posted": posted, "popen": popen, "app": fake_app}


def _closed(win32):
    return any(msg == WM_CLOSE and h == HWND for h, msg in win32["posted"])


class TestGuiModeOwnership:
    def test_xg_we_launched_is_closed_on_disconnect(self, win32):
        """Application.connect() failing first means no XG was running."""
        win32["app"].connect.side_effect = [
            automator_mod.ElementNotFoundError(), win32["app"]
        ]
        auto = XGAutomator(xg_path=win32["exe"], headless=False)
        auto.connect()

        assert win32["popen"].called, "expected XG to be launched"
        auto.disconnect()

        assert _closed(win32), "an XG we launched must not be left running"

    def test_xg_the_user_already_had_open_is_left_alone(self, win32):
        auto = XGAutomator(xg_path=win32["exe"], headless=False)
        auto.connect()

        assert not win32["popen"].called
        auto.disconnect()

        assert not _closed(win32), "the user's own XG window must survive"

    def test_disconnect_is_idempotent(self, win32):
        win32["app"].connect.side_effect = [
            automator_mod.ElementNotFoundError(), win32["app"]
        ]
        auto = XGAutomator(xg_path=win32["exe"], headless=False)
        auto.connect()

        auto.disconnect()
        auto.disconnect()

        closes = [1 for h, msg in win32["posted"] if msg == WM_CLOSE and h == HWND]
        assert len(closes) == 1

    def test_disconnect_without_connect_is_a_no_op(self, win32):
        auto = XGAutomator(xg_path=win32["exe"], headless=False)
        auto.disconnect()

        assert not _closed(win32)


class TestHeadlessModeUnchanged:
    def test_headless_still_closes_its_hidden_instance(self, win32):
        auto = XGAutomator(xg_path=win32["exe"], headless=True)
        auto._hwnd = HWND

        auto.disconnect()

        assert _closed(win32)


class TestProcessIsReallyGone:
    """WM_CLOSE is a request XG can decline.

    Verified against a real XG2: a buttonless startup dialog is skipped in
    GUI mode and blocks the main window from processing the close, so the
    process outlives disconnect() unless it is killed outright.
    """

    def _launched(self, win32):
        win32["app"].connect.side_effect = [
            automator_mod.ElementNotFoundError(), win32["app"]
        ]
        auto = XGAutomator(xg_path=win32["exe"], headless=False)
        auto.connect()
        return auto, win32["popen"].return_value

    def test_process_that_exits_on_wm_close_is_not_killed(self, win32):
        auto, proc = self._launched(win32)
        proc.wait.return_value = 0

        auto.disconnect()

        assert not proc.kill.called

    def test_process_that_ignores_wm_close_is_killed(self, win32):
        auto, proc = self._launched(win32)
        proc.wait.side_effect = automator_mod.subprocess.TimeoutExpired("xg", 8)

        auto.disconnect()

        assert proc.kill.called, "an XG that ignores WM_CLOSE must be terminated"

    def test_the_users_own_xg_is_never_killed(self, win32):
        """No Popen handle means no process of ours to reap."""
        auto = XGAutomator(xg_path=win32["exe"], headless=False)
        auto.connect()

        auto.disconnect()

        assert not win32["popen"].called
        assert auto._xg_process is None

    def test_reaping_is_not_repeated_on_a_second_disconnect(self, win32):
        auto, proc = self._launched(win32)
        proc.wait.side_effect = automator_mod.subprocess.TimeoutExpired("xg", 8)

        auto.disconnect()
        auto.disconnect()

        assert proc.kill.call_count == 1

    def test_a_kill_failure_does_not_propagate(self, win32):
        auto, proc = self._launched(win32)
        proc.wait.side_effect = automator_mod.subprocess.TimeoutExpired("xg", 8)
        proc.kill.side_effect = OSError("access denied")

        auto.disconnect()  # must not raise
