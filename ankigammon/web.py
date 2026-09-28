"""Entry point for the browser version (ankigammon.com/app), which runs this
package unmodified under Pyodide.

Analyzed input is read directly: XG binary files (.xg, .xgp), HedgeHog's
.ogxm files and XG text export. Everything else is analyzed by HedgeHog for
the user's connected account; the page makes those requests, since Python in
the worker cannot wait on them, and hands the answers back here to parse
(`position_requests` / `apply_position_analysis` for pasted positions,
`matrix_requests` / `apply_matrix_analysis` for score matrices and the other
card-back analyses, and a match's .ogxm to `load_file`). Cards leave as an .apkg download or go straight to a running
Anki via AnkiConnect.

Functions take and return JSON strings so the JavaScript side needs no
knowledge of Python objects.
"""

import json
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from ankigammon import settings as settings_module
from ankigammon.anki.ankiconnect import AnkiConnect
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
    "generate_score_matrix",
    "score_matrix_max_size",
    "generate_move_score_matrix",
    "generate_move_cube_matrix",
    "hedgehog_preset",
)
MATRIX_SETTINGS = ("generate_score_matrix", "generate_move_score_matrix", "generate_move_cube_matrix")

SUPPORTED_EXTENSIONS = (".xg", ".xgp", ".ogxm")
MATCH_EXTENSIONS = (".xg", ".ogxm")

_work_dir: Optional[Path] = None
_decisions: List[Decision] = []
_pending: List[Decision] = []
_analyzed_paste: List[Decision] = []
# A paste's answers must belong to the paste the page asked about, not a later one.
_paste_request = 0
# HedgeHog's answers for the card-back analyses, by (preset, XGID)
_prefetched: Dict[Tuple[str, str], dict] = {}
_warnings: List[str] = []


def start(work_dir: str = "/tmp/ankigammon") -> None:
    """Begin a session whose settings live in `work_dir`, never the user's home config.

    Card generation reads the process-wide settings, so the session's instance
    is installed there.
    """
    global _work_dir, _decisions, _pending, _analyzed_paste, _prefetched, _warnings
    _work_dir = Path(work_dir)
    _work_dir.mkdir(parents=True, exist_ok=True)
    settings_module._settings = Settings(config_path=_work_dir / "config.json")
    # HedgeHog is the browser's only engine; this names its depth on the cards.
    settings_module._settings.analyzer_type = "hedgehog"
    _decisions = []
    _pending = []
    _analyzed_paste = []
    _prefetched = {}
    _warnings = []


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
    """{"o": ..., "x": ...} from a match file's header; null where the file has none."""
    if Path(path).suffix.lower() == ".ogxm":
        from ankigammon.parsers.ogxm_parser import extract_player_names
        player_o, player_x = extract_player_names(path)
    else:
        from ankigammon.parsers.xg_binary_parser import XGBinaryParser
        player_o, player_x = XGBinaryParser.extract_player_names(path)
    return json.dumps({"o": player_o, "x": player_x})


def analysis_kind(path: str) -> str:
    """{"analyzed": bool, "import": "mat"|"sgf"|"xg"|null, "text": bool}.
    `analyzed` files load as they are; `text` ones are XG analysis saved as text,
    for `load_text`; otherwise `import` is the HedgeHog route that analyzes the
    file, or null when it is no match file. JellyFish text often comes as .txt
    or with no extension, so content decides."""
    data = Path(path).read_bytes()
    head = data[:4]
    if head == b"OGXM" or Path(path).suffix.lower() in SUPPORTED_EXTENSIONS:
        return json.dumps({"analyzed": True, "import": None, "text": False})
    if head == b"RGMH":
        return json.dumps({"analyzed": False, "import": "xg", "text": False})
    if b"\x00" in data[:4096]:
        return json.dumps({"analyzed": False, "import": None, "text": False})
    text = data[:65536].decode("utf-8", errors="ignore")
    if "XGID=" in text and ("eq:" in text or "Double/" in text or "No double" in text):
        return json.dumps({"analyzed": True, "import": None, "text": True})
    kind = "sgf" if text.lstrip().startswith("(;") else "mat"
    return json.dumps({"analyzed": False, "import": kind, "text": False})


def load_file(path: str, checker_threshold: float = 0.08, cube_threshold: float = 0.08,
              include_player_x: bool = True, include_player_o: bool = True,
              source_description: Optional[str] = None) -> str:
    """Parse an XG binary or OGXM file. Match files are filtered like the
    desktop import; a position file (.xgp) is taken whole. For an OGXM file,
    `source_description` names where the analysis came from."""
    from ankigammon.parsers.xg_binary_parser import ParseError, XGBinaryParser
    global _decisions
    suffix = Path(path).suffix.lower()
    is_ogxm = suffix == ".ogxm" or Path(path).read_bytes()[:4] == b"OGXM"
    if suffix not in SUPPORTED_EXTENSIONS and not is_ogxm:
        raise ValueError(
            f"{Path(path).name} has no analysis yet. HedgeHog can analyze it: "
            "see HedgeHog at the top of the app."
        )
    if is_ogxm:
        from ankigammon.parsers.ogxm_parser import parse_ogxm_bytes
        from ankigammon.utils.ogxm_reader import OgxmError
        try:
            parsed = parse_ogxm_bytes(
                Path(path).read_bytes(),
                source_description=source_description or f"OGXM file '{Path(path).name}'",
            )
        except OgxmError as e:
            raise ValueError(f"{Path(path).name}: {e}") from e
        _decisions = filter_decisions(
            parsed, checker_threshold, cube_threshold,
            include_player_x, include_player_o, _settings().max_moves,
        )
        return _loaded(len(parsed))
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
    analyzed = [d for d in parsed if d.candidate_moves]
    if not analyzed:
        raise ValueError(
            "No analyzed positions or position IDs found. Paste the text XG copies "
            "with Ctrl+C after analyzing, or XGID, GNU BG or OGID position IDs."
        )
    _decisions = analyzed
    return _loaded(len(parsed))


def position_requests(text: str, preset: str = "2ply") -> str:
    """Read a paste and say what HedgeHog must analyse:
    {"request", "analyzed", "pending", "rejected", "batches", "cost"}. Each batch
    is a request for the page to send ({"ogids", "jacoby", "indices"});
    positions XG already analyzed are kept as they are.
    `apply_position_analysis` takes the answers with the same "request".
    """
    from ankigammon.parsers import hedgehog_parser, position_ids
    from ankigammon.parsers.xg_text_parser import XGTextParser
    global _pending, _analyzed_paste, _paste_request
    _settings()
    _paste_request += 1
    parsed = XGTextParser.parse_string(text)
    _analyzed_paste = [d for d in parsed if d.candidate_moves]
    rejected: List[str] = []
    if _analyzed_paste:
        _pending = [d for d in parsed if not d.candidate_moves]
    else:
        _pending, rejected = position_ids.parse_position_id_lines(text)
    batches, _ = hedgehog_parser.plan_batches([d.xgid for d in _pending], preset)
    return json.dumps({
        "request": _paste_request,
        "analyzed": len(_analyzed_paste),
        "pending": len(_pending),
        "rejected": [position_ids.describe_rejected_id(line) for line in rejected],
        "batches": batches,
        "cost": hedgehog_parser.estimated_cost(batches, preset),
    })


def apply_position_analysis(results_json: str, preset_label: str = "3-ply",
                            request: Optional[int] = None) -> str:
    """Build the pasted positions from HedgeHog's answers, one per pending
    position in `position_requests`' order (a failure is HedgeHog's
    {"success": false, ...}). Returns the loaded summary plus "failed", the
    messages of positions HedgeHog could not analyse."""
    from ankigammon.anki.decision_serialize import carry_user_metadata
    from ankigammon.parsers.hedgehog_parser import parse_position_result
    global _decisions, _pending
    _settings()
    results = json.loads(results_json)
    if (request is not None and request != _paste_request) or len(results) != len(_pending):
        raise ValueError("HedgeHog's answers do not match the pasted positions; paste them again.")
    analyzed: List[Decision] = []
    failed: List[str] = []
    for pending, result in zip(_pending, results):
        try:
            decision = parse_position_result(json.dumps(result), pending.xgid,
                                             pending.decision_type, preset_label)
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            failed.append(str(e) if isinstance(e, ValueError) else "HedgeHog's answer could not be read.")
            continue
        carry_user_metadata(pending, decision)
        decision.source_description = (
            f"Analyzed with HedgeHog ({preset_label}) from {pending.original_position_format or 'XGID'}"
        )
        analyzed.append(decision)
    total = len(_analyzed_paste) + len(_pending)
    if not analyzed and not _analyzed_paste:
        raise ValueError(failed[0] if failed else "HedgeHog analyzed none of the pasted positions.")
    _decisions = _analyzed_paste + analyzed
    _pending = []
    loaded = json.loads(_loaded(total))
    loaded["failed"] = failed
    return json.dumps(loaded)


def _matrix_analyzer():
    """The engine for the optional analyses: HedgeHog's answers fetched ahead
    of time (`matrix_requests`), or None when the settings ask for none."""
    s = _settings()
    if not any(s.get(key) for key in MATRIX_SETTINGS):
        return None
    from ankigammon.utils.prefetch_analyzer import CachedAnalyzer
    preset = s.hedgehog_preset
    answers = {xgid: result for (p, xgid), result in _prefetched.items() if p == preset}
    return CachedAnalyzer(answers, s.hedgehog_preset_label())


def _card_generator(show_options: bool, interactive_moves: bool, analyzer=None):
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
        analyzer=analyzer if analyzer is not None else _matrix_analyzer(),
    )


def _chosen(indices_json: str) -> List[Decision]:
    indices = json.loads(indices_json)
    return [_decisions[i] for i in indices] if indices else list(_decisions)


def matrix_requests(indices_json: str, preset: str = "2ply") -> str:
    """What HedgeHog must analyse for the card-back analyses the settings ask
    for (score matrix, move score matrix, cube-position comparison) on the
    chosen positions, all when `indices_json` is "[]": {"xgids", "batches",
    "cost"}. Positions already fetched at `preset` are left out, so an empty
    list means the cards can be built. `apply_matrix_analysis` takes the
    answers back with these "xgids"."""
    from ankigammon.parsers.hedgehog_parser import estimated_cost, plan_batches
    from ankigammon.utils.prefetch_analyzer import RecordingAnalyzer
    s = _settings()
    if not any(s.get(key) for key in MATRIX_SETTINGS):
        return json.dumps({"xgids": [], "batches": [], "cost": 0})
    recorder = RecordingAnalyzer(s.hedgehog_preset_label(preset))
    generator = _card_generator(False, False, analyzer=recorder)
    for decision in _chosen(indices_json):
        generator.study_extras(decision)
    needed = [xgid for xgid in recorder.requested if (preset, xgid) not in _prefetched]
    batches, _ = plan_batches(needed, preset)
    return json.dumps({"xgids": needed, "batches": batches, "cost": estimated_cost(batches, preset)})


def _same_position(sent: str, echoed: str) -> bool:
    """Whether HedgeHog's echoed OGID is the one sent; it fills in the move id."""
    a, b = sent.split(":"), (echoed or "").split(":")
    return a[:5] == b[:5] and a[6:9] == b[6:9]


def apply_matrix_analysis(xgids_json: str, results_json: str, preset: str = "2ply") -> str:
    """Keep HedgeHog's answers for `matrix_requests`' "xgids", one per XGID in
    that order. Failures are not kept, so the next request asks again.
    Returns {"stored", "failed": [HedgeHog's messages]}."""
    from ankigammon.parsers.hedgehog_parser import xgid_to_ogid
    xgids, results = json.loads(xgids_json), json.loads(results_json)
    if len(results) != len(xgids):
        raise ValueError("HedgeHog's answers do not match the positions asked for; try again.")
    stored = 0
    failed: List[str] = []
    for xgid, result in zip(xgids, results):
        if not isinstance(result, dict) or result.get("success") is False:
            error = (result or {}).get("error") if isinstance(result, dict) else None
            failed.append((error or {}).get("message") or "HedgeHog could not analyze a position.")
        elif not _same_position(xgid_to_ogid(xgid)[0], result.get("ogid")):
            failed.append("HedgeHog answered for a different position; try again.")
        else:
            _prefetched[(preset, xgid)] = result
            stored += 1
    return json.dumps({"stored": stored, "failed": failed})


def generation_warnings() -> str:
    """The warnings of the last preview or export, e.g. a score matrix left off."""
    return json.dumps(_warnings)


def _keep_warnings(warnings: List[str]) -> List[str]:
    global _warnings
    _warnings = list(warnings)
    return _warnings


def preview(index: int, show_options: bool = True, interactive_moves: bool = True) -> str:
    """{"front", "back", "css"}: the exact HTML and stylesheet an export would store."""
    from ankigammon.anki.card_styles import get_card_css
    generator = _card_generator(show_options, interactive_moves)
    card = generator.generate_card(_decisions[index], card_id=f"preview_{index}")
    return json.dumps({"front": card["front"], "back": card["back"], "css": get_card_css(),
                       "warnings": _keep_warnings(generator.generation_warnings)})


def export_apkg(indices_json: str, deck_name: str, show_options: bool = True,
                interactive_moves: bool = True, use_subdecks: bool = False) -> str:
    """Write an .apkg of the chosen positions (all when `indices_json` is "[]")
    and return its path."""
    from ankigammon.anki.apkg_exporter import ApkgExporter
    s = _settings()
    chosen = _chosen(indices_json)
    if not chosen:
        raise ValueError("No positions to export")
    exporter = ApkgExporter(_work_dir, deck_name)
    path = exporter.export(
        chosen,
        output_file="ankigammon.apkg",
        show_options=show_options,
        color_scheme=s.color_scheme,
        interactive_moves=interactive_moves,
        orientation=s.board_orientation,
        use_subdecks=use_subdecks,
        analyzer=_matrix_analyzer(),
    )
    _keep_warnings(exporter.generation_warnings)
    return path


def export_pack(indices_json: str, deck_name: str) -> str:
    """The chosen positions (all when `indices_json` is "[]") as a study pack
    for the trainer, a JSON string."""
    from ankigammon.study_pack import build_pack
    _settings()
    chosen = _chosen(indices_json)
    extras = None
    analyzer = _matrix_analyzer()
    if analyzer is not None:
        generator = _card_generator(False, False, analyzer=analyzer)
        extras = [generator.study_extras(decision) for decision in chosen]
    pack = build_pack(chosen, deck_name, extras)
    if not pack["positions"]:
        raise ValueError("No positions to export")
    return json.dumps(pack, separators=(",", ":"))


def _xhr_post(url: str, payload: dict) -> dict:
    """POST from the web worker with a synchronous XMLHttpRequest.

    A plain-text body keeps it a CORS "simple" request: AnkiConnect answers
    preflights only for origins it already allows, and it parses the body as
    JSON whatever the content type.
    """
    from js import XMLHttpRequest

    xhr = XMLHttpRequest.new()
    xhr.open("POST", url, False)
    try:
        xhr.send(json.dumps(payload))
    except Exception:
        raise ConnectionError(
            f"Could not reach Anki at {url}. Check that Anki is running with AnkiConnect "
            "and that this site is allowed."
        ) from None
    if xhr.status != 200:
        raise ConnectionError(f"AnkiConnect at {url} answered HTTP {xhr.status}.")
    return json.loads(xhr.responseText)


class _BrowserAnkiConnect(AnkiConnect):
    """The desktop AnkiConnect client with the transport swapped, so model
    setup, field migration and upsert-by-XGID behave exactly as on desktop."""

    def __init__(self, url: str, deck_name: str, transport: Callable[[str, dict], dict],
                 api_key: Optional[str] = None):
        super().__init__(url=url, deck_name=deck_name)
        self._transport = transport
        self._api_key = api_key
        self.added = 0

    def _post(self, payload: dict) -> dict:
        if self._api_key:
            payload = {**payload, "key": self._api_key}
        return self._transport(self.url, payload)

    def add_note(self, *args, **kwargs) -> int:
        note_id = super().add_note(*args, **kwargs)
        self.added += 1
        return note_id


def send_to_anki(indices_json: str, deck_name: str, url: str = "http://127.0.0.1:8765",
                 show_options: bool = True, interactive_moves: bool = True,
                 use_subdecks: bool = False, api_key: str = "",
                 progress: Optional[Callable[[int, int], None]] = None,
                 transport: Optional[Callable[[str, dict], dict]] = None) -> str:
    """Add or update the chosen positions in a running Anki through AnkiConnect,
    matched by XGID like the desktop export. Returns
    {"total", "added", "updated", "decks"}.

    The page must have obtained permission first (AnkiConnect's
    requestPermission from the main thread), since that call opens Anki's
    dialog and the browser's local-network prompt.
    """
    from ankigammon.anki.deck_utils import group_decisions_by_deck

    _settings()
    indices = json.loads(indices_json)
    chosen = [_decisions[i] for i in indices] if indices else list(_decisions)
    if not chosen:
        raise ValueError("No positions to send")
    groups = group_decisions_by_deck(chosen, deck_name, use_subdecks)

    client = _BrowserAnkiConnect(url, deck_name, transport or _xhr_post, api_key or None)
    client.create_model()
    for name in groups:
        client.create_deck(name)

    generator = _card_generator(show_options, interactive_moves)
    total = len(chosen)
    done = 0
    for name, decisions in groups.items():
        for decision in decisions:
            if progress:
                progress(done, total)
            card = generator.generate_card(decision, card_id=f"card_{done}")
            client.upsert_note(
                front=card["front"],
                back=card["back"],
                tags=card.get("tags", []),
                deck_name=name,
                xgid=card.get("xgid", ""),
                analysis_data=card.get("analysis_data", ""),
            )
            done += 1
    if progress:
        progress(done, total)
    return json.dumps({"total": total, "added": client.added,
                       "updated": total - client.added, "decks": list(groups),
                       "warnings": _keep_warnings(generator.generation_warnings)})
