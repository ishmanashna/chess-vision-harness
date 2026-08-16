"""IPC helpers for the out-of-process calibration worker.

Serve reads live calibration activity from ``status.json`` (written by the worker
each second). Display GETs do not RPC the worker for ratings, quality samples, or
the accuracy map — only POST start/stop/pairing and worker health use HTTP.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

from .paths import default_calibration_worker_port, resolve_calibration_worker_dir


def calibration_in_process() -> bool:
    """When true, continuous calibration runs inside the serve process (tests)."""
    return os.environ.get("CHESS_HARNESS_CALIBRATION_IN_PROCESS", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def is_calibration_worker_process() -> bool:
    return os.environ.get("CHESS_HARNESS_CALIBRATION_WORKER", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def calibration_worker_port() -> int:
    return default_calibration_worker_port()


def calibration_worker_base_url() -> str:
    return f"http://127.0.0.1:{calibration_worker_port()}"


def calibration_worker_status_path() -> str:
    return str(resolve_calibration_worker_dir() / "status.json")


def default_idle_worker_snapshot() -> Dict[str, Any]:
    """Baseline snapshot when the worker is down or status.json is missing."""
    from .continuous_calibration import (
        DEFAULT_PAIRING_MODE,
        PARALLEL_CONFIRM_ABOVE,
        PROCESS_POOL_WORKERS,
        fleet_parallel_confirm_above,
        fleet_parallel_hard_cap,
        list_calibratable_engine_ids,
        list_pairing_opponent_choices,
        parallel_hard_cap,
    )

    return {
        "active": False,
        "continuous_engines": [],
        "parallel_by_engine": {},
        "skipped_games": 0,
        "in_flight_by_engine": {},
        "recent_games": [],
        "pairing_mode": DEFAULT_PAIRING_MODE,
        "fixed_opponent_id": "stockfish:0",
        "pairing_opponents": list_pairing_opponent_choices(),
        "calibratable_engines": list_calibratable_engine_ids(
            pairing_mode=DEFAULT_PAIRING_MODE
        ),
        "process_pool_workers": PROCESS_POOL_WORKERS,
        "parallel_hard_cap": parallel_hard_cap(),
        "parallel_confirm_above": PARALLEL_CONFIRM_ABOVE,
        "fleet_parallel_in_use": 0,
        "fleet_parallel_hard_cap": fleet_parallel_hard_cap(),
        "fleet_parallel_confirm_above": fleet_parallel_confirm_above(),
        "pairing_locked": False,
    }


def read_worker_status_snapshot() -> Dict[str, Any]:
    """Read the worker's on-disk status snapshot (no HTTP)."""
    idle = default_idle_worker_snapshot()
    path = Path(calibration_worker_status_path())
    if not path.is_file():
        return idle
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return idle
    if not isinstance(data, dict):
        return idle
    return {**idle, **data}


def http_json(
    method: str,
    path: str,
    *,
    query: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None,
    timeout: float = 30.0,
    base_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Synchronous JSON HTTP call to the calibration worker."""
    base = (base_url or calibration_worker_base_url()).rstrip("/")
    url = f"{base}{path}"
    if query:
        params = urllib.parse.urlencode(
            {k: v for k, v in query.items() if v is not None},
            doseq=True,
        )
        url = f"{url}?{params}"
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {"detail": raw or exc.reason}
        detail = payload.get("detail", payload)
        raise RuntimeError(str(detail)) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"calibration worker unreachable at {base}: {exc}") from exc
    if not raw:
        return {}
    return json.loads(raw)


def worker_health_ok(base_url: Optional[str] = None, timeout: float = 1.0) -> bool:
    try:
        payload = http_json("GET", "/health", timeout=timeout, base_url=base_url)
        return bool(payload.get("ok"))
    except Exception:
        return False
