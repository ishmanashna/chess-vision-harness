#!/usr/bin/env python3
"""Apply ladder-coverage-plan catalog changes to opponents.json."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "opponents.json"

DISABLE_IDS = {
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
    "minimalchess-0.2",
    "minimalchess-0.3",
    "toledo",
    "patricia:800",
    "patricia:1000",
    "patricia:1200",
}

SF_HARNESS_BASE = {
    "display_name": "Stockfish 17.1",
    "type": "stockfish_harness",
    "uci_elo": 1320,
    "skill_level": 0,
    "rating_source": "stockfish_harness",
}

NEW_SF_HARNESS = [
    ("stockfish-handicap:noise3", 1250, 0.03, "3% random-move noise — upper ladder"),
    ("stockfish-handicap:noise4", 1220, 0.04, "4% random-move noise — upper ladder"),
    ("stockfish-handicap:noise6", 1180, 0.06, "6% random-move noise — upper ladder"),
    ("stockfish-handicap:noise17", 820, 0.17, "17% random-move noise — mid ladder"),
    ("stockfish-handicap:noise22", 720, 0.22, "22% random-move noise — mid ladder"),
    ("stockfish-handicap:noise28", 620, 0.28, "28% random-move noise — mid ladder"),
    ("stockfish-handicap:noise30", 480, 0.30, "30% random-move noise — lower ladder"),
    ("stockfish-handicap:noise32", 520, 0.32, "32% random-move noise — mid ladder"),
    ("stockfish-handicap:noise36", 460, 0.36, "36% random-move noise — lower ladder"),
    ("stockfish-handicap:noise38", 420, 0.38, "38% random-move noise — lower ladder"),
]

INVERSE_ENTRIES = [
    ("inverse-sf:exclude-top1", 300, "exclude_top1", 10, "~300 ELO"),
    ("inverse-sf:exclude-top2", 200, "exclude_top2", 10, "~200 ELO"),
    ("inverse-sf:second-worst", 100, "second_worst", 10, "~100 ELO"),
    ("inverse-sf:exclude-top3", 0, "exclude_top3", 10, "~0 ELO"),
    ("inverse-sf:bottom-half", -100, "bottom_half", 10, "~−100 ELO"),
    ("inverse-sf:bottom5", -200, "bottom5", 10, "~−200 ELO"),
    ("inverse-sf:worst-d8", -300, "worst", 8, "~−300 ELO"),
    ("inverse-sf:worst-d10", -400, "worst", 10, "~−400 ELO"),
    ("inverse-sf:worst-d12", -500, "worst", 12, "~−500 ELO"),
    ("inverse-sf:worst-d14", -600, "worst", 14, "~−600 ELO"),
]

MC_HARNESS = [
    ("minimalchess-0.2:noise15", 850, 0.15, "Backup ~850 if SF noise17 overlaps"),
    ("minimalchess-0.2:noise30", 500, 0.30, "Backup ~500 if SF noise30 overlaps"),
]


def sf_harness_entry(oid: str, elo: int, noise: float, note: str) -> dict:
    return {
        "id": oid,
        **SF_HARNESS_BASE,
        "display_name": f"Stockfish 17.1 ({int(noise * 100)}% noise)",
        "elo": elo,
        "rating_note": f"Stockfish skill 0 with {int(noise * 100)}% random-move noise — {note}",
        "harness": {"movetime_ms": 50, "random_move_pct": noise},
    }


def inverse_entry(oid: str, elo: int, mode: str, depth: int, note: str) -> dict:
    label = oid.split(":", 1)[-1].replace("-", " ")
    return {
        "id": oid,
        "display_name": f"Inverse SF ({label})",
        "type": "inverse_sf",
        "elo": elo,
        "rating_source": "inverse_sf",
        "rating_note": f"Stockfish eval inverse mode {mode} depth {depth} — target {note}",
        "inverse": {"mode": mode, "depth": depth, "movetime_ms": 100},
    }


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


def main() -> None:
    data = json.loads(PATH.read_text(encoding="utf-8"))
    opponents = data["opponents"]
    by_id = {o["id"]: o for o in opponents}

    for oid in DISABLE_IDS:
        if oid in by_id:
            by_id[oid]["enabled"] = False

    if "stockfish-handicap:depth4" in by_id:
        by_id["stockfish-handicap:depth4"]["harness"] = {
            "depth": 2,
            "movetime_ms": 15,
        }
        by_id["stockfish-handicap:depth4"]["rating_note"] = (
            "Stockfish skill 0 depth 2 — retuned for low ladder"
        )

    if "stockfish-handicap:depth4-noise10" in by_id:
        by_id["stockfish-handicap:depth4-noise10"]["harness"] = {
            "depth": 2,
            "movetime_ms": 15,
            "random_move_pct": 0.1,
        }
        by_id["stockfish-handicap:depth4-noise10"]["display_name"] = (
            "Stockfish 17.1 (depth 2 + 10% noise)"
        )

    existing_ids = set(by_id)
    insert_before = "stockfish:0"
    insert_idx = next(
        i for i, o in enumerate(opponents) if o["id"] == insert_before
    )

    new_entries = []
    for args in NEW_SF_HARNESS:
        oid = args[0]
        if oid not in existing_ids:
            new_entries.append(sf_harness_entry(*args))

    for args in INVERSE_ENTRIES:
        oid = args[0]
        if oid not in existing_ids:
            new_entries.append(inverse_entry(*args))

    for args in MC_HARNESS:
        oid = args[0]
        if oid not in existing_ids:
            new_entries.append(mc_harness_entry(*args))

    if new_entries:
        opponents[insert_idx:insert_idx] = new_entries

    data["rating_source"]["inverse_sf"] = (
        "Stockfish full-strength eval + inverse move selection — calibrate effective ELO"
    )
    data["rating_source"]["uci_harness"] = (
        "UCI engine + play harness (depth, movetime, noise) — calibrate effective ELO"
    )

    PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Updated {PATH.name}: disabled {len(DISABLE_IDS)}, added {len(new_entries)} opponents")


if __name__ == "__main__":
    main()
