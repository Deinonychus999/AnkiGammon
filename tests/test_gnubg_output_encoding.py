"""gnubg output that is not UTF-8 must not abort the analysis.

gnubg prints the player names from the user's own settings in its board
diagram, in their codepage: a Cyrillic name arrives as cp1251 bytes, which
a strict UTF-8 decode rejected ("'utf-8' codec can't decode byte 0xd0"),
failing every position. The parsers only match ASCII labels, so those
bytes can be replaced.
"""

import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

from ankigammon.utils.gnubg_analyzer import GNUBGAnalyzer


# "Ѓ" is 0x81 in cp1251, a byte that neither UTF-8 nor cp1252 decodes, so
# the test fails without the fix whatever the machine's default encoding.
CP1251_NAME = "Ѓорѓи".encode("cp1251")
OUTPUT = (
    b" +12-11-10--9--8--7-------6--5--4--3--2--1-+     X: " + CP1251_NAME + b" (Cube: 2)\n"
    b"Cubeful equities:\n"
    b"1. No double           +0.278\n"
)


@pytest.fixture
def analyzer():
    with mock.patch.object(Path, "exists", return_value=True):
        return GNUBGAnalyzer("/fake/gnubg", analysis_ply=2)


def test_cp1251_player_name_does_not_break_position_analysis(analyzer):
    real_run = subprocess.run
    emit = [sys.executable, "-c", f"import sys; sys.stdout.buffer.write({OUTPUT!r})"]

    def run_emitter(cmd, **kwargs):
        return real_run(emit, **kwargs)

    with mock.patch("ankigammon.utils.gnubg_analyzer.subprocess.run", run_emitter):
        output = analyzer._run_gnubg("unused.txt")

    assert "1. No double           +0.278" in output
