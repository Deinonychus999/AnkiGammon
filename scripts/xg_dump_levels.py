"""Dump XG analysis-level metadata from .xg binary files.

Goal: figure out what EvalLevel.Level integers actually mean. The xgstruct.py
comments only say "see PLAYERLEVEL table" without giving the table. So we
brute-force the mapping by recording, for every candidate move in every
analyzed position across a collection of .xg files:

  * EvalLevel.Level          per-slot analysis depth, the field we want to label
  * rolled_out               whether RolloutIndexM[i] >= 0 for that slot
  * slot rank                position in DataMoves.Moves (0 = best by XG order)
  * MoveEntry.AnalyzeM       the position-level requested analyze depth
  * equity                   Eval[i][6]

Then we summarize: which Level numbers appear, how they correlate with
rollout flags, ranks, and the requested AnalyzeM. That's enough evidence to
choose human-readable labels instead of guessing.
"""

from __future__ import annotations

import argparse
import glob
import os
from collections import Counter, defaultdict
from typing import Iterable, List, Tuple

from ankigammon.thirdparty.xgdatatools import xgimport, xgstruct


def iter_move_entries(xg_path: str) -> Iterable[xgstruct.MoveEntry]:
    xg = xgimport.Import(xg_path)
    for segment in xg.getfilesegment():
        if segment.type != xgimport.Import.Segment.XG_GAMEFILE:
            continue
        segment.fd.seek(0)
        while True:
            try:
                rec = xgstruct.GameFileRecord(version=-1).fromstream(segment.fd)
            except Exception:
                break
            if rec is None:
                break
            if isinstance(rec, xgstruct.MoveEntry):
                yield rec


def collect_slot_rows(xg_paths: List[str]) -> List[dict]:
    rows: List[dict] = []
    for fn in xg_paths:
        try:
            for me in iter_move_entries(fn):
                if not me.DataMoves:
                    continue
                dm = me.DataMoves
                if not dm.EvalLevel:
                    continue
                n = min(me.NMoveEval, dm.NMoves)
                for i in range(n):
                    ri = me.RolloutIndexM[i] if me.RolloutIndexM else -1
                    rolled_out = ri is not None and ri >= 0
                    rows.append({
                        'file': os.path.basename(fn),
                        'slot': i,
                        'level': dm.EvalLevel[i].Level,
                        'rolled_out': rolled_out,
                        'rollout_idx': ri,
                        'analyze_m': me.AnalyzeM,
                        'equity': dm.Eval[i][6],
                        'played': bool(me.Played),
                        'n_moves': n,
                    })
        except Exception as exc:  # noqa: BLE001
            print(f"  skip {fn}: {exc}")
    return rows


def summarize(rows: List[dict]) -> None:
    by_level: dict[int, List[dict]] = defaultdict(list)
    for r in rows:
        by_level[r['level']].append(r)

    print(f"\nTotal slots: {len(rows)}")
    print(f"Distinct EvalLevel.Level values: {sorted(by_level.keys())}\n")

    header = (
        f"{'Level':>6}  {'Count':>6}  {'Rollout%':>9}  "
        f"{'Rank1%':>7}  {'AnalyzeM modes':<30}  {'eq mean':>9}"
    )
    print(header)
    print("-" * len(header))
    for lvl in sorted(by_level.keys()):
        bucket = by_level[lvl]
        count = len(bucket)
        ro_share = sum(r['rolled_out'] for r in bucket) / count
        rank1_share = sum(1 for r in bucket if r['slot'] == 0) / count
        am_counts = Counter(r['analyze_m'] for r in bucket)
        am_modes = ', '.join(f"{a}:{c}" for a, c in am_counts.most_common(3))
        eq_mean = sum(r['equity'] for r in bucket) / count
        print(
            f"{lvl:>6}  {count:>6}  {ro_share:>8.1%}  "
            f"{rank1_share:>6.1%}  {am_modes:<30}  {eq_mean:>+9.4f}"
        )


def cross_check_played_slot(rows: List[dict]) -> None:
    """For each position, find the level of slot 0 (XG's rank-1 best move) and
    contrast it with levels of lower-ranked slots. If slot 0 is consistently a
    given Level for a file, that's likely the 'primary' analysis depth.
    """
    by_file: dict[str, List[dict]] = defaultdict(list)
    for r in rows:
        by_file[r['file']].append(r)

    print("\nPer-file: distribution of levels at slot 0 vs slots 1+")
    print(f"{'file':<45}  {'slot0 levels':<30}  {'slot1+ levels'}")
    print('-' * 110)
    for fn, file_rows in sorted(by_file.items()):
        slot0 = Counter(r['level'] for r in file_rows if r['slot'] == 0)
        slotN = Counter(r['level'] for r in file_rows if r['slot'] > 0)
        s0 = ', '.join(f"{l}:{c}" for l, c in slot0.most_common(4))
        sN = ', '.join(f"{l}:{c}" for l, c in slotN.most_common(4))
        print(f"{fn[:45]:<45}  {s0:<30}  {sN}")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("paths", nargs="*", default=["match_files/*.xg"])
    args = p.parse_args()

    xg_paths: List[str] = []
    for pat in args.paths:
        xg_paths.extend(sorted(glob.glob(pat)))
    if not xg_paths:
        print("No .xg files matched.")
        return

    print(f"Scanning {len(xg_paths)} .xg file(s):")
    for fn in xg_paths:
        print(f"  - {fn}")

    rows = collect_slot_rows(xg_paths)
    summarize(rows)
    cross_check_played_slot(rows)


if __name__ == "__main__":
    main()
