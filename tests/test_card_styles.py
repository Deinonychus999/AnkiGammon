"""Tests for the wide-screen two-column card CSS and its export wiring (issue #49)."""

import re
import tempfile
from pathlib import Path

from ankigammon.anki.card_styles import CARD_CSS, MODEL_NAME, get_card_css

WIDE_MEDIA_QUERY = "@media screen and (min-width: 1200px) and (min-height: 600.02px)"
MARKER_GUARD = ".card:has(.card-back.two-col)"


def _wide_block() -> str:
    """Extract the wide-screen media block (from the query to CSS end)."""
    start = CARD_CSS.index(WIDE_MEDIA_QUERY)
    return CARD_CSS[start:]


class TestWideLayoutCss:

    def test_wide_media_query_present(self):
        assert WIDE_MEDIA_QUERY in CARD_CSS

    def test_every_wide_rule_is_marker_gated(self):
        """The stylesheet is pushed onto ALL existing notes; every rule in
        the wide block must be gated on the .two-col marker so old notes'
        frozen HTML renders unchanged."""
        block = re.sub(r"/\*.*?\*/", "", _wide_block(), flags=re.S)
        # Each selector line (part before '{') must carry the :has() guard.
        selectors = re.findall(r"([^{}]+)\{", block.split(WIDE_MEDIA_QUERY, 1)[1])
        # Skip the property-only matches by only checking selector groups
        # that contain a class/element token.
        for group in selectors:
            for selector in group.split(","):
                selector = selector.strip()
                if not selector or ":" == selector[0]:
                    continue
                assert selector.startswith(MARKER_GUARD), (
                    f"un-gated selector in wide block: {selector!r}"
                )

    def test_wide_block_is_layout_only(self):
        """Color declarations here would silently beat the earlier
        .night_mode overrides by sheet order."""
        block = _wide_block()
        assert "color:" not in block
        assert "background" not in block

    def test_wide_block_grid_and_full_width_rows(self):
        block = _wide_block()
        assert "display: grid" in block
        assert "grid-column: 1 / -1" in block
        for cls in (".score-matrix", ".move-score-matrix",
                    ".cube-matrix-details", ".source-info"):
            assert cls in block

    def test_css_brace_balance(self):
        assert CARD_CSS.count("{") == CARD_CSS.count("}")

    def test_get_card_css_returns_card_css(self):
        assert get_card_css() == CARD_CSS


class TestExporterWiring:

    def test_apkg_model_css_contains_wide_layout(self):
        from ankigammon.anki.apkg_exporter import ApkgExporter

        exporter = ApkgExporter(output_dir=Path(tempfile.mkdtemp()))
        assert WIDE_MEDIA_QUERY in exporter.model.css

    def test_ankiconnect_styling_update_contains_wide_layout(self):
        from ankigammon.anki.ankiconnect import AnkiConnect

        calls = []

        def fake_invoke(self, action, **params):
            calls.append((action, params))
            if action == "modelNames":
                return [MODEL_NAME]
            if action == "modelFieldNames":
                # Contains XGID and AnalysisData so no field migration fires.
                return ["XGID", "Front", "Back", "AnalysisData"]
            return None

        client = AnkiConnect.__new__(AnkiConnect)
        client.invoke = fake_invoke.__get__(client)
        client.create_model()

        styling_calls = [p for a, p in calls if a == "updateModelStyling"]
        assert len(styling_calls) == 1
        assert WIDE_MEDIA_QUERY in styling_calls[0]["model"]["css"]

    def test_ankiconnect_create_model_contains_wide_layout(self):
        from ankigammon.anki.ankiconnect import AnkiConnect

        calls = []

        def fake_invoke(self, action, **params):
            calls.append((action, params))
            if action == "modelNames":
                return []  # No existing model -> createModel branch
            return None

        client = AnkiConnect.__new__(AnkiConnect)
        client.invoke = fake_invoke.__get__(client)
        client.create_model()

        create_calls = [p for a, p in calls if a == "createModel"]
        assert len(create_calls) == 1
        assert WIDE_MEDIA_QUERY in create_calls[0]["css"]
