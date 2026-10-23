"""A card made again from the same position must not ask the engine again.

Reported against HedgeHog: regenerating a collection (after a theme change, or
to fix a card) re-ran every score matrix and cube-position table, spending the
allowance each time. The engine's answers are stored per position and reused.

They are stored raw, not as finished tables, so a parser or rendering fix
still reaches a regenerated card, and each request's answers are kept as they
arrive, so a refusal part way through a table loses none already paid for.
"""

import json
from unittest import mock

import pytest

from ankigammon.analysis.answer_cache import AnswerCache, CachingAnalyzer
from ankigammon.anki.card_generator import CardGenerator
from ankigammon.models import DecisionType
from ankigammon.parsers.hedgehog_parser import decision_from_xgid, plan_batches
from ankigammon.settings import Settings
from ankigammon.utils.hedgehog_client import HedgehogRefusal
from ankigammon.utils.prefetch_analyzer import RecordingAnalyzer, estimate_hedgehog_cost

CUBE_7PT = "XGID=-BBB--CC----eA--bc-e-B----:0:0:1:00:2:1:0:7:10"
CHECKER_7PT = "XGID=-b----E-C---eE---c-e----B-:0:0:1:31:0:0:0:7:10"
ENGINE = "hedgehog:2ply"


class CountingEngine(RecordingAnalyzer):
    """A HedgeHog-shaped engine that counts every position it is asked for."""

    def __init__(self):
        super().__init__()
        self.asked = []

    def _answer(self, xgid):
        self.asked.append(xgid)
        return super()._answer(xgid)


def _analyzed(xgid, decision_type):
    engine = RecordingAnalyzer()
    raw, _ = engine._answer(xgid)
    return engine.parse_analysis(raw, xgid, decision_type)


class TestAnswerCache:
    def test_round_trips_answers(self, tmp_path):
        cache = AnswerCache(tmp_path / "a.sqlite3")
        cache.put_many(ENGINE, {"p1": ("raw1", DecisionType.CUBE_ACTION), "p2": ("raw2", DecisionType.CHECKER_PLAY)})

        assert cache.get_many(ENGINE, ["p1", "p2", "p3"]) == {
            "p1": ("raw1", DecisionType.CUBE_ACTION),
            "p2": ("raw2", DecisionType.CHECKER_PLAY),
        }

    def test_another_engine_or_depth_is_a_miss(self, tmp_path):
        cache = AnswerCache(tmp_path / "a.sqlite3")
        cache.put_many("hedgehog:2ply", {"p": ("raw", DecisionType.CUBE_ACTION)})

        assert cache.get_many("hedgehog:4ply", ["p"]) == {}
        assert cache.get_many("gnubg:3-ply", ["p"]) == {}

    def test_an_unreadable_file_is_an_empty_cache(self, tmp_path):
        path = tmp_path / "a.sqlite3"
        path.write_bytes(b"not a database at all" * 100)
        cache = AnswerCache(path)

        assert cache.get_many(ENGINE, ["p"]) == {}
        cache.put_many(ENGINE, {"p": ("raw", DecisionType.CUBE_ACTION)})  # must not raise

    def test_clear_removes_answers_and_the_old_table_files(self, tmp_path):
        cache = AnswerCache(tmp_path / "a.sqlite3")
        cache.put_many(ENGINE, {"p": ("raw", DecisionType.CUBE_ACTION)})
        legacy = tmp_path / "0123abcd.json"
        legacy.write_text("{}", encoding="utf-8")

        assert cache.stats()[0] == 1
        cache.clear()

        assert cache.stats()[0] == 0
        assert not legacy.exists()

    def test_a_missing_file_is_not_created_by_reading(self, tmp_path):
        cache = AnswerCache(tmp_path / "sub" / "a.sqlite3")

        assert cache.get_many(ENGINE, ["p"]) == {}
        assert cache.stats() == (0, 0)
        assert not cache.path.exists()


class TestCachingAnalyzer:
    def test_a_fully_stored_request_never_starts_the_engine(self, tmp_path):
        cache = AnswerCache(tmp_path / "a.sqlite3")
        engine = CountingEngine()
        CachingAnalyzer(lambda: engine, cache, ENGINE).analyze_positions_parallel([CUBE_7PT])

        never = mock.Mock(side_effect=AssertionError("engine started"))
        answers = CachingAnalyzer(never, cache, ENGINE).analyze_positions_parallel([CUBE_7PT])

        assert answers[0][1] == DecisionType.CUBE_ACTION
        assert engine.asked == [CUBE_7PT]

    def test_only_the_missing_positions_are_asked_for(self, tmp_path):
        cache = AnswerCache(tmp_path / "a.sqlite3")
        engine = CountingEngine()
        view = CachingAnalyzer(lambda: engine, cache, ENGINE)
        view.analyze_positions_parallel([CUBE_7PT])

        view.analyze_positions_parallel([CUBE_7PT, CHECKER_7PT])

        assert engine.asked == [CUBE_7PT, CHECKER_7PT]

    def test_answers_from_before_a_refusal_are_kept(self, tmp_path):
        """HedgeHog sends a big table as several batches; a 429 on a later one
        must not throw away the ones already paid for."""
        cache = AnswerCache(tmp_path / "a.sqlite3")
        ids = [f"{CUBE_7PT[:-2]}{n:02d}" for n in range(3)]

        class RefusesSecondBatch(CountingEngine):
            def request_groups(self, position_ids):
                return [[i] for i in range(len(position_ids))]

            def _answer(self, xgid):
                if len(self.asked) == 1:
                    raise HedgehogRefusal("rate_limited", "Too many requests", status=429)
                return super()._answer(xgid)

        with pytest.raises(HedgehogRefusal):
            CachingAnalyzer(RefusesSecondBatch, cache, ENGINE).analyze_positions_parallel(ids)

        assert set(cache.get_many(ENGINE, ids)) == {ids[0]}

    def test_an_answer_that_does_not_parse_is_not_stored(self, tmp_path):
        cache = AnswerCache(tmp_path / "a.sqlite3")
        engine = CountingEngine()
        engine._answer = lambda xgid: (json.dumps({"success": False}), DecisionType.CUBE_ACTION)

        CachingAnalyzer(lambda: engine, cache, ENGINE).analyze_positions_parallel([CUBE_7PT])

        assert cache.get_many(ENGINE, [CUBE_7PT]) == {}

    def test_a_stored_answer_that_stops_parsing_is_dropped(self, tmp_path):
        """A parser change must not pin a table to "could not be made"."""
        cache = AnswerCache(tmp_path / "a.sqlite3")
        engine = CountingEngine()
        CachingAnalyzer(lambda: engine, cache, ENGINE).analyze_positions_parallel([CUBE_7PT])

        view = CachingAnalyzer(lambda: engine, cache, ENGINE)
        raw, _ = view.analyze_positions_parallel([CUBE_7PT])[0]
        with mock.patch.object(engine, "parse_cube_decision", side_effect=ValueError("new format")):
            with pytest.raises(ValueError):
                view.parse_cube_decision(raw)

        assert cache.get_many(ENGINE, [CUBE_7PT]) == {}

    def test_progress_reaches_the_end_on_a_full_hit(self, tmp_path):
        cache = AnswerCache(tmp_path / "a.sqlite3")
        engine = CountingEngine()
        CachingAnalyzer(lambda: engine, cache, ENGINE).analyze_positions_parallel([CUBE_7PT])
        seen = []

        CachingAnalyzer(lambda: engine, cache, ENGINE).analyze_positions_parallel(
            [CUBE_7PT], progress_callback=lambda done, total: seen.append((done, total))
        )

        assert seen == [(1, 1)]


class TestHedgehogBatchesStayTheSame:
    def test_asking_one_group_at_a_time_sends_the_same_batches(self):
        from ankigammon.utils.hedgehog_analyzer import HedgehogAnalyzer

        client = mock.Mock()
        client.analyze_positions.side_effect = lambda ogids, *a, **k: [{"ogid": o} for o in ogids]
        analyzer = HedgehogAnalyzer(preset="2ply", client=client)
        ids = [CUBE_7PT] * 20 + [CUBE_7PT.replace(":10", ":11")] * 3

        for group in analyzer.request_groups(ids):
            analyzer.analyze_positions_parallel([ids[i] for i in group])

        assert client.analyze_positions.call_count == len(plan_batches(ids, "2ply")[0])


@pytest.fixture
def settings(tmp_path, monkeypatch):
    s = Settings(config_path=tmp_path / "config.json")
    s.analyzer_type = "hedgehog"
    s.generate_score_matrix = True
    s.generate_move_score_matrix = True
    s.generate_move_cube_matrix = True
    s.score_matrix_max_size = 3
    monkeypatch.setattr("ankigammon.anki.card_generator.get_settings", lambda: s)
    return s


class TestCardsMadeAgain:
    def test_regenerating_a_card_asks_the_engine_for_nothing(self, qapp, settings, tmp_path):
        cache = AnswerCache(tmp_path / "a.sqlite3")
        decisions = [
            _analyzed(CUBE_7PT, DecisionType.CUBE_ACTION),
            _analyzed(CHECKER_7PT, DecisionType.CHECKER_PLAY),
        ]

        first_engine = CountingEngine()
        first = CardGenerator(tmp_path / "c1", analyzer=first_engine, answer_cache=cache)
        first_backs = [first.generate_card(d)["back"] for d in decisions]
        assert "score-matrix-table" in first_backs[0]
        assert "move-score-matrix-table" in first_backs[1]

        again_engine = CountingEngine()
        again = CardGenerator(tmp_path / "c2", analyzer=again_engine, answer_cache=cache)
        again_backs = [again.generate_card(d)["back"] for d in decisions]

        assert again_engine.asked == []
        for before, after in zip(first_backs, again_backs):
            for marker in ("score-matrix-table", "move-score-matrix-table"):
                assert (marker in before) == (marker in after)
        assert not again.generation_warnings

    def test_without_a_cache_every_card_asks_the_engine(self, qapp, settings, tmp_path):
        decision = _analyzed(CUBE_7PT, DecisionType.CUBE_ACTION)
        engine = CountingEngine()
        CardGenerator(tmp_path / "c1", analyzer=engine).generate_card(decision)
        asked_once = len(engine.asked)

        CardGenerator(tmp_path / "c2", analyzer=engine).generate_card(decision)

        assert len(engine.asked) == 2 * asked_once

    def test_the_allowance_estimate_leaves_stored_answers_out(self, qapp, settings, tmp_path):
        cache = AnswerCache(tmp_path / "a.sqlite3")
        decision = decision_from_xgid(CUBE_7PT, DecisionType.CUBE_ACTION)
        settings.score_matrix_max_size = 0
        settings.generate_move_score_matrix = settings.generate_move_cube_matrix = False
        before = estimate_hedgehog_cost([decision], "2ply", tmp_path, answer_cache=cache, engine_key=ENGINE)

        CardGenerator(tmp_path / "c", analyzer=CountingEngine(), answer_cache=cache).generate_card(
            _analyzed(CUBE_7PT, DecisionType.CUBE_ACTION)
        )
        after = estimate_hedgehog_cost([decision], "2ply", tmp_path, answer_cache=cache, engine_key=ENGINE)

        assert before == 1 + 5
        assert after == 1
