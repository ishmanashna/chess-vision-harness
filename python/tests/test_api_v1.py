"""Integration tests for /api/v1 public agent HTTP API."""

from __future__ import annotations

import shutil
from typing import Any

import pytest
from fastapi.testclient import TestClient

from conftest import FIXTURES, LOW_OPPONENT

from chess_harness.game_manager import GameManager
from chess_harness.spectator import app

_FORBIDDEN_KEYS = frozenset({"fen", "board_fen", "moves", "start_fen"})


def _assert_no_leaks(obj: Any) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            assert key not in _FORBIDDEN_KEYS
            _assert_no_leaks(value)
    elif isinstance(obj, list):
        for item in obj:
            _assert_no_leaks(item)


@pytest.fixture
def api_client(tmp_path, monkeypatch):
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
    spec._game_service = None
    if hasattr(spec._get_controller(), "opponent_mgr"):
        spec._get_controller().opponent_mgr.release()


def _auth_headers(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def test_api_v1_full_game_flow(api_client):
    client, harness_dir = api_client

    reg = client.post("/api/v1/agents", json={"id": "api-agent", "name": "API Agent"})
    assert reg.status_code == 200
    reg_data = reg.json()
    assert reg_data["ok"] is True
    assert reg_data["model_id"] == "api-agent"
    assert reg_data["name"] == "API Agent"
    assert "api_key" in reg_data
    _assert_no_leaks(reg_data)
    api_key = reg_data["api_key"]

    keys_file = harness_dir / "api_keys.json"
    assert keys_file.exists()
    assert api_key not in keys_file.read_text(encoding="utf-8")

    listed = client.get("/api/v1/agents")
    assert listed.status_code == 200
    agents = listed.json()["agents"]
    assert any(a["id"] == "api-agent" for a in agents)
    assert "api_key" not in listed.text

    create = client.post(
        "/api/v1/games",
        headers=_auth_headers(api_key),
        json={"opponent": LOW_OPPONENT, "agent_color": "white"},
    )
    assert create.status_code == 200
    game = create.json()
    assert game["ok"] is True
    game_id = game["game_id"]
    assert game.get("board_url") == f"/api/v1/games/{game_id}/board"
    assert "board_path" not in game
    _assert_no_leaks(game)

    status = client.get(f"/api/v1/games/{game_id}/status", headers=_auth_headers(api_key))
    assert status.status_code == 200
    status_data = status.json()
    assert status_data["ok"] is True
    _assert_no_leaks(status_data)

    board = client.get(f"/api/v1/games/{game_id}/board", headers=_auth_headers(api_key))
    assert board.status_code == 200
    assert board.headers["content-type"] == "image/png"
    assert board.content[:8] == b"\x89PNG\r\n\x1a\n"

    move = client.post(
        f"/api/v1/games/{game_id}/move/e2e4",
        headers=_auth_headers(api_key),
    )
    assert move.status_code == 200
    move_data = move.json()
    assert move_data["ok"] is True
    _assert_no_leaks(move_data)

    bad_move = client.post(
        f"/api/v1/games/{game_id}/move/a9a9",
        headers=_auth_headers(api_key),
    )
    assert bad_move.status_code == 400
    assert bad_move.json()["ok"] is False
    _assert_no_leaks(bad_move.json())

    pgn_blocked = client.get(f"/api/v1/games/{game_id}/pgn", headers=_auth_headers(api_key))
    assert pgn_blocked.status_code == 400
    assert pgn_blocked.json()["ok"] is False

    resign = client.post(f"/api/v1/games/{game_id}/resign", headers=_auth_headers(api_key))
    assert resign.status_code == 200
    resign_data = resign.json()
    assert resign_data["ok"] is True
    _assert_no_leaks(resign_data)

    pgn = client.get(f"/api/v1/games/{game_id}/pgn", headers=_auth_headers(api_key))
    assert pgn.status_code == 200
    pgn_data = pgn.json()
    assert pgn_data["ok"] is True
    assert "pgn" in pgn_data
    _assert_no_leaks(pgn_data)

    leaderboard = client.get("/api/v1/leaderboard")
    assert leaderboard.status_code == 200
    assert leaderboard.json()["ok"] is True

    legacy = client.get("/api/games")
    assert legacy.status_code == 200
    payload = legacy.json()
    assert isinstance(payload, dict)
    assert isinstance(payload.get("games"), list)
    assert "total" in payload


def test_api_v1_auth_and_model_mismatch(api_client):
    client, _ = api_client

    reg_a = client.post("/api/v1/agents", json={"id": "agent-a", "name": "A"})
    reg_b = client.post("/api/v1/agents", json={"id": "agent-b", "name": "B"})
    key_a = reg_a.json()["api_key"]
    key_b = reg_b.json()["api_key"]

    create = client.post(
        "/api/v1/games",
        headers=_auth_headers(key_a),
        json={"opponent": LOW_OPPONENT, "agent_color": "white"},
    )
    game_id = create.json()["game_id"]

    denied = client.get(f"/api/v1/games/{game_id}/status", headers=_auth_headers(key_b))
    assert denied.status_code == 401

    missing = client.get(f"/api/v1/games/{game_id}/status")
    assert missing.status_code == 401

    unknown = client.get(
        "/api/v1/games/missing-game/status",
        headers=_auth_headers(key_a),
    )
    assert unknown.status_code == 404


def test_api_v1_board_text_fallback_is_live_and_authenticated(api_client):
    client, _ = api_client
    reg = client.post("/api/v1/agents", json={"id": "text-agent"})
    api_key = reg.json()["api_key"]
    other = client.post("/api/v1/agents", json={"id": "other-text-agent"})
    other_key = other.json()["api_key"]

    create = client.post(
        "/api/v1/games",
        headers=_auth_headers(api_key),
        json={"opponent": LOW_OPPONENT, "agent_color": "white"},
    )
    game_id = create.json()["game_id"]

    board = client.get(f"/api/v1/games/{game_id}/board.txt", headers=_auth_headers(api_key))
    assert board.status_code == 200
    assert board.headers["content-type"].startswith("text/plain")
    assert board.headers["cache-control"] == "no-store"
    assert "8 r n b q k b n r" in board.text
    assert "1 R N B Q K B N R" in board.text
    assert "fen" not in board.text.lower()
    assert "legal" not in board.text.lower()

    denied = client.get(f"/api/v1/games/{game_id}/board.txt", headers=_auth_headers(other_key))
    assert denied.status_code == 401

    moved = client.post(f"/api/v1/games/{game_id}/move/e2e4", headers=_auth_headers(api_key))
    assert moved.status_code == 200
    updated = client.get(f"/api/v1/games/{game_id}/board.txt", headers=_auth_headers(api_key))
    assert "4 . . . . P . . ." in updated.text


def test_api_v1_status_includes_play_rating(api_client):
    client, harness_dir = api_client
    reg = client.post("/api/v1/agents", json={"id": "est-agent", "name": "Est Agent"})
    api_key = reg.json()["api_key"]

    create = client.post(
        "/api/v1/games",
        headers=_auth_headers(api_key),
        json={"opponent": LOW_OPPONENT, "agent_color": "white"},
    )
    game_id = create.json()["game_id"]

    gm = GameManager(str(harness_dir))
    state = gm.load_state(game_id)
    state.update(
        {
            "status": "finished",
            "result": "1-0",
            "quality_at": "2026-01-01T00:00:00+00:00",
            "white_accuracy": 90.0,
            "black_accuracy": 55.0,
            "white_play_rating": 1200.0,
            "black_play_rating": 800.0,
            "agent_play_rating": 1200.0,
        }
    )
    gm.save_state(game_id, state)

    status = client.get(f"/api/v1/games/{game_id}/status", headers=_auth_headers(api_key))
    assert status.status_code == 200
    data = status.json()
    assert data["ok"] is True
    assert data["white_play_rating"] == 1200.0
    assert data["black_play_rating"] == 800.0
    assert data["agent_play_rating"] == 1200.0
    assert data["white_accuracy"] == 90.0
    _assert_no_leaks(data)
