"""What the diagnostic log from GitHub issue #59 showed, and the fixes for it.

Three score-matrix failures across four days of logs, all inside XG
automation and none of them slowness (889 analyses, max 9s):

* Twice, ``Headless file open timed out`` with the diagnostics reading
  ``title='' ... 0 window(s)``: XG had exited. The analyzer kept driving the
  dead handle, so every remaining cell in that run waited 10s and failed, and
  every remaining card lost its table. One exit became "2 of 4 tables".
* Once, a 600s analysis wait after a leaked "Save Game" dialog. Every
  ``close_match`` had been answering that prompt with **Yes** - a save we
  never want - because ``_dismiss_unexpected_dialogs`` defaults to accept.

So: a dead XG is detected and fails fast; the analyzer relaunches and retries
the position once (only when XG is actually gone - never a blind retry); and
closing a throwaway match answers No.
"""

import itertools
import sys
from pathlib import Path
from unittest import mock

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="XG automation is Windows-only")
pytest.importorskip("pywinauto")

from ankigammon.models import DecisionType  # noqa: E402
from ankigammon.utils.xg_auto import automator as automator_mod  # noqa: E402
from ankigammon.utils.xg_auto.automator import XGAutomationError, XGAutomator  # noqa: E402
from ankigammon.utils.xg_analyzer import XGAnalyzer  # noqa: E402

HWND = 0x1234
XGID = "XGID=-b----E-C--AeD---bAdb---A-:0:0:1:52:0:0:3:0:10"


def _auto(alive=True):
    auto = XGAutomator(xg_path=None, headless=True)
    auto._hwnd = HWND
    return auto


# ---------------------------------------------------------------------------
# close_match answers No
# ---------------------------------------------------------------------------

class TestCloseMatchDoesNotSave:
    def test_save_prompt_is_declined(self):
        auto = _auto()
        with mock.patch.object(XGAutomator, "send_command"), \
             mock.patch.object(XGAutomator, "_dismiss_unexpected_dialogs") as dismiss, \
             mock.patch.object(automator_mod.time, "sleep"):
            auto.close_match()

        dismiss.assert_called_once_with(accept=False)


# ---------------------------------------------------------------------------
# A dead XG is recognised
# ---------------------------------------------------------------------------

class TestIsAlive:
    def test_live_window_is_alive(self):
        auto = _auto()
        fake = mock.MagicMock(); fake.IsWindow.return_value = True
        with mock.patch.object(automator_mod, "user32", fake):
            assert auto.is_alive() is True

    def test_destroyed_window_is_not_alive(self):
        auto = _auto()
        fake = mock.MagicMock(); fake.IsWindow.return_value = False
        with mock.patch.object(automator_mod, "user32", fake):
            assert auto.is_alive() is False

    def test_never_connected_is_not_alive(self):
        auto = XGAutomator(xg_path=None, headless=True)
        assert auto.is_alive() is False


class TestFileOperationFailsFastWhenXgIsGone:
    def test_raises_immediately_naming_the_cause(self):
        """Ten seconds of polling for a dialog from a process that has exited."""
        auto = _auto()
        fake = mock.MagicMock(); fake.IsWindow.return_value = False
        with mock.patch.object(XGAutomator, "send_command"), \
             mock.patch.object(XGAutomator, "_find_file_dialog_win32", return_value=0), \
             mock.patch.object(automator_mod, "user32", fake), \
             mock.patch.object(automator_mod.time, "sleep") as sleep, \
             mock.patch.object(automator_mod.time, "time", side_effect=itertools.count(0.0, 0.3)):
            with pytest.raises(XGAutomationError) as info:
                auto._headless_file_operation(Path("x.txt"), 127, "open")

        assert "no longer running" in str(info.value)
        assert sleep.call_count <= 1, "should not have waited out the 10s timeout"

    def test_a_live_xg_still_gets_the_full_wait(self):
        auto = _auto()
        fake = mock.MagicMock(); fake.IsWindow.return_value = True
        with mock.patch.object(XGAutomator, "send_command"), \
             mock.patch.object(XGAutomator, "_find_file_dialog_win32", return_value=0), \
             mock.patch.object(XGAutomator, "_describe_windows_for_timeout", return_value="x"), \
             mock.patch.object(automator_mod, "user32", fake), \
             mock.patch.object(automator_mod.time, "sleep"), \
             mock.patch.object(automator_mod.time, "time", side_effect=itertools.chain([0.0], itertools.repeat(100.0))):
            with pytest.raises(XGAutomationError) as info:
                auto._headless_file_operation(Path("x.txt"), 127, "open")

        assert "timed out" in str(info.value)


# ---------------------------------------------------------------------------
# The analyzer relaunches a dead XG and retries once
# ---------------------------------------------------------------------------

def _fake_automator(alive=True, import_raises=None):
    a = mock.MagicMock()
    a.is_alive.return_value = alive
    if import_raises:
        a.import_xgid_from_file.side_effect = import_raises
    a.cmd.EXPORT_POS_CLIPBOARD = 131
    a.get_clipboard_text_validated.return_value = "XGID=... analysis text"
    return a


class TestEnsureConnectedReconnectsADeadInstance:
    def test_dead_automator_is_replaced(self):
        analyzer = XGAnalyzer(xg_path="C:/xg.exe")
        dead = _fake_automator(alive=False)
        analyzer._automator, analyzer._connected = dead, True
        fresh = _fake_automator(alive=True)
        with mock.patch("ankigammon.utils.xg_auto.automator.XGAutomator", return_value=fresh) as cls, \
             mock.patch.object(analyzer, "terminate", wraps=analyzer.terminate) as term:
            analyzer._ensure_connected()

        assert analyzer._automator is fresh
        assert cls.called, "a new XG should have been launched"
        assert term.called, "the dead instance should have been cleaned up first"
        fresh.connect.assert_called_once()

    def test_live_automator_is_kept(self):
        analyzer = XGAnalyzer(xg_path="C:/xg.exe")
        live = _fake_automator(alive=True)
        analyzer._automator, analyzer._connected = live, True
        with mock.patch("ankigammon.utils.xg_auto.automator.XGAutomator") as cls:
            analyzer._ensure_connected()

        assert analyzer._automator is live
        assert not cls.called


class TestAnalyzePositionRetriesOnlyWhenXgDied:
    def test_dead_xg_mid_position_relaunches_and_retries_once(self):
        """Alive when the position starts, gone by the time the error is inspected."""
        analyzer = XGAnalyzer(xg_path="C:/xg.exe")
        first = _fake_automator(alive=True, import_raises=XGAutomationError("Headless file open timed out"))
        first.is_alive.side_effect = [True, False]
        second = _fake_automator(alive=True)
        analyzer._automator, analyzer._connected = first, True
        with mock.patch("ankigammon.utils.xg_auto.automator.XGAutomator", return_value=second) as cls, \
             mock.patch("time.sleep"):
            text, kind = analyzer.analyze_position(XGID)

        assert kind == DecisionType.CHECKER_PLAY
        assert text == "XGID=... analysis text"
        first.import_xgid_from_file.assert_called_once()
        second.import_xgid_from_file.assert_called_once()
        second.run_analysis.assert_called_once()
        assert cls.call_count == 1, "exactly one relaunch"

    def test_failure_with_xg_still_alive_is_not_retried(self):
        """A live XG that errors is a real problem; retrying blindly would hide it."""
        analyzer = XGAnalyzer(xg_path="C:/xg.exe")
        live = _fake_automator(alive=True, import_raises=XGAutomationError("Headless file open timed out"))
        analyzer._automator, analyzer._connected = live, True
        with mock.patch("ankigammon.utils.xg_auto.automator.XGAutomator") as cls, \
             mock.patch.object(automator_mod.time, "sleep"):
            with pytest.raises(XGAutomationError):
                analyzer.analyze_position(XGID)

        assert not cls.called
        assert live.import_xgid_from_file.call_count == 1

    def test_a_second_death_is_not_retried_again(self):
        """One relaunch, one retry; if the relaunched XG dies too, give up."""
        analyzer = XGAnalyzer(xg_path="C:/xg.exe")
        first = _fake_automator(alive=True, import_raises=XGAutomationError("gone"))
        first.is_alive.side_effect = [True, False]
        second = _fake_automator(alive=True, import_raises=XGAutomationError("gone again"))
        second.is_alive.side_effect = [True, False]
        analyzer._automator, analyzer._connected = first, True
        with mock.patch("ankigammon.utils.xg_auto.automator.XGAutomator", return_value=second) as cls, \
             mock.patch("time.sleep"):
            with pytest.raises(XGAutomationError, match="gone again"):
                analyzer.analyze_position(XGID)

        assert first.import_xgid_from_file.call_count == 1
        assert second.import_xgid_from_file.call_count == 1
        assert cls.call_count == 1, "no second relaunch"


# ---------------------------------------------------------------------------
# A missing Analyze Session dialog is treated as abnormal
# ---------------------------------------------------------------------------

class TestMissingAnalyzeSessionDialog:
    def test_is_logged_as_a_warning_and_dialogs_are_swept_before_waiting(self, caplog):
        """The sweep has to come before the wait, or the wait sits on the modal."""
        auto = _auto()
        order = []
        with mock.patch.object(XGAutomator, "send_command"), \
             mock.patch.object(XGAutomator, "_match_loaded", return_value=True), \
             mock.patch.object(XGAutomator, "_handle_analyze_session_dialog", return_value=False), \
             mock.patch.object(XGAutomator, "_wait_for_analysis",
                               side_effect=lambda: order.append("wait")), \
             mock.patch.object(XGAutomator, "_dismiss_unexpected_dialogs",
                               side_effect=lambda accept=True: order.append(f"dismiss:{accept}")), \
             mock.patch.object(automator_mod.time, "sleep"), \
             caplog.at_level("WARNING"):
            auto.run_analysis()

        assert any("Analyze Session" in r.message for r in caplog.records), caplog.text
        wait_at = order.index("wait")
        assert "dismiss:False" in order[:wait_at], order

    def test_found_dialog_is_the_quiet_path(self, caplog):
        auto = _auto()
        with mock.patch.object(XGAutomator, "send_command"), \
             mock.patch.object(XGAutomator, "_match_loaded", return_value=True), \
             mock.patch.object(XGAutomator, "_handle_analyze_session_dialog", return_value=True), \
             mock.patch.object(XGAutomator, "_wait_for_analysis"), \
             mock.patch.object(XGAutomator, "_dismiss_unexpected_dialogs"), \
             mock.patch.object(automator_mod.time, "sleep"), \
             caplog.at_level("WARNING"):
            auto.run_analysis()

        assert not [r for r in caplog.records if "Analyze Session" in r.message]
