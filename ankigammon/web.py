"""Entry point for the browser version (ankigammon.com/app), which runs this
package unmodified under Pyodide.

No analysis engine exists in the browser, so only input that already carries
analysis is accepted: XG binary files (.xg, .xgp) and XG text export.

Functions take and return JSON strings so the JavaScript side needs no
knowledge of Python objects.
"""

import json
from pathlib import Path
from typing import List, Optional

from ankigammon import settings as settings_module
from ankigammon.import_filter import filter_decisions
from ankigammon.models import Decision, DecisionType
from ankigammon.settings import Settings

CARD_SETTINGS = (
    "color_scheme",
    "board_orientation",
    "max_moves",
    "swap_checker_colors",
    "show_pip_count",
    "score_format",
    "split_cube_decisions",
    "preview_moves_before_submit",
)

SUPPORTED_EXTENSIONS = (".xg", ".xgp")

_work_dir: Optional[Path] = None
_decisions: List[Decision] = []


def start(work_dir: str = "/tmp/ankigammon") -> None:
    """Begin a session whose settings live in `work_dir`, never the user's home config.

    Card generation reads the process-wide settings, so the session's instance
    is installed there.
    """
    global _work_dir, _decisions
    _work_dir = Path(work_dir)
    _work_dir.mkdir(parents=True, exist_ok=True)
    settings_module._settings = Settings(config_path=_work_dir / "config.json")
    _decisions = []


def _settings() -> Settings:
    if _work_dir is None:
        raise RuntimeError("web.start() must be called first")
    return settings_module.get_settings()


def configure(options_json: str) -> None:
    """Apply card settings, e.g. {"color_scheme": "ocean", "max_moves": 4}."""
    s = _settings()
    for key, value in json.loads(options_json).items():
        if key not in CARD_SETTINGS:
            raise ValueError(f"Unknown card setting: {key}")
        setattr(s, key, value)


def _played(d: Decision):
    return next((m for m in d.candidate_moves if m.was_played), None)


def _error(d: Decision) -> Optional[float]:
    if d.xg_error_move is not None:
        return d.xg_error_move
    played = _played(d)
    if played is not None and played.xg_error is not None:
        return abs(played.xg_error)
    return None


def _summary(index: int, d: Decision) -> dict:
    played = _played(d)
    return {
        "index": index,
        "type": "cube" if d.decision_type == DecisionType.CUBE_ACTION else "checker",
        "on_roll": d.on_roll.name,
        "dice": list(d.dice) if d.dice else None,
        "game": d.game_number,
        "xgid": d.xgid,
        "played": played.notation if played else None,
        "error": _error(d),
        "has_note": bool(d.note),
    }


def _loaded(total: int) -> str:
    return json.dumps({
        "total": total,
        "positions": [_summary(i, d) for i, d in enumerate(_decisions)],
    })


def read_player_names(path: str) -> str:
    """{"o": ..., "x": ...} from an .xg file's header; null where the file has none."""
    from ankigammon.parsers.xg_binary_parser import XGBinaryParser
    player_o, player_x = XGBinaryParser.extract_player_names(path)
    return json.dumps({"o": player_o, "x": player_x})


def load_file(path: str, checker_threshold: float = 0.08, cube_threshold: float = 0.08,
              include_player_x: bool = True, include_player_o: bool = True) -> str:
    """Parse an XG binary file. Match files are filtered like the desktop import;
    a position file (.xgp) is taken whole."""
    from ankigammon.parsers.xg_binary_parser import ParseError, XGBinaryParser
    global _decisions
    suffix = Path(path).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"The browser version reads .xg and .xgp files, not {suffix or 'this file'}. "
            "Other formats need an analysis engine: use the desktop app."
        )
    try:
        parsed = XGBinaryParser.parse_file(path)
    except ParseError as e:
        raise ValueError(
            f"{Path(path).name} could not be read as an eXtreme Gammon file. "
            "If it opens in XG, email it to contact@ankigammon.com so it can be fixed."
        ) from e
    if suffix == ".xgp":
        _decisions = parsed
    else:
        _decisions = filter_decisions(
            parsed, checker_threshold, cube_threshold,
            include_player_x, include_player_o, _settings().max_moves,
        )
    return _loaded(len(parsed))


def load_text(text: str) -> str:
    """Parse positions copied out of eXtreme Gammon (Ctrl+C). Positions XG had
    not analyzed are dropped; `total` minus the positions kept says how many."""
    from ankigammon.parsers.xg_text_parser import XGTextParser
    global _decisions
    _settings()
    parsed = XGTextParser.parse_string(text)
    _decisions = [d for d in parsed if d.candidate_moves]
    if not _decisions:
        raise ValueError(
            "No analyzed positions found. Paste the text XG copies with Ctrl+C "
            "after analyzing; bare position IDs need the desktop app."
        )
    return _loaded(len(parsed))


def _card_generator(show_options: bool, interactive_moves: bool):
    from ankigammon.anki.card_generator import CardGenerator
    from ankigammon.renderer.color_schemes import get_scheme
    from ankigammon.renderer.svg_board_renderer import SVGBoardRenderer
    s = _settings()
    scheme = get_scheme(s.color_scheme)
    if s.swap_checker_colors:
        scheme = scheme.with_swapped_checkers()
    return CardGenerator(
        output_dir=_work_dir,
        show_options=show_options,
        interactive_moves=interactive_moves,
        renderer=SVGBoardRenderer(color_scheme=scheme, orientation=s.board_orientation),
    )


def preview(index: int, show_options: bool = True, interactive_moves: bool = True) -> str:
    """{"front", "back", "css"}: the exact HTML and stylesheet an export would store."""
    from ankigammon.anki.card_styles import get_card_css
    card = _card_generator(show_options, interactive_moves).generate_card(
        _decisions[index], card_id=f"preview_{index}")
    return json.dumps({"front": card["front"], "back": card["back"], "css": get_card_css()})


def export_apkg(indices_json: str, deck_name: str, show_options: bool = True,
                interactive_moves: bool = True, use_subdecks: bool = False) -> str:
    """Write an .apkg of the chosen positions (all when `indices_json` is "[]")
    and return its path."""
    from ankigammon.anki.apkg_exporter import ApkgExporter
    s = _settings()
    indices = json.loads(indices_json)
    chosen = [_decisions[i] for i in indices] if indices else list(_decisions)
    if not chosen:
        raise ValueError("No positions to export")
    return ApkgExporter(_work_dir, deck_name).export(
        chosen,
        output_file="ankigammon.apkg",
        show_options=show_options,
        color_scheme=s.color_scheme,
        interactive_moves=interactive_moves,
        orientation=s.board_orientation,
        use_subdecks=use_subdecks,
    )
