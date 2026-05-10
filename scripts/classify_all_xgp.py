"""Scan every .xgp file in a folder and classify by entry structure + key
discriminator fields. Goal: find the one field that reliably distinguishes
move-xgp from cube-xgp.

Usage:
    python scripts/classify_all_xgp.py <folder>

Example (XG's default save location on Windows):
    python scripts/classify_all_xgp.py "%USERPROFILE%/Documents/eXtremeGammon"
"""
import argparse
import sys
from pathlib import Path
from collections import Counter, defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ankigammon.thirdparty.xgdatatools import xgimport, xgstruct


def inspect(path: Path):
    """Return dict with key features of the file's entries, or None on error."""
    try:
        xg_import = xgimport.Import(str(path))
        file_version = -1
        has_move = False
        has_cube = False
        cube_flagdouble = None
        cube_level = None
        cube_analyzec = None
        cube_errcube = None
        move_analyzem = None
        move_nmoves = None
        move_errmove = None
        move_datamoves_nmoves = None
        for segment in xg_import.getfilesegment():
            if segment.type != xgimport.Import.Segment.XG_GAMEFILE:
                continue
            segment.fd.seek(0)
            while True:
                record = xgstruct.GameFileRecord(version=file_version).fromstream(segment.fd)
                if record is None:
                    break
                if isinstance(record, xgstruct.HeaderMatchEntry):
                    file_version = record.Version
                elif isinstance(record, xgstruct.CubeEntry):
                    has_cube = True
                    cube_analyzec = record.get("AnalyzeC")
                    cube_errcube = record.get("ErrCube")
                    doubled = record.get("Doubled")
                    if doubled:
                        cube_flagdouble = doubled.get("FlagDouble")
                        cube_level = doubled.get("Level")
                elif isinstance(record, xgstruct.MoveEntry):
                    has_move = True
                    move_analyzem = record.get("AnalyzeM")
                    move_nmoves = record.get("NMoveEval")
                    move_errmove = record.get("ErrMove")
                    dm = record.get("DataMoves")
                    if dm is not None:
                        move_datamoves_nmoves = getattr(dm, "NMoves", None)
        return {
            "has_move": has_move,
            "has_cube": has_cube,
            "cube_flagdouble": cube_flagdouble,
            "cube_level": cube_level,
            "cube_analyzec": cube_analyzec,
            "cube_errcube": cube_errcube,
            "move_analyzem": move_analyzem,
            "move_nmoves": move_nmoves,
            "move_errmove": move_errmove,
            "move_datamoves_nmoves": move_datamoves_nmoves,
        }
    except Exception as e:
        return {"error": str(e)}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "folder",
        type=Path,
        help="Folder containing .xgp files to classify",
    )
    args = parser.parse_args()
    if not args.folder.is_dir():
        sys.exit(f"Not a directory: {args.folder}")

    files = sorted(args.folder.glob("*.xgp"))
    print(f"Found {len(files)} .xgp files in {args.folder}\n")

    structure_counts = Counter()
    # Track distinct tuples of discriminator fields per structure type
    structures = defaultdict(lambda: defaultdict(list))

    errors = 0
    for f in files:
        info = inspect(f)
        if "error" in info:
            errors += 1
            continue
        key = (info["has_move"], info["has_cube"])
        structure_counts[key] += 1
        # Build a "signature" of the cube entry's state (rounded/bucketed)
        sig = (
            info["cube_flagdouble"],
            info["cube_level"],
            info["cube_analyzec"],
            "ErrCube=-1000" if info["cube_errcube"] == -1000.0 else f"ErrCube={info['cube_errcube']}",
            info["move_analyzem"] if info["has_move"] else None,
            info["move_datamoves_nmoves"] if info["has_move"] else None,
        )
        structures[key][sig].append(f.name)

    print(f"Errors: {errors}\n")
    print("Entry-presence breakdown:")
    for (hm, hc), count in structure_counts.most_common():
        label = f"move={hm}, cube={hc}"
        print(f"  {label}: {count} files")

    print()
    print("Signatures within each structure (sig = flagdouble, level, analyzeC, errcube, analyzeM, nmoves):")
    for (hm, hc), sigs in structures.items():
        print(f"\n  [move={hm}, cube={hc}]")
        for sig, names in sorted(sigs.items(), key=lambda kv: -len(kv[1])):
            example = names[0] if names else "?"
            print(f"    {sig}  ×{len(names)}   e.g. {example}")


if __name__ == "__main__":
    main()
