"""Soak: launch a fresh XG2 N times and import a position each time.

Opt-in:  ANKIGAMMON_LIVE_SOAK=1   (runs: ANKIGAMMON_SOAK_RUNS, default 10)

The import path fails intermittently with "Headless file open timed out"
(roughly 1 in 14 launches when first observed) and a single failure carries
no evidence about why. This measures the rate and, on any failure, records
the profile in use, the main window title, the skip set, and every top-level
window in XG's process, so a failure is a report rather than a mystery.

Each run is ~20-25s. Anything the run starts is force-killed afterwards.
"""

import ctypes
import ctypes.wintypes as wt
import os
import sys
import time
from contextlib import ExitStack, nullcontext
from pathlib import Path
from unittest import mock

import pytest

from tests.conftest import XG_EXE, force_kill, wait_for_exit, xg_pids

pytestmark = [
    pytest.mark.live_xg,
    pytest.mark.skipif(sys.platform != "win32", reason="XG automation is Windows-only"),
]

XGID = "XGID=-b----E-C--AeD---bAdb---A-:0:0:1:52:0:0:3:0:10"


def _window_inventory(automator_mod, auto):
    """Every top-level window in XG's process, as (hwnd, class, title, visible, edit, skipped)."""
    user32 = automator_mod.user32
    pid = wt.DWORD()
    user32.GetWindowThreadProcessId(auto._hwnd, ctypes.byref(pid))
    rows = []

    def _cb(hwnd, _lparam):
        p = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
        if p.value != pid.value:
            return True
        cls = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, cls, 64)
        title = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, title, 256)
        has_edit = bool(
            user32.GetDlgItem(hwnd, 0x047C)
            or automator_mod.XGAutomator._find_child_by_class(hwnd, ["Edit", "TEdit"])
        )
        rows.append((
            hex(int(hwnd)), cls.value, title.value[:40],
            bool(user32.IsWindowVisible(hwnd)), has_edit,
            int(hwnd) in auto._skip_hwnds,
        ))
        return True

    user32.EnumWindows(automator_mod.WNDENUMPROC(_cb), 0)
    return rows


def _one_run(automator_mod, index):
    """Fresh launch, one import. Returns a result dict; never raises."""
    before = xg_pids()
    auto = automator_mod.XGAutomator(xg_path=Path(XG_EXE), headless=True)
    result = {"run": index, "ok": False, "profile": None, "seconds": None, "error": None}
    t0 = time.time()
    try:
        auto.connect()
        result["profile"] = auto.cmd.version
        result["title_after_connect"] = auto._xg_base_title
        result["skip_after_connect"] = len(auto._skip_hwnds)
        auto.import_xgid_from_file(XGID)
        result["ok"] = True
    except Exception as exc:  # noqa: BLE001 - the whole point is to record it
        result["error"] = f"{type(exc).__name__}: {exc}"
        try:
            result["windows"] = _window_inventory(automator_mod, auto)
            result["skip_set"] = sorted(hex(h) for h in auto._skip_hwnds)
            main = ctypes.create_unicode_buffer(256)
            automator_mod.user32.GetWindowTextW(auto._hwnd, main, 256)
            result["main_title_at_failure"] = main.value
        except Exception as diag_exc:  # noqa: BLE001
            result["diagnostics_error"] = repr(diag_exc)
    finally:
        result["seconds"] = round(time.time() - t0, 1)
        try:
            auto.disconnect()
        except Exception:  # noqa: BLE001
            pass
        stragglers = xg_pids() - before
        force_kill(stragglers)
        wait_for_exit(stragglers, timeout=10)
    return result


def _format(result):
    head = (f"run {result['run']:>2}: {'ok  ' if result['ok'] else 'FAIL'} "
            f"profile={result['profile']} {result['seconds']}s")
    if result["ok"]:
        return head
    lines = [head, f"    error: {result['error']}",
             f"    main title at failure: {result.get('main_title_at_failure')!r}",
             f"    title after connect:   {result.get('title_after_connect')!r}",
             f"    skip set: {result.get('skip_set')}"]
    for row in result.get("windows", []):
        hwnd, cls, title, visible, edit, skipped = row
        lines.append(f"    window {hwnd} {cls:<14} vis={visible!s:<5} edit={edit!s:<5} "
                     f"skipped={skipped!s:<5} {title!r}")
    if "diagnostics_error" in result:
        lines.append(f"    (diagnostics failed: {result['diagnostics_error']})")
    return "\n".join(lines)


def _prefix_behaviour(automator_mod):
    """Put the pre-fix behaviour back on the instrumented code.

    ANKIGAMMON_SOAK_PREFIX=1 disables exe-based version detection and
    skip-set pruning, so the same run measures the baseline and still
    reports diagnostics on any failure.
    """
    stack = ExitStack()
    stack.enter_context(mock.patch.object(
        automator_mod.XGAutomator, "_profile_from_exe", return_value=None
    ))
    stack.enter_context(mock.patch.object(
        automator_mod.XGAutomator, "_prune_dead_skip_hwnds",
        lambda self, hwnds=None: None,
    ))
    return stack


def test_repeated_fresh_launches_import_cleanly():
    if os.environ.get("ANKIGAMMON_LIVE_SOAK") != "1":
        pytest.skip("soak is opt-in (ANKIGAMMON_LIVE_SOAK=1, ANKIGAMMON_SOAK_RUNS=N)")
    if XG_EXE is None:
        pytest.skip("eXtreme Gammon 2 not found")
    pytest.importorskip("psutil")
    if xg_pids():
        pytest.skip("XG already running; the soak needs a clean slate")

    from ankigammon.utils.xg_auto import automator as automator_mod

    runs = int(os.environ.get("ANKIGAMMON_SOAK_RUNS", "10"))
    prefix = os.environ.get("ANKIGAMMON_SOAK_PREFIX") == "1"
    with (_prefix_behaviour(automator_mod) if prefix else nullcontext()):
        results = [_one_run(automator_mod, i + 1) for i in range(runs)]

    report = "\n".join(_format(r) for r in results)
    failures = [r for r in results if not r["ok"]]
    print(f"\nmode: {'PRE-FIX behaviour' if prefix else 'current code'}")
    print(report)
    print(f"\n{len(failures)}/{runs} failed")

    assert not failures, f"{len(failures)}/{runs} launches failed:\n{report}"
