"""Notes in XG text exports that the block splitter used to eat.

Reported on Reddit: "It looks like having an '=' in the note confuses ag
(no note posted)."

The splitter searched for `XGID=` anywhere on a line rather than at the start
of one, so a note that referenced another position by ID split the export
mid-note. Two neighbouring false positives are pinned alongside it: an OGID
pattern loose enough to match ordinary prose, and an analysis-terminator
pattern that swallowed a note opening with "Opponent:".
"""

import pytest

from ankigammon.parsers.xg_text_parser import XGTextParser


CHECKER_EXPORT = """XGID=-b----E-C--AeD---bAdb---A-:0:0:1:52:0:0:3:0:10

X:Player 1   O:Player 2
Score is X:0 O:0. Unlimited Game, Jacoby Beaver
Pip count  X: 159  O: 163 X-O: 0-0
Cube: 1
X to play 52

    1. XG Roller++ 18/11                        eq:-0.0026
      Player:   50.64% (G:11.55% B:0.54%)
      Opponent: 49.36% (G:13.95% B:0.42%)

    2. XG Roller++ 24/22 18/13                  eq:-0.1141 (-0.1114)
      Player:   48.27% (G:10.81% B:0.55%)
      Opponent: 51.73% (G:15.83% B:0.49%)

{NOTE}

eXtreme Gammon Version: 2.10
"""


def _parse_with_note(note_text):
    """Parse the export with note_text in the comment slot."""
    return XGTextParser.parse_string(CHECKER_EXPORT.replace("{NOTE}", note_text))


class TestNotesThatLookLikeStructure:
    def test_note_referencing_another_xgid_is_kept(self):
        note = "Compare with XGID=-b----E-C--AeD---bAdb---A-:0:0:1:31:0:0:3:0:10 here"
        decisions = _parse_with_note(note)

        assert len(decisions) == 1, "a mid-line XGID= must not split the export"
        assert decisions[0].note == note

    def test_bare_xgid_token_inside_a_sentence_is_kept(self):
        note = "see XGID=abc for the mirror"
        decisions = _parse_with_note(note)

        assert len(decisions) == 1
        assert decisions[0].note == note

    def test_note_opening_with_a_colon_triple_is_kept(self):
        """Prose can collide with the OGID pattern; the cube field disambiguates."""
        note = "13:14:ABC style ref"
        decisions = _parse_with_note(note)

        assert len(decisions) == 1
        assert decisions[0].note == note

    def test_note_opening_with_opponent_is_kept(self):
        note = "Opponent: 3 pips better after this"
        decisions = _parse_with_note(note)

        assert len(decisions) == 1
        assert decisions[0].note == note


class TestOrdinaryNotesStillWork:
    @pytest.mark.parametrize("note", [
        "When ahead in the race, race!",
        "Race lead = 4 pips, so run.",
        "= run when ahead",
        "ND = -0.081, D/T = -0.166",
        "eq=-0.0026 is close",
        "Cube: 1 means centered",
        "Pip count X: 159",
        "line one\nline two",
    ])
    def test_note_round_trips(self, note):
        decisions = _parse_with_note(note)

        assert len(decisions) == 1
        assert decisions[0].note == note

    def test_export_without_a_note_yields_none(self):
        text = CHECKER_EXPORT.replace("{NOTE}\n\n", "")
        decisions = XGTextParser.parse_string(text)

        assert len(decisions) == 1
        assert decisions[0].note is None


class TestRealPositionIdsStillSplit:
    """The tightened patterns must not stop recognising genuine position IDs."""

    def test_two_xgid_blocks_still_split(self):
        first = CHECKER_EXPORT.replace("{NOTE}", "note one")
        second = CHECKER_EXPORT.replace(
            "XGID=-b----E-C--AeD---bAdb---A-:0:0:1:52:0:0:3:0:10",
            "XGID=-b----E-C--AeD---bAdb---A-:0:0:1:31:0:0:3:0:10",
        ).replace("{NOTE}", "note two")
        decisions = XGTextParser.parse_string(first + "\n" + second)

        assert len(decisions) == 2
        assert decisions[0].note == "note one"
        assert decisions[1].note == "note two"

    def test_detector_agrees_with_the_parser_on_block_count(self):
        """format_detector and XGTextParser share one pattern; keep them in step."""
        import tempfile
        from pathlib import Path

        from ankigammon.gui.format_detector import FormatDetector, InputFormat
        from ankigammon.settings import Settings

        with tempfile.TemporaryDirectory() as tmp:
            detector = FormatDetector(Settings(config_path=Path(tmp) / "c.json"))
            for note in (
                "see XGID=abc for the mirror",
                "13:14:ABC style ref",
                "Opponent: 3 pips better",
                "plain note",
            ):
                text = CHECKER_EXPORT.replace("{NOTE}", note)
                result = detector.detect(text)

                assert result.format == InputFormat.FULL_ANALYSIS, note
                assert result.count == 1, note
                assert len(XGTextParser.parse_string(text)) == 1, note

    def test_ogid_header_is_still_recognised(self):
        ogid = "11jjjjjhhhccccc:ooddddd88866666:N0N:52:W:IW:0:0:7:0"
        text = CHECKER_EXPORT.replace(
            "XGID=-b----E-C--AeD---bAdb---A-:0:0:1:52:0:0:3:0:10", ogid
        ).replace("{NOTE}", "ogid note")
        decisions = XGTextParser.parse_string(text)

        assert len(decisions) == 1
        assert decisions[0].note == "ogid note"
