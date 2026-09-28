"""HedgeHog as an analysis engine: positions through the partner API's batch
position analysis, match files through its match analysis and the OGXM file it
returns. Every analysis is charged to the connected user's HedgeHog plan.
"""

import json
import logging
import threading
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from ankigammon.models import Decision, DecisionType
from ankigammon.parsers import hedgehog_parser
from ankigammon.parsers.hedgehog_parser import BATCH_SIZES
from ankigammon.utils.analyzer_base import BackgammonAnalyzer
from ankigammon.utils.hedgehog_client import HedgehogClient

logger = logging.getLogger(__name__)


class HedgehogAnalyzer(hedgehog_parser.PositionResultParsing, BackgammonAnalyzer):
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
        batches, decision_types = hedgehog_parser.plan_batches(position_ids, self.preset)

        results: List[Optional[Tuple[str, DecisionType]]] = [None] * len(position_ids)
        done = 0
        for batch in batches:
            if cancelled():
                raise InterruptedError("Analysis cancelled by user")
            answers = self.client.analyze_positions(
                batch["ogids"], self.preset, batch["jacoby"], cancelled=cancelled,
            )
            for i, answer in zip(batch["indices"], answers):
                results[i] = (json.dumps(answer), decision_types[i])
            done += len(batch["indices"])
            if progress_callback:
                progress_callback(done, len(position_ids))
        return results

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
