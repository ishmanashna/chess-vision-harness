"""Integration tests for agent-vs-agent play (Phases 0–1)."""

from __future__ import annotations

import shutil
from typing import Any

import pytest
from fastapi.testclient import TestClient

from conftest import FIXTURES

from chess_harness.game_manager import GameManager
from chess_harness.game_types import GAME_TYPE_AGENT_VS_AGENT
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
def avaa_client(tmp_path, monkeypatch):
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


def _register_pair(client: TestClient) -> tuple[str, str, str, str]:
    white = client.post("/api/v1/agents", json={"id": "avaa-white", "name": "White Agent"})
    black = client.post("/api/v1/agents", json={"id": "avaa-black", "name": "Black Agent"})
    assert white.status_code == 200
    assert black.status_code == 200
    white_key = white.json()["api_key"]
    black_key = black.json()["api_key"]
    return white_key, black_key, "avaa-white", "avaa-black"


def _create_avaa(
    client: TestClient,
    white_key: str,
    white_id: str,
    black_id: str,
) -> str:
    create = client.post(
        "/api/v1/games/agent-vs-agent",
        headers=_auth(white_key),
        json={"white_model_id": white_id, "black_model_id": black_id},
    )
    assert create.status_code == 200, create.text
    data = create.json()
    assert data["ok"] is True
    assert data.get("agent_color") == "WHITE"
    assert data.get("your_turn") is True
    _assert_no_leaks(data)
    return data["game_id"]


def test_avaa_new_game_no_engine(avaa_client):
    client, harness_dir = avaa_client
    white_key, _, white_id, black_id = _register_pair(client)
    game_id = _create_avaa(client, white_key, white_id, black_id)

    state = GameManager(str(harness_dir)).load_state(game_id)
    assert state is not None
    assert state["game_type"] == GAME_TYPE_AGENT_VS_AGENT
    assert state.get("opponent_id") is None
    assert state.get("opponent_uci_config") is None
    assert state["white_model_id"] == white_id
    assert state["black_model_id"] == black_id

    game_dir = harness_dir / "games" / game_id
    assert (game_dir / "board.png").exists()
    assert (game_dir / "board_white.png").exists()
    assert (game_dir / "board_black.png").exists()


def test_avaa_turn_and_board_access(avaa_client):
    client, _ = avaa_client
    white_key, black_key, white_id, black_id = _register_pair(client)
    game_id = _create_avaa(client, white_key, white_id, black_id)

    white_board = client.get(f"/api/v1/games/{game_id}/board", headers=_auth(white_key))
    assert white_board.status_code == 200
    assert white_board.content[:8] == b"\x89PNG\r\n\x1a\n"

    black_board_wait = client.get(f"/api/v1/games/{game_id}/board", headers=_auth(black_key))
    assert black_board_wait.status_code == 403

    move = client.post(
        f"/api/v1/games/{game_id}/move/e2e4",
        headers=_auth(white_key),
    )
    assert move.status_code == 200
    move_data = move.json()
    assert move_data["your_turn"] is False
    _assert_no_leaks(move_data)

    white_status = client.get(f"/api/v1/games/{game_id}/status", headers=_auth(white_key))
    assert white_status.status_code == 200
    assert white_status.json()["your_turn"] is False

    black_status = client.get(f"/api/v1/games/{game_id}/status", headers=_auth(black_key))
    assert black_status.status_code == 200
    assert black_status.json()["your_turn"] is True

    white_board_after = client.get(f"/api/v1/games/{game_id}/board", headers=_auth(white_key))
    assert white_board_after.status_code == 403

    black_board = client.get(f"/api/v1/games/{game_id}/board", headers=_auth(black_key))
    assert black_board.status_code == 200


def test_avaa_off_turn_move_400(avaa_client):
    client, _ = avaa_client
    white_key, black_key, white_id, black_id = _register_pair(client)
    game_id = _create_avaa(client, white_key, white_id, black_id)

    off_turn = client.post(
        f"/api/v1/games/{game_id}/move/e7e5",
        headers=_auth(black_key),
    )
    assert off_turn.status_code == 400
    assert off_turn.json()["error"] == "Not your turn"


def test_avaa_few_plies_no_engine(avaa_client):
    client, harness_dir = avaa_client
    white_key, black_key, white_id, black_id = _register_pair(client)
    game_id = _create_avaa(client, white_key, white_id, black_id)

    sequence = [
        (white_key, "e2e4"),
        (black_key, "e7e5"),
        (white_key, "g1f3"),
        (black_key, "b8c6"),
    ]
    for key, uci in sequence:
        resp = client.post(
            f"/api/v1/games/{game_id}/move/{uci}",
            headers=_auth(key),
        )
        assert resp.status_code == 200, resp.text
        _assert_no_leaks(resp.json())

    state = GameManager(str(harness_dir)).load_state(game_id)
    assert state is not None
    assert len(state["moves"]) == 4
    assert state["moves"] == ["e2e4", "e7e5", "g1f3", "b8c6"]
    assert state["status"] == "in_progress"


def test_avaa_participant_auth(avaa_client):
    client, harness_dir = avaa_client
    white_key, black_key, white_id, black_id = _register_pair(client)
    from chess_harness.api_keys import ApiKeyStore

    outsider_key = ApiKeyStore(path=harness_dir / "api_keys.json").create("composer-2.5")
    game_id = _create_avaa(client, white_key, white_id, black_id)

    denied = client.get(f"/api/v1/games/{game_id}/status", headers=_auth(outsider_key))
    assert denied.status_code == 401

    black_create = client.post(
        "/api/v1/games/agent-vs-agent",
        headers=_auth(black_key),
        json={"white_model_id": white_id, "black_model_id": black_id},
    )
    assert black_create.status_code == 200
    assert black_create.json().get("agent_color") == "BLACK"
    assert black_create.json().get("your_turn") is False
