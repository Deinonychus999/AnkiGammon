"""Engines that answer from HedgeHog results fetched ahead of time.

In the browser, Python cannot wait on the network while a card is being built,
so the optional analyses (score matrix, move score matrix, cube-position
comparison) run twice: first against RecordingAnalyzer, which notes every
position the card generator asks about and answers with placeholders; the
page then fetches those from HedgeHog; and the cards are built against
CachedAnalyzer, which answers from what was fetched. Qt-free and network-free.
"""

import json
from typing import Callable, Dict, List, Optional, Tuple

from ankigammon.models import Decision, DecisionType
from ankigammon.parsers.hedgehog_parser import PositionResultParsing, xgid_to_ogid
from ankigammon.utils.analyzer_base import BackgammonAnalyzer


class _AnswersInAdvance(PositionResultParsing, BackgammonAnalyzer):
    def __init__(self, preset_label: str = "HedgeHog"):
        self.preset_label = preset_label

    def _answer(self, xgid: str) -> Tuple[str, DecisionType]:
        raise NotImplementedError

    def analyze_position(self, position_id: str) -> Tuple[str, DecisionType]:
        return self._answer(position_id)

    def analyze_positions_parallel(
        self,
        position_ids: List[str],
        max_workers: Optional[int] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        cancellation_callback: Optional[Callable[[], bool]] = None
    ) -> List[Tuple[str, DecisionType]]:
        answers = [self._answer(xgid) for xgid in position_ids]
        if progress_callback:
            progress_callback(len(answers), len(answers))
        return answers

    def analyze_match_file(self, file_path: str, max_moves: int = 8,
                           progress_callback=None) -> List[Decision]:
        raise ValueError("Match files are analyzed on HedgeHog, not through fetched answers")

    def terminate(self) -> None:
        pass


class RecordingAnalyzer(_AnswersInAdvance):
    """Notes the positions asked about, in order and once each."""

    def __init__(self, preset_label: str = "HedgeHog"):
        super().__init__(preset_label)
        self.requested: List[str] = []

    def _answer(self, xgid: str) -> Tuple[str, DecisionType]:
        if xgid not in self.requested:
            self.requested.append(xgid)
        ogid, decision_type, _ = xgid_to_ogid(xgid)
        if decision_type == DecisionType.CHECKER_PLAY:
            placeholder = {"decision_type": "checker", "ogid": ogid,
                           "alternatives": [{"move_notation": "24/23", "equity": 0.0}]}
        else:
            placeholder = {"decision_type": "cube", "ogid": ogid, "cube_decision": {
                "action": "No Double", "no_double_equity": 0.0,
                "double_take_equity": 0.0, "double_pass_equity": 1.0,
            }}
        return json.dumps(placeholder), decision_type


class CachedAnalyzer(_AnswersInAdvance):
    """Answers from HedgeHog results keyed by XGID; a position that was never
    fetched is an error, which the card generator reports and skips."""

    def __init__(self, answers: Dict[str, dict], preset_label: str = "HedgeHog"):
        super().__init__(preset_label)
        self.answers = answers

    def _answer(self, xgid: str) -> Tuple[str, DecisionType]:
        result = self.answers.get(xgid)
        if result is None:
            raise ValueError("This analysis has not been fetched from HedgeHog")
        if result.get("success") is False:
            raise ValueError((result.get("error") or {}).get("message") or "HedgeHog could not analyze this position")
        _, decision_type, _ = xgid_to_ogid(xgid)
        return json.dumps(result), decision_type


def estimate_hedgehog_cost(decisions: List[Decision], preset: str, output_dir) -> int:
    """About how many position analyses exporting `decisions` costs on
    HedgeHog: the positions without analysis, plus the optional analyses the
    settings ask for, each card's sent as its own batches as the desktop does."""
    from ankigammon.anki.card_generator import CardGenerator
    from ankigammon.parsers.hedgehog_parser import estimated_cost, plan_batches

    unanalyzed = [d.xgid for d in decisions if not d.candidate_moves and d.xgid]
    cost = estimated_cost(plan_batches(unanalyzed, preset)[0], preset) if unanalyzed else 0
    recorder = RecordingAnalyzer()
    generator = CardGenerator(output_dir=output_dir, analyzer=recorder)
    for decision in decisions:
        recorder.requested = []
        generator.study_extras(decision)
        if recorder.requested:
            cost += estimated_cost(plan_batches(recorder.requested, preset)[0], preset)
    return cost
