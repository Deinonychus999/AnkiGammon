"""A HedgeHog rate limit stops the run instead of stripping score matrices.

Reported from a Fedora user's logs: HedgeHog answered "Too many requests. Try
again in 4 hours." (429 rate_limited), and Send to Anki kept going. Every later
card asked HedgeHog again, two or three times, and was written without its
tables; Send to Anki upserts by XGID, so cards that already had score matrices
lost them. A rate limit now stops the run before the card that hit it, and the
analyzer stops asking HedgeHog once it has said no.

An exhausted free allowance is different: the export dialog asks before
starting when the allowance looks short, so that run continues without the
tables, as the user agreed, but without asking HedgeHog again.
"""

from unittest import mock

import pytest

from ankigammon.anki.decision_serialize import decision_to_json
from ankigammon.models import CubeState, Decision, DecisionType, Move, Player, Position
from ankigammon.settings import Settings
from ankigammon.utils.analyzer_base import EngineRefusesRun
from ankigammon.utils.hedgehog_analyzer import HedgehogAnalyzer
from ankigammon.utils.hedgehog_client import HedgehogRateLimited, HedgehogRefusal
from tests.test_hedgehog_client import _client, fake  # noqa: F401  (fixture)

TOO_MANY = "Too many requests. Try again in 4 hours."
XGIDS = [
    "XGID=-b----E-C--AeD---bAdb---A-:0:0:1:00:0:0:3:0:10",
    "XGID=-a-BBBB----A---c-bbbbb----:0:0:1:00:2:3:0:7:10",
    "XGID=--BBCBB----A---c-bbbbb--A-:0:0:1:00:1:4:0:7:10",
]


def _rate_limited() -> HedgehogRateLimited:
    return HedgehogRateLimited("rate_limited", TOO_MANY, 429, {})


def _allowance_exhausted() -> HedgehogRefusal:
    return HedgehogRefusal("allowance_exhausted", "You've used today's free position analyses.", 429, {})


def _cube_decision(xgid: str) -> Decision:
    return Decision(
        position=Position(points=[0] * 26), xgid=xgid, on_roll=Player.X, dice=None,
        match_length=7, cube_value=1, cube_owner=CubeState.CENTERED,
        decision_type=DecisionType.CUBE_ACTION,
        candidate_moves=[Move(notation="No double", equity=-0.08, rank=1)],
    )


class RefusingClient:
    """HedgeHog's client, answering every batch with the given refusal."""

    def __init__(self, refusal):
        self.refusal = refusal
        self.calls = 0

    def analyze_positions(self, ogids, preset, jacoby, cancelled=None):
        self.calls += 1
        raise self.refusal


@pytest.fixture
def settings(tmp_path):
    s = Settings(config_path=tmp_path / "config.json")
    s.generate_score_matrix = True
    s.score_matrix_max_size = 2
    s.deck_name = "Rate limit"
    return s


class TestClient:
    @pytest.mark.parametrize("code", ["rate_limited", "client_rate_limited"])
    def test_a_rate_limit_stops_the_run(self, fake, code):  # noqa: F811
        fake.refusal = {"error": code, "message": TOO_MANY}
        with pytest.raises(EngineRefusesRun) as refusal:
            _client(fake).analyze_positions(["x"], "2ply")
        assert isinstance(refusal.value, HedgehogRefusal)
        assert str(refusal.value) == TOO_MANY

    def test_an_exhausted_allowance_does_not(self, fake):  # noqa: F811
        fake.refusal = {"error": "allowance_exhausted", "message": "You've used today's free position analyses."}
        with pytest.raises(HedgehogRefusal) as refusal:
            _client(fake).analyze_positions(["x"], "2ply")
        assert not isinstance(refusal.value, EngineRefusesRun)


class TestAnalyzerStopsAsking:
    @pytest.mark.parametrize("refusal", [_rate_limited, _allowance_exhausted])
    def test_after_a_429_it_refuses_without_asking_again(self, refusal):
        client = RefusingClient(refusal())
        analyzer = HedgehogAnalyzer(client=client)
        for _ in range(3):
            with pytest.raises(HedgehogRefusal):
                analyzer.analyze_positions_parallel(XGIDS[:1])
        assert client.calls == 1

    def test_other_refusals_are_asked_again(self):
        client = RefusingClient(HedgehogRefusal("server_error", "HedgeHog had a problem.", 502, {}))
        analyzer = HedgehogAnalyzer(client=client)
        for _ in range(2):
            with pytest.raises(HedgehogRefusal):
                analyzer.analyze_positions_parallel(XGIDS[:1])
        assert client.calls == 2


class FakeAnki:
    def __init__(self, *args, **kwargs):
        self.sent = []

    def test_connection(self):
        return True

    def create_model(self):
        pass

    def create_deck(self, name):
        pass

    def upsert_note(self, **note):
        self.sent.append(note["xgid"])


def _export(qapp, settings, analyzer, matrix, method="ankiconnect", output_path=None):
    from ankigammon.gui.dialogs.export_dialog import ExportWorker

    anki = FakeAnki()
    worker = ExportWorker(
        {settings.deck_name: [_cube_decision(x) for x in XGIDS]}, settings, method,
        output_path=output_path, import_mode="upsert", analyzer=analyzer,
    )
    results = []
    worker.finished.connect(lambda ok, msg: results.append((ok, msg)))
    with mock.patch("ankigammon.gui.dialogs.export_dialog.AnkiConnect", return_value=anki), \
            mock.patch("ankigammon.anki.card_generator.get_settings", return_value=settings), \
            mock.patch("ankigammon.analysis.score_matrix.generate_score_matrix", side_effect=matrix), \
            mock.patch("ankigammon.analysis.score_matrix.format_matrix_as_html",
                       return_value="<table class=score-matrix-table></table>"):
        worker.run()
    return anki.sent, results, worker


def _limited_at_second(xgid, analyzer, **kwargs):
    if xgid == XGIDS[1]:
        raise _rate_limited()
    return object(), object()


class TestSendToAnki:
    def test_a_rate_limit_stops_before_the_card_that_hit_it(self, qapp, settings):
        sent, results, _ = _export(qapp, settings, mock.MagicMock(), _limited_at_second)

        assert sent == XGIDS[:1]
        [(ok, message)] = results
        assert not ok
        assert TOO_MANY in message
        assert "Stopped after sending 1 of 3 card(s)" in message

    def test_an_exhausted_allowance_still_sends_every_card_asking_once(self, qapp, settings):
        client = RefusingClient(_allowance_exhausted())
        analyzer = HedgehogAnalyzer(client=client)

        def matrix(xgid, analyzer, **kwargs):
            analyzer.analyze_positions_parallel([xgid])

        sent, results, _ = _export(qapp, settings, analyzer, matrix)

        assert sent == XGIDS
        [(ok, message)] = results
        assert ok
        assert "You've used today's free position analyses." in message
        assert client.calls == 1


class TestOtherExports:
    def test_an_apkg_is_not_written(self, qapp, settings, tmp_path):
        target = tmp_path / "deck.apkg"
        _, [(ok, message)], _ = _export(qapp, settings, mock.MagicMock(), _limited_at_second, "apkg", str(target))
        assert not ok
        assert TOO_MANY in message
        assert "Stopped at position 2 of 3; no file was written." in message
        assert not target.exists()

    def test_nothing_goes_to_the_trainer(self, qapp, settings):
        _, [(ok, message)], worker = _export(qapp, settings, mock.MagicMock(), _limited_at_second, "trainer")
        assert not ok
        assert TOO_MANY in message
        assert "Stopped at position 2 of 3; nothing was sent to the trainer." in message
        assert worker.pack is None


class TestRegenerate:
    def test_a_rate_limit_stops_and_leaves_the_card_alone(self, qapp, settings):
        from ankigammon.gui.dialogs.regenerate_dialog import MODE_RENDER_ONLY, RegenerateWorker

        class Anki:
            updated = []

            def test_connection(self):
                return True

            def create_model(self):
                pass

            def invoke(self, action, **kwargs):
                return [1, 2]

            def notes_info(self, ids):
                return [{
                    "noteId": i,
                    "fields": {
                        "XGID": {"value": XGIDS[i]},
                        "Front": {"value": ""},
                        "Back": {"value": "<table class=score-matrix-table></table>"},
                        "AnalysisData": {"value": decision_to_json(_cube_decision(XGIDS[i]))},
                    },
                } for i in ids]

            def update_note_fields(self, note_id, *args, **kwargs):
                self.updated.append(note_id)

            def update_note_tags(self, *args, **kwargs):
                pass

        worker = RegenerateWorker(settings, MODE_RENDER_ONLY)
        results = []
        worker.finished.connect(lambda ok, msg: results.append((ok, msg)))
        with mock.patch("ankigammon.gui.dialogs.regenerate_dialog.AnkiConnect", return_value=Anki()), \
                mock.patch("ankigammon.anki.card_generator.get_settings", return_value=settings), \
                mock.patch.object(Settings, "is_engine_available", return_value=True), \
                mock.patch("ankigammon.utils.analyzer_base.create_analyzer", return_value=mock.MagicMock()), \
                mock.patch("ankigammon.analysis.score_matrix.generate_score_matrix",
                           side_effect=_rate_limited()):
            worker.run()

        assert Anki.updated == []
        [(ok, message)] = results
        assert not ok
        assert TOO_MANY in message
        assert "Stopped at card 1 of 2" in message
