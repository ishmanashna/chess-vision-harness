#!/usr/bin/env python3
"""Prune opponents.json: Stockfish-only ladder, remove third-party engines, fill gaps."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "opponents.json"

# Remove entirely (not just disable).
REMOVE_IDS = {
    "patricia:500",
    "patricia:800",
    "patricia:1000",
    "patricia:1200",
    "toledo",
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
}

# Mid-band overlap — disable only (not low-ELO inverse rungs).
DISABLE_IDS = {
    "stockfish-handicap:noise4",
    "stockfish-handicap:noise6",
    "stockfish-handicap:noise15",
    "stockfish-handicap:noise20",
    "stockfish-handicap:noise25",
    "stockfish-handicap:noise28",
    "stockfish-handicap:noise32",
    "stockfish-handicap:depth4-noise10",
}

MC_HARNESS = [
    ("minimalchess-0.2:noise15", 850, 0.15, "Backup mid-ladder if SF noise17 overlaps"),
    ("minimalchess-0.2:noise30", 500, 0.30, "Backup lower ladder if SF noise30 overlaps"),
]


def mc_harness_entry(oid: str, elo: int, noise: float, note: str) -> dict:
    pct = int(noise * 100)
    return {
        "id": oid,
        "display_name": f"MinimalChess 0.2 ({pct}% noise)",
        "type": "uci_harness",
        "elo": elo,
        "binary": "bin/opponents/minimalchess-0.2.exe",
        "rating_source": "uci_harness",
        "rating_note": note,
        "harness": {"movetime_ms": 50, "random_move_pct": noise},
    }


SF_BASE = {
    "type": "stockfish_harness",
    "uci_elo": 1320,
    "skill_level": 0,
    "rating_source": "stockfish_harness",
}

NEW_NOISE = [
    # Upper-mid gap fillers (calibrated gaps noise5→noise10, noise10→noise12, noise30→noise36).
    ("stockfish-handicap:noise11", 1020, 0.11, 50, None, "11% noise — upper gap fill"),
    ("stockfish-handicap:noise14", 880, 0.14, 50, None, "14% noise — upper gap fill"),
    ("stockfish-handicap:noise26", 630, 0.26, 50, None, "26% noise — mid gap fill"),
    # Bridge noise38 (545) → inverse band (~160).
    ("stockfish-handicap:noise40", 400, 0.40, 50, None, "40% noise — mid gap fill"),
    ("stockfish-handicap:noise42", 350, 0.42, 50, None, "42% noise — mid gap fill"),
    ("stockfish-handicap:noise45", 300, 0.45, 50, None, "45% noise — mid gap fill"),
    ("stockfish-handicap:noise39", 475, 0.39, 50, None, "39% noise — bridge noise38→noise40"),
    ("stockfish-handicap:noise89", -485, 0.89, 30, 1, "89% noise + depth 1 — bridge noise86→noise92"),
    # Sub-random band (target below calibrated random ~60).
    ("stockfish-handicap:noise52", 30, 0.52, 30, 1, "52% noise + depth 1 — sub-random"),
    ("stockfish-handicap:noise58", -20, 0.58, 30, 1, "58% noise + depth 1 — sub-random"),
    ("stockfish-handicap:noise62", -60, 0.62, 30, 1, "62% noise + depth 1 — sub-random"),
    ("stockfish-handicap:noise68", -120, 0.68, 30, 1, "68% noise + depth 1 — sub-random"),
    ("stockfish-handicap:noise74", -200, 0.74, 30, 1, "74% noise + depth 1 — sub-random"),
    ("stockfish-handicap:noise80", -300, 0.80, 30, 1, "80% noise + depth 1 — sub-random"),
    ("stockfish-handicap:noise86", -420, 0.86, 30, 1, "86% noise + depth 1 — sub-random"),
    ("stockfish-handicap:noise92", -550, 0.92, 30, 1, "92% noise + depth 1 — sub-random"),
]

NEW_INVERSE = [
    ("inverse-sf:worst-d4", -80, "worst", 4, "~sub-random shallow worst"),
    ("inverse-sf:worst-d6", -180, "worst", 6, "~sub-random shallow worst"),
    ("inverse-sf:bottom5-d4", -250, "bottom5", 4, "~sub-random bottom-5 at depth 4"),
    ("inverse-sf:third-worst-d6", -350, "third_worst", 6, "~sub-random third-worst"),
]


def sf_noise_entry(oid: str, elo: int, noise: float, movetime_ms: int, depth, note: str) -> dict:
    harness: dict = {"movetime_ms": movetime_ms, "random_move_pct": noise}
    label = f"{int(noise * 100)}% noise"
    if depth is not None:
        harness["depth"] = depth
        label = f"depth {depth} + {label}"
    return {
        "id": oid,
        "display_name": f"Stockfish 17.1 ({label})",
        **SF_BASE,
        "elo": elo,
        "rating_note": f"Stockfish skill 0 — {note}",
        "harness": harness,
    }


def inverse_entry(oid: str, elo: int, mode: str, depth: int, note: str) -> dict:
    label = oid.split(":", 1)[-1].replace("-", " ")
    return {
        "id": oid,
        "display_name": f"Inverse SF ({label})",
        "type": "inverse_sf",
        "elo": elo,
        "rating_source": "inverse_sf",
        "rating_note": f"Inverse {mode} depth {depth} — {note}",
        "inverse": {"mode": mode, "depth": depth, "movetime_ms": 50},
    }


def main() -> None:
    data = json.loads(PATH.read_text(encoding="utf-8"))
    opponents = [o for o in data["opponents"] if o["id"] not in REMOVE_IDS]
    by_id = {o["id"]: o for o in opponents}

    for oid in DISABLE_IDS:
        if oid in by_id:
            by_id[oid]["enabled"] = False

    if "stockfish-handicap:depth4" in by_id:
        by_id["stockfish-handicap:depth4"]["harness"] = {"depth": 2, "movetime_ms": 15}

    existing = set(by_id)
    insert_idx = next(i for i, o in enumerate(opponents) if o["id"] == "stockfish:0")
    new_entries = []
    for args in NEW_NOISE:
        oid = args[0]
        if oid not in existing:
            new_entries.append(sf_noise_entry(*args))
    for args in NEW_INVERSE:
        oid = args[0]
        if oid not in existing:
            new_entries.append(inverse_entry(*args))
    for args in MC_HARNESS:
        oid = args[0]
        if oid not in existing:
            new_entries.append(mc_harness_entry(*args))

    if new_entries:
        opponents[insert_idx:insert_idx] = new_entries

    if "patricia" in data.get("rating_source", {}):
        del data["rating_source"]["patricia"]
    data["rating_source"]["uci_harness"] = (
        "UCI engine + play harness (depth, movetime, noise) — calibrate effective ELO"
    )
    data["rating_source"]["stockfish_harness"] = (
        "Stockfish UCI_Elo tier + play harness (depth, movetime, noise) — calibrate effective ELO"
    )
    data["rating_source"]["inverse_sf"] = (
        "Stockfish eval + inverse move selection — calibrate effective ELO (sub-random band)"
    )
    data["opponents"] = opponents

    PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(
        f"Pruned {PATH.name}: removed {len(REMOVE_IDS)}, disabled {len(DISABLE_IDS)}, "
        f"added {len(new_entries)} rungs"
    )


if __name__ == "__main__":
    main()
