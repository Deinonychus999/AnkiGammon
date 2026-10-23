"""On-disk store of the engine answers behind a card's optional tables.

The score matrix, move score matrix and cube-position comparison are each
built from one engine answer per variant of the position, and on HedgeHog
every request spends allowance. Making a card again (a regenerate after a
theme change, a re-export, a collection opened afresh) reads those answers
back instead of asking again.

Answers are stored as the engine's raw output, not as finished tables, so a
fix to how answers are parsed or drawn still reaches every card on its next
regenerate, and each request's answers are kept as soon as they arrive, so a
refusal part way through a table loses none that were already paid for.
"""

import logging
from contextlib import closing
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from ankigammon.models import Decision, DecisionType
from ankigammon.utils.analyzer_base import BackgammonAnalyzer

logger = logging.getLogger(__name__)

# SQLite stays a lazy import: the browser version (Pyodide) loads this module
# through card_generator but never makes a cache, and ships without sqlite3.
_MAX_PARAMS = 500

Answer = Tuple[str, DecisionType]


class AnswerCache:
    def __init__(self, path: Path):
        self.path = Path(path)

    @classmethod
    def default(cls) -> "AnswerCache":
        return cls(Path.home() / ".ankigammon" / "analysis_cache" / "answers.sqlite3")

    def _connect(self):
        import sqlite3
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path), timeout=10)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS answers ("
            " engine TEXT NOT NULL, position TEXT NOT NULL,"
            " decision_type TEXT NOT NULL, raw TEXT NOT NULL,"
            " PRIMARY KEY (engine, position))"
        )
        return conn

    def get_many(self, engine: str, positions: Sequence[str]) -> Dict[str, Answer]:
        """The stored answers among `positions`; a cache that cannot be read is empty."""
        unique = list(dict.fromkeys(positions))
        found: Dict[str, Answer] = {}
        if not unique or not self.path.exists():
            return found
        try:
            with closing(self._connect()) as conn:
                for start in range(0, len(unique), _MAX_PARAMS):
                    chunk = unique[start:start + _MAX_PARAMS]
                    rows = conn.execute(
                        "SELECT position, decision_type, raw FROM answers"
                        f" WHERE engine = ? AND position IN ({','.join('?' * len(chunk))})",
                        [engine, *chunk],
                    )
                    for position, decision_type, raw in rows:
                        if decision_type in DecisionType.__members__:
                            found[position] = (raw, DecisionType[decision_type])
        except Exception:
            logger.warning("Could not read the analysis cache %s", self.path, exc_info=True)
        return found

    def put_many(self, engine: str, answers: Dict[str, Answer]) -> None:
        """Best effort: an answer that cannot be stored only costs a later request."""
        if not answers:
            return
        try:
            with closing(self._connect()) as conn, conn:
                conn.executemany(
                    "INSERT OR REPLACE INTO answers VALUES (?, ?, ?, ?)",
                    [(engine, position, dt.name, raw) for position, (raw, dt) in answers.items()],
                )
        except Exception:
            logger.warning("Could not write the analysis cache %s", self.path, exc_info=True)

    def discard(self, engine: str, position: str) -> None:
        try:
            with closing(self._connect()) as conn, conn:
                conn.execute("DELETE FROM answers WHERE engine = ? AND position = ?", (engine, position))
        except Exception:
            logger.warning("Could not update the analysis cache %s", self.path, exc_info=True)

    def stats(self) -> Tuple[int, int]:
        """(answers stored, bytes on disk)."""
        if not self.path.exists():
            return 0, 0
        try:
            with closing(self._connect()) as conn:
                count = conn.execute("SELECT COUNT(*) FROM answers").fetchone()[0]
            return count, self.path.stat().st_size
        except Exception:
            return 0, 0

    def clear(self) -> None:
        # 1.19.0 kept finished tables as JSON files in the same folder.
        for legacy in self.path.parent.glob("*.json"):
            try:
                legacy.unlink()
            except OSError:
                pass
        if not self.path.exists():
            return
        try:
            with closing(self._connect()) as conn:
                with conn:
                    conn.execute("DELETE FROM answers")
                conn.execute("VACUUM")
        except Exception:
            logger.warning("Could not clear the analysis cache %s", self.path, exc_info=True)


class CachingAnalyzer(BackgammonAnalyzer):
    """Answers from the cache, asking `engine()` only for positions it lacks.

    The engine is reached through a callable so a card whose answers are all
    stored never starts one. Only answers that parse into moves are stored,
    and a stored answer that stops parsing is dropped, so neither a failed
    analysis nor a parser change can pin a table to "could not be made".
    """

    def __init__(self, engine: Callable[[], BackgammonAnalyzer], cache: AnswerCache, engine_key: str):
        self._engine = engine
        self.cache = cache
        self.engine_key = engine_key
        self._served: Dict[str, str] = {}

    def analyze_position(self, position_id: str) -> Answer:
        return self.analyze_positions_parallel([position_id])[0]

    def analyze_positions_parallel(
        self,
        position_ids: List[str],
        max_workers: Optional[int] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        cancellation_callback: Optional[Callable[[], bool]] = None
    ) -> List[Answer]:
        total = len(position_ids)
        answers = self.cache.get_many(self.engine_key, position_ids)
        for position, (raw, _) in answers.items():
            self._served[raw] = position
        missing = [p for p in dict.fromkeys(position_ids) if p not in answers]
        if missing:
            engine = self._engine()
            asked = 0
            for group in engine.request_groups(missing):
                ids = [missing[i] for i in group]
                offset = total - len(missing) + asked

                def progress(done: int, _: int, offset=offset) -> None:
                    if progress_callback:
                        progress_callback(min(offset + done, total), total)

                results = engine.analyze_positions_parallel(
                    ids, max_workers=max_workers,
                    progress_callback=progress, cancellation_callback=cancellation_callback,
                )
                fresh = dict(zip(ids, results))
                answers.update(fresh)
                self.cache.put_many(self.engine_key, {
                    p: answer for p, answer in fresh.items() if self._parses(engine, *answer)
                })
                asked += len(ids)
        elif progress_callback:
            progress_callback(total, total)
        return [answers[p] for p in position_ids]

    @staticmethod
    def _parses(engine: BackgammonAnalyzer, raw: str, decision_type: DecisionType) -> bool:
        try:
            if decision_type == DecisionType.CHECKER_PLAY:
                return bool(engine.parse_checker_play(raw))
            return bool(engine.parse_cube_decision(raw))
        except Exception:
            return False

    def _parsed(self, parse: Callable[[], List], raw: str) -> List:
        try:
            moves = parse()
        except Exception:
            self._forget(raw)
            raise
        if not moves:
            self._forget(raw)
        return moves

    def _forget(self, raw: str) -> None:
        position = self._served.pop(raw, None)
        if position is not None:
            self.cache.discard(self.engine_key, position)

    def parse_checker_play(self, raw_output: str):
        return self._parsed(lambda: self._engine().parse_checker_play(raw_output), raw_output)

    def parse_cube_decision(self, raw_output: str, cube_value: int = 1):
        return self._parsed(lambda: self._engine().parse_cube_decision(raw_output, cube_value), raw_output)

    def parse_analysis(self, raw_output: str, xgid: str, decision_type: DecisionType) -> Decision:
        return self._engine().parse_analysis(raw_output, xgid, decision_type)

    def analyze_match_file(self, file_path: str, max_moves: int = 8, progress_callback=None) -> List[Decision]:
        return self._engine().analyze_match_file(file_path, max_moves, progress_callback)

    def terminate(self) -> None:
        """The engine belongs to whoever made it, not to this view of it."""
