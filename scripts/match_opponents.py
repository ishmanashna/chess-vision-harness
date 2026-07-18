#!/usr/bin/env python3
"""One-off head-to-head games between two catalog opponents (no ELO updates)."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python" / "src"))
sys.path.insert(0, str(ROOT / "elo_calibration"))

import chess_harness.bootstrap  # noqa: E402

from calibration.game_loop import play_game  # noqa: E402
from calibration.play_config import MatchConfig, PlayConfig  # noqa: E402
from chess_harness.opponents import get_catalog  # noqa: E402


def _play_config_for(opponent_id: str) -> PlayConfig:
    """Use catalog harness movetime when present; else calibration default 100ms."""
    opp = get_catalog().get(opponent_id)
    movetime = 100
    depth = None
    noise = 0.0
    if opp.harness:
        movetime = int(opp.harness.get("movetime_ms", movetime))
        depth = opp.harness.get("depth")
        noise = float(opp.harness.get("random_move_pct", 0.0))
    return PlayConfig(movetime_ms=movetime, depth=depth, random_move_pct=noise)


def _uci_snapshot(opponent_id: str) -> dict:
    from calibration.engine_player import EnginePlayer, release_all_engines

    player = EnginePlayer(opponent_id, _play_config_for(opponent_id))
    try:
        return player.configure_snapshot()
    finally:
        release_all_engines()


def main() -> int:
    parser = argparse.ArgumentParser(description="Play N games between two opponents")
    parser.add_argument("a", help="First opponent id")
    parser.add_argument("b", help="Second opponent id")
    parser.add_argument("-n", "--games", type=int, default=20, help="Total games (alternating colors)")
    parser.add_argument("--max-plies", type=int, default=200)
    args = parser.parse_args()

    catalog = get_catalog()
    for oid in (args.a, args.b):
        catalog.get(oid)

    print(f"Match: {args.a} vs {args.b} ({args.games} games, alternating colors)")
    print(f"  {args.a} config: {_uci_snapshot(args.a)}")
    print(f"  {args.b} config: {_uci_snapshot(args.b)}")
    print()

    results: list[str] = []
    score_a = 0.0
    for i in range(args.games):
        white_id, black_id = (args.a, args.b) if i % 2 == 0 else (args.b, args.a)
        match = MatchConfig(
            white_id=white_id,
            black_id=black_id,
            max_plies=args.max_plies,
            white=_play_config_for(white_id),
            black=_play_config_for(black_id),
        )
        result = play_game(match)
        results.append(result)
        if result == "1/2-1/2":
            score_a += 0.5
        elif (result == "1-0" and white_id == args.a) or (result == "0-1" and black_id == args.a):
            score_a += 1.0
        print(f"  Game {i + 1:2d}: {white_id} (W) vs {black_id} (B) -> {result}")

    wins_a = sum(
        1
        for i, result in enumerate(results)
        if (result == "1-0" and i % 2 == 0) or (result == "0-1" and i % 2 == 1)
    )
    wins_b = sum(
        1
        for i, result in enumerate(results)
        if (result == "1-0" and i % 2 == 1) or (result == "0-1" and i % 2 == 0)
    )
    draws = results.count("1/2-1/2")

    print()
    print(f"Score for {args.a}: {score_a} / {args.games}  ({wins_a}W {draws}D {args.games - wins_a - draws}L)")
    print(f"Score for {args.b}: {args.games - score_a} / {args.games}  ({wins_b}W {draws}D {args.games - wins_b - draws}L)")
    print(f"Results: {dict(Counter(results))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
