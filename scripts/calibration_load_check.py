#!/usr/bin/env python3
"""Verify /health and agent moves stay responsive while capped calibration runs.

Usage (harness on localhost:8765, calibration worker spawned by serve):

    python scripts/calibration_load_check.py

Environment:
    CHESS_HARNESS_LOAD_BASE — default http://127.0.0.1:8765
    CHESS_HARNESS_CALIBRATION_PARALLEL — default 2 (capped load)
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = os.environ.get("CHESS_HARNESS_LOAD_BASE", "http://127.0.0.1:8765").rstrip("/")
PARALLEL = max(1, min(4, int(os.environ.get("CHESS_HARNESS_CALIBRATION_PARALLEL", "2"))))
HEALTH_BUDGET_SEC = float(os.environ.get("CHESS_HARNESS_HEALTH_BUDGET_SEC", "1.0"))
ENGINE_ID = os.environ.get(
    "CHESS_HARNESS_CALIBRATION_ENGINE",
    "stockfish-handicap:noise10",
)
PROBE_ROUNDS = 8
LIST_WORKERS = 6


def _request(method: str, path: str, *, query: dict | None = None, timeout: float = 30.0) -> tuple[int, float, str]:
    url = f"{BASE}{path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    start = time.perf_counter()
    req = urllib.request.Request(url, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.status, time.perf_counter() - start, body
    except urllib.error.HTTPError as exc:
        return exc.code, time.perf_counter() - start, exc.read().decode("utf-8", errors="replace")
    except OSError as exc:
        return 0, time.perf_counter() - start, str(exc)


def _post_calibration(path: str, query: dict | None = None) -> tuple[int, str]:
    status, _elapsed, body = _request("POST", path, query=query, timeout=120.0)
    return status, body


def main() -> int:
    health_before, _, _ = _request("GET", "/health")
    if health_before != 200:
        print(f"Harness not healthy at {BASE}/health (status={health_before})", file=sys.stderr)
        return 1

    start_status, start_body = _post_calibration(
        f"/api/calibration/continuous/{urllib.parse.quote(ENGINE_ID, safe='')}/start",
        query={"parallel": PARALLEL, "confirm": "1"},
    )
    if start_status != 200:
        print(f"Failed to start calibration ({start_status}): {start_body}", file=sys.stderr)
        return 1

    health_latencies: list[float] = []
    list_ok = 0
    list_total = 0

    def hammer_list() -> None:
        nonlocal list_ok, list_total
        for _ in range(3):
            status, _elapsed, _body = _request("GET", "/api/games")
            list_total += 1
            if status == 200:
                list_ok += 1

    with concurrent.futures.ThreadPoolExecutor(max_workers=LIST_WORKERS + 1) as pool:
        list_futs = [pool.submit(hammer_list) for _ in range(LIST_WORKERS)]
        for _ in range(PROBE_ROUNDS):
            status, elapsed, _body = _request("GET", "/health", timeout=10.0)
            health_latencies.append(elapsed)
            if status != 200:
                print(f"/health returned {status} during calibration", file=sys.stderr)
                _post_calibration("/api/calibration/stop-all")
                return 1
        for fut in concurrent.futures.as_completed(list_futs):
            fut.result()

    _post_calibration("/api/calibration/stop-all")

    metrics_status, _elapsed, metrics_body = _request("GET", "/api/v1/metrics")
    engine_count = None
    if metrics_status == 200:
        try:
            engine_count = json.loads(metrics_body).get("engine_count")
        except json.JSONDecodeError:
            pass

    max_health = max(health_latencies)
    print(f"calibration_parallel={PARALLEL}")
    print(f"list_ok={list_ok}/{list_total}")
    print(f"health_max_ms={max_health * 1000:.1f}")
    print(f"health_p95_ms={sorted(health_latencies)[max(0, int(len(health_latencies) * 0.95) - 1)] * 1000:.1f}")
    if engine_count is not None:
        print(f"engine_count={engine_count}")

    if list_ok != list_total:
        return 2
    if max_health > HEALTH_BUDGET_SEC:
        print(f"health exceeded budget {HEALTH_BUDGET_SEC}s", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
