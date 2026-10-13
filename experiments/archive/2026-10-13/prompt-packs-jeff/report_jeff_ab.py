#!/usr/bin/env python3
"""Per-seat W-D-L table for Jeff prompt-pack A/B."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "python" / "src"))

PACK_ORDER = ["j1", "j2", "j3", "j4", "j5"]
COMPARE_OPPONENTS = {
    "stockfish-handicap:noise38",
    "stockfish-handicap:noise30",
    "stockfish-handicap:noise72",
}


def _rows_from_snapshot(snap: Dict[str, Any]) -> List[Dict[str, Any]]:
    packs = snap.get("packs") or []
    if isinstance(packs, dict):
        out = []
        for pid, meta in packs.items():
            row = dict(meta) if isinstance(meta, dict) else {}
            row["id"] = pid
            out.append(row)
        return out
    return list(packs)


def _empty() -> Dict[str, Any]:
    return {
        "wins": 0,
        "draws": 0,
        "losses": 0,
        "finished": 0,
        "in_progress": 0,
        "mean_accuracy": None,
        "accuracies": [],
    }


def _from_pack_rows(snap: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    by = {pid: {"id": pid, **_empty()} for pid in PACK_ORDER}
    for row in _rows_from_snapshot(snap):
        pid = str(row.get("id") or "")
        if pid not in by:
            by[pid] = {"id": pid, **_empty()}
        by[pid]["wins"] = int(row.get("wins") or 0)
        by[pid]["draws"] = int(row.get("draws") or 0)
        by[pid]["losses"] = int(row.get("losses") or 0)
        by[pid]["finished"] = int(row.get("finished") or 0)
        by[pid]["in_progress"] = int(row.get("in_progress") or 0)
        by[pid]["mean_accuracy"] = row.get("mean_accuracy") or row.get("avg_accuracy")
        by[pid]["title"] = row.get("title") or pid
        by[pid].pop("accuracies", None)
    for row in by.values():
        row.pop("accuracies", None)
    return by


def _from_games(snap: Dict[str, Any], *, compare_only: bool) -> Dict[str, Dict[str, Any]]:
    by = {pid: {"id": pid, **_empty()} for pid in PACK_ORDER}
    games = snap.get("games") or []
    for g in games:
        pid = str(g.get("prompt_pack") or g.get("pack_id") or "")
        if not pid:
            continue
        if pid not in by:
            by[pid] = {"id": pid, **_empty()}
        opp = str(g.get("opponent_id") or g.get("opponent") or "")
        if compare_only and opp and opp not in COMPARE_OPPONENTS:
            continue
        status = str(g.get("status") or "")
        if status == "in_progress":
            by[pid]["in_progress"] += 1
            continue
        outcome = str(g.get("outcome") or g.get("agent_outcome") or "").lower()
        if outcome in {"win", "w"}:
            by[pid]["wins"] += 1
            by[pid]["finished"] += 1
        elif outcome in {"draw", "d"}:
            by[pid]["draws"] += 1
            by[pid]["finished"] += 1
        elif outcome in {"loss", "l"}:
            by[pid]["losses"] += 1
            by[pid]["finished"] += 1
        acc = g.get("accuracy") if g.get("accuracy") is not None else g.get("agent_accuracy")
        if acc is not None:
            by[pid]["accuracies"].append(float(acc))
    for pid, row in by.items():
        if row["accuracies"]:
            row["mean_accuracy"] = sum(row["accuracies"]) / len(row["accuracies"])
        del row["accuracies"]
    return by


def render(stats: Dict[str, Dict[str, Any]], *, compare_only: bool) -> str:
    lines = [
        "# Jeff A/B report",
        "",
        f"_compare_wave_only={compare_only}_",
        "",
        "| Pack | W | D | L | Finished | In progress | Mean accuracy |",
        "|------|---|---|---|----------|-------------|---------------|",
    ]
    for pid in PACK_ORDER:
        row = stats.get(pid) or {}
        acc = row.get("mean_accuracy")
        acc_s = f"{acc:.1f}" if isinstance(acc, (int, float)) else "â€”"
        lines.append(
            f"| {pid} | {row.get('wins', 0)} | {row.get('draws', 0)} | "
            f"{row.get('losses', 0)} | {row.get('finished', 0)} | "
            f"{row.get('in_progress', 0)} | {acc_s} |"
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--compare-wave-only", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    from chess_harness.prompt_test_ops import build_prompt_test_snapshot

    snap = build_prompt_test_snapshot(family="jeff")
    games = snap.get("games") or []
    if args.compare_wave_only and games:
        stats = _from_games(snap, compare_only=True)
    elif games and not args.compare_wave_only:
        stats = _from_games(snap, compare_only=False)
    else:
        stats = _from_pack_rows(snap)

    md = render(stats, compare_only=args.compare_wave_only)
    print(md)
    if args.write:
        out = HERE / "latest-report.md"
        out.write_text(md, encoding="utf-8")
        print(f"Wrote {out}")
    if args.json:
        print(json.dumps(stats, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

