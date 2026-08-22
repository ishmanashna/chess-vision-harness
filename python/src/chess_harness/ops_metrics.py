"""In-process origin request metrics for the localhost operator panel."""

from __future__ import annotations

import os
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Deque, Dict, List, Optional

from fastapi import HTTPException, Request
from starlette.responses import Response

__all__ = [
    "ROUTE_FAMILIES",
    "classify_route_family",
    "is_routine_client_error",
    "metrics_snapshot",
    "record_request",
    "register_ops_metrics",
    "reset_metrics",
]

BUCKET_SECONDS = 60
BUCKET_COUNT = 24 * 60
MAX_ERROR_EVENTS = 100
MAX_LATENCY_SAMPLES = 8000

ROUTE_FAMILIES = ("static", "api_v1", "watch", "other")

_GAME_MOVE_PATH = re.compile(r"^/api/v1/games/[^/]+/move(?:/|$)")
_PLAY_MOVE_PATH = re.compile(r"^/api/play/[^/]+/move(?:/|$)")
_SCHEMA_PATH = re.compile(
    r"^/api/v1/(?:games/[^/]+/move|puzzles/[^/]+/move|identify/[^/]+/answer)(?:/|$)"
)
_IDENTIFY_ANSWER_PATH = re.compile(r"^/api/v1/identify/[^/]+/answer(?:/|$)")


def classify_route_family(path: str) -> str:
    if path.startswith("/css/") or path.startswith("/js/") or path in {
        "/favicon.ico",
        "/favicon.svg",
    }:
        return "static"
    if path.startswith("/api/v1/"):
        return "api_v1"
    if (
        path.startswith("/g/")
        or path.startswith("/p/")
        or path.startswith("/i/")
        or path.startswith("/spectator")
    ):
        return "watch"
    return "other"


def is_routine_client_error(status: int, path: str, method: str) -> bool:
    """Expected agent/client mistakes — not operator outages."""
    if status == 400 and (_GAME_MOVE_PATH.match(path) or _PLAY_MOVE_PATH.match(path)):
        return True
    if status == 400 and _IDENTIFY_ANSWER_PATH.match(path):
        return True
    if status == 422 and _SCHEMA_PATH.match(path):
        return True
    return False


@dataclass
class MinuteBucket:
    requests: int = 0
    bytes_out: int = 0
    status_2xx: int = 0
    status_4xx: int = 0
    status_5xx: int = 0
    routine_4xx: int = 0
    outage_errors: int = 0
    routes: Dict[str, int] = field(default_factory=dict)


@dataclass
class ErrorEvent:
    ts: float
    status: int
    method: str
    path: str
    route_family: str
    duration_ms: float
    kind: str


class MetricsRing:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: Dict[int, MinuteBucket] = {}
        self._latencies_ms: Deque[float] = deque(maxlen=MAX_LATENCY_SAMPLES)
        self._errors: Deque[ErrorEvent] = deque(maxlen=MAX_ERROR_EVENTS)
        self._route_totals: Dict[str, int] = {name: 0 for name in ROUTE_FAMILIES}

    def reset(self) -> None:
        with self._lock:
            self._buckets.clear()
            self._latencies_ms.clear()
            self._errors.clear()
            self._route_totals = {name: 0 for name in ROUTE_FAMILIES}

    def record(
        self,
        *,
        path: str,
        method: str,
        status: int,
        duration_ms: float,
        bytes_out: int = 0,
    ) -> None:
        minute = int(time.time()) // BUCKET_SECONDS
        family = classify_route_family(path)
        routine = is_routine_client_error(status, path, method)
        outage = status >= 500 or (400 <= status < 500 and not routine)

        with self._lock:
            bucket = self._buckets.setdefault(minute, MinuteBucket())
            bucket.requests += 1
            bucket.bytes_out += max(0, bytes_out)
            bucket.routes[family] = bucket.routes.get(family, 0) + 1
            self._route_totals[family] = self._route_totals.get(family, 0) + 1

            if 200 <= status < 300:
                bucket.status_2xx += 1
            elif 400 <= status < 500:
                bucket.status_4xx += 1
                if routine:
                    bucket.routine_4xx += 1
                else:
                    bucket.outage_errors += 1
            elif status >= 500:
                bucket.status_5xx += 1
                bucket.outage_errors += 1

            self._latencies_ms.append(duration_ms)

            if outage:
                kind = "5xx" if status >= 500 else "unexpected_4xx"
                self._errors.append(
                    ErrorEvent(
                        ts=time.time(),
                        status=status,
                        method=method,
                        path=path,
                        route_family=family,
                        duration_ms=round(duration_ms, 1),
                        kind=kind,
                    )
                )

            self._prune_locked(minute)

    def _prune_locked(self, now_minute: int) -> None:
        cutoff = now_minute - BUCKET_COUNT + 1
        for key in list(self._buckets.keys()):
            if key < cutoff:
                del self._buckets[key]

    def snapshot(self) -> Dict[str, Any]:
        now_minute = int(time.time()) // BUCKET_SECONDS
        start_minute = now_minute - BUCKET_COUNT + 1

        with self._lock:
            total_requests = 0
            total_outage = 0
            total_routine = 0
            total_5xx = 0
            total_unexpected_4xx = 0
            buckets_out: List[Dict[str, Any]] = []

            for minute in range(start_minute, now_minute + 1):
                bucket = self._buckets.get(minute)
                requests = bucket.requests if bucket else 0
                outage = bucket.outage_errors if bucket else 0
                routine = bucket.routine_4xx if bucket else 0
                total_requests += requests
                total_outage += outage
                total_routine += routine
                if bucket:
                    total_5xx += bucket.status_5xx
                    total_unexpected_4xx += bucket.outage_errors - bucket.status_5xx

                buckets_out.append(
                    {
                        "minute": _minute_iso(minute),
                        "requests": requests,
                        "outage_errors": outage,
                        "routine_4xx": routine,
                    }
                )

            latencies = list(self._latencies_ms)
            route_rows = []
            for family in ROUTE_FAMILIES:
                route_rows.append(
                    {
                        "family": family,
                        "requests": self._route_totals.get(family, 0),
                    }
                )

            events = [
                {
                    "at": _ts_iso(ev.ts),
                    "status": ev.status,
                    "method": ev.method,
                    "path": ev.path,
                    "route_family": ev.route_family,
                    "duration_ms": ev.duration_ms,
                    "kind": ev.kind,
                }
                for ev in reversed(self._errors)
            ]

        error_rate = round((total_outage / total_requests) * 100.0, 2) if total_requests else 0.0
        p95 = _percentile(latencies, 95.0)

        return {
            "origin_requests_24h": total_requests,
            "error_rate": error_rate,
            "p95_ms": p95,
            "routine_4xx_24h": total_routine,
            "outage_errors_24h": total_outage,
            "events_5xx_24h": total_5xx,
            "events_unexpected_4xx_24h": max(0, total_unexpected_4xx),
            "route_families": list(ROUTE_FAMILIES),
            "routes": route_rows,
            "buckets": buckets_out,
            "errors": {
                "events_5xx": total_5xx,
                "events_unexpected_4xx": max(0, total_unexpected_4xx),
                "recent": events,
            },
            "storage": "in_memory",
            "note": "Origin request metrics reset when chess-harness serve restarts.",
        }


_ring = MetricsRing()


def reset_metrics() -> None:
    _ring.reset()


def record_request(**kwargs) -> None:
    _ring.record(**kwargs)


def metrics_snapshot() -> Dict[str, Any]:
    return _ring.snapshot()


def _minute_iso(minute: int) -> str:
    dt = datetime.fromtimestamp(minute * BUCKET_SECONDS, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + "Z"


def _ts_iso(ts: float) -> str:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + "Z"


def _percentile(values: List[float], pct: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    idx = int(round((pct / 100.0) * (len(ordered) - 1)))
    return round(ordered[idx], 1)


def _response_bytes(response: Response) -> int:
    length = response.headers.get("content-length")
    if length and length.isdigit():
        return int(length)
    body = getattr(response, "body", None)
    if isinstance(body, (bytes, bytearray)):
        return len(body)
    return 0


def register_ops_metrics(app, *, enable_test_hook: Optional[bool] = None) -> None:
    """Attach ASGI middleware and optional loopback-only test hook."""

    @app.middleware("http")
    async def _ops_metrics_middleware(request: Request, call_next: Callable):
        started = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - started) * 1000.0
        try:
            record_request(
                path=request.url.path,
                method=request.method,
                status=response.status_code,
                duration_ms=duration_ms,
                bytes_out=_response_bytes(response),
            )
        except Exception:
            pass
        return response

    from .calibration_auth import host_is_loopback

    @app.get("/api/ops/test/force-5xx")
    async def _ops_force_5xx(request: Request):
        allowed = enable_test_hook
        if allowed is None:
            allowed = os.environ.get("CHESS_HARNESS_OPS_METRICS_TEST_HOOK") == "1"
        if not allowed or not host_is_loopback(request):
            raise HTTPException(status_code=404)
        raise HTTPException(status_code=500, detail="ops metrics test hook")
