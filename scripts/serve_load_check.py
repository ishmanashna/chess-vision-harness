#!/usr/bin/env python3
"""Quick serve responsiveness check while hammering /api/games.

Usage (with harness already running on localhost:8765):

    python scripts/serve_load_check.py

Parallel list requests run while /health is probed; prints max health latency
and current engine_count from /api/v1/metrics when available.
"""

from __future__ import annotations

import concurrent.futures
import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8765"
LIST_WORKERS = 12
LIST_ROUNDS = 3


def _get(path: str) -> tuple[int, float, str]:
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(f"{BASE}{path}", timeout=10) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, time.perf_counter() - start, body
    except urllib.error.HTTPError as exc:
        return exc.code, time.perf_counter() - start, exc.read().decode("utf-8", errors="replace")
    except OSError as exc:
        return 0, time.perf_counter() - start, str(exc)


def main() -> int:
    health_latencies: list[float] = []
    list_ok = 0
    list_total = 0

    def hammer_list() -> None:
        nonlocal list_ok, list_total
        for _ in range(LIST_ROUNDS):
            status, _elapsed, _body = _get("/api/games")
            list_total += 1
            if status == 200:
                list_ok += 1

    with concurrent.futures.ThreadPoolExecutor(max_workers=LIST_WORKERS + 1) as pool:
        list_futs = [pool.submit(hammer_list) for _ in range(LIST_WORKERS)]
        for _ in range(5):
            status, elapsed, _body = _get("/health")
            health_latencies.append(elapsed)
            if status != 200:
                print(f"/health returned {status}", file=sys.stderr)
                return 1
        for fut in concurrent.futures.as_completed(list_futs):
            fut.result()

    metrics_status, _elapsed, metrics_body = _get("/api/v1/metrics")
    engine_count = None
    if metrics_status == 200:
        try:
            engine_count = json.loads(metrics_body).get("engine_count")
        except json.JSONDecodeError:
            pass

    print(f"list_ok={list_ok}/{list_total}")
    print(f"health_max_ms={max(health_latencies) * 1000:.1f}")
    print(f"health_p95_ms={sorted(health_latencies)[int(len(health_latencies) * 0.95) - 1] * 1000:.1f}")
    if engine_count is not None:
        print(f"engine_count={engine_count}")
    return 0 if list_ok == list_total and max(health_latencies) < 1.0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
