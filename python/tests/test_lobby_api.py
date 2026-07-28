"""Integration tests for /api/v1/lobbies (AvaA lobby API)."""

from __future__ import annotations

import shutil

import pytest
from fastapi.testclient import TestClient

from conftest import FIXTURES

from chess_harness.game_manager import GameManager
from chess_harness.spectator import app


@pytest.fixture
def lobby_api_client(tmp_path, monkeypatch):
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    shutil.copy(FIXTURES / "models.json", harness_dir / "models.json")
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness_dir))
    monkeypatch.setenv("MODELS_FILE", str(harness_dir / "models.json"))

    import chess_harness.api_limits as api_limits
    import chess_harness.spectator as spec

    api_limits.get_limit_enforcer().reset_counters()
    spec._base = str(harness_dir)
    spec.game_manager = GameManager(str(harness_dir))
    spec._controller = None
    spec._game_service = None

    client = TestClient(app)
    yield client, harness_dir
    api_limits.get_limit_enforcer().reset_counters()
    spec._game_service = None
    spec._controller = None
    if spec._engine is not None:
        spec._engine.quit()
        spec._engine = None
    if hasattr(spec._get_controller(), "opponent_mgr"):
        spec._get_controller().opponent_mgr.release()


def _auth(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def _register(client: TestClient, model_id: str, name: str) -> tuple[str, str]:
    reg = client.post("/api/v1/agents", json={"id": model_id, "name": name})
    assert reg.status_code == 200, reg.text
    data = reg.json()
    return data["api_key"], data["model_id"]


def test_lobby_list_create_join_match(lobby_api_client):
    client, _ = lobby_api_client
    host_key, host_id = _register(client, "lobby-host", "Host")
    join_key, join_id = _register(client, "lobby-join", "Joiner")

    empty = client.get("/api/v1/lobbies")
    assert empty.status_code == 200
    assert empty.json()["lobbies"] == []

    create = client.post(
        "/api/v1/lobbies",
        headers=_auth(host_key),
        json={"action": "create", "color_offer": "white"},
    )
    assert create.status_code == 200, create.text
    created = create.json()
    assert created["ok"] is True
    assert created["status"] == "waiting"
    lobby_id = created["lobby_id"]

    listed = client.get("/api/v1/lobbies")
    assert listed.status_code == 200
    rows = listed.json()["lobbies"]
    assert len(rows) == 1
    assert rows[0]["lobby_id"] == lobby_id
    assert rows[0]["color_offer"] == "white"

    waiting = client.get(f"/api/v1/lobbies/{lobby_id}", headers=_auth(host_key))
    assert waiting.status_code == 200
    assert waiting.json()["status"] == "waiting"

    matched = client.post(
        "/api/v1/lobbies",
        headers=_auth(join_key),
        json={"action": "find", "lobby_id": lobby_id},
    )
    assert matched.status_code == 200, matched.text
    match_data = matched.json()
    assert match_data["ok"] is True
    assert match_data["status"] == "matched"
    assert match_data.get("game_id")
    assert match_data.get("your_color") in ("WHITE", "BLACK")
    assert match_data.get("agent_brief")
    assert "poll" in match_data["agent_brief"].lower()

    host_poll = client.get(f"/api/v1/lobbies/{lobby_id}", headers=_auth(host_key))
    assert host_poll.status_code == 200
    host_data = host_poll.json()
    assert host_data["status"] == "matched"
    assert host_data["game_id"] == match_data["game_id"]
    assert host_data.get("your_color") == "WHITE"
    assert host_data.get("agent_brief")

    assert client.get("/api/v1/lobbies").json()["lobbies"] == []


def test_lobby_host_cancel(lobby_api_client):
    client, _ = lobby_api_client
    host_key, _ = _register(client, "cancel-host", "Cancel Host")

    create = client.post(
        "/api/v1/lobbies",
        headers=_auth(host_key),
        json={"action": "create", "color_offer": "random"},
    )
    lobby_id = create.json()["lobby_id"]

    denied = client.delete(f"/api/v1/lobbies/{lobby_id}")
    assert denied.status_code == 401

    cancelled = client.delete(f"/api/v1/lobbies/{lobby_id}", headers=_auth(host_key))
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    assert client.get("/api/v1/lobbies").json()["lobbies"] == []
