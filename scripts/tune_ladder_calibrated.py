#!/usr/bin/env python3
"""Tune ladder using CALIBRATED ELO only. Never prunes ratings files."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
import chess_harness.bootstrap  # noqa: F401

from chess_harness.calibration_view import merge_calibration_ratings
from chess_harness.opponents import get_catalog

PATH = ROOT / "opponents.json"
MIN_GAP = 50
MAX_GAP = 100
MISSION_TOP = 1300
MISSION_BOTTOM = -600

SF_BASE = {
    "type": "stockfish_harness",
    "uci_elo": 1320,
    "skill_level": 0,
    "rating_source": "stockfish_harness",
}

ALWAYS_REMOVE = {
    "stockfish-handicap:noise4",
    "stockfish-handicap:noise6",
    "stockfish-handicap:noise15",
    "stockfish-handicap:noise20",
    "stockfish-handicap:noise25",
    "stockfish-handicap:noise28",
    "stockfish-handicap:noise32",
    "stockfish-handicap:depth4-noise10",
    "minimalchess-0.2",
    "minimalchess-0.3",
    "minimalchess-0.2:noise15",
    "minimalchess-0.2:noise30",
    "stockfish-handicap:blitz50",
    "stockfish-handicap:blitz100",
    "stockfish-handicap:blitz200",
    "stockfish-handicap:blitz350",
    "stockfish-handicap:blitz500",
    "stockfish-handicap:blitz800",
    "stockfish-handicap:depth6",
    "stockfish-handicap:depth8",
    "stockfish-handicap:depth10",
    "stockfish-handicap:depth12",
    "stockfish-handicap:depth14",
    "stockfish-handicap:depth16",
    "stockfish-handicap:depth18",
    "stockfish-handicap:reference",
    "patricia:500",
    "patricia:800",
    "patricia:1000",
    "patricia:1200",
    "toledo",
}

# Survive overlap clustering — well-calibrated anchors.
PROTECTED = {
    "stockfish:0",
    "stockfish-handicap:depth4",
    "stockfish-handicap:noise5",
    "stockfish-handicap:noise10",
    "stockfish-handicap:noise12",
    "stockfish-handicap:noise22",
    "stockfish-handicap:noise30",
    "stockfish-handicap:noise38",
    "stockfish-handicap:noise52",
    "stockfish-handicap:noise62",
    "random",
    "inverse-sf:exclude-top1",
    "inverse-sf:worst-d10",
}


def prio(oid: str) -> int:
    if oid in ("random", "stockfish:0"):
        return 1000
    if oid.startswith("minimalchess"):
        return 0
    if oid.startswith("inverse-sf"):
        return 1
    return 2


def calibrated_rungs() -> list[tuple[str, int, int]]:
    catalog = get_catalog()
    cal = merge_calibration_ratings(max_age_sec=None)
    rungs: list[tuple[str, int, int]] = []
    for opp in catalog.list_opponents():
        if not opp.enabled:
            continue
        if opp.type == "stockfish":
            if opp.id == "stockfish:0":
                rungs.append((opp.id, opp.elo, 0))
            continue
        row = cal.get(opp.id)
        if not row or int(row.get("games", 0)) == 0:
            continue
        elo = int(row["elo"])
        if MISSION_BOTTOM <= elo <= MISSION_TOP:
            rungs.append((opp.id, elo, int(row["games"])))
    rungs.sort(key=lambda x: -x[1])
    return rungs


def cluster_overlap_removals(rungs: list[tuple[str, int, int]]) -> set[str]:
    """In each tight band (span < MIN_GAP), keep protected or most games."""
    remove: set[str] = set()
    i = 0
    while i < len(rungs):
        band = [rungs[i]]
        j = i + 1
        while j < len(rungs):
            if any(b[1] - rungs[j][1] < MIN_GAP for b in band):
                band.append(rungs[j])
                j += 1
            else:
                break
        if len(band) > 1:
            protected_in_band = [r for r in band if r[0] in PROTECTED]
            if protected_in_band:
                for r in band:
                    if r[0] not in PROTECTED:
                        remove.add(r[0])
            else:
                keep_id = max(band, key=lambda r: (prio(r[0]), r[2]))[0]
                for r in band:
                    if r[0] != keep_id:
                        remove.add(r[0])
        i = j
    return remove


def active_rungs(rungs: list[tuple[str, int, int]], remove: set[str]) -> list[tuple[str, int, int]]:
    return [r for r in rungs if r[0] not in remove]


def find_gaps(rungs: list[tuple[str, int, int]]) -> list[dict]:
    out = []
    for i in range(len(rungs) - 1):
        hi_id, hi_elo, _ = rungs[i]
        lo_id, lo_elo, _ = rungs[i + 1]
        gap = hi_elo - lo_elo
        if gap > MAX_GAP:
            out.append(
                {
                    "high_id": hi_id,
                    "high_elo": hi_elo,
                    "low_id": lo_id,
                    "low_elo": lo_elo,
                    "gap": gap,
                    "target": (hi_elo + lo_elo) // 2,
                }
            )
    return out


def sf_noise(oid: str, noise: float, *, movetime_ms: int = 50, depth: int | None = None, note: str) -> dict:
    harness: dict = {"movetime_ms": movetime_ms, "random_move_pct": noise}
    label = f"{int(noise * 100)}% noise"
    if depth is not None:
        harness["depth"] = depth
        label = f"depth {depth} + {label}"
    return {
        "id": oid,
        "display_name": f"Stockfish 17.1 ({label})",
        **SF_BASE,
        "elo": 500,
        "rating_note": note,
        "harness": harness,
    }


def noise_pct(oid: str) -> float | None:
    m = re.search(r"noise(\d+)", oid)
    return int(m.group(1)) / 100.0 if m else None


def gap_fill_entry(gap: dict, existing: set[str]) -> dict | None:
    target = gap["target"]
    hi, lo = gap["high_id"], gap["low_id"]

    if lo.startswith("inverse-sf") and hi == "random":
        for pct in (0.94, 0.91, 0.88, 0.85):
            oid = f"stockfish-handicap:noise{int(pct * 100)}"
            if oid not in existing:
                return sf_noise(
                    oid, pct, movetime_ms=30, depth=1,
                    note=f"Uncalibrated gap fill ~{target} between {hi} and {lo}",
                )
        return None

    if (hi == "random" and lo == "inverse-sf:exclude-top1") or (
        hi == "inverse-sf:exclude-top1" and lo == "inverse-sf:worst-d10"
    ):
        for pct in (0.96, 0.93, 0.90, 0.87):
            oid = f"stockfish-handicap:noise{int(pct * 100)}"
            if oid not in existing:
                return sf_noise(
                    oid, pct, movetime_ms=25, depth=1,
                    note=f"Uncalibrated gap fill ~{target} between {hi} and {lo}",
                )

    hp, lp = noise_pct(hi), noise_pct(lo)
    if hp is not None and lp is not None and hp > lp:
        for mid in (round((hp + lp) / 2, 2), round((hp * 0.66 + lp * 0.34), 2)):
            n = int(round(mid * 100))
            oid = f"stockfish-handicap:noise{n}"
            if oid not in existing and 1 <= n <= 99:
                return sf_noise(
                    oid, mid,
                    movetime_ms=30 if n >= 70 else 50,
                    depth=1 if n >= 70 else None,
                    note=f"Uncalibrated gap fill ~{target} ({hi} {gap['high_elo']} → {lo} {gap['low_elo']})",
                )

    for n in (7, 8, 13, 16, 19, 21, 24, 27, 33, 41, 46, 55, 65, 72, 78, 83):
        oid = f"stockfish-handicap:noise{n}"
        if oid not in existing:
            return sf_noise(
                oid, n / 100.0,
                movetime_ms=30 if n >= 70 else 50,
                depth=1 if n >= 70 else None,
                note=f"Uncalibrated gap fill ~{target} between {hi} and {lo}",
            )
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    rungs = calibrated_rungs()
    rungs_for_cluster = [r for r in rungs if r[0] not in ALWAYS_REMOVE]
    remove = cluster_overlap_removals(rungs_for_cluster) | ALWAYS_REMOVE
    # Drop inverse modes not in protected keep pair (except gap fills later).
    for oid, _, _ in rungs:
        if oid.startswith("inverse-sf") and oid not in PROTECTED:
            remove.add(oid)

    to_add: list[dict] = []
    existing = {o["id"] for o in json.loads(PATH.read_text())["opponents"]}

    for _ in range(12):
        gaps = find_gaps(active_rungs(rungs, remove))
        if not gaps:
            break
        added = False
        for gap in gaps:
            entry = gap_fill_entry(gap, existing | {e["id"] for e in to_add} | remove)
            if entry and entry["id"] not in existing:
                to_add.append(entry)
                existing.add(entry["id"])
                added = True
                break
        if not added:
            break

    remaining = find_gaps(active_rungs(rungs, remove))

    if args.dry_run:
        kept = active_rungs(rungs, remove)
        print(json.dumps({
            "remove_count": len(remove),
            "remove": sorted(remove),
            "add": [e["id"] for e in to_add],
            "kept_calibrated": [(a, b, c) for a, b, c in kept],
            "remaining_gaps": remaining,
        }, indent=2))
        return 0

    data = json.loads(PATH.read_text(encoding="utf-8"))
    opponents = [o for o in data["opponents"] if o["id"] not in remove]
    idx = next(i for i, o in enumerate(opponents) if o["id"] == "stockfish:0")
    for entry in to_add:
        if entry["id"] not in {o["id"] for o in opponents}:
            opponents.insert(idx, entry)
            idx += 1
    data["opponents"] = opponents
    PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    print(f"Removed {len(remove)} catalog entries (ratings/history untouched)")
    print(f"Added {len(to_add)} uncalibrated gap fillers (elo=500 until calibrated)")
    for e in to_add:
        print(f"  + {e['id']}")
    print(f"Remaining gaps > {MAX_GAP}: {len(remaining)}")
    for g in remaining:
        print(f"  {g['gap']}  {g['high_id']} -> {g['low_id']}")
    return 1 if remaining else 0


if __name__ == "__main__":
    raise SystemExit(main())
