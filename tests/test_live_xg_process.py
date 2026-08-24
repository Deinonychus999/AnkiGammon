"""Process ownership against a real eXtreme Gammon 2.

Opt-in: ANKIGAMMON_LIVE_XG=1 (see tests/conftest.py).

These exist because the mocked equivalents in test_xg_process_cleanup.py all
passed while real XG2 stayed running after disconnect(). XG skips buttonless
startup dialogs in GUI mode, and that dialog blocks the main window from ever
processing WM_CLOSE - so "we posted WM_CLOSE" proves nothing about whether
the process actually died. Only a real run does.

Each test launches XG windows and force-kills anything it started.
"""

import subprocess
import sys
import time

import pytest

from tests.conftest import force_kill, wait_for_exit, xg_pids

pytestmark = [
    pytest.mark.live_xg,
    pytest.mark.skipif(sys.platform != "win32", reason="XG automation is Windows-only"),
]


def _automator(xg_exe, **kwargs):
    from ankigammon.utils.xg_auto.automator import XGAutomator

    return XGAutomator(xg_path=xg_exe, **kwargs)


class TestGuiModeOwnership:
    def test_launched_xg_is_really_gone_after_disconnect(self, live_xg, no_xg_running):
        """The headline check: no XG2 left in the process table."""
        before = no_xg_running
        auto = _automator(live_xg, headless=False)
        ours = set()
        try:
            auto.connect()
            ours = xg_pids() - before
            assert ours, "connect() should have launched XG"
            assert auto._launched_xg is True

            auto.disconnect()

            assert wait_for_exit(ours), (
                f"XG still running after disconnect: {sorted(ours & xg_pids())}"
            )
        finally:
            force_kill(ours)
            wait_for_exit(ours, timeout=10)

    def test_xg_the_user_already_had_open_survives(self, live_xg, no_xg_running):
        """An instance we did not start is not ours to close."""
        before = no_xg_running
        theirs = set()
        try:
            subprocess.Popen([str(live_xg)])
            deadline = time.time() + 45
            while time.time() < deadline and not theirs:
                theirs = xg_pids() - before
                time.sleep(0.5)
            assert theirs, "could not start a stand-in user XG"
            time.sleep(6)  # let XG finish initialising before attaching

            auto = _automator(live_xg, headless=False)
            auto.connect()

            assert auto._launched_xg is False
            assert not (xg_pids() - before - theirs), "should not have launched another XG"

            auto.disconnect()
            time.sleep(3)

            assert theirs & xg_pids(), "disconnect() killed the user's own XG"
        finally:
            force_kill(theirs)
            wait_for_exit(theirs, timeout=10)


class TestHeadlessMode:
    """Headless is the mode XGAnalyzer actually uses in production."""

    def test_headless_instance_is_really_gone_after_disconnect(self, live_xg, no_xg_running):
        before = no_xg_running
        auto = _automator(live_xg, headless=True)
        ours = set()
        try:
            auto.connect()
            ours = xg_pids() - before
            assert ours, "headless connect() should have launched XG"

            auto.disconnect()

            assert wait_for_exit(ours), (
                f"headless XG still running: {sorted(ours & xg_pids())}"
            )
        finally:
            force_kill(ours)
            wait_for_exit(ours, timeout=10)

    def test_disconnect_twice_is_harmless(self, live_xg, no_xg_running):
        before = no_xg_running
        auto = _automator(live_xg, headless=True)
        ours = set()
        try:
            auto.connect()
            ours = xg_pids() - before
            auto.disconnect()
            auto.disconnect()  # must not raise

            assert wait_for_exit(ours)
        finally:
            force_kill(ours)
            wait_for_exit(ours, timeout=10)
