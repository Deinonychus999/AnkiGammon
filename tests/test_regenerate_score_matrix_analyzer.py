"""Regenerate must not start a second analysis engine for score matrices.

Reported after the 1.8.1 fixes: "the tables of most cards were updated. I
just noticed that some were deleted instead of updated."

Both export paths hand their analyzer to CardGenerator so the connection is
reused. RegenerateWorker did not, so CardGenerator lazily built a second one.
With XG that is fatal: a second headless connect runs
_kill_stale_xg_instances, which terminates the hidden XG the regenerate
worker is still using. Score-matrix generation then throws, and
_generate_score_matrix_html swallows it and returns "" - the card is written
back with no table and nothing is reported. A table that was there is gone.

The second analyzer is also never terminated, so it strands a process too.
"""

from unittest import mock

import pytest

from ankigammon.anki.decision_serialize import decision_to_json
from ankigammon.gui.dialogs.regenerate_dialog import (
    MODE_REANALYZE,
    MODE_RENDER_ONLY,
    RegenerateWorker,
)
from ankigammon.models import CubeState, Decision, DecisionType, Move, Player, Position
from ankigammon.settings import Settings
from tests.conftest import GNUBG_EXE

CUBE_XGID = "XGID=-b----E-C--AeD---bAdb---A-:0:0:1:00:0:0:3:0:10"
MATRIX_MARKER = "<!--SCORE-MATRIX-->"


class SpyAnalyzer:
    """Stands in for a live engine connection; records its own lifecycle."""

    _next_id = 0

    def __init__(self):
        SpyAnalyzer._next_id += 1
        self.id = SpyAnalyzer._next_id
        self.terminated = False

    def analyze_positions_parallel(self, xgids, progress_callback=None, **kw):
        return [("<raw>", DecisionType.CUBE_ACTION) for _ in xgids]

    def parse_analysis(self, raw_output, xgid, decision_type):
        return _cube_decision()

    def terminate(self):
        self.terminated = True


def _cube_decision(note=None) -> Decision:
    return Decision(
        position=Position(points=[0] * 26),
        xgid=CUBE_XGID,
        on_roll=Player.X,
        dice=None,
        match_length=7,
        score_x=0,
        score_o=0,
        cube_value=1,
        cube_owner=CubeState.CENTERED,
        decision_type=DecisionType.CUBE_ACTION,
        candidate_moves=[
            Move(notation="No double", equity=-0.08, rank=1),
            Move(notation="Double, take", equity=-0.16, rank=2),
        ],
        note=note,
    )


@pytest.fixture
def matrix_settings(tmp_path):
    """Settings with score matrices on and an engine that looks available."""
    if GNUBG_EXE is None:
        pytest.skip("needs an executable to satisfy is_gnubg_available()")
    settings = Settings(config_path=tmp_path / "config.json")
    settings.analyzer_type = "gnubg"
    settings.gnubg_path = GNUBG_EXE
    settings.generate_score_matrix = True
    assert settings.is_gnubg_available()
    return settings


@pytest.fixture
def spy_factory():
    """Count every analyzer the run creates, and hand back spies."""
    created = []

    def factory(_settings):
        analyzer = SpyAnalyzer()
        created.append(analyzer)
        return analyzer

    return created, factory


def _note(note_id=1, note_text="keep me"):
    blob = decision_to_json(_cube_decision(note=note_text))
    return {
        "noteId": note_id,
        "fields": {
            "XGID": {"value": CUBE_XGID},
            "Front": {"value": "<div>front</div>"},
            "Back": {"value": "<div>old back</div>"},
            "AnalysisData": {"value": blob},
        },
    }


class FakeAnkiConnect:
    def __init__(self, notes):
        self._notes = {n["noteId"]: n for n in notes}
        self.writes = {}

    def test_connection(self):
        return True

    def create_model(self):
        pass

    def invoke(self, action, **kwargs):
        assert action == "findNotes"
        return list(self._notes)

    def notes_info(self, note_ids):
        return [self._notes[i] for i in note_ids]

    def update_note_fields(self, note_id, front, back, xgid="", analysis_data=None):
        self.writes[note_id] = {"back": back, "analysis_data": analysis_data}

    def update_note_tags(self, note_id, tags):
        pass


def _run(mode, settings, spy_factory, notes=None):
    """Drive the worker with the REAL CardGenerator so matrices are attempted."""
    created, factory = spy_factory
    client = FakeAnkiConnect(notes or [_note()])
    matrix_calls = []
    result = {}

    def fake_generate_score_matrix(**kwargs):
        matrix_calls.append(kwargs)
        return object()

    worker = RegenerateWorker(settings, mode)
    worker.finished.connect(lambda ok, msg: result.update(ok=ok, msg=msg))

    with mock.patch(
        "ankigammon.gui.dialogs.regenerate_dialog.AnkiConnect", return_value=client
    ), mock.patch(
        "ankigammon.utils.analyzer_base.create_analyzer", side_effect=factory
    ), mock.patch(
        "ankigammon.anki.card_generator.get_settings", return_value=settings
    ), mock.patch(
        "ankigammon.analysis.score_matrix.generate_score_matrix",
        side_effect=fake_generate_score_matrix,
    ), mock.patch(
        "ankigammon.analysis.score_matrix.format_matrix_as_html",
        return_value=MATRIX_MARKER,
    ):
        worker.run()

    return client, created, matrix_calls, result


class TestReanalyzeReusesOneEngine:
    def test_only_one_analyzer_is_created(self, qapp, matrix_settings, spy_factory):
        _, created, _, result = _run(MODE_REANALYZE, matrix_settings, spy_factory)

        assert result["ok"], result
        assert len(created) == 1, (
            f"regenerate started {len(created)} engines; a second one kills the "
            "first XG instance and the card loses its table"
        )

    def test_matrix_uses_the_workers_analyzer(self, qapp, matrix_settings, spy_factory):
        _, created, matrix_calls, result = _run(MODE_REANALYZE, matrix_settings, spy_factory)

        assert result["ok"], result
        assert matrix_calls, "score matrix was never attempted"
        assert matrix_calls[0]["analyzer"] is created[0]

    def test_the_table_survives_the_regenerate(self, qapp, matrix_settings, spy_factory):
        """The user-visible symptom: the table must still be on the card."""
        client, _, _, result = _run(MODE_REANALYZE, matrix_settings, spy_factory)

        assert result["ok"], result
        assert MATRIX_MARKER in client.writes[1]["back"], "the table was dropped"

    def test_every_analyzer_is_terminated(self, qapp, matrix_settings, spy_factory):
        _, created, _, result = _run(MODE_REANALYZE, matrix_settings, spy_factory)

        assert result["ok"], result
        assert all(a.terminated for a in created), (
            "an engine was left running: " + repr([a.id for a in created if not a.terminated])
        )

    def test_note_still_preserved_alongside_the_table(self, qapp, matrix_settings, spy_factory):
        client, _, _, result = _run(MODE_REANALYZE, matrix_settings, spy_factory)

        assert result["ok"], result
        assert "keep me" in client.writes[1]["back"]


class TestRenderOnlyDoesNotLeak:
    """Re-render builds matrices too, so it can create an engine of its own."""

    def test_analyzer_created_for_a_matrix_is_terminated(
        self, qapp, matrix_settings, spy_factory
    ):
        _, created, _, result = _run(MODE_RENDER_ONLY, matrix_settings, spy_factory)

        assert result["ok"], result
        assert all(a.terminated for a in created), (
            "re-render left an engine running"
        )

    def test_render_only_still_draws_the_table(self, qapp, matrix_settings, spy_factory):
        client, _, _, result = _run(MODE_RENDER_ONLY, matrix_settings, spy_factory)

        assert result["ok"], result
        assert MATRIX_MARKER in client.writes[1]["back"]
