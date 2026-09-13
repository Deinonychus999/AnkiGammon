"""A fast analysis is the normal path, not a warning.

In the issue #59 diagnostics XG finished every position before the first
0.5s poll, so "Analyze menu item never became disabled" fired 344 times
against 21 successful matrices and buried the three real errors in the
same log. The start wait cannot tell "finished already" from "never
started"; the main loop settles it a second later, so nothing above debug
belongs here.
"""

import logging
import sys
from unittest import mock

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="XG automation is Windows-only")
pytest.importorskip("pywinauto")

from ankigammon.utils.xg_auto import automator as automator_mod  # noqa: E402
from ankigammon.utils.xg_auto.automator import XGAutomator  # noqa: E402


def test_analysis_finishing_before_the_first_poll_logs_nothing_above_info(caplog):
    auto = XGAutomator(xg_path=None, headless=True)
    auto._hwnd = 0x1234
    auto._cmd = automator_mod.XG_PROFILES["2.19"]

    with mock.patch.object(XGAutomator, "_check_for_completion_dialog", return_value=False), \
         mock.patch.object(XGAutomator, "_check_menu_item_enabled", return_value=True), \
         mock.patch.object(XGAutomator, "_check_status_bar", return_value=False), \
         mock.patch.object(XGAutomator, "_dismiss_unexpected_dialogs"), \
         mock.patch.object(XGAutomator, "_read_progress", return_value=""), \
         mock.patch.object(automator_mod.time, "sleep"), \
         caplog.at_level(logging.DEBUG, logger="ankigammon.utils.xg_auto.automator"):
        auto._wait_for_analysis()

    messages = [r.getMessage() for r in caplog.records]
    assert any("fast completion" in m for m in messages), messages
    loud = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert not loud, [r.getMessage() for r in loud]
