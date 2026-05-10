"""Dump all fields of Move and Cube entries from .xgp files to find which
field distinguishes a 'move-xgp' from a 'cube-xgp'.

Usage:
    python scripts/dump_xgp_fields.py <file.xgp> [<file2.xgp> ...]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ankigammon.thirdparty.xgdatatools import xgimport, xgstruct


def summarize_entry(entry, entry_name: str) -> dict:
    """Return flat dict of scalar/short fields (skip big arrays)."""
    out = {"_type": entry_name}
    for k, v in entry.items():
        if k in ("PositionI", "PositionEnd", "PositionTutor", "Position", "DataMoves", "Doubled", "Moves"):
            if k == "Doubled" and v is not None:
                d = {}
                for dk, dv in v.items():
                    if dk == "Pos":
                        d["Pos_nonzero"] = sum(1 for x in (dv or []) if x != 0)
                    elif dk in ("Eval", "EvalDouble"):
                        d[dk + "_nonzero"] = sum(1 for x in (dv or []) if x != 0)
                    elif isinstance(dv, (int, float, bool, str)) or dv is None:
                        d[dk] = dv
                out["Doubled"] = d
            elif v is None:
                out[k] = None
            elif k in ("PositionI", "PositionEnd", "PositionTutor", "Position"):
                out[k + "_nonzero"] = sum(1 for x in (v or []) if x != 0)
            elif k == "Moves":
                out["Moves_nonzero"] = sum(1 for x in (v or []) if x != 0)
            elif k == "DataMoves" and v is not None:
                out["DataMoves_NMoves"] = getattr(v, "NMoves", None)
        elif isinstance(v, (int, float, bool, str)) or v is None:
            out[k] = v
        elif isinstance(v, (tuple, list)) and len(v) <= 8:
            out[k] = list(v)
    return out


def dump_file(path: Path):
    print(f"\n{'='*70}")
    print(f"FILE: {path.name}  (size={path.stat().st_size} bytes)")
    print('='*70)
    try:
        xg_import = xgimport.Import(str(path))
        file_version = -1
        entries = []
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
                    entries.append(("HeaderMatch", {k: v for k, v in record.items()
                                                    if isinstance(v, (int, float, bool, str)) or v is None}))
                elif isinstance(record, xgstruct.HeaderGameEntry):
                    entries.append(("HeaderGame", {k: v for k, v in record.items()
                                                   if isinstance(v, (int, float, bool, str)) or v is None}))
                elif isinstance(record, xgstruct.MoveEntry):
                    entries.append(("MoveEntry", summarize_entry(record, "Move")))
                elif isinstance(record, xgstruct.CubeEntry):
                    entries.append(("CubeEntry", summarize_entry(record, "Cube")))
                else:
                    entries.append((type(record).__name__, {}))
        print(f"Total entries: {len(entries)}")
        print(f"Entry types in order: {[e[0] for e in entries]}\n")
        for name, fields in entries:
            if name not in ("MoveEntry", "CubeEntry"):
                continue
            print(f"--- {name} ---")
            for k in sorted(fields.keys()):
                v = fields[k]
                if k == "Doubled" and isinstance(v, dict):
                    print(f"  Doubled:")
                    for dk in sorted(v.keys()):
                        print(f"    {dk} = {v[dk]}")
                else:
                    print(f"  {k} = {v}")
            print()
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback; traceback.print_exc()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "files",
        nargs="+",
        type=Path,
        help="One or more .xgp files to inspect",
    )
    args = parser.parse_args()
    for path in args.files:
        if not path.is_file():
            print(f"WARNING: not a file, skipping: {path}", file=sys.stderr)
            continue
        dump_file(path)
