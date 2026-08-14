"""Phase 7: calibration operator safety (caps, confirms, live status, secret gating)."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chess_harness.calibration_view import get_calibration_status, get_calibration_status_live
from chess_harness.continuous_calibration import (
    PARALLEL_CONFIRM_ABOVE,
    assess_fleet_parallel,
    assess_parallel_start,
    assess_start_all,
    fleet_parallel_hard_cap,
    get_continuous_calibration,
    parallel_hard_cap,
)
from chess_harness.ladder_display import render_calibration_html


def test_parallel_hard_cap_is_bounded():
    cap = parallel_hard_cap()
    assert 1 <= cap <= 16


def test_assess_parallel_start_requires_confirm_above_soft_cap():
    above = PARALLEL_CONFIRM_ABOVE + 1
    assert assess_parallel_start(above, confirm=False) is not None
    assert assess_parallel_start(above, confirm=True) is None


def test_assess_parallel_start_blocks_above_hard_cap_even_with_confirm():
    hard = parallel_hard_cap()
    assert assess_parallel_start(hard + 1, confirm=True) is not None


def test_assess_start_all_requires_confirm():
    mgr = get_continuous_calibration()
    err = assess_start_all(mgr, 1, confirm=False)
    assert err is not None
    assert "confirm" in err


def test_assess_fleet_parallel_blocks_over_cap():
    mgr = get_continuous_calibration()
    hard = fleet_parallel_hard_cap()
    mgr._parallel = {"filled": hard}
    err = assess_fleet_parallel(mgr, 1, confirm=True)
    assert err is not None
    assert "fleet" in err.lower()


def test_assess_start_all_blocks_when_fleet_exceeded(monkeypatch):
    import chess_harness.continuous_calibration as cc

    mgr = get_continuous_calibration()
    many = [f"engine-{i}" for i in range(20)]
    monkeypatch.setattr(cc, "list_calibratable_engine_ids", lambda **kw: many)
    err = assess_start_all(mgr, 1, confirm=True)
    assert err is not None
    assert "fleet" in err.lower()


def test_start_already_running_returns_409(spectator_client):
    mgr = get_continuous_calibration()
    engine_id = "stockfish-handicap:noise10"
    mgr._active_engines.add(engine_id)
    mgr._parallel[engine_id] = 1
    client = spectator_client
    host = {"Host": "127.0.0.1:8765"}
    try:
        resp = client.post(
            f"/api/calibration/continuous/{engine_id}/start?parallel=1",
            headers=host,
        )
        assert resp.status_code == 409
        assert "already running" in resp.json()["detail"].lower()
    finally:
        mgr._active_engines.discard(engine_id)
        mgr._parallel.pop(engine_id, None)


def test_get_calibration_status_live_is_lightweight():
    live = get_calibration_status_live()
    full = get_calibration_status()
    assert "rating_table" not in live
    assert "play_rating" not in live
    assert "play_rating_map" not in live
    assert live["pairing_locked"] is False
    assert live["parallel_hard_cap"] == parallel_hard_cap()
    assert "fleet_parallel_hard_cap" in live
    assert "rating_table" in full


def test_calibration_secret_not_in_html_when_not_loopback(monkeypatch):
    monkeypatch.setenv("CHESS_HARNESS_CALIBRATION_SECRET", "super-secret-value")
    html = render_calibration_html(loopback=False)
    assert "super-secret-value" not in html
    assert '<meta name="calibration-secret"' not in html
    assert "cal-secret-panel" in html


def test_calibration_secret_meta_on_loopback_only(monkeypatch):
    monkeypatch.setenv("CHESS_HARNESS_CALIBRATION_SECRET", "loopback-only-secret")
    loopback_html = render_calibration_html(loopback=True)
    remote_html = render_calibration_html(loopback=False)
    assert "loopback-only-secret" in loopback_html
    assert "loopback-only-secret" not in remote_html


def test_start_all_requires_confirm_on_api(spectator_client):
    client = spectator_client
    denied = client.post(
        "/api/calibration/start-all?parallel=1",
        headers={"Host": "127.0.0.1:8765"},
    )
    assert denied.status_code == 400
    assert "confirm" in denied.json()["detail"].lower()


def test_pairing_mode_locked_while_running(spectator_client):
    mgr = get_continuous_calibration()
    mgr._active_engines.add("test-engine")
    client = spectator_client
    host = {"Host": "127.0.0.1:8765"}
    try:
        blocked = client.post(
            "/api/calibration/pairing-mode?mode=random",
            headers=host,
        )
        assert blocked.status_code == 409
    finally:
        mgr._active_engines.discard("test-engine")


def test_high_parallel_requires_confirm_on_api(spectator_client):
    client = spectator_client
    host = {"Host": "127.0.0.1:8765"}
    parallel = PARALLEL_CONFIRM_ABOVE + 1
    denied = client.post(
        f"/api/calibration/continuous/stockfish-handicap:noise10/start?parallel={parallel}",
        headers=host,
    )
    assert denied.status_code == 400
    ok = client.post(
        f"/api/calibration/continuous/stockfish-handicap:noise10/start?parallel={parallel}&confirm=1",
        headers=host,
    )
    assert ok.status_code == 200
    client.post("/api/calibration/stop-all", headers=host)


def test_live_status_endpoint(spectator_client):
    client = spectator_client
    resp = client.get("/api/calibration/status/live")
    assert resp.status_code == 200
    data = resp.json()
    assert "rating_table" not in data
    assert "parallel_hard_cap" in data
    assert "fleet_parallel_hard_cap" in data
