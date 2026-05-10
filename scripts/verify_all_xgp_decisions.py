"""Run the parser on every .xgp file in a folder and verify each produces
exactly 1 decision. Useful regression check after touching xg_binary_parser.

Usage:
    python scripts/verify_all_xgp_decisions.py <folder>
"""
import argparse
import logging
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.getLogger().setLevel(logging.ERROR)

from ankigammon.parsers.xg_binary_parser import XGBinaryParser


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "folder",
        type=Path,
        help="Folder containing .xgp files to verify",
    )
    args = parser.parse_args()
    if not args.folder.is_dir():
        sys.exit(f"Not a directory: {args.folder}")

    files = sorted(args.folder.glob("*.xgp"))

    counts: Counter = Counter()
    errors = []
    wrong_count = []
    for f in files:
        try:
            decisions = XGBinaryParser.parse_file(str(f))
            types = tuple(d.decision_type.name for d in decisions)
            counts[(len(decisions), types)] += 1
            if len(decisions) != 1:
                wrong_count.append((f.name, len(decisions), types))
        except Exception as e:
            errors.append((f.name, str(e)))

    print(f"Total files: {len(files)}")
    print(f"Errors: {len(errors)}")
    for name, err in errors[:5]:
        print(f"  {name}: {err}")

    print(f"\nDecision count distribution:")
    for (n, types), count in counts.most_common():
        print(f"  {n} decisions {types} — {count} files")

    if wrong_count:
        print(f"\nFiles with != 1 decision:")
        for name, n, types in wrong_count[:10]:
            print(f"  {name}: {n} decisions, types={types}")

    return 1 if errors or wrong_count else 0


if __name__ == "__main__":
    sys.exit(main())
