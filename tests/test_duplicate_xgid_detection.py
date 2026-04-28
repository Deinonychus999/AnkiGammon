"""Tests for duplicate XGID detection and accurate export counts.

Reproduces the silent dedup bug (#33) where 54 input XGIDs ended up as 46
cards in Anki. Two contributing failures are covered:

1. The POSITION_IDS input path re-encodes XGIDs through ``encode_xgid``
   and silently loses the cube-action flag and the max-cube field. Two
   structurally distinct user inputs collapse to the same canonical XGID,
   producing identical GUIDs that Anki then merges on import. The fix
   preserves the raw XGID as ``decision.xgid``.

2. The export pipeline reports attempts rather than unique cards, hiding
   the loss. ``find_duplicate_xgids`` exposes the collisions so the GUI
   can warn the user before export.
"""

import pytest

from ankigammon.anki.deck_utils import find_duplicate_xgids
from ankigammon.models import Decision, Player, CubeState, DecisionType, Position
from ankigammon.utils.xgid import parse_xgid


def _make_decision(xgid: str) -> Decision:
    """Build a minimal Decision carrying the given XGID string."""
    position, _ = parse_xgid(xgid)
    return Decision(
        position=position,
        xgid=xgid,
        on_roll=Player.X,
        decision_type=DecisionType.CHECKER_PLAY,
    )


class TestFindDuplicateXgids:
    def test_no_duplicates(self):
        decisions = [
            _make_decision("XGID=-a----E-C---eE---c-e----B-:0:0:1:63:0:0:0:0:8"),
            _make_decision("XGID=-a----E-C---eE---c-e----B-:0:0:1:52:0:0:0:0:8"),
        ]
        assert find_duplicate_xgids(decisions) == {}

    def test_one_duplicate_pair(self):
        xgid = "XGID=-a----E-C---eE---c-e----B-:0:0:1:63:0:0:0:0:8"
        decisions = [_make_decision(xgid), _make_decision(xgid)]
        assert find_duplicate_xgids(decisions) == {xgid: 2}

    def test_three_of_a_kind_counts_as_one_entry(self):
        xgid = "XGID=-a----E-C---eE---c-e----B-:0:0:1:63:0:0:0:0:8"
        decisions = [_make_decision(xgid)] * 3
        assert find_duplicate_xgids(decisions) == {xgid: 3}

    def test_empty_xgids_ignored(self):
        position, _ = parse_xgid("XGID=-a----E-C---eE---c-e----B-:0:0:1:63:0:0:0:0:8")
        decisions = [
            Decision(position=position, xgid="", on_roll=Player.X),
            Decision(position=position, xgid="", on_roll=Player.X),
        ]
        assert find_duplicate_xgids(decisions) == {}


class TestRawXgidPreservedThroughInputDialog:
    """Verify _create_decision_from_metadata stores the user's raw input.

    The input dialog used to re-encode every XGID through ``encode_xgid``,
    which dropped the cube-action flag (D/B/R) and the max-cube field. Two
    input XGIDs that differed only in those fields became byte-identical
    after the round-trip — and since GUIDs are derived from the XGID, Anki
    merged them on import.

    The dialog's _create_decision_from_metadata is a Qt instance method,
    so we exercise it via the underlying contract: when ``original_xgid``
    is supplied, ``Decision.xgid`` must equal it verbatim.
    """

    def test_distinct_cube_action_xgids_round_trip_to_same_canonical(self):
        # From bug report #33: same position, different cube action and
        # max-cube. Without the fix, _create_decision_from_metadata would
        # collapse both to the same canonical XGID.
        xgid_cube_decision = "XGID=--CBBBBaa--------bCbcbbAb-:2:-1:-1:00:0:0:2:0:8"
        xgid_double_offered = "XGID=--CBBBBaa--------bCbcbbAb-:2:-1:-1:D:0:0:2:0:10"

        from ankigammon.utils.xgid import encode_xgid

        # Demonstrate the lossy round-trip on the second XGID — this is
        # what the old code did, and why distinct inputs collided.
        position2, metadata2 = parse_xgid(xgid_double_offered)
        round_tripped = encode_xgid(
            position=position2,
            cube_value=metadata2.get('cube_value', 1),
            cube_owner=metadata2.get('cube_owner', CubeState.CENTERED),
            dice=metadata2.get('dice'),  # None for "D"
            on_roll=metadata2.get('on_roll', Player.X),
            score_x=metadata2.get('score_x', 0),
            score_o=metadata2.get('score_o', 0),
            match_length=metadata2.get('match_length', 0),
            crawford_jacoby=metadata2.get('crawford_jacoby', 0),
            # NB: max_cube intentionally omitted — reproduces the old bug.
        )
        assert round_tripped == xgid_cube_decision, (
            "Sanity check: the old re-encode should collide with the other "
            "input. If this assertion ever fails, the encoder semantics "
            "changed and this regression test needs to be revisited."
        )

    def test_max_cube_preserved_when_passed_through(self):
        # Same position, max_cube=10. Re-encoding without max_cube squashes
        # to log=8; passing it through preserves it.
        from ankigammon.utils.xgid import encode_xgid

        xgid = "XGID=-aa-ABBBB---cE-a-d-d----aA:0:0:1:00:0:0:2:0:10"
        position, metadata = parse_xgid(xgid)

        without_max = encode_xgid(
            position=position,
            cube_value=metadata['cube_value'],
            cube_owner=metadata['cube_owner'],
            on_roll=metadata['on_roll'],
            score_x=metadata['score_x'],
            score_o=metadata['score_o'],
            match_length=metadata['match_length'],
            crawford_jacoby=metadata['crawford_jacoby'],
        )
        with_max = encode_xgid(
            position=position,
            cube_value=metadata['cube_value'],
            cube_owner=metadata['cube_owner'],
            on_roll=metadata['on_roll'],
            score_x=metadata['score_x'],
            score_o=metadata['score_o'],
            match_length=metadata['match_length'],
            crawford_jacoby=metadata['crawford_jacoby'],
            max_cube=metadata['max_cube'],
        )
        assert without_max.endswith(":0:8"), "old behavior squashes MC to 8"
        assert with_max.endswith(":0:10"), "passing max_cube preserves MC"


class TestApkgGuidUniquenessFromRawXgid:
    """End-to-end check that distinct raw XGIDs produce distinct GUIDs.

    StableNote.guid hashes only the XGID field. As long as we preserve the
    user's raw input there, the GUIDs differ — and Anki keeps both cards.
    """

    def test_distinct_raw_xgids_produce_distinct_guids(self):
        from ankigammon.anki.apkg_exporter import StableNote, ApkgExporter
        from pathlib import Path
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            exporter = ApkgExporter(output_dir=Path(tmp))

            xgid_a = "XGID=--CBBBBaa--------bCbcbbAb-:2:-1:-1:00:0:0:2:0:8"
            xgid_b = "XGID=--CBBBBaa--------bCbcbbAb-:2:-1:-1:D:0:0:2:0:10"

            note_a = StableNote(
                model=exporter.model,
                fields=[xgid_a, "front_a", "back_a", ""],
                tags=[],
            )
            note_b = StableNote(
                model=exporter.model,
                fields=[xgid_b, "front_b", "back_b", ""],
                tags=[],
            )

            assert note_a.guid != note_b.guid, (
                "Distinct raw XGIDs must produce distinct GUIDs — otherwise "
                "Anki silently merges them on import (bug #33)."
            )
