"""Offline example: replace the synthetic body in a future experiment launcher."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from run_record import RunRecord  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-root", type=Path, default=HERE / "runs")
    args = parser.parse_args()
    config = json.loads((HERE / "config.json").read_text(encoding="utf-8"))
    if config.get("synthetic") is not True:
        parser.error("This example only supports synthetic runs; implement a real launcher separately")
    try:
        run = RunRecord(args.output_root, args.run_id, config, (HERE / "prompt.txt").read_bytes())
    except (ValueError, FileExistsError) as exc:
        parser.error(str(exc))
    try:
        run.event("seat_started", seat_id="synthetic-1", phase="offline-demo")
        run.event("heartbeat", seat_id="synthetic-1", phase="offline-demo")
        run.event("seat_finished", seat_id="synthetic-1", phase="completed", reason="fixture complete")
        run.finish("completed", reason="offline scaffold verified", summary=(
            "One synthetic seat completed. No provider calls, chess games, or model "
            "quality measurements were made. This is bookkeeping evidence only."
        ))
    except Exception:
        if run.manifest["status"] == "running":
            run.finish("failed", reason="offline example failed", summary="Inspect local diagnostics; no research conclusion.")
        raise
    print(run.directory)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
