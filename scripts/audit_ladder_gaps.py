#!/usr/bin/env python3
"""Report ELO gaps > max_gap in the 1300 → −600 mission band."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python" / "src"))
import chess_harness.bootstrap  # noqa: F401

from chess_harness.calibration_view import ladder_elo_for_opponent, merge_calibration_ratings
from chess_harness.opponents import get_catalog


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit ladder ELO gaps")
    parser.add_argument("--top", type=int, default=1300)
    parser.add_argument("--bottom", type=int, default=-600)
    parser.add_argument("--max-gap", type=int, default=100)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    catalog = get_catalog()
    cal = merge_calibration_ratings(max_age_sec=None)

    rungs: list[tuple[str, int]] = []
    for opp in catalog.list_opponents():
        if not opp.enabled:
            continue
        if opp.type == "stockfish":
            if opp.id == "stockfish:0":
                rungs.append((opp.id, opp.elo))
            continue
        elo = ladder_elo_for_opponent(opp, cal)
        row = cal.get(opp.id)
        if not row or int(row.get("games", 0)) == 0:
            elo = opp.elo
        if args.bottom <= elo <= args.top:
            rungs.append((opp.id, elo))

    rungs.sort(key=lambda x: x[1], reverse=True)

    gaps = []
    for i in range(len(rungs) - 1):
        hi_id, hi_elo = rungs[i]
        lo_id, lo_elo = rungs[i + 1]
        gap = hi_elo - lo_elo
        if gap > args.max_gap:
            gaps.append(
                {
                    "high_id": hi_id,
                    "high_elo": hi_elo,
                    "low_id": lo_id,
                    "low_elo": lo_elo,
                    "gap": gap,
                }
            )

    if args.json:
        print(json.dumps({"rungs": rungs, "gaps": gaps}, indent=2))
        return 0

    print(f"Ladder rungs in [{args.bottom}, {args.top}] ({len(rungs)} active):\n")
    for oid, elo in rungs:
        print(f"  {elo:5d}  {oid}")

    print(f"\nGaps > {args.max_gap} ELO: {len(gaps)}")
    for g in gaps:
        print(
            f"  {g['gap']:4d}  {g['high_id']} ({g['high_elo']}) -> "
            f"{g['low_id']} ({g['low_elo']})"
        )
    return 1 if gaps else 0


if __name__ == "__main__":
    raise SystemExit(main())
