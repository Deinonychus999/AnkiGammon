"""HedgeHog as an analysis engine: positions through the partner API's batch
position analysis, match files through its match analysis and the OGXM file it
returns. Every analysis is charged to the connected user's HedgeHog plan.
"""

import json
import logging
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from ankigammon.models import Decision, DecisionType, Move
from ankigammon.parsers import hedgehog_parser
from ankigammon.utils.analyzer_base import BackgammonAnalyzer
from ankigammon.utils.hedgehog_client import HedgehogClient

logger = logging.getLogger(__name__)

# A batch counts as one analysis only when the whole of it takes under a second
# of engine time. About 12 positions fit at 2ply; deeper presets are counted per
# position however they are sent, so they only need fewer requests.
BATCH_SIZES = {"1ply": 64, "2ply": 12, "3ply": 64, "+": 8, "++": 8}


class HedgehogAnalyzer(BackgammonAnalyzer):
    """Analyze positions and matches on hedgehog-bg.com for the connected user."""

    def __init__(self, preset: str = "2ply", preset_label: Optional[str] = None,
                 client: Optional[HedgehogClient] = None):
        self.preset = preset
        self.preset_label = preset_label or preset
        self.client = client or HedgehogClient()
        self._cancel = threading.Event()

    # --- Positions ------------------------------------------------------------

    def analyze_position(self, position_id: str) -> Tuple[str, DecisionType]:
        return self.analyze_positions_parallel([position_id])[0]

    def analyze_positions_parallel(
        self,
        position_ids: List[str],
        max_workers: Optional[int] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        cancellation_callback: Optional[Callable[[], bool]] = None
    ) -> List[Tuple[str, DecisionType]]:
        self._cancel.clear()
        cancelled = lambda: self._cancel.is_set() or bool(cancellation_callback and cancellation_callback())
        prepared = [hedgehog_parser.xgid_to_ogid(xgid) for xgid in position_ids]

        # `jacoby` applies to a whole batch, so the two rules go in separate batches.
        groups: Dict[bool, List[int]] = {}
        for index, (_, _, jacoby) in enumerate(prepared):
            groups.setdefault(jacoby, []).append(index)
        size = BATCH_SIZES.get(self.preset, 8)

        results: List[Optional[Tuple[str, DecisionType]]] = [None] * len(position_ids)
        done = 0
        for jacoby, indices in groups.items():
            for start in range(0, len(indices), size):
                if cancelled():
                    raise InterruptedError("Analysis cancelled by user")
                chunk = indices[start:start + size]
                answers = self.client.analyze_positions(
                    [prepared[i][0] for i in chunk], self.preset, jacoby, cancelled=cancelled,
                )
                for i, answer in zip(chunk, answers):
                    results[i] = (json.dumps(answer), prepared[i][1])
                done += len(chunk)
                if progress_callback:
                    progress_callback(done, len(position_ids))
        return results

    def parse_analysis(self, raw_output: str, xgid: str, decision_type: DecisionType) -> Decision:
        return hedgehog_parser.parse_position_result(raw_output, xgid, decision_type, self.preset_label)

    def parse_checker_play(self, raw_output: str) -> List[Move]:
        result = json.loads(raw_output)
        return hedgehog_parser.checker_moves(result, self._decision_for(result), self.preset_label)

    def parse_cube_decision(self, raw_output: str, cube_value: int = 1) -> List[Move]:
        result = json.loads(raw_output)
        try:
            return hedgehog_parser.cube_decision_moves(result, self._decision_for(result))
        except ValueError:
            return []

    @staticmethod
    def _decision_for(result: dict) -> Decision:
        """The game context of a bare result, read from the OGID HedgeHog analysed."""
        from ankigammon.utils.ogid import parse_ogid
        from ankigammon.utils.xgid import encode_xgid
        position, metadata = parse_ogid(result["ogid"])
        match_length = metadata.get("match_length", 0)
        xgid = encode_xgid(
            position, cube_value=metadata.get("cube_value", 1), cube_owner=metadata.get("cube_owner"),
            dice=metadata.get("dice"), on_roll=metadata["on_roll"],
            score_x=metadata.get("score_x", 0), score_o=metadata.get("score_o", 0),
            match_length=match_length,
            crawford_jacoby=1 if metadata.get("match_modifier") == "C" else 0,
        )
        decision_type = (
            DecisionType.CHECKER_PLAY if result.get("decision_type") == "checker" else DecisionType.CUBE_ACTION
        )
        return hedgehog_parser.decision_from_xgid(xgid, decision_type)

    # --- Matches ----------------------------------------------------------------

    def analyze_match_file(
        self,
        file_path: str,
        max_moves: int = 8,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> List[Decision]:
        from ankigammon.parsers.ogxm_parser import parse_ogxm_bytes

        self._cancel.clear()
        report = progress_callback or (lambda message: None)
        name = Path(file_path).name

        report(f"Sending {name} to HedgeHog...")
        converted = self.client.import_match(file_path)
        for warning in (converted.get("report") or {}).get("warnings") or []:
            logger.info("HedgeHog import note for %s: %s", name, warning)
        saved = self.client.save_match(converted["data"])

        report(f"HedgeHog is analyzing {name} ({self.preset_label})...\n"
               "This may take a minute for long matches.")
        job = self.client.analyze_match(saved["match_id"], self.preset)
        analysis = self.client.wait_analysis(job["analysis_id"], cancelled=self._cancel.is_set)

        report("Downloading HedgeHog's analysis...")
        data = self.client.analysis_file(analysis["id"])
        model = analysis.get("model_name") or "HedgeHog"
        return parse_ogxm_bytes(
            data,
            level=self.preset_label,
            source_description=f"HedgeHog analysis ({model}, {self.preset_label}) from '{name}'",
        )

    def terminate(self) -> None:
        self._cancel.set()
