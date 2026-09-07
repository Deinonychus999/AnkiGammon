"""The file dialog must hold the whole path before it is confirmed.

Seen three times on real XG 2.19 straight after launch: the dialog resets its
filename box while still initialising, so a path typed via WM_CHAR comes back
missing its leading characters ("Got: id_import.txt"). The old code then
force-set the text with WM_SETTEXT - which does not update the dialog's COM
state - and confirmed anyway; the dialog stuck, the import never took, and XG
later exited. Now the path is retyped until it reads back correctly.
"""

import ctypes
import sys
from pathlib import Path
from unittest import mock

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="XG automation is Windows-only")
pytest.importorskip("pywinauto")

from ankigammon.utils.xg_auto import automator as automator_mod  # noqa: E402
from ankigammon.utils.xg_auto.automator import XGAutomator  # noqa: E402

DLG, EDIT = 0x500, 0x501
PATH = Path(r"C:\Users\x\AppData\Local\Temp\ankigammon\xgid_import.txt")


class FakeEdit:
    """An edit box that drops the first `drop` typed characters on the first
    `resets` rounds - the dialog clearing itself mid-typing."""

    def __init__(self, drop=0, resets=0):
        self.text = ""
        self.drop, self.resets = drop, resets
        self.round = 0
        self.typing_rounds = 0
        self.settext_calls = 0
        self.dialog_open = True

    def send(self, hwnd, msg, wparam, lparam):
        A = automator_mod.XGAutomator
        if hwnd == EDIT:
            if msg in (A.EM_SETSEL, A.WM_CLEAR):
                if msg == A.WM_CLEAR:
                    # Each WM_CLEAR from the automator starts a typing round;
                    # the first one precedes the first round.
                    self.text = ""
                    self.round = self.typing_rounds
                    self.typing_rounds += 1
                return 0
            if msg == A.WM_CHAR:
                self.text += chr(wparam)
                # dialog reset partway through this round: lose the head
                if self.round < self.resets and len(self.text) == self.drop:
                    self.text = ""
                return 0
            if msg == automator_mod.WM_GETTEXTLENGTH:
                return len(self.text)
            if msg == automator_mod.WM_GETTEXT:
                data = self.text.encode("utf-16-le") + b"\x00\x00"
                ctypes.memmove(lparam, data, min(len(data), wparam * 2))
                return len(self.text)
            if msg == A.WM_SETTEXT:
                self.settext_calls += 1
                self.text = ctypes.wstring_at(lparam)
                return 1
        if hwnd == DLG and msg == automator_mod.WM_COMMAND:
            self.dialog_open = False  # IDOK closes it
            return 0
        return 0


def _run(edit):
    auto = XGAutomator(xg_path=None, headless=True)
    auto._hwnd = 0x1234
    user32 = mock.MagicMock()
    user32.GetDlgItem.return_value = 0x47C
    user32.IsWindow.side_effect = lambda h: edit.dialog_open if h == DLG else True
    user32.GetWindowThreadProcessId.return_value = 1
    with mock.patch.object(automator_mod, "SendMessageW", side_effect=edit.send), \
         mock.patch.object(automator_mod, "PostMessageW", side_effect=edit.send), \
         mock.patch.object(automator_mod, "user32", user32), \
         mock.patch.object(automator_mod, "WNDENUMPROC", lambda f: f), \
         mock.patch.object(XGAutomator, "_find_child_by_class", return_value=EDIT), \
         mock.patch.object(automator_mod.time, "sleep"):
        auto._autofill_file_dialog_win32(DLG, PATH)
    return edit


class TestPathIsRetypedUntilItReadsBack:
    def test_a_ready_dialog_is_typed_once(self):
        edit = _run(FakeEdit())

        assert edit.text == str(PATH)
        assert edit.typing_rounds == 1
        assert edit.settext_calls == 0

    def test_a_reset_mid_typing_is_retyped(self):
        """The observed failure: first round loses its head, second round is whole."""
        edit = _run(FakeEdit(drop=len(str(PATH)) - len("id_import.txt"), resets=1))

        assert edit.text == str(PATH), "confirmed with a truncated path"
        assert edit.typing_rounds == 2
        assert edit.settext_calls == 0, "WM_SETTEXT does not reach the dialog's COM state"

    def test_two_resets_still_recover(self):
        edit = _run(FakeEdit(drop=5, resets=2))

        assert edit.text == str(PATH)
        assert edit.typing_rounds == 3

    def test_after_three_failed_rounds_the_old_fallback_still_applies(self):
        edit = _run(FakeEdit(drop=5, resets=99))

        assert edit.settext_calls == 1
        assert edit.text == str(PATH)
        assert edit.typing_rounds == 3

    def test_the_dialog_is_confirmed_afterwards(self):
        edit = _run(FakeEdit(drop=5, resets=1))

        assert edit.dialog_open is False
