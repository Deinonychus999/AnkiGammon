"""Regenerate only what needs it, and never trade a table for nothing.

Follow-up to GitHub issue #59. A regenerate that loses a score matrix used
to overwrite a card that had one, and the only way to get it back was to
regenerate the whole collection again and hope. Two changes:

* An "only cards missing optional analysis" scope, so a rerun targets the
  cards that actually lost something.
* A safeguard: if an optional block a card already had fails to rebuild,
  that card is left untouched and the summary says so.

The cube-position comparison was indistinguishable when absent (by design
when the best move is the same everywhere, or by failure), so it now writes
a marker for each case. Cards made before the markers stay "unknown".
"""

from unittest import mock

import pytest

from ankigammon.anki.decision_serialize import decision_to_json
from ankigammon.anki.optional_analysis import (
    CUBE_COMPARISON_FAILED_MARKER,
    CUBE_COMPARISON_MARKER,
    CUBE_COMPARISON_SAME_MARKER,
    CUBE_MATRIX_MARKER,
    MOVE_MATRIX_MARKER,
    is_cube_xgid,
    lost_optional_blocks,
    missing_optional_blocks,
)
from ankigammon.gui.dialogs.regenerate_dialog import (
    MODE_REANALYZE,
    MODE_RENDER_ONLY,
    RegenerateWorker,
)
from ankigammon.models import CubeState, Decision, DecisionType, Move, Player, Position
from ankigammon.settings import Settings
from tests.conftest import GNUBG_EXE

CUBE_XGID = "XGID=-b----E-C--AeD---bAdb---A-:0:0:1:00:0:0:0:7:10"
CHECKER_XGID = "XGID=-b----E-C--AeD---bAdb---A-:0:0:1:52:0:0:0:7:10"
TABLE = f'<table class="{CUBE_MATRIX_MARKER}"></table>'
MOVE_TABLE = f'<table class="{MOVE_MATRIX_MARKER}"></table>'
COMPARISON = f'<details class="{CUBE_COMPARISON_MARKER}"></details>'


def _settings(tmp_path, **flags):
    s = Settings(config_path=tmp_path / "config.json")
    s.generate_score_matrix = flags.get("score", False)
    s.generate_move_score_matrix = flags.get("move", False)
    s.generate_move_cube_matrix = flags.get("comparison", False)
    return s


def _decision(xgid, cube=True, note=None, match_length=7):
    return Decision(
        position=Position(points=[0] * 26), xgid=xgid,
        on_roll=Player.X, dice=None if cube else (5, 2),
        match_length=match_length, cube_value=1, cube_owner=CubeState.CENTERED,
        decision_type=DecisionType.CUBE_ACTION if cube else DecisionType.CHECKER_PLAY,
        candidate_moves=[Move(notation="No double" if cube else "18/11", equity=-0.05, rank=1)],
        note=note,
    )


def _note(note_id, xgid, back, cube=True, blob=True, match_length=7):
    fields = {
        "XGID": {"value": xgid},
        "Front": {"value": ""},
        "Back": {"value": back},
        "AnalysisData": {"value": decision_to_json(_decision(xgid, cube, match_length=match_length)) if blob else ""},
    }
    return {"noteId": note_id, "fields": fields}


# ---------------------------------------------------------------------------
# Pure detection
# ---------------------------------------------------------------------------

class TestIsCubeXgid:
    def test_no_dice_is_a_cube_action(self):
        assert is_cube_xgid(CUBE_XGID) is True

    def test_dice_is_a_checker_play(self):
        assert is_cube_xgid(CHECKER_XGID) is False

    def test_garbage_is_unknown(self):
        assert is_cube_xgid("not an xgid") is None


class TestMissingOptionalBlocks:
    def test_cube_card_without_table_is_missing_when_enabled(self, tmp_path):
        assert missing_optional_blocks("<div/>", True, _settings(tmp_path, score=True)) == ["score matrix"]

    def test_cube_card_with_table_is_not_missing(self, tmp_path):
        assert missing_optional_blocks(TABLE, True, _settings(tmp_path, score=True)) == []

    def test_nothing_missing_when_setting_is_off(self, tmp_path):
        assert missing_optional_blocks("<div/>", True, _settings(tmp_path)) == []

    def test_one_point_match_can_never_have_a_matrix(self, tmp_path):
        assert missing_optional_blocks("<div/>", True, _settings(tmp_path, score=True), match_length=1) == []

    def test_checker_card_without_move_table_is_missing(self, tmp_path):
        assert missing_optional_blocks("<div/>", False, _settings(tmp_path, move=True)) == ["move score matrix"]

    def test_cube_setting_does_not_apply_to_checker_cards(self, tmp_path):
        assert missing_optional_blocks("<div/>", False, _settings(tmp_path, score=True)) == []

    def test_comparison_present_is_not_missing(self, tmp_path):
        assert missing_optional_blocks(COMPARISON, False, _settings(tmp_path, comparison=True)) == []

    def test_comparison_same_marker_is_not_missing(self, tmp_path):
        """Absent by design: the best move is the same at every cube position."""
        assert missing_optional_blocks(CUBE_COMPARISON_SAME_MARKER, False, _settings(tmp_path, comparison=True)) == []

    def test_comparison_failed_marker_is_missing(self, tmp_path):
        assert missing_optional_blocks(CUBE_COMPARISON_FAILED_MARKER, False, _settings(tmp_path, comparison=True)) == ["cube-position comparison"]

    def test_comparison_with_no_marker_is_unknown_not_missing(self, tmp_path):
        """A card from before the markers cannot be told apart; leave it alone."""
        assert missing_optional_blocks("<div/>", False, _settings(tmp_path, comparison=True)) == []


class TestLostOptionalBlocks:
    def test_table_present_before_and_gone_after_is_lost(self):
        assert lost_optional_blocks(TABLE, "<div/>") == ["score matrix"]

    def test_nothing_lost_when_old_card_had_nothing(self):
        assert lost_optional_blocks("<div/>", "<div/>") == []

    def test_nothing_lost_when_new_card_still_has_it(self):
        assert lost_optional_blocks(TABLE, TABLE) == []

    def test_every_block_kind_is_checked(self):
        old = TABLE + MOVE_TABLE + COMPARISON
        assert lost_optional_blocks(old, "<div/>") == [
            "score matrix", "move score matrix", "cube-position comparison",
        ]


# ---------------------------------------------------------------------------
# Worker: scope and safeguard
# ---------------------------------------------------------------------------

class FakeAnki:
    def __init__(self, notes):
        self._notes = {n["noteId"]: n for n in notes}
        self.writes = {}

    def test_connection(self):
        return True

    def create_model(self):
        pass

    def invoke(self, action, **kw):
        return list(self._notes)

    def notes_info(self, ids):
        return [self._notes[i] for i in ids]

    def update_note_fields(self, note_id, front, back, xgid="", analysis_data=None):
        self.writes[note_id] = back

    def update_note_tags(self, note_id, tags):
        pass


class FakeCardGen:
    """Renders a back with or without the table, optionally reporting a failure."""

    def __init__(self, back, warn=False):
        self.back, self.warn = back, warn
        self.generation_warnings = []
        self.seen = []

    def generate_card(self, decision):
        self.seen.append(decision.xgid)
        if self.warn:
            self.generation_warnings.append(f"Score matrix failed for {decision.xgid}")
        return {"front": "", "back": self.back, "xgid": decision.xgid,
                "analysis_data": decision_to_json(decision), "tags": []}


class FakeAnalyzer:
    def analyze_positions_parallel(self, xgids, progress_callback=None, **kw):
        return [("<raw>", DecisionType.CUBE_ACTION) for _ in xgids]

    def parse_analysis(self, raw, xgid, decision_type):
        return _decision(xgid)

    def terminate(self):
        pass


def _run(mode, settings, notes, card_gen, only_missing=False):
    client = FakeAnki(notes)
    result = {}
    messages = []
    worker = RegenerateWorker(settings, mode, only_missing=only_missing)
    worker.finished.connect(lambda ok, msg: result.update(ok=ok, msg=msg))
    worker.status_message.connect(messages.append)
    with mock.patch("ankigammon.gui.dialogs.regenerate_dialog.AnkiConnect", return_value=client), \
         mock.patch("ankigammon.utils.analyzer_base.create_analyzer", return_value=FakeAnalyzer()), \
         mock.patch.object(RegenerateWorker, "_build_card_generator", return_value=card_gen):
        worker.run()
    return client, result, messages


class TestOnlyMissingScope:
    def test_only_the_card_missing_its_table_is_regenerated(self, qapp, tmp_path):
        settings = _settings(tmp_path, score=True, move=True)
        notes = [
            _note(1, CUBE_XGID, "<div/>"),                 # missing
            _note(2, CUBE_XGID, TABLE),                    # fine
            _note(3, CHECKER_XGID, MOVE_TABLE, cube=False),  # fine
        ]
        client, result, _ = _run(MODE_RENDER_ONLY, settings, notes, FakeCardGen(TABLE), only_missing=True)

        assert result["ok"], result
        assert set(client.writes) == {1}

    def test_scope_off_regenerates_everything(self, qapp, tmp_path):
        settings = _settings(tmp_path, score=True)
        notes = [_note(1, CUBE_XGID, "<div/>"), _note(2, CUBE_XGID, TABLE)]
        client, result, _ = _run(MODE_RENDER_ONLY, settings, notes, FakeCardGen(TABLE))

        assert set(client.writes) == {1, 2}

    def test_nothing_missing_finishes_cleanly_without_writing(self, qapp, tmp_path):
        settings = _settings(tmp_path, score=True)
        client, result, _ = _run(MODE_RENDER_ONLY, settings, [_note(1, CUBE_XGID, TABLE)],
                                 FakeCardGen(TABLE), only_missing=True)

        assert result["ok"]
        assert "No cards are missing" in result["msg"]
        assert client.writes == {}

    def test_scope_applies_to_reanalyze_too(self, qapp, tmp_path):
        settings = _settings(tmp_path, score=True)
        notes = [_note(1, CUBE_XGID, "<div/>"), _note(2, CUBE_XGID, TABLE)]
        client, result, _ = _run(MODE_REANALYZE, settings, notes, FakeCardGen(TABLE), only_missing=True)

        assert result["ok"], result
        assert set(client.writes) == {1}

    def test_legacy_card_without_blob_is_typed_from_its_xgid(self, qapp, tmp_path):
        """No saved blob, so the card type has to come from the XGID's dice field."""
        settings = _settings(tmp_path, score=True)
        notes = [
            _note(1, CUBE_XGID, "<div/>", blob=False),  # legacy, missing
            _note(2, CUBE_XGID, TABLE, blob=False),     # legacy, fine
        ]
        client, result, _ = _run(MODE_REANALYZE, settings, notes, FakeCardGen(TABLE), only_missing=True)

        assert set(client.writes) == {1}

    def test_summary_reports_how_many_were_selected(self, qapp, tmp_path):
        settings = _settings(tmp_path, score=True)
        notes = [_note(1, CUBE_XGID, "<div/>"), _note(2, CUBE_XGID, TABLE)]
        _, _, messages = _run(MODE_RENDER_ONLY, settings, notes, FakeCardGen(TABLE), only_missing=True)

        assert any("1 of 2" in m for m in messages), messages


class TestSafeguard:
    """A rerun whose optional block fails must not overwrite a card that had it."""

    def test_reanalyze_keeps_a_card_whose_table_failed_to_rebuild(self, qapp, tmp_path):
        settings = _settings(tmp_path, score=True)
        notes = [_note(1, CUBE_XGID, TABLE)]
        client, result, _ = _run(MODE_REANALYZE, settings, notes, FakeCardGen("<div/>", warn=True))

        assert result["ok"], result
        assert client.writes == {}, "the card with a table was overwritten by one without"
        assert "Kept 1 card" in result["msg"]

    def test_render_only_keeps_it_too(self, qapp, tmp_path):
        settings = _settings(tmp_path, score=True)
        notes = [_note(1, CUBE_XGID, TABLE)]
        client, result, _ = _run(MODE_RENDER_ONLY, settings, notes, FakeCardGen("<div/>", warn=True))

        assert client.writes == {}
        assert "Kept 1 card" in result["msg"]

    def test_a_card_that_never_had_a_table_is_still_written(self, qapp, tmp_path):
        """Nothing to protect; the user gets the fresh render and the warning."""
        settings = _settings(tmp_path, score=True)
        notes = [_note(1, CUBE_XGID, "<div/>")]
        client, result, _ = _run(MODE_REANALYZE, settings, notes, FakeCardGen("<div/>", warn=True))

        assert set(client.writes) == {1}
        assert "Kept" not in result["msg"]

    def test_turning_a_setting_off_still_writes(self, qapp, tmp_path):
        """No failure fired, so a table disappearing is the user's choice."""
        settings = _settings(tmp_path, score=False)
        notes = [_note(1, CUBE_XGID, TABLE)]
        client, result, _ = _run(MODE_REANALYZE, settings, notes, FakeCardGen("<div/>", warn=False))

        assert set(client.writes) == {1}

    def test_other_cards_in_the_batch_are_unaffected(self, qapp, tmp_path):
        settings = _settings(tmp_path, score=True)
        notes = [_note(1, CUBE_XGID, TABLE), _note(2, CUBE_XGID, "<div/>")]
        client, result, _ = _run(MODE_REANALYZE, settings, notes, FakeCardGen("<div/>", warn=True))

        assert set(client.writes) == {2}
        assert "Kept 1 card" in result["msg"]


# ---------------------------------------------------------------------------
# Comparison markers
# ---------------------------------------------------------------------------

class TestComparisonMarkers:
    @pytest.fixture
    def gen(self, qapp, tmp_path):
        if GNUBG_EXE is None:
            pytest.skip("needs an executable to satisfy is_gnubg_available()")
        from ankigammon.anki.card_generator import CardGenerator

        settings = _settings(tmp_path, comparison=True)
        settings.analyzer_type = "gnubg"
        settings.gnubg_path = GNUBG_EXE
        with mock.patch("ankigammon.anki.card_generator.get_settings", return_value=settings):
            yield CardGenerator(output_dir=tmp_path / "cards", analyzer=mock.MagicMock())

    def test_same_best_move_everywhere_writes_the_same_marker(self, gen):
        with mock.patch("ankigammon.analysis.move_cube_matrix.generate_move_cube_matrix", return_value=object()), \
             mock.patch("ankigammon.analysis.move_cube_matrix.best_move_differs", return_value=False):
            html = gen._generate_move_cube_matrix_html(_decision(CHECKER_XGID, cube=False))

        assert html == CUBE_COMPARISON_SAME_MARKER
        assert not gen.generation_warnings

    def test_failure_writes_the_failed_marker_and_a_warning(self, gen):
        with mock.patch("ankigammon.analysis.move_cube_matrix.generate_move_cube_matrix",
                        side_effect=RuntimeError("engine died")):
            html = gen._generate_move_cube_matrix_html(_decision(CHECKER_XGID, cube=False))

        assert html == CUBE_COMPARISON_FAILED_MARKER
        assert gen.generation_warnings

    def test_marker_lands_in_the_card_back_invisibly(self, gen):
        with mock.patch("ankigammon.analysis.move_cube_matrix.generate_move_cube_matrix", return_value=object()), \
             mock.patch("ankigammon.analysis.move_cube_matrix.best_move_differs", return_value=False):
            back = gen.generate_card(_decision(CHECKER_XGID, cube=False))["back"]

        assert CUBE_COMPARISON_SAME_MARKER in back
        assert "cube-matrix-details" not in back, "an empty comparison section was rendered"


# ---------------------------------------------------------------------------
# Dialog
# ---------------------------------------------------------------------------

class TestDialog:
    def test_checkbox_exists_and_defaults_off(self, qapp, tmp_path):
        from ankigammon.gui.dialogs.regenerate_dialog import RegenerateDialog

        dialog = RegenerateDialog(_settings(tmp_path))

        assert not dialog.chk_only_missing.isChecked()
        assert "missing" in dialog.chk_only_missing.text().lower()
