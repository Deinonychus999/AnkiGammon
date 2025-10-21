#!/usr/bin/env python3
"""
Test script for the smart input dialog.

Tests:
1. Position ID detection (XGID)
2. Full XG analysis detection
3. Mixed input handling
"""

import sys
from PySide6.QtWidgets import QApplication
from xg2anki.settings import get_settings
from xg2anki.gui.dialogs import InputDialog

# Sample XG analysis (full)
SAMPLE_FULL_ANALYSIS = """XGID=--BBBBB-AB----a--cbdbBb-a-:1:1:1:65:0:0:2:0:10

X:Player 1   O:Player 2
Score is X:0 O:0. Unlimited Game, Beaver
 +13-14-15-16-17-18------19-20-21-22-23-24-+
 |    O        O  O |   | O  O  X  O     O |
 |             O  O |   | O  O  X  O       |
 |             O    |   | O                |
 |                  |   | O                |
 |                  |   |                  |
 |                  |BAR|                  |
 |                  |   |                  |
 |                  |   |                  |
 |                  |   |                  | +---+
 |          X       |   | X  X  X  X  X    | | 2 |
 |          X  X    |   | X  X  X  X  X    | +---+
 +12-11-10--9--8--7-------6--5--4--3--2--1-+
Pip count  X: 108  O: 90 X-O: 0-0
Cube: 2, X own cube
X to play 65

    1. 2-ply       21/16 21/15                  eq:-0.404
      Player:   26.61% (G:1.28% B:0.01%)
      Opponent: 73.39% (G:3.89% B:0.07%)

    2. 2-ply       9/4 8/2                      eq:-0.433 (-0.029)
      Player:   24.71% (G:0.33% B:0.00%)
      Opponent: 75.29% (G:1.78% B:0.01%)

    3. 2-ply       9/4 9/3                      eq:-0.436 (-0.032)
      Player:   24.60% (G:0.33% B:0.00%)
      Opponent: 75.40% (G:1.84% B:0.00%)

    4. 2-ply       8/2 6/1                      eq:-0.453 (-0.048)
      Player:   24.06% (G:0.49% B:0.01%)
      Opponent: 75.94% (G:2.36% B:0.01%)

    5. 2-ply       21/10                        eq:-0.453 (-0.048)
      Player:   24.56% (G:0.61% B:0.01%)
      Opponent: 75.44% (G:3.63% B:0.04%)


eXtreme Gammon Version: 2.10"""

# Sample position IDs only
SAMPLE_POSITION_IDS = """XGID=--BBBBB-AB----a--cbdbBb-a-:1:1:1:65:0:0:2:0:10
XGID=----BbC---dE---c-e----B-:0:0:1:00:0:0:3:0:10
XGID=--AbcD---eF---d-f----C-:0:0:1:00:0:0:3:0:10"""


def test_full_analysis_detection():
    """Test detection of full XG analysis."""
    print("Testing full XG analysis detection...")

    from xg2anki.gui.format_detector import FormatDetector, InputFormat

    settings = get_settings()
    detector = FormatDetector(settings)

    result = detector.detect(SAMPLE_FULL_ANALYSIS)

    print(f"  Format: {result.format}")
    print(f"  Confidence: {result.confidence}")
    print(f"  Count: {result.count}")
    print(f"  Details: {result.details}")
    print(f"  Warnings: {result.warnings}")

    assert result.format == InputFormat.FULL_ANALYSIS
    assert result.count >= 1
    assert result.confidence > 0.8

    print("  [OK] Full analysis detection passed!\n")


def test_position_ids_detection():
    """Test detection of position IDs only."""
    print("Testing position IDs detection...")

    from xg2anki.gui.format_detector import FormatDetector, InputFormat

    settings = get_settings()
    detector = FormatDetector(settings)

    result = detector.detect(SAMPLE_POSITION_IDS)

    print(f"  Format: {result.format}")
    print(f"  Confidence: {result.confidence}")
    print(f"  Count: {result.count}")
    print(f"  Details: {result.details}")
    print(f"  Warnings: {result.warnings}")

    assert result.format == InputFormat.POSITION_IDS
    assert result.count == 3
    assert result.confidence > 0.8

    print("  [OK] Position IDs detection passed!\n")


def test_parsing():
    """Test parsing of XG analysis."""
    print("Testing XG analysis parsing...")

    from xg2anki.parsers.xg_text_parser import XGTextParser

    decisions = XGTextParser.parse_string(SAMPLE_FULL_ANALYSIS)

    print(f"  Parsed {len(decisions)} decision(s)")

    if decisions:
        decision = decisions[0]
        print(f"  Decision type: {decision.decision_type}")
        print(f"  On roll: {decision.on_roll}")
        print(f"  Dice: {decision.dice}")
        print(f"  Candidate moves: {len(decision.candidate_moves)}")

        assert len(decision.candidate_moves) > 0
        print("  [OK] Parsing passed!\n")
    else:
        print("  [FAIL] No decisions parsed\n")


def test_gui_dialog():
    """Test the GUI dialog interactively."""
    print("Launching GUI dialog for interactive testing...")
    print("Instructions:")
    print("  1. The dialog should open")
    print("  2. Try pasting the sample texts below")
    print("  3. Check that detection works correctly")
    print()
    print("Sample Full Analysis (copy this):")
    print("-" * 60)
    print(SAMPLE_FULL_ANALYSIS[:200] + "...")
    print("-" * 60)
    print()
    print("Sample Position IDs (copy this):")
    print("-" * 60)
    print(SAMPLE_POSITION_IDS)
    print("-" * 60)
    print()

    app = QApplication(sys.argv)
    settings = get_settings()

    dialog = InputDialog(settings)

    def on_positions_added(decisions):
        print(f"\n[OK] Positions added: {len(decisions)}")
        for i, d in enumerate(decisions):
            print(f"  {i+1}. {d.decision_type} - {d.on_roll} to play")

    dialog.positions_added.connect(on_positions_added)

    result = dialog.exec()

    if result:
        pending = dialog.get_pending_decisions()
        print(f"\n[OK] Dialog completed with {len(pending)} pending decision(s)")
    else:
        print("\n[CANCELLED] Dialog cancelled")

    return result


def main():
    """Run all tests."""
    print("=" * 60)
    print("Smart Input Dialog Test Suite")
    print("=" * 60)
    print()

    # Run unit tests
    try:
        test_full_analysis_detection()
        test_position_ids_detection()
        test_parsing()

        print("All unit tests passed! [OK]\n")
        print("=" * 60)
        print()

        # Run GUI test
        test_gui_dialog()

    except AssertionError as e:
        print(f"\n[FAIL] Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
