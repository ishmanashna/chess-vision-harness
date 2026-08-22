"""Unit tests for in-process origin request metrics."""

from __future__ import annotations

from chess_harness.ops_metrics import (
    MetricsRing,
    classify_route_family,
    is_routine_client_error,
    metrics_snapshot,
    record_request,
    reset_metrics,
)


def test_fresh_ring_is_empty():
    ring = MetricsRing()
    snap = ring.snapshot()
    assert snap["origin_requests_24h"] == 0
    assert snap["errors"]["recent"] == []
    assert snap["error_rate"] == 0.0
    assert snap["p95_ms"] is None


def test_reset_metrics_clears_global_ring():
    record_request(
        path="/health",
        method="GET",
        status=200,
        duration_ms=1.0,
    )
    assert metrics_snapshot()["origin_requests_24h"] >= 1
    reset_metrics()
    assert metrics_snapshot()["origin_requests_24h"] == 0


def test_classify_route_families():
    assert classify_route_family("/css/site.css") == "static"
    assert classify_route_family("/js/ops.js") == "static"
    assert classify_route_family("/api/v1/games/x/status") == "api_v1"
    assert classify_route_family("/g/game-1") == "watch"
    assert classify_route_family("/p/attempt-1") == "watch"
    assert classify_route_family("/spectator/") == "watch"
    assert classify_route_family("/health") == "other"
    assert classify_route_family("/ops/") == "other"


def test_routine_client_error_classification():
    assert is_routine_client_error(400, "/api/v1/games/g1/move/e2e5", "POST")
    assert is_routine_client_error(400, "/api/play/g1/move/e2e5", "POST")
    assert is_routine_client_error(422, "/api/v1/games/g1/move", "POST")
    assert is_routine_client_error(400, "/api/v1/identify/a1/answer", "POST")
    assert not is_routine_client_error(404, "/api/v1/games/g1/status", "GET")
    assert not is_routine_client_error(500, "/health", "GET")


def test_illegal_move_4xx_not_outage_event():
    ring = MetricsRing()
    ring.record(
        path="/api/v1/games/g1/move/e2e5",
        method="POST",
        status=400,
        duration_ms=3.0,
    )
    snap = ring.snapshot()
    assert snap["routine_4xx_24h"] == 1
    assert snap["outage_errors_24h"] == 0
    assert snap["errors"]["recent"] == []


def test_5xx_recorded_as_outage_event():
    ring = MetricsRing()
    ring.record(
        path="/health",
        method="GET",
        status=500,
        duration_ms=8.0,
    )
    snap = ring.snapshot()
    assert snap["outage_errors_24h"] == 1
    assert snap["errors"]["events_5xx"] == 1
    assert len(snap["errors"]["recent"]) == 1
    assert snap["errors"]["recent"][0]["status"] == 500
    assert snap["errors"]["recent"][0]["kind"] == "5xx"
