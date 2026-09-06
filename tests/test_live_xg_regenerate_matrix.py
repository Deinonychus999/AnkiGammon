"""Regenerating a cube card with score matrices, against a real XG2.

Opt-in: ANKIGAMMON_LIVE_XG=1 (see tests/conftest.py).

The mocked test in test_regenerate_score_matrix_analyzer.py proves the root
cause (two engines instead of one) but cannot show the damage: with GnuBG a
second engine is merely wasteful. With XG it is destructive, because a second
headless connect runs _kill_stale_xg_instances and terminates the hidden XG
the worker is still using. The matrix then throws,
_generate_score_matrix_html swallows it and returns "", and the card is
written back without its table and without any warning.

Only a real XG run shows that, which is the whole point of this file.

Anki is faked here; the bug is in engine handling, not in AnkiConnect.
"""

import sys

import pytest

from ankigammon.anki.decision_serialize import decision_to_json
from ankigammon.gui.dialogs.regenerate_dialog import MODE_REANALYZE, RegenerateWorker
from ankigammon.models import CubeState, Decision, DecisionType, Move, Player, Position
from tests.conftest import force_kill, wait_for_exit, xg_pids

pytestmark = [
    pytest.mark.live_xg,
    pytest.mark.skipif(sys.platform != "win32", reason="XG automation is Windows-only"),
]

CUBE_XGID = "XGID=-b----E-C--AeD---bAdb---A-:0:0:1:00:0:0:3:0:10"
COMMENT = "Too good to double."
MATRIX_MARKER = "score-matrix-table"


def _seed_decision() -> Decision:
    return Decision(
        position=Position(points=[0] * 26),
        xgid=CUBE_XGID,
        on_roll=Player.X,
        dice=None,
        cube_value=1,
        cube_owner=CubeState.CENTERED,
        decision_type=DecisionType.CUBE_ACTION,
        candidate_moves=[Move(notation="No double", equity=-0.08, rank=1)],
        note=COMMENT,
    )


class FakeAnki:
    """Stands in for the collection; every engine here is real."""

    def __init__(self):
        self.written = {}

    def test_connection(self):
        return True

    def create_model(self):
        pass

    def invoke(self, action, **kwargs):
        assert action == "findNotes"
        return [1]

    def notes_info(self, note_ids):
        return [{
            "noteId": 1,
            "fields": {
                "XGID": {"value": CUBE_XGID},
                "Front": {"value": "<div>front</div>"},
                "Back": {"value": "<div>old</div>"},
                "AnalysisData": {"value": decision_to_json(_seed_decision())},
            },
        }]

    def update_note_fields(self, note_id, front, back, xgid="", analysis_data=None):
        self.written = {"back": back, "analysis_data": analysis_data}

    def update_note_tags(self, note_id, tags):
        pass


@pytest.fixture
def regenerated(qapp, live_xg, no_xg_running, tmp_path):
    """Regenerate one cube card with matrices on, using real XG throughout."""
    from unittest import mock

    from ankigammon.settings import Settings

    settings = Settings(config_path=tmp_path / "config.json")
    settings.analyzer_type = "xg"
    settings.xg_exe_path = str(live_xg)
    settings.xg_analysis_level = "Very Quick"
    settings.generate_score_matrix = True
    settings.score_matrix_max_size = 2  # keeps a live matrix down to a few cells

    before = no_xg_running
    client = FakeAnki()
    worker = RegenerateWorker(settings, MODE_REANALYZE)
    outcome = {}
    worker.finished.connect(lambda ok, msg: outcome.update(ok=ok, msg=msg))

    try:
        with mock.patch(
            "ankigammon.gui.dialogs.regenerate_dialog.AnkiConnect", return_value=client
        ), mock.patch(
            "ankigammon.anki.card_generator.get_settings", return_value=settings
        ):
            worker.run()
        yield client, outcome, before
    finally:
        stragglers = xg_pids() - before
        force_kill(stragglers)
        wait_for_exit(stragglers, timeout=10)


class TestRegenerateWithMatrices:
    def test_regenerate_succeeds(self, regenerated):
        _, outcome, _ = regenerated

        assert outcome["ok"], outcome["msg"]

    def test_the_score_matrix_is_on_the_regenerated_card(self, regenerated):
        """The reported symptom: the table came back missing, silently."""
        client, outcome, _ = regenerated

        assert outcome["ok"], outcome["msg"]
        assert MATRIX_MARKER in client.written["back"], (
            "the score matrix was dropped from the card; a second XG instance "
            "killed the one the worker was using"
        )

    def test_the_comment_is_still_there_too(self, regenerated):
        client, outcome, _ = regenerated

        assert outcome["ok"], outcome["msg"]
        assert COMMENT in client.written["back"]

    def test_no_xg_process_is_left_running(self, regenerated):
        _, _, before = regenerated

        assert wait_for_exit(xg_pids() - before), (
            f"XG left running: {sorted(xg_pids() - before)}"
        )
