"""Nothing to analyze must fail in seconds, not in ten minutes.

Reproduced live while chasing GitHub issue #59: after an import that did not
take, XG sat with no match open. With no match XG greys out both Analyze and
Close, and the analysis wait read "Analyze menu disabled" as "analysis
started" and waited out its full 600s timeout. The user's 12:50 wedge in the
diagnostic log was the same state, reached via a leaked Save dialog.

So a match must be confirmed loaded before the Analyze command is sent - the
one moment when a disabled Close item unambiguously means "no match" - and
the position is re-imported once after a dialog sweep if it was not.
"""

import itertools
import sys
from unittest import mock

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="XG automation is Windows-only")
pytest.importorskip("pywinauto")

from ankigammon.models import DecisionType  # noqa: E402
from ankigammon.utils.xg_auto import automator as automator_mod  # noqa: E402
from ankigammon.utils.xg_auto.automator import (  # noqa: E402
    XGAutomationError,
    XGAutomator,
    XGNoMatchLoadedError,
)
from ankigammon.utils.xg_analyzer import XGAnalyzer  # noqa: E402

HWND = 0x1234
BASE = "eXtreme Gammon 2.19.211.pre-release"
XGID = "XGID=-b----E-C--AeD---bAdb---A-:0:0:1:52:0:0:3:0:10"


def _auto(base_title=BASE):
    auto = XGAutomator(xg_path=None, headless=True)
    auto._hwnd = HWND
    auto._xg_base_title = base_title
    auto._cmd = automator_mod.XG_PROFILES["2.19"]
    return auto


def _user32_with_title(title):
    fake = mock.MagicMock()
    fake.GetWindowTextW.side_effect = lambda h, buf, n: setattr(buf, "value", title)
    fake.IsWindow.return_value = True
    return fake


class TestMatchLoaded:
    def test_title_with_a_suffix_means_loaded(self):
        auto = _auto()
        with mock.patch.object(automator_mod, "user32", _user32_with_title(BASE + " *")), \
             mock.patch.object(XGAutomator, "_check_menu_item_enabled", return_value=False):
            assert auto._match_loaded() is True

    def test_close_enabled_means_loaded_even_if_the_title_did_not_change(self):
        """XG does not always retitle after a clipboard import."""
        auto = _auto()
        with mock.patch.object(automator_mod, "user32", _user32_with_title(BASE)), \
             mock.patch.object(XGAutomator, "_check_menu_item_enabled", return_value=True):
            assert auto._match_loaded() is True

    def test_bare_title_and_close_disabled_means_nothing_loaded(self):
        """The state observed live: Analyze and Close greyed, title bare."""
        auto = _auto()
        with mock.patch.object(automator_mod, "user32", _user32_with_title(BASE)), \
             mock.patch.object(XGAutomator, "_check_menu_item_enabled", return_value=False):
            assert auto._match_loaded() is False

    def test_a_trailing_space_after_closing_is_not_a_suffix(self):
        """Observed on XG 2.19: after Close the title reads 'eXtreme Gammon ... '."""
        auto = _auto()
        with mock.patch.object(automator_mod, "user32", _user32_with_title(BASE + " ")), \
             mock.patch.object(XGAutomator, "_check_menu_item_enabled", return_value=False):
            assert auto._match_loaded() is False

    def test_unknown_base_title_falls_back_to_the_menu(self):
        auto = _auto(base_title="")
        with mock.patch.object(automator_mod, "user32", _user32_with_title(BASE)), \
             mock.patch.object(XGAutomator, "_check_menu_item_enabled", return_value=False):
            assert auto._match_loaded() is False


class TestRunAnalysisRefusesAnEmptyXg:
    def test_raises_before_sending_the_analyze_command(self):
        auto = _auto()
        with mock.patch.object(XGAutomator, "_match_loaded", return_value=False), \
             mock.patch.object(XGAutomator, "_dismiss_unexpected_dialogs"), \
             mock.patch.object(XGAutomator, "send_command") as send, \
             mock.patch.object(XGAutomator, "_wait_for_analysis") as wait, \
             mock.patch.object(automator_mod.time, "sleep"):
            with pytest.raises(XGNoMatchLoadedError) as info:
                auto.run_analysis()

        assert "nothing to analyze" in str(info.value).lower()
        assert not send.called, "Analyze was sent to an XG with no match"
        assert not wait.called, "the 600s wait must never start"

    def test_it_is_an_automation_error_too(self):
        assert issubclass(XGNoMatchLoadedError, XGAutomationError)

    def test_a_loaded_match_proceeds_as_before(self):
        auto = _auto()
        with mock.patch.object(XGAutomator, "_match_loaded", return_value=True), \
             mock.patch.object(XGAutomator, "_dismiss_unexpected_dialogs"), \
             mock.patch.object(XGAutomator, "send_command") as send, \
             mock.patch.object(XGAutomator, "_handle_analyze_session_dialog", return_value=True), \
             mock.patch.object(XGAutomator, "_wait_for_analysis") as wait, \
             mock.patch.object(automator_mod.time, "sleep"):
            auto.run_analysis()

        assert send.called
        assert wait.called


class TestPositionLoadWaitReportsFailure:
    def test_unchanged_title_returns_false_and_warns(self, caplog):
        auto = _auto()
        with mock.patch.object(automator_mod, "user32", _user32_with_title(BASE)), \
             mock.patch.object(XGAutomator, "_dismiss_unexpected_dialogs"), \
             mock.patch.object(automator_mod.time, "sleep"), \
             mock.patch.object(automator_mod.time, "time",
                               side_effect=itertools.chain([0.0, 0.0], itertools.repeat(100.0))), \
             caplog.at_level("WARNING"):
            loaded = auto._wait_for_position_loaded(timeout=10.0)

        assert loaded is False
        assert any("not confirmed" in r.message.lower() for r in caplog.records), caplog.text

    def test_changed_title_returns_true(self):
        auto = _auto()
        with mock.patch.object(automator_mod, "user32", _user32_with_title(BASE + " *")), \
             mock.patch.object(XGAutomator, "_dismiss_unexpected_dialogs"), \
             mock.patch.object(automator_mod.time, "sleep"), \
             mock.patch.object(automator_mod.time, "time", side_effect=itertools.count(0.0, 0.5)):
            assert auto._wait_for_position_loaded(timeout=10.0) is True


def _fake_automator():
    a = mock.MagicMock()
    a.is_alive.return_value = True
    a.cmd.EXPORT_POS_CLIPBOARD = 131
    a.get_clipboard_text_validated.return_value = "XGID=... analysis text"
    return a


class TestAnalyzePositionReimportsOnce:
    def test_no_match_loaded_sweeps_dialogs_and_retries_once(self):
        analyzer = XGAnalyzer(xg_path="C:/xg.exe")
        auto = _fake_automator()
        auto.run_analysis.side_effect = [XGNoMatchLoadedError("nothing to analyze"), None]
        analyzer._automator, analyzer._connected = auto, True
        with mock.patch("time.sleep"):
            text, kind = analyzer.analyze_position(XGID)

        assert text == "XGID=... analysis text"
        assert kind == DecisionType.CHECKER_PLAY
        assert auto.import_xgid_from_file.call_count == 2, "the position must be re-imported"
        assert auto.run_analysis.call_count == 2
        auto._dismiss_unexpected_dialogs.assert_any_call(accept=False)

    def test_a_second_empty_xg_is_not_retried_again(self):
        analyzer = XGAnalyzer(xg_path="C:/xg.exe")
        auto = _fake_automator()
        auto.run_analysis.side_effect = XGNoMatchLoadedError("nothing to analyze")
        analyzer._automator, analyzer._connected = auto, True
        with mock.patch("time.sleep"):
            with pytest.raises(XGNoMatchLoadedError):
                analyzer.analyze_position(XGID)

        assert auto.run_analysis.call_count == 2

    def test_other_automation_errors_from_a_live_xg_are_not_retried(self):
        analyzer = XGAnalyzer(xg_path="C:/xg.exe")
        auto = _fake_automator()
        auto.run_analysis.side_effect = XGAutomationError("Analysis did not complete")
        analyzer._automator, analyzer._connected = auto, True
        with mock.patch("time.sleep"):
            with pytest.raises(XGAutomationError):
                analyzer.analyze_position(XGID)

        assert auto.run_analysis.call_count == 1
