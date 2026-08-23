"""Diagnostics for the reported "checker play fails, cube works" export.

A user reported that pasted position IDs analyze fine for cube decisions
but fail for checker plays, quoting the GNU BG ID
"4HPwATDgc/ABMA:cInlAAAAAAE". That ID has an 11-character Match ID where
the format requires 12; gnubg itself ignores it ("Setting GNUbg ID
4HPwATDgc/ABMA:" leaves the match state untouched), and AnkiGammon
dropped the line with no reason given.

Covers the three gaps that made this hard to diagnose:
  * an empty analysis says what gnubg actually replied
  * a rejected position ID says why it was rejected
"""

import os
from pathlib import Path
from unittest import mock

import pytest
from PySide6.QtWidgets import QApplication

from ankigammon.gui.dialogs.input_dialog import InputDialog
from ankigammon.models import DecisionType
from ankigammon.parsers.gnubg_parser import GNUBGParser
from ankigammon.utils.gnubg_analyzer import GNUBGAnalyzer


CHECKER_XGID = "XGID=-b----E-C---eE---c-e----B-:0:0:-1:31:0:0:0:0:8"
CUBE_XGID = "XGID=-b----E-C---eE---c-e----B-:0:0:-1:00:0:0:0:0:8"

# The user's ID, verbatim.
SHORT_MATCH_ID = "4HPwATDgc/ABMA:cInlAAAAAAE"


@pytest.fixture
def analyzer():
    with mock.patch.object(Path, "exists", return_value=True):
        return GNUBGAnalyzer("/fake/gnubg", analysis_ply=2)


def _commands(analyzer, xgid, decision_type):
    path = analyzer._create_command_file(xgid, decision_type)
    try:
        return Path(path).read_text().splitlines()
    finally:
        Path(path).unlink()


class TestEmptyAnalysisMessage:
    def test_cube_reply_to_a_checker_question_is_named(self):
        # The signature of dice never reaching gnubg.
        text = "Cube analysis\nCubeful equities:\n1. No double  +0.112\n"

        message = GNUBGParser._describe_empty_analysis(text, DecisionType.CHECKER_PLAY)

        assert "cube decision" in message
        assert "roll never reached it" in message

    def test_gnubg_reply_is_quoted(self):
        text = "GNU Backgammon 1.08.003\nNo game in progress.\n"

        message = GNUBGParser._describe_empty_analysis(text, DecisionType.CHECKER_PLAY)

        assert "No game in progress." in message
        # The banner is noise, not the reason.
        assert "GNU Backgammon 1.08.003" not in message

    def test_message_survives_empty_output(self):
        message = GNUBGParser._describe_empty_analysis("", DecisionType.CUBE_ACTION)

        assert message == "No moves found in gnubg output for cube_action"


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


class TestRejectedPositionIds:
    def test_short_match_id_is_still_rejected(self, qapp):
        # gnubg ignores this ID, so accepting it would analyze a different
        # position than the user pasted.
        dialog = InputDialog.__new__(InputDialog)

        assert InputDialog._parse_position_id(dialog, SHORT_MATCH_ID) is None

    def test_rejection_names_the_match_id_length(self, qapp):
        message = InputDialog._describe_rejected_id(SHORT_MATCH_ID)

        assert "12-character Match ID" in message
        assert "has 11" in message

    def test_unrecognizable_input_still_gets_a_reason(self, qapp):
        message = InputDialog._describe_rejected_id("total garbage")

        assert "Not a valid XGID, GNU BG ID, or OGID." in message
