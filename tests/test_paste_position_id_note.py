"""Free-text notes pasted alongside bare position IDs.

Reported on Reddit: "The comments show up on the card when the position
imported is analyzed and not when the position is unanalyzed."

A full XG analysis export carries its note in the footer, which
XGTextParser._parse_comment picks up. A bare XGID has no such structure, and
the POSITION_IDS branch used to feed every pasted line to _parse_position_id
and drop whatever failed - silently discarding the user's comment.

Lines that genuinely look like a mistyped position ID must still be reported
as rejected rather than swallowed as note text.
"""

import tempfile
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from ankigammon.gui.dialogs.input_dialog import InputDialog
from ankigammon.gui.format_detector import InputFormat
from ankigammon.settings import Settings


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


XGID_A = "XGID=-b----E-C--AeD---bAdb---A-:0:0:1:52:0:0:3:0:10"
XGID_B = "XGID=-b----E-C--AeD---bAdb---A-:0:0:1:31:0:0:3:0:10"


@pytest.fixture
def dialog(qapp):
    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(config_path=Path(tmp) / "config.json")
        yield InputDialog(settings)


def _parse(dialog, text):
    decisions = dialog._parse_input(text, InputFormat.POSITION_IDS)
    rejected = getattr(dialog, "rejected_position_ids", [])
    return decisions, rejected


class TestNoteAttachedToPastedPositionId:
    def test_note_line_after_id_becomes_the_note(self, dialog):
        decisions, rejected = _parse(dialog, XGID_A + "\nRace lead = 4 pips, so run.")

        assert len(decisions) == 1
        assert decisions[0].note == "Race lead = 4 pips, so run."
        assert rejected == []

    def test_note_without_equals_sign_also_survives(self, dialog):
        decisions, _ = _parse(dialog, XGID_A + "\nWhen ahead in the race, race!")

        assert len(decisions) == 1
        assert decisions[0].note == "When ahead in the race, race!"

    def test_multi_line_note_is_joined(self, dialog):
        text = XGID_A + "\nfirst thought\nsecond thought"
        decisions, _ = _parse(dialog, text)

        assert len(decisions) == 1
        assert decisions[0].note == "first thought\nsecond thought"

    def test_each_position_keeps_its_own_note(self, dialog):
        text = "\n".join([XGID_A, "comment for A", XGID_B, "comment for B"])
        decisions, rejected = _parse(dialog, text)

        assert len(decisions) == 2
        assert decisions[0].note == "comment for A"
        assert decisions[1].note == "comment for B"
        assert rejected == []

    def test_note_before_the_first_id_attaches_to_it(self, dialog):
        """XG puts the comment above the ID in some copy modes."""
        decisions, _ = _parse(dialog, "heading comment\n" + XGID_A)

        assert len(decisions) == 1
        assert decisions[0].note == "heading comment"

    def test_position_without_a_note_keeps_note_none(self, dialog):
        decisions, rejected = _parse(dialog, XGID_A)

        assert len(decisions) == 1
        assert decisions[0].note is None
        assert rejected == []

    def test_bare_ids_only_do_not_annotate_each_other(self, dialog):
        decisions, rejected = _parse(dialog, XGID_A + "\n" + XGID_B)

        assert len(decisions) == 2
        assert all(d.note is None for d in decisions)
        assert rejected == []


class TestMalformedIdsStillReported:
    """The rejected-ID diagnostic must survive the note feature."""

    def test_truncated_gnuid_is_rejected_not_treated_as_a_note(self, dialog):
        bad = "4HPwATDgc/ABMA:short"
        decisions, rejected = _parse(dialog, XGID_A + "\n" + bad)

        assert len(decisions) == 1
        assert decisions[0].note is None
        assert rejected == [bad]

    def test_malformed_xgid_is_rejected_not_treated_as_a_note(self, dialog):
        bad = "XGID=totally-bogus"
        decisions, rejected = _parse(dialog, XGID_A + "\n" + bad)

        assert rejected == [bad]
        assert decisions[0].note is None

    def test_note_and_malformed_id_can_coexist(self, dialog):
        bad = "4HPwATDgc/ABMA:short"
        text = "\n".join([XGID_A, "a real comment", bad])
        decisions, rejected = _parse(dialog, text)

        assert len(decisions) == 1
        assert decisions[0].note == "a real comment"
        assert rejected == [bad]

    def test_rejects_do_not_leak_into_the_next_paste(self, dialog):
        """The list is per-paste; a stale one re-warns about unrelated input."""
        _parse(dialog, "4HPwATDgc/ABMA:short")

        decisions, rejected = _parse(dialog, XGID_A)

        assert len(decisions) == 1
        assert rejected == []

    def test_rejects_do_not_leak_into_a_full_analysis_paste(self, dialog):
        from ankigammon.gui.format_detector import InputFormat as _F

        _parse(dialog, "4HPwATDgc/ABMA:short")
        dialog._parse_input("not really analysis text", _F.FULL_ANALYSIS)

        assert dialog.rejected_position_ids == []

    def test_nothing_parseable_still_reports_rejects(self, dialog):
        bad = "4HPwATDgc/ABMA:short"
        decisions, rejected = _parse(dialog, bad)

        assert decisions == []
        assert rejected == [bad]

    @pytest.mark.parametrize("terse", ["ND:+0.05", "D/T:-0.166", "8/5:strong"])
    def test_terse_colon_notes_are_kept_not_reported(self, dialog, terse):
        """An unspaced note with a colon is still a note, not a mistyped ID."""
        decisions, rejected = _parse(dialog, XGID_A + "\n" + terse)

        assert decisions[0].note == terse
        assert rejected == []
