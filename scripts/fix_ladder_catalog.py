#!/usr/bin/env python3
"""Fix catalog: drop high-ELO clutter, re-enable low inverse rungs, restore MinimalChess."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "config" / "opponents.json"

# Delete from catalog — historical ratings stay in elo_calibration/results/.
HIGH_ELO_REMOVE = {
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

# Mid-band overlap only — stay disabled, not deleted.
MID_OVERLAP_DISABLE = {
    "stockfish-handicap:noise4",
    "stockfish-handicap:noise6",
    "stockfish-handicap:noise15",
    "stockfish-handicap:noise20",
    "stockfish-handicap:noise25",
    "stockfish-handicap:noise28",
    "stockfish-handicap:noise32",
    "stockfish-handicap:depth4-noise10",
}

INVERSE_REENABLE = {
    "inverse-sf:exclude-top1",
    "inverse-sf:exclude-top2",
    "inverse-sf:second-worst",
    "inverse-sf:exclude-top3",
    "inverse-sf:bottom-half",
    "inverse-sf:worst-d8",
    "inverse-sf:worst-d10",
    "inverse-sf:worst-d12",
}

MC_ENTRIES = [
    {
        "id": "minimalchess-0.2",
        "display_name": "MinimalChess 0.2",
        "type": "uci",
        "elo": 909,
        "binary": "bin/opponents/minimalchess-0.2.exe",
        "rating_source": "ccrl",
        "ccrl_name": "MinimalChess 0.2 64-bit",
        "enabled": False,
    },
    {
        "id": "minimalchess-0.3",
        "display_name": "MinimalChess 0.3",
        "type": "uci",
        "elo": 1439,
        "binary": "bin/opponents/minimalchess-0.3/minimalchess-0.3.exe",
        "rating_source": "ccrl",
        "ccrl_name": "MinimalChess 0.3 64-bit",
        "enabled": False,
    },
    {
        "id": "minimalchess-0.2:noise15",
        "display_name": "MinimalChess 0.2 (15% noise)",
        "type": "uci_harness",
        "elo": 850,
        "binary": "bin/opponents/minimalchess-0.2.exe",
        "rating_source": "uci_harness",
        "rating_note": "Backup mid-ladder if SF noise17 overlaps",
        "harness": {"movetime_ms": 50, "random_move_pct": 0.15},
    },
    {
        "id": "minimalchess-0.2:noise30",
        "display_name": "MinimalChess 0.2 (30% noise)",
        "type": "uci_harness",
        "elo": 500,
        "binary": "bin/opponents/minimalchess-0.2.exe",
        "rating_source": "uci_harness",
        "rating_note": "Backup lower ladder if SF noise30 overlaps",
        "harness": {"movetime_ms": 50, "random_move_pct": 0.30},
    },
]


def main() -> None:
    data = json.loads(PATH.read_text(encoding="utf-8"))
    opponents = [o for o in data["opponents"] if o["id"] not in HIGH_ELO_REMOVE]
    by_id = {o["id"]: o for o in opponents}

    for oid in MID_OVERLAP_DISABLE:
        if oid in by_id:
            by_id[oid]["enabled"] = False

    for oid in INVERSE_REENABLE:
        if oid in by_id:
            by_id[oid].pop("enabled", None)

    for entry in MC_ENTRIES:
        if entry["id"] not in by_id:
            insert = next(i for i, o in enumerate(opponents) if o["id"] == "stockfish:0")
            opponents.insert(insert, entry)
            by_id[entry["id"]] = entry

    data["rating_source"]["uci_harness"] = (
        "UCI engine + play harness (depth, movetime, noise) — calibrate effective ELO"
    )
    data["opponents"] = opponents
    PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(
        f"Fixed catalog: removed {len(HIGH_ELO_REMOVE)} high-ELO clutter entries, "
        f"re-enabled {len(INVERSE_REENABLE)} inverse rungs, "
        f"MinimalChess harnesses present"
    )


if __name__ == "__main__":
    main()
