#!/usr/bin/env python3
"""Measure opponent move latency (spawn + per-move) for calibration planning."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import chess

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python" / "src"))
import chess_harness.bootstrap  # noqa: E401

from chess_harness.engine import OpponentEngineManager
from chess_harness.opponents import Opponent, get_catalog


SAMPLE_FENS = [
    chess.STARTING_FEN,
    "rnbqkb1r/pppp1ppp/5n2/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq - 2 3",
]


def _percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(round((pct / 100.0) * (len(ordered) - 1)))
    return ordered[max(0, min(idx, len(ordered) - 1))]


def benchmark_opponent(opp: Opponent, *, moves: int, fens: List[str]) -> Dict[str, Any]:
    mgr = OpponentEngineManager()
    move_ms: List[float] = []
    spawn_ms = 0.0
    error: str | None = None
    try:
        if opp.type != "random":
            t0 = time.perf_counter()
            mgr.get_adapter(opp)
            spawn_ms = (time.perf_counter() - t0) * 1000.0

        board = chess.Board()
        fen_idx = 0
        for _ in range(moves):
            if board.is_game_over():
                board.set_fen(fens[fen_idx % len(fens)])
                fen_idx += 1
            t0 = time.perf_counter()
            result = mgr.play(opp, board, time_limit=0.1)
            move_ms.append((time.perf_counter() - t0) * 1000.0)
            board.push(result.move)
    except Exception as exc:
        error = str(exc)
    finally:
        mgr.release()

    median = statistics.median(move_ms) if move_ms else 0.0
    plies_per_game = 80
    sec_per_game = (spawn_ms / 1000.0) + (median / 1000.0) * plies_per_game
    games_per_hour = 3600.0 / sec_per_game if sec_per_game > 0 else 0.0

    return {
        "id": opp.id,
        "type": opp.type,
        "enabled": opp.enabled,
        "spawn_ms": round(spawn_ms, 1),
        "move_median_ms": round(median, 1),
        "move_p95_ms": round(_percentile(move_ms, 95), 1),
        "moves_sampled": len(move_ms),
        "games_per_hour_est": round(games_per_hour, 1),
        "slow": median > 500 or spawn_ms > 2000,
        "error": error,
    }


def format_markdown(rows: List[Dict[str, Any]]) -> str:
    lines = [
        "| Opponent | Type | Spawn ms | Move median ms | P95 ms | Games/hr est | Slow |",
        "|----------|------|----------|----------------|--------|--------------|------|",
    ]
    for row in rows:
        if row.get("error"):
            lines.append(f"| `{row['id']}` | {row['type']} | — | — | — | — | error |")
            continue
        slow = "yes" if row.get("slow") else ""
        lines.append(
            f"| `{row['id']}` | {row['type']} | {row['spawn_ms']} | "
            f"{row['move_median_ms']} | {row['move_p95_ms']} | "
            f"{row['games_per_hour_est']} | {slow} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark opponent move speed")
    parser.add_argument("--moves", type=int, default=8, help="Moves per opponent")
    parser.add_argument("--json", type=Path, default=None, help="Write JSON report path")
    parser.add_argument("--markdown", type=Path, default=None, help="Write markdown table path")
    parser.add_argument("--only", nargs="*", help="Limit to opponent ids")
    args = parser.parse_args()

    catalog = get_catalog()
    opponents = catalog.list_opponents()
    if args.only:
        want = set(args.only)
        opponents = [o for o in opponents if o.id in want]

    rows: List[Dict[str, Any]] = []
    for opp in opponents:
        if not catalog._is_playable(opp):
            rows.append(
                {
                    "id": opp.id,
                    "type": opp.type,
                    "enabled": opp.enabled,
                    "error": "not playable (binary missing)",
                }
            )
            continue
        rows.append(benchmark_opponent(opp, moves=args.moves, fens=SAMPLE_FENS))

    rows.sort(key=lambda r: (r.get("move_median_ms") or 0, r["id"]))

    print(format_markdown(rows))
    if args.json:
        args.json.write_text(json.dumps({"opponents": rows}, indent=2), encoding="utf-8")
        print(f"Wrote {args.json}", file=sys.stderr)
    if args.markdown:
        args.markdown.write_text(format_markdown(rows), encoding="utf-8")
        print(f"Wrote {args.markdown}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
