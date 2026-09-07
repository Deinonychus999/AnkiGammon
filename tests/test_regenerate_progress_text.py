"""The regenerate log counts positions the way a person reads them.

Reported on #59: "Analyzing position 0/5 ... 5/5 ... having both 0/5 and 5/5
seemed worth noting." The engine reports completed positions (0..N); the log
should say which one is in progress (1..N) and then that all are done.
"""

from unittest import mock

from ankigammon.gui.dialogs.regenerate_dialog import MODE_REANALYZE, RegenerateWorker
from ankigammon.models import Decision, DecisionType, Player, Position
from ankigammon.settings import Settings

XGIDS = [
    "XGID=-b----E-C--AeD---bAdb---A-:0:0:1:52:0:0:3:0:10",
    "XGID=-b----E-C--AeD---bAdb---A-:0:0:1:31:0:0:3:0:10",
]


class ReportingAnalyzer:
    """Calls the progress callback the way XGAnalyzer does: before each
    position with the count so far, then once more with the total."""

    def analyze_positions_parallel(self, xgids, progress_callback=None, **kw):
        for i, _ in enumerate(xgids):
            if progress_callback:
                progress_callback(i, len(xgids))
        if progress_callback:
            progress_callback(len(xgids), len(xgids))
        return [("<raw>", DecisionType.CHECKER_PLAY) for _ in xgids]

    def parse_analysis(self, raw, xgid, decision_type):
        return Decision(position=Position(points=[0] * 26), xgid=xgid,
                        on_roll=Player.X, dice=(5, 2),
                        decision_type=DecisionType.CHECKER_PLAY)

    def terminate(self):
        pass


class FakeAnki:
    def test_connection(self):
        return True

    def create_model(self):
        pass

    def invoke(self, action, **kw):
        return [1, 2]

    def notes_info(self, ids):
        return [{"noteId": i, "fields": {"XGID": {"value": XGIDS[i - 1]},
                                         "AnalysisData": {"value": ""},
                                         "Back": {"value": ""}}} for i in ids]

    def update_note_fields(self, *a, **kw):
        pass

    def update_note_tags(self, *a, **kw):
        pass


def test_progress_reads_one_based_and_ends_with_a_done_line(qapp):
    worker = RegenerateWorker(Settings(), MODE_REANALYZE)
    messages = []
    worker.status_message.connect(messages.append)
    card_gen = mock.MagicMock()
    card_gen.generate_card.return_value = {"front": "", "back": "", "xgid": "", "analysis_data": "", "tags": []}
    card_gen.generation_warnings = []
    with mock.patch("ankigammon.gui.dialogs.regenerate_dialog.AnkiConnect", return_value=FakeAnki()), \
         mock.patch("ankigammon.utils.analyzer_base.create_analyzer", return_value=ReportingAnalyzer()), \
         mock.patch.object(RegenerateWorker, "_build_card_generator", return_value=card_gen):
        worker.run()

    progress = [m for m in messages if m.startswith("Analyz")]
    assert "Analyzing position 1/2..." in progress
    assert "Analyzing position 2/2..." in progress
    assert "Analyzed 2/2 position(s)." in progress
    assert not any("0/2" in m for m in progress), progress
