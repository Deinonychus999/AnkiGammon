"""Render an HTML gallery of back-card outputs across .xg files.

Picks a handful of interesting checker-play positions from each .xg file in
`match_files/`, runs them through the real `CardGenerator`, and stitches the
resulting back-card HTML into one self-contained report. Use this to visually
sanity-check the analysis-level badges and the new tier-then-error sort
order against real positions.

Run:
    python scripts/build_analysis_level_report.py

Output: docs/analysis_level_report.html (open in a browser).
"""

from __future__ import annotations

import glob
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ankigammon.anki.card_generator import CardGenerator
from ankigammon.anki.card_styles import CARD_CSS
from ankigammon.models import Decision, DecisionType
from ankigammon.parsers.xg_binary_parser import XGBinaryParser

REPO_ROOT = Path(__file__).resolve().parent.parent
MATCH_FILES_DIR = REPO_ROOT / "match_files"
XGP_SAMPLE_DIR = REPO_ROOT / "xg_dump" / "xgp"
OUTPUT_PATH = REPO_ROOT / "docs" / "analysis_level_report.html"

# Cap how many positions we surface per file so the page stays reasonable.
MAX_POSITIONS_PER_FILE = 4
MAX_MOVES_TO_SHOW = 5

# Cap how many .xgp single-position files we render. There are hundreds in
# xg_dump/, so we just pull a stratified sample big enough to exercise each
# label (Book/Rollout/N-ply/XG Roller variants) without bloating the report.
MAX_XGP_SAMPLES = 8


@dataclass
class Pick:
    decision: Decision
    why: str  # one-line reason this position is interesting


# Pinned positions referenced in the GitHub issue reports. Matched purely by
# game context (no filenames or player names), so the script stays
# share-safe.  Each entry: dice tuple, score_o, score_x, match_length,
# a notation that must appear in the candidate set, "why" label.
PINNED_POSITIONS: List[Tuple[Tuple[int, int], int, int, int, str, str]] = [
    (
        (2, 1),
        1,
        0,
        7,
        "13/11 6/5*",
        "Issue screenshot 1: dice=21, 7pt 1-0 — was capped at 2 moves before fix",
    ),
    (
        (3, 2),
        1,
        0,
        7,
        "24/21 23/21",
        "Issue screenshot 2: dice=32, 7pt 1-0 — checks tier-then-error sort "
        "(XG Roller+ rows above 4-ply rows)",
    ),
]


def find_pinned_position(file_path: Path) -> List[Pick]:
    """Return any pinned positions (from the issue reports) that live in this file.

    Matched by game context (dice, score, match length, presence of a
    distinctive candidate notation) — never by filename — so the same script
    works regardless of how the source .xg is named.
    """
    found: List[Pick] = []
    try:
        decisions = XGBinaryParser.parse_file(str(file_path))
    except Exception:
        return []
    for dice, so, sx, ml, must_have_notation, why in PINNED_POSITIONS:
        for d in decisions:
            if d.decision_type != DecisionType.CHECKER_PLAY:
                continue
            if d.dice not in (dice, (dice[1], dice[0])):
                continue
            if d.score_o != so or d.score_x != sx or d.match_length != ml:
                continue
            if must_have_notation not in {m.notation for m in d.candidate_moves}:
                continue
            found.append(Pick(decision=d, why=why))
            break
    return found


def pick_interesting_positions(file_path: Path) -> List[Pick]:
    """Choose positions that exercise the tier-label and sort logic."""
    decisions = XGBinaryParser.parse_file(str(file_path))
    checker = [
        d for d in decisions
        if d.decision_type == DecisionType.CHECKER_PLAY and len(d.candidate_moves) >= 3
    ]

    picks: List[Pick] = []
    seen_xgids: set[str] = set()

    def add(decision: Decision, why: str) -> None:
        key = decision.xgid or f"{decision.dice}-{decision.score_o}-{decision.score_x}"
        if key in seen_xgids:
            return
        seen_xgids.add(key)
        picks.append(Pick(decision=decision, why=why))

    # 1) Positions with both XG Roller variants AND ply tiers — best for
    #    showcasing tier-first sort.
    for d in checker:
        labels = {m.analysis_level for m in d.candidate_moves}
        has_roller = any("Roller" in (l or "") for l in labels)
        has_ply = any((l or "").endswith("-ply") for l in labels)
        if has_roller and has_ply:
            add(d, "Mixed tiers: XG Roller variants alongside N-ply")
            if len([p for p in picks if "Mixed tiers" in p.why]) >= 2:
                break

    # 2) Positions with full rollouts (Level=100 / rolled_out flag).
    for d in checker:
        if any(m.analysis_level == "Rollout" for m in d.candidate_moves):
            add(d, "Rollout-analyzed: top moves rolled out, rest at heuristic depth")
            if len([p for p in picks if "Rollout-analyzed" in p.why]) >= 1:
                break

    # 3) A pure single-tier position (every candidate at the same depth) — the
    #    badge should still render consistently, sort falls through to error.
    for d in checker:
        labels = {m.analysis_level for m in d.candidate_moves}
        if len(labels) == 1 and len(d.candidate_moves) >= 4:
            add(d, "Uniform tier: all candidates analyzed at the same depth")
            if len([p for p in picks if "Uniform tier" in p.why]) >= 1:
                break

    # 4) Fill remaining slots with positions that simply have many candidates.
    for d in sorted(checker, key=lambda d: -len(d.candidate_moves)):
        add(d, f"Wide candidate set ({len(d.candidate_moves)} moves)")
        if len(picks) >= MAX_POSITIONS_PER_FILE:
            break

    return picks[:MAX_POSITIONS_PER_FILE]


def render_back(gen: CardGenerator, decision: Decision) -> str:
    """Generate the back-card HTML for a decision via the real generator."""
    card = gen.generate_card(decision, 0)
    if isinstance(card, dict):
        return card.get("back", "")
    if isinstance(card, tuple) and len(card) >= 2:
        return card[1]
    if hasattr(card, "back"):
        return card.back
    return str(card)


def format_metadata_line(decision: Decision) -> str:
    dice_str = f"{decision.dice[0]}{decision.dice[1]}" if decision.dice else "—"
    match_str = "money" if decision.match_length == 0 else f"{decision.match_length}pt"
    return (
        f"dice={dice_str}, score O={decision.score_o} X={decision.score_x}, "
        f"match={match_str}, candidates={len(decision.candidate_moves)}"
    )


def build_xg_tab_body(file_paths: List[Path]) -> str:
    """HTML for the ".xg / .xgp gallery" tab (no <html>/<style> wrapper)."""
    sections: List[str] = []
    summary_rows: List[str] = []
    position_counter = 0  # Stable across files; used to mint anchor ids.

    with tempfile.TemporaryDirectory() as tmp:
        gen = CardGenerator(Path(tmp))
        gen.settings.max_moves = MAX_MOVES_TO_SHOW

        for fp in file_paths:
            try:
                pinned = find_pinned_position(fp)
                other = pick_interesting_positions(fp)
                # Drop other picks that duplicate a pinned position.
                pinned_keys = {p.decision.xgid for p in pinned if p.decision.xgid}
                other = [p for p in other if p.decision.xgid not in pinned_keys]
                # Pinned first, then enough heuristic picks to reach the cap.
                picks = (pinned + other)[:MAX_POSITIONS_PER_FILE + len(pinned)]
            except Exception as exc:  # noqa: BLE001
                sections.append(
                    f'<section class="file"><h2>{fp.name}</h2>'
                    f'<p class="error">Parse error: {exc}</p></section>'
                )
                continue

            if not picks:
                continue

            file_blocks: List[str] = []
            for i, pick in enumerate(picks, start=1):
                d = pick.decision
                position_counter += 1
                anchor = f"pos-{position_counter}"
                back_html = render_back(gen, d)
                tier_summary = ", ".join(
                    f"{(m.analysis_level or '?')}" for m in d.candidate_moves[:MAX_MOVES_TO_SHOW]
                )
                summary_rows.append(
                    f'<tr><td>{fp.name}</td>'
                    f'<td><a href="#{anchor}">{format_metadata_line(d)}</a></td>'
                    f'<td>{pick.why}</td><td>{tier_summary}</td></tr>'
                )
                file_blocks.append(f'''
                <article class="position" id="{anchor}">
                    <header>
                        <h3>Position {i}: {pick.why}</h3>
                        <p class="meta">{format_metadata_line(d)}</p>
                        <p class="xgid">XGID: <code>{d.xgid or "—"}</code></p>
                    </header>
                    <div class="back-card-wrapper">
                        {back_html}
                    </div>
                </article>
                ''')

            sections.append(f'''
            <section class="file">
                <h2>{fp.name}</h2>
                {"".join(file_blocks)}
            </section>
            ''')

    summary_table = (
        '<table class="summary"><thead><tr>'
        '<th>File</th><th>Position</th><th>Reason</th><th>Tier labels (first 5)</th>'
        '</tr></thead><tbody>'
        + "".join(summary_rows)
        + '</tbody></table>'
    )

    return f"""
<p class="intro">
Each section shows back-card HTML produced by the real CardGenerator for
interesting positions in one .xg or .xgp file. Spot-check the per-move
"analysis level" badge (Rollout / Book / XG Roller variants / N-ply) and the
tier-then-error sort order.
</p>

<h2>Summary</h2>
{summary_table}

{"".join(sections)}
"""


def build_gnubg_tab_body(test_positions: List["GnubgCase"]) -> str:
    """HTML for the "GnuBG live-analysis comparison" tab.

    Runs each test position through gnubg-cli at the requested ply, then
    renders the back card alongside the raw GnuBG text output so a human can
    visually confirm the parsed/rendered table matches the source-of-truth
    GnuBG produced.
    """
    from ankigammon.parsers.gnubg_parser import GNUBGParser
    from ankigammon.utils.gnubg_analyzer import GNUBGAnalyzer
    from ankigammon.settings import Settings as _Settings

    settings = _Settings()
    gnubg_path = settings.gnubg_path
    if not gnubg_path or not Path(gnubg_path).exists():
        return (
            '<p class="error">GnuBG executable not found at '
            f'<code>{gnubg_path or "(unset)"}</code>. Configure the path in '
            'Settings or skip this tab.</p>'
        )

    sections: List[str] = []
    summary_rows: List[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        gen = CardGenerator(Path(tmp))
        gen.settings.max_moves = MAX_MOVES_TO_SHOW

        for i, case in enumerate(test_positions, start=1):
            anchor = f"gnubg-pos-{i}"
            print(f"  [{i}/{len(test_positions)}] Analyzing {case.label} at {case.ply}-ply...")
            try:
                analyzer = GNUBGAnalyzer(gnubg_path, analysis_ply=case.ply)
                raw_output, dtype = analyzer.analyze_position(case.xgid)
                decision = GNUBGParser.parse_analysis(raw_output, case.xgid, dtype)
                card = gen.generate_card(decision, i)
                back_html = card.get("back", "") if isinstance(card, dict) else ""
                # Trim the verbose GnuBG banner; keep the meaningful body.
                raw_trimmed = _trim_gnubg_output(raw_output)
                # Per-move parsed summary as a quick orientation table.
                parsed_rows = "".join(
                    f'<tr><td>{m.rank}</td><td>{m.notation}</td>'
                    f'<td>{m.equity:+.4f}</td>'
                    f'<td>{m.analysis_level or "—"}</td></tr>'
                    for m in decision.candidate_moves[:MAX_MOVES_TO_SHOW]
                )
                parsed_table = (
                    '<table class="parsed-moves"><thead><tr>'
                    '<th>Rank</th><th>Move</th><th>Equity</th><th>Level</th>'
                    '</tr></thead><tbody>'
                    + parsed_rows + '</tbody></table>'
                )
                tier_summary = ", ".join(
                    (m.analysis_level or "?")
                    for m in decision.candidate_moves[:MAX_MOVES_TO_SHOW]
                )
                summary_rows.append(
                    f'<tr><td><a href="#{anchor}">{case.label}</a></td>'
                    f'<td>{case.ply}-ply requested</td>'
                    f'<td>{dtype.value}</td>'
                    f'<td>{tier_summary}</td></tr>'
                )
                sections.append(f'''
<article class="position gnubg-pos" id="{anchor}">
    <header>
        <h3>{i}. {case.label}</h3>
        <p class="meta">Requested ply: {case.ply}. Decision type: {dtype.value}.
        Parsed {len(decision.candidate_moves)} candidate move(s).</p>
        <p class="xgid">XGID: <code>{case.xgid}</code></p>
    </header>
    <div class="gnubg-compare">
        <div class="gnubg-pane">
            <h4>Raw GnuBG output</h4>
            <pre class="gnubg-raw">{_html_escape(raw_trimmed)}</pre>
        </div>
        <div class="gnubg-pane">
            <h4>Parsed moves (drives the back card)</h4>
            {parsed_table}
            <h4 style="margin-top:14px">Rendered back card</h4>
            <div class="back-card-wrapper">{back_html}</div>
        </div>
    </div>
</article>
''')
            except Exception as exc:  # noqa: BLE001
                sections.append(
                    f'<article class="position gnubg-pos" id="{anchor}">'
                    f'<h3>{i}. {case.label}</h3>'
                    f'<p class="meta">XGID: <code>{case.xgid}</code></p>'
                    f'<p class="error">GnuBG run failed: {exc}</p>'
                    '</article>'
                )

    summary_table = (
        '<table class="summary"><thead><tr>'
        '<th>Position</th><th>Requested ply</th><th>Type</th>'
        '<th>Per-move levels (first 5)</th>'
        '</tr></thead><tbody>'
        + "".join(summary_rows)
        + '</tbody></table>'
    )

    return f"""
<p class="intro">
Each position below is fed as a bare XGID into <code>gnubg-cli.exe</code> at
the requested ply. The raw GnuBG text output (left) is the source of truth;
the parsed moves table and rendered back card (right) show what AnkiGammon
extracts from it. Watch for: per-move ply labels that match the
<code>Cubeful N-ply</code> prefix in the raw output, the played/best
ordering, and whether GnuBG's mixed-tier evaluation (top moves at higher
ply, screened tail at lower ply) is preserved.
</p>

<h2>Summary</h2>
{summary_table}

{"".join(sections)}
"""


def _html_escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )


def _trim_gnubg_output(raw: str) -> str:
    """Strip the noisy startup banner so the move table is the focus."""
    lines = raw.split("\n")
    # Drop everything before the first "Position ID:" line — that's where
    # the meaningful output starts.
    for i, ln in enumerate(lines):
        if "Position ID:" in ln:
            return "\n".join(lines[i:]).strip()
    return raw.strip()


@dataclass
class GnubgCase:
    """One row in the GnuBG comparison tab."""
    label: str          # short, human-readable position description
    xgid: str           # input to GnuBG
    ply: int            # requested analysis depth


def build_report(file_paths: List[Path], gnubg_cases: Optional[List["GnubgCase"]] = None) -> str:
    xg_body = build_xg_tab_body(file_paths)
    gnubg_body = build_gnubg_tab_body(gnubg_cases) if gnubg_cases else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>AnkiGammon — analysis-level badge sample report</title>
<style>
html {{ scroll-behavior: smooth; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #f6f6f6;
    color: #222;
    margin: 0;
    padding: 24px 32px;
    line-height: 1.5;
}}
h1 {{ font-size: 24px; margin: 0 0 8px 0; }}
.intro {{ color: #555; max-width: 80ch; }}
section.file {{
    background: white;
    border: 1px solid #ddd;
    border-radius: 8px;
    margin: 24px 0;
    padding: 16px 20px;
}}
section.file > h2 {{
    font-size: 18px;
    margin: 0 0 12px 0;
    color: #2a4d6e;
    border-bottom: 1px solid #eee;
    padding-bottom: 6px;
}}
article.position {{
    margin: 18px 0;
    padding: 12px;
    background: #fafafa;
    border: 1px solid #eee;
    border-radius: 6px;
    scroll-margin-top: 16px;
}}
article.position:target {{
    /* Briefly draws the eye when jumped to from the summary table. */
    animation: targetFlash 1.6s ease-out;
    border-color: #f39c12;
}}
@keyframes targetFlash {{
    from {{ background: #fff4d6; }}
    to   {{ background: #fafafa; }}
}}
article.position header h3 {{
    font-size: 15px;
    margin: 0 0 6px 0;
    color: #444;
}}
article.position .meta {{
    font-size: 13px;
    color: #777;
    margin: 2px 0;
}}
article.position .xgid {{
    font-size: 12px;
    color: #888;
    margin: 2px 0 10px 0;
}}
article.position code {{ background: #efefef; padding: 1px 4px; border-radius: 3px; }}
.back-card-wrapper {{
    background: white;
    border: 1px solid #ddd;
    border-radius: 4px;
    padding: 8px;
    overflow-x: auto;
}}
table.summary {{
    border-collapse: collapse;
    width: 100%;
    margin: 16px 0 24px 0;
    background: white;
    font-size: 13px;
}}
table.summary th, table.summary td {{
    border: 1px solid #ddd;
    padding: 6px 10px;
    text-align: left;
    vertical-align: top;
}}
table.summary th {{ background: #eef3f8; }}
table.summary a {{
    color: #1f5fa3;
    text-decoration: none;
    font-weight: 500;
}}
table.summary a:hover {{ text-decoration: underline; }}
.error {{ color: #c0392b; }}

/* Tab navigation */
.tab-nav {{
    display: flex;
    gap: 4px;
    margin: 12px 0 0 0;
    border-bottom: 2px solid #ccc;
}}
.tab-nav button {{
    background: #e8e8e8;
    border: 1px solid #ccc;
    border-bottom: none;
    padding: 8px 16px;
    cursor: pointer;
    font-size: 14px;
    border-radius: 6px 6px 0 0;
    color: #555;
}}
.tab-nav button.active {{
    background: white;
    color: #222;
    font-weight: 600;
    border-color: #ccc;
    margin-bottom: -2px;
    border-bottom: 2px solid white;
}}
.tab-pane {{ display: none; padding-top: 14px; }}
.tab-pane.active {{ display: block; }}

/* GnuBG comparison panes */
.gnubg-compare {{
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr);
    gap: 18px;
    align-items: start;
}}
.gnubg-pane h4 {{
    font-size: 13px;
    margin: 0 0 8px 0;
    color: #1f5fa3;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}}
pre.gnubg-raw {{
    background: #1e1e1e;
    color: #d4d4d4;
    padding: 12px;
    border-radius: 4px;
    overflow-x: auto;
    font-size: 11.5px;
    line-height: 1.4;
    max-height: 600px;
    overflow-y: auto;
    margin: 0;
}}
table.parsed-moves {{
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
    background: white;
    margin-bottom: 8px;
}}
table.parsed-moves th, table.parsed-moves td {{
    border: 1px solid #ddd;
    padding: 4px 8px;
}}
table.parsed-moves th {{ background: #eef3f8; }}

/* Inline the production card CSS so the back-card HTML renders correctly. */
{CARD_CSS}
</style>
</head>
<body>
<h1>Analysis-level badge sample report</h1>
<p class="intro" style="margin-bottom: 4px;">
Generated by <code>scripts/build_analysis_level_report.py</code>. Switch
between the .xg/.xgp gallery and the live-GnuBG comparison using the tabs
below.
</p>

<nav class="tab-nav">
    <button class="tab-btn active" data-tab="xg">XG / XGP files</button>
    <button class="tab-btn" data-tab="gnubg">GnuBG comparison</button>
</nav>

<div id="tab-xg" class="tab-pane active">
{xg_body}
</div>

<div id="tab-gnubg" class="tab-pane">
{gnubg_body if gnubg_body else '<p class="intro">GnuBG comparison disabled (no cases provided).</p>'}
</div>

<script>
(function () {{
    var buttons = document.querySelectorAll('.tab-btn');
    var panes = document.querySelectorAll('.tab-pane');
    buttons.forEach(function (btn) {{
        btn.addEventListener('click', function () {{
            buttons.forEach(function (b) {{ b.classList.remove('active'); }});
            panes.forEach(function (p) {{ p.classList.remove('active'); }});
            btn.classList.add('active');
            var target = document.getElementById('tab-' + btn.dataset.tab);
            if (target) target.classList.add('active');
        }});
    }});
    // If the URL hash points at an anchor inside a non-active tab, switch
    // to that tab on load so the deep link works.
    if (window.location.hash) {{
        var el = document.querySelector(window.location.hash);
        if (el) {{
            var pane = el.closest('.tab-pane');
            if (pane) {{
                var tabId = pane.id.replace(/^tab-/, '');
                var btn = document.querySelector('.tab-btn[data-tab="' + tabId + '"]');
                if (btn) btn.click();
                // Re-scroll after switching tabs.
                setTimeout(function () {{ el.scrollIntoView({{behavior:'smooth'}}); }}, 50);
            }}
        }}
    }}
}})();
</script>
</body>
</html>
"""


def select_xgp_samples() -> List[Path]:
    """Pick a small stratified sample of .xgp files covering each label.

    .xgp is a single-position export; one position per file. We bucket the
    available files by the most-common analysis_level on the first decision
    in each, then take up to one file per bucket so the report ends up with
    one Rollout example, one Book example, one 4-ply example, etc.
    """
    if not XGP_SAMPLE_DIR.exists():
        return []
    candidates = sorted(XGP_SAMPLE_DIR.glob("*.xgp"))
    by_label: Dict[str, Path] = {}
    for fp in candidates:
        try:
            decisions = XGBinaryParser.parse_file(str(fp))
        except Exception:
            continue
        if not decisions or not decisions[0].candidate_moves:
            continue
        # Dominant label in the first decision (small ties broken by order).
        labels = [m.analysis_level for m in decisions[0].candidate_moves
                  if m.analysis_level]
        if not labels:
            continue
        dominant = max(set(labels), key=labels.count)
        by_label.setdefault(dominant, fp)
        if len(by_label) >= MAX_XGP_SAMPLES:
            break
    return list(by_label.values())[:MAX_XGP_SAMPLES]


def default_gnubg_cases() -> List[GnubgCase]:
    """Curated XGIDs spanning opening / midgame / race / cube / bearoff,
    each at a deliberately chosen ply so the rendered tab shows a healthy
    mix of analysis-level badges (1-ply, 2-ply, 3-ply, 4-ply) and decision
    types (checker play + cube actions). The intent is to *visually* prove
    the gnubg_parser.py fix populates `analysis_level` correctly across
    GnuBG's tiered output (top moves at higher ply, screened tail lower).
    """
    return [
        # --- Opening rolls --------------------------------------------------
        GnubgCase(
            label="Opening: 31 (start of game, classic split/slot)",
            xgid="XGID=-b----E-C---eE---c-e----B-:0:0:1:31:0:0:0:7:10",
            ply=2,
        ),
        GnubgCase(
            label="Opening: 65 (lover's leap)",
            xgid="XGID=-b----E-C---eE---c-e----B-:0:0:1:65:0:0:0:7:10",
            ply=2,
        ),
        GnubgCase(
            label="Opening: 21 (tournament 7pt, score 1-0 — issue position)",
            xgid="XGID=-b----E-C---eE---c-e----B-:0:0:1:21:1:0:0:7:10",
            ply=3,
        ),
        # --- Midgame -------------------------------------------------------
        GnubgCase(
            label="Midgame: prime vs prime (5-3 roll, complex decision)",
            xgid="XGID=-aBCBBDCB----d----c-c-A--A:0:0:1:53:0:0:0:7:10",
            ply=2,
        ),
        GnubgCase(
            # Real position pulled from the Csaba match — both sides hold
            # advanced anchors, classic holding-game tension.
            label="Midgame: holding game (real position from match)",
            xgid="XGID=abaB-BC-B--AcB-a-c-dA---B-:1:-1:-1:21:1:0:0:7:8",
            ply=3,
        ),
        # --- Race ----------------------------------------------------------
        GnubgCase(
            label="Race: pure race, no contact",
            xgid="XGID=---BDDC-B-----b-bbbab-----:0:0:1:53:0:0:0:7:10",
            ply=1,  # races barely need plies; 1-ply screening is enough
        ),
        # --- Bearoff -------------------------------------------------------
        GnubgCase(
            label="Bearoff: contact bearoff (forced precision)",
            xgid="XGID=-BBBBBA-------------aaabba:0:0:1:64:0:0:0:7:10",
            ply=2,
        ),
        # --- Cube decisions ------------------------------------------------
        # XGID dice field "00" means "no dice rolled — cube action pending".
        # Real positions from the Csaba and USBGF matches.
        GnubgCase(
            label="Cube: initial double, 7pt match (centered cube)",
            xgid="XGID=-a--a-E-C---dE--ac-e----B-:0:0:1:00:0:0:0:7:8",
            ply=2,
        ),
        GnubgCase(
            label="Cube: contact midgame, 11pt match",
            xgid="XGID=-b---BD-B---eE---c-e----B-:0:0:-1:00:0:0:0:11:8",
            ply=3,
        ),
    ]


def main() -> None:
    file_paths = sorted(MATCH_FILES_DIR.glob("*.xg"))
    if not file_paths:
        print(f"No .xg files found in {MATCH_FILES_DIR}")
        return

    xgp_paths = select_xgp_samples()
    gnubg_cases = default_gnubg_cases()
    print(f"Building report from {len(file_paths)} .xg file(s), "
          f"{len(xgp_paths)} .xgp sample(s), and "
          f"{len(gnubg_cases)} live-GnuBG case(s):")
    for fp in file_paths:
        print(f"  - {fp.name}")
    for fp in xgp_paths:
        print(f"  - {fp.name} (xgp sample)")
    for case in gnubg_cases:
        print(f"  - GnuBG {case.ply}-ply: {case.label}")

    html = build_report(file_paths + xgp_paths, gnubg_cases=gnubg_cases)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"\nWrote report to {OUTPUT_PATH}")
    print(f"Open with: start {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
