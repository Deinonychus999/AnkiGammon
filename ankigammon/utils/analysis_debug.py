"""Capture engine responses that could not be parsed.

When analysis of a single position fails, the message alone rarely says
why — the answer is in what the engine actually replied. That reply is
written here so "Create Bug Report" ships it.
"""

from pathlib import Path
from typing import Optional

DEBUG_FILENAME = "debug_failed_analysis.txt"

_SEPARATOR = "=" * 60
_DIVIDER = "-" * 60
_MAX_ENTRIES = 5
_MAX_OUTPUT_CHARS = 20000


def failed_analysis_path() -> Path:
    return Path.home() / ".ankigammon" / DEBUG_FILENAME


def record_failed_analysis(
    position_id: Optional[str],
    raw_output: Optional[str],
    error: Exception,
) -> Optional[Path]:
    """Append one unparseable engine response; keep only the recent few.

    Never raises: this runs on an error path that must not fail again.
    """
    try:
        path = failed_analysis_path()
        path.parent.mkdir(parents=True, exist_ok=True)

        output = (raw_output or "")[:_MAX_OUTPUT_CHARS]
        entry = (
            f"{_SEPARATOR}\n"
            f"Position: {position_id}\n"
            f"Error: {type(error).__name__}: {error}\n"
            f"{_DIVIDER}\n"
            f"{output}\n\n"
        )

        previous = path.read_text(encoding="utf-8") if path.exists() else ""
        # One separator per entry, so this splits entries and nothing else.
        entries = [e for e in previous.split(_SEPARATOR + "\n") if e.strip()]
        kept = "".join(_SEPARATOR + "\n" + e for e in entries[-(_MAX_ENTRIES - 1):])

        path.write_text(kept + entry, encoding="utf-8")
        return path
    except Exception:
        return None
