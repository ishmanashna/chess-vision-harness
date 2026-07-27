"""Tests for /api/v1 abuse limits and metrics."""

from __future__ import annotations

import shutil

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from conftest import FIXTURES, LOW_OPPONENT

from chess_harness.api_limits import ApiLimitEnforcer, AuthContext
from chess_harness.api_v1 import build_router
from chess_harness.game_manager import GameManager
from chess_harness.game_service import GameService
from chess_harness.limits import HarnessLimits, load_limits


def test_load_limits_defaults(monkeypatch):
    for name in (
        "CHESS_HARNESS_MAX_CONCURRENT_GAMES",
        "CHESS_HARNESS_MAX_ENGINE_PROCESSES",
        "CHESS_HARNESS_MAX_GAMES_PER_HOUR_PER_KEY",
        "CHESS_HARNESS_MAX_MOVES_PER_HOUR_PER_KEY",
        "CHESS_HARNESS_IDLE_TIMEOUT_SEC",
        "CHESS_HARNESS_MAX_AGENT_REGISTRATIONS_PER_IP_PER_HOUR",
    ):
        monkeypatch.delenv(name, raising=False)
    lim = load_limits()
    assert lim.max_concurrent_games == 10
    assert lim.max_moves_per_hour_per_key == 600
    assert lim.idle_timeout_sec == 1800


def test_sliding_window_retry_after():
    enforcer = ApiLimitEnforcer(
        HarnessLimits(
            max_concurrent_games=10,
            max_engine_processes=12,
            max_games_per_hour_per_key=1,
            max_moves_per_hour_per_key=600,
            idle_timeout_sec=1800,
            max_agent_registrations_per_ip_per_hour=10,
        )
    )
    auth = AuthContext(model_id="m", key_fingerprint="fp-test")
    enforcer.record_create_game(auth)
    denied = enforcer.check_create_game(
        GameService(game_manager=GameManager()), auth
    )
    assert denied is not None
    assert denied.status_code == 429
    assert int(denied.headers["retry-after"]) >= 1


@pytest.fixture
def limit_client(tmp_path, monkeypatch):
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    shutil.copy(FIXTURES / "models.json", harness_dir / "models.json")
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness_dir))
    monkeypatch.setenv("MODELS_FILE", str(harness_dir / "models.json"))

    game_manager = GameManager(str(harness_dir))

    def get_game_service() -> GameService:
        return GameService(game_manager=game_manager)

    tight = HarnessLimits(
        max_concurrent_games=2,
        max_engine_processes=12,
        max_games_per_hour_per_key=2,
        max_moves_per_hour_per_key=3,
        idle_timeout_sec=300,
        max_agent_registrations_per_ip_per_hour=2,
    )
    enforcer = ApiLimitEnforcer(tight)

    app = FastAPI()
    app.include_router(build_router(get_game_service, limit_enforcer=enforcer))
    client = TestClient(app)
    yield client, harness_dir, enforcer
    get_game_service().controller.opponent_mgr.release()


def _auth(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def _register(client: TestClient, agent_id: str) -> str:
    reg = client.post("/api/v1/agents", json={"id": agent_id, "name": agent_id})
    assert reg.status_code == 200
    return reg.json()["api_key"]


def test_concurrent_games_returns_503(limit_client):
    client, _, _ = limit_client
    key = _register(client, "limit-agent")

    for _ in range(2):
        resp = client.post(
            "/api/v1/games",
            headers=_auth(key),
            json={"opponent": LOW_OPPONENT, "agent_color": "white"},
        )
        assert resp.status_code == 200

    blocked = client.post(
        "/api/v1/games",
        headers=_auth(key),
        json={"opponent": LOW_OPPONENT, "agent_color": "white"},
    )
    assert blocked.status_code == 503
    assert blocked.json()["ok"] is False
    assert blocked.headers.get("retry-after")


def test_games_per_hour_per_key_returns_429(limit_client):
    client, _, _ = limit_client
    key = _register(client, "rate-agent")

    for _ in range(2):
        create = client.post(
            "/api/v1/games",
            headers=_auth(key),
            json={"opponent": LOW_OPPONENT, "agent_color": "white"},
        )
        assert create.status_code == 200
        game_id = create.json()["game_id"]
        client.post(f"/api/v1/games/{game_id}/resign", headers=_auth(key))

    blocked = client.post(
        "/api/v1/games",
        headers=_auth(key),
        json={"opponent": LOW_OPPONENT, "agent_color": "white"},
    )
    assert blocked.status_code == 429
    assert "game limit" in blocked.json()["error"].lower()
    assert blocked.headers.get("retry-after")


def test_moves_per_hour_per_key_returns_429(limit_client):
    client, _, _ = limit_client
    key = _register(client, "move-rate-agent")
    create = client.post(
        "/api/v1/games",
        headers=_auth(key),
        json={"opponent": LOW_OPPONENT, "agent_color": "white"},
    )
    game_id = create.json()["game_id"]

    for move in ("e2e4", "g1f3", "f1c4"):
        resp = client.post(
            f"/api/v1/games/{game_id}/move/{move}",
            headers=_auth(key),
        )
        assert resp.status_code == 200

    blocked = client.post(
        f"/api/v1/games/{game_id}/move/d2d4",
        headers=_auth(key),
    )
    assert blocked.status_code == 429
    assert "move limit" in blocked.json()["error"].lower()
    assert blocked.headers.get("retry-after")


def test_agent_registration_ip_limit(limit_client):
    client, _, _ = limit_client
    assert client.post("/api/v1/agents", json={"id": "ip-a", "name": "A"}).status_code == 200
    assert client.post("/api/v1/agents", json={"id": "ip-b", "name": "B"}).status_code == 200
    blocked = client.post("/api/v1/agents", json={"id": "ip-c", "name": "C"})
    assert blocked.status_code == 429
    assert blocked.headers.get("retry-after")


def test_metrics_endpoint(limit_client):
    client, harness_dir, _ = limit_client
    key = _register(client, "metrics-agent")
    client.post(
        "/api/v1/games",
        headers=_auth(key),
        json={"opponent": LOW_OPPONENT, "agent_color": "white"},
    )

    metrics = client.get("/api/v1/metrics")
    assert metrics.status_code == 200
    data = metrics.json()
    assert data["ok"] is True
    assert data["active_games"] == 1
    assert "disk_free_bytes" in data
    assert data["disk_free_bytes"] is None or data["disk_free_bytes"] > 0
    assert data["limits"]["max_concurrent_games"] == 2
    assert "api_key" not in metrics.text
    assert str(harness_dir) not in metrics.text
