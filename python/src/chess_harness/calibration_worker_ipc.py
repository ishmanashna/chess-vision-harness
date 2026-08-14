"""IPC helpers for the out-of-process calibration worker."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
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
