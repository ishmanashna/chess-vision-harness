#!/usr/bin/env python3
"""Kill orphaned opponent UCI subprocesses and calibration pool workers."""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chess_harness.engine_cleanup import (  # noqa: E402
    DEFAULT_OPPONENT_PROCESS_NAMES,
    kill_opponent_processes,
    kill_orphan_pool_workers,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Kill orphaned chess harness processes")
    parser.add_argument(
        "--pool-workers",
        action="store_true",
        help="Also kill orphaned ProcessPoolExecutor python workers",
    )
    parser.add_argument("names", nargs="*", default=list(DEFAULT_OPPONENT_PROCESS_NAMES))
    args = parser.parse_args()
    killed = kill_opponent_processes(*args.names)
    if args.pool_workers:
        count = kill_orphan_pool_workers()
        if count:
            killed["python-pool-workers"] = count
    if not killed:
        print("No orphaned harness processes found.")
        return 0
    for name, count in killed.items():
        print(f"Killed {name}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
