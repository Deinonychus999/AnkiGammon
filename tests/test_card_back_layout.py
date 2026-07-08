"""Structural tests for the responsive two-column card back (issue #49).

The wide-screen CSS grid keys off three markup contracts in _generate_back:
the .two-col marker on .card-back, board + metadata inside .back-main, and
answer/note/analysis inside .back-side, with matrices and source info as
direct children of .card-back. These tests pin that structure across the
variant matrix (cube/checker x static/interactive x MCQ on/off) using real
decisions parsed from a sample match, so animation and MCQ scripts are
exercised with legal moves.
"""

import os
import tempfile
from html.parser import HTMLParser
from pathlib import Path

import pytest

from ankigammon.anki.card_generator import CardGenerator
from ankigammon.models import DecisionType
from ankigammon.parsers.xg_binary_parser import XGBinaryParser

MATCH_FILE = os.path.join(
    os.path.dirname(__file__), "..", "match_files",
    "2025-11-02#49733 Csaba Daday-Lorenzo Pacini.xg",
)


class _AncestryParser(HTMLParser):
    """Records, for each element, the classes/ids of its open ancestors."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []  # (tag, classes, id) of open elements
        # (classes, id, ancestor_markers) per element seen
        self.elements = []

    def _record(self, attrs):
        attrs = dict(attrs)
        classes = set((attrs.get("class") or "").split())
        elem_id = attrs.get("id")
        markers = set()
        for _tag, anc_classes, anc_id in self.stack:
            markers |= anc_classes
            if anc_id:
                markers.add(f"#{anc_id}")
        self.elements.append((classes, elem_id, markers))
        return classes, elem_id

    def handle_starttag(self, tag, attrs):
        classes, elem_id = self._record(attrs)
        self.stack.append((tag, classes, elem_id))

    def handle_startendtag(self, tag, attrs):
        # Self-closing (e.g. SVG <circle/>): record, never push
        self._record(attrs)

    def handle_endtag(self, tag):
        # Pop through any unclosed void tags to the matching open tag
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                return

    def ancestors_of(self, *, cls=None, elem_id=None):
        """Ancestor markers of the first element with the class or id."""
        for classes, eid, markers in self.elements:
            if cls is not None and cls in classes:
                return markers
            if elem_id is not None and eid == elem_id:
                return markers
        return None


def _parse(back_html: str) -> _AncestryParser:
    parser = _AncestryParser()
    parser.feed(back_html)
    return parser


@pytest.fixture(scope="module")
def decisions():
    parser = XGBinaryParser()
    return parser.parse_file(MATCH_FILE)


@pytest.fixture(scope="module")
def checker_decision(decisions):
    for d in decisions:
        if (d.decision_type == DecisionType.CHECKER_PLAY
                and d.dice and len(d.candidate_moves) >= 3):
            return d
    pytest.skip("no suitable checker decision in sample match")


@pytest.fixture(scope="module")
def cube_decision(decisions):
    for d in decisions:
        if d.decision_type == DecisionType.CUBE_ACTION and d.candidate_moves:
            return d
    pytest.skip("no suitable cube decision in sample match")


def _back(decision, **gen_kwargs) -> str:
    with tempfile.TemporaryDirectory() as tmpdir:
        gen = CardGenerator(Path(tmpdir), **gen_kwargs)
        return gen.generate_card(decision)["back"]


def _assert_two_col_contract(back_html: str, *, board_marker: str):
    assert '<div class="card-back two-col">' in back_html
    tree = _parse(back_html)

    board_ancestors = tree.ancestors_of(**(
        {"elem_id": board_marker[1:]} if board_marker.startswith("#")
        else {"cls": board_marker}
    ))
    assert board_ancestors is not None, f"{board_marker} missing from back"
    assert "back-main" in board_ancestors
    assert "back-side" not in board_ancestors

    metadata_ancestors = tree.ancestors_of(cls="metadata")
    assert metadata_ancestors is not None and "back-main" in metadata_ancestors

    source_ancestors = tree.ancestors_of(cls="source-info")
    assert source_ancestors is not None
    assert "two-col" in source_ancestors
    assert "back-side" not in source_ancestors and "back-main" not in source_ancestors


class TestBackLayoutStructure:

    def test_cube_static(self, cube_decision):
        back = _back(cube_decision, show_options=False, interactive_moves=False)
        _assert_two_col_contract(back, board_marker="position-svg")
        tree = _parse(back)
        assert "back-side" in tree.ancestors_of(cls="answer")
        assert "back-side" in tree.ancestors_of(cls="analysis-container")

    def test_cube_mcq(self, cube_decision):
        back = _back(cube_decision, show_options=True, interactive_moves=False)
        _assert_two_col_contract(back, board_marker="position-svg")
        tree = _parse(back)
        assert "back-side" in tree.ancestors_of(elem_id="mcq-feedback")
        assert "back-side" in tree.ancestors_of(elem_id="mcq-standard-answer")

    def test_checker_static_with_note(self, checker_decision):
        checker_decision.note = "Remember: prime before you attack."
        try:
            back = _back(checker_decision, show_options=False,
                         interactive_moves=False)
        finally:
            checker_decision.note = None
        _assert_two_col_contract(back, board_marker="position-svg")
        tree = _parse(back)
        assert "back-side" in tree.ancestors_of(cls="note-section")
        assert "back-side" in tree.ancestors_of(cls="moves-table")

    def test_checker_interactive_mcq(self, checker_decision):
        back = _back(checker_decision, show_options=True, interactive_moves=True)
        _assert_two_col_contract(back, board_marker="#animated-board")
        tree = _parse(back)
        assert "back-side" in tree.ancestors_of(elem_id="mcq-feedback")
        # The moves table must stay a real <table> (MCQ JS uses row.cells)
        assert "<table" in back and 'class="moves-table' in back
        # Animation scripts still emitted after the layout change
        assert "getCheckersAtPoint" in back

    def test_narrow_dom_order_unchanged(self, cube_decision):
        """Stacked (narrow) rendering relies on document order: board,
        metadata, answer, analysis, source info."""
        back = _back(cube_decision, show_options=False, interactive_moves=False)
        indexes = [back.index('class="position-svg'),
                   back.index('class="metadata"'),
                   back.index('class="answer"'),
                   back.index('class="source-info"')]
        assert indexes == sorted(indexes)
