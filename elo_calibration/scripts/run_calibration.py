#!/usr/bin/env python3
"""CLI entrypoint for elo_calibration/."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent / "src"))
sys.path.insert(0, str(ROOT))

from calibration.runner import run_suite  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Engine ELO calibration — schedule games and update floating ratings"
    )
    parser.add_argument("--suite", default="quick", help="Suite name (quick, patricia, ladder)")
    parser.add_argument(
        "--play",
        action="store_true",
        help="Actually run engine games (default is dry-run: plan only)",
    )
    parser.add_argument(
        "--reset-ratings",
        action="store_true",
        help="Ignore saved ratings.json and re-seed floating players at 500",
    )
    parser.add_argument("--seed", type=int, default=42, help="RNG seed for openings/colors")
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Parallel engine games (default 4; use 1 for sequential)",
    )
    args = parser.parse_args()

    suite_path = ROOT / "suites" / f"{args.suite}.yaml"
    results_dir = ROOT / "results" / args.suite
    if not suite_path.exists():
        print(f"Suite not found: {suite_path}", file=sys.stderr)
        return 1

    summary = run_suite(
        suite_path,
        results_dir,
        seed=args.seed,
        play=args.play,
        reset_ratings=args.reset_ratings,
        workers=args.workers if args.play else 1,
    )

    mode = "played" if args.play else "planned"
    print(f"{mode.capitalize()} {summary['scheduled_games']} games -> {results_dir}")
    print(json.dumps(summary.get("rating_table", []), indent=2))
    if not args.play:
        print("\nDry run only. Pass --play to start engines.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
