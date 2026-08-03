"""Tests for live leaderboard API (Phase 5)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
from fastapi.testclient import TestClient

from conftest import FIXTURES

from chess_harness.game_manager import GameManager
from chess_harness.spectator import app


@pytest.fixture
def live_lb_client(tmp_path, monkeypatch):
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    shutil.copy(FIXTURES / "models.json", harness_dir / "models.json")
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness_dir))
    monkeypatch.setenv("MODELS_FILE", str(harness_dir / "models.json"))

    import chess_harness.spectator as spec

    spec._base = str(harness_dir)
    spec.game_manager = GameManager(str(harness_dir))
    spec._controller = None
    spec._game_service = None

    client = TestClient(app)
    yield client, harness_dir
    spec._game_service = None
    spec._controller = None
    if spec._engine is not None:
        spec._engine.quit()
        spec._engine = None
    if hasattr(spec, "_get_controller"):
        try:
            spec._get_controller().opponent_mgr.release()
        except Exception:
            pass


def _assert_snapshot_shape(data: dict) -> None:
    assert isinstance(data.get("generated_at"), str)
    agents = data.get("agents")
    assert isinstance(agents, list)
    for agent in agents:
        assert "id" in agent
        assert "name" in agent
        assert "elo" in agent
        assert "games" in agent
        assert "provisional" in agent
    opponents = data.get("opponents")
    assert isinstance(opponents, list)
    for row in opponents:
        assert "id" in row
        assert "name" in row
        assert "elo" in row


def test_live_leaderboard_endpoint_shape(live_lb_client):
    client, _ = live_lb_client
    resp = client.get("/api/leaderboard/live")
    assert resp.status_code == 200
    assert resp.headers.get("cache-control") == "no-store"
    data = resp.json()
    _assert_snapshot_shape(data)
    assert len(data["agents"]) >= 1


def test_data_leaderboard_json_serves_live_on_origin(live_lb_client):
    client, _ = live_lb_client
    resp = client.get("/data/leaderboard.json")
    assert resp.status_code == 200
    assert resp.headers.get("cache-control") == "no-store"
    data = resp.json()
    _assert_snapshot_shape(data)


def test_client_health_requires_reachable_origin():
    js = (ROOT / "public-site" / "js" / "common.js").read_text(encoding="utf-8")
    assert "data.origin === true" not in js
    assert "fetchLeaderboardSnapshot" in js
    assert "live leaderboard fetch failed" in js


def test_proxy_allows_live_leaderboard_path():
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "public-site" / "functions" / "_proxy.js"
    text = path.read_text(encoding="utf-8")
    assert "/api/leaderboard/live" in text


def test_load_live_leaderboard_matches_export(tmp_path, monkeypatch):
    from chess_harness.models import ModelRegistry
    from chess_harness.snapshot_leaderboard import (
        export_leaderboard_snapshot,
        load_live_leaderboard,
    )

    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    models_file = harness_dir / "models.json"
    shutil.copy(FIXTURES / "models.json", models_file)
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness_dir))

    live = load_live_leaderboard(base_dir=str(harness_dir), registry=ModelRegistry(models_file))
    out = tmp_path / "lb.json"
    export_leaderboard_snapshot(out, base_dir=str(harness_dir), registry=ModelRegistry(models_file))
    exported = json.loads(out.read_text(encoding="utf-8"))
    assert live["agents"] == exported["agents"]
    assert live["opponents"] == exported["opponents"]
