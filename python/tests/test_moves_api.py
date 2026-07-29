"""Phase 7 tests: agent /moves (AvH only) and spectator /api/games/{id}/moves."""

from __future__ import annotations

import shutil

import pytest
from fastapi.testclient import TestClient

from conftest import FIXTURES, LOW_OPPONENT

from chess_harness.game_manager import GameManager
from chess_harness.spectator import app


def _auth(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


@pytest.fixture
def moves_client(tmp_path, monkeypatch):
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


def _register_agent(client: TestClient, model_id: str = "moves-agent") -> str:
    resp = client.post("/api/v1/agents", json={"id": model_id, "name": model_id})
    assert resp.status_code == 200, resp.text
    return resp.json()["api_key"]


def _create_human_game(
    client: TestClient,
    api_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> str:
    import chess_harness.human_vs_agent as hva

    monkeypatch.setattr(hva.random, "choice", lambda _items: "WHITE")
    create = client.post(
        "/api/v1/games/human",
        headers=_auth(api_key),
        json={"nickname": "Bob"},
    )
    assert create.status_code == 200, create.text
    return create.json()["game_id"]


def test_avh_agent_moves_allowed_mid_game(moves_client, monkeypatch):
    client, _ = moves_client
    api_key = _register_agent(client)
    game_id = _create_human_game(client, api_key, monkeypatch)

    client.post(f"/api/v1/games/{game_id}/move/e2e4", headers=_auth(api_key))

    resp = client.get(f"/api/v1/games/{game_id}/moves", headers=_auth(api_key))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["plies"] == 1
    assert body["plies_detail"] == [{"uci": "e2e4", "san": "e4"}]
    assert body["move_rows"] == [{"num": 1, "white": "e4", "black": ""}]
    assert "fen" not in body
    assert "board_fen" not in body
    assert "start_fen" not in body


def test_ave_agent_moves_denied(moves_client):
    client, _ = moves_client
    api_key = _register_agent(client, "ave-agent")
    create = client.post(
        "/api/v1/games",
        headers=_auth(api_key),
        json={"opponent": LOW_OPPONENT, "agent_color": "white"},
    )
    assert create.status_code == 200, create.text
    game_id = create.json()["game_id"]

    client.post(f"/api/v1/games/{game_id}/move/e2e4", headers=_auth(api_key))

    resp = client.get(f"/api/v1/games/{game_id}/moves", headers=_auth(api_key))
    assert resp.status_code == 403
    assert resp.json()["ok"] is False
    assert "agent vs human" in resp.json()["error"].lower()


def test_avaa_agent_moves_denied(moves_client):
    client, _ = moves_client
    white_key = _register_agent(client, "avaa-w")
    black_key = _register_agent(client, "avaa-b")
    create = client.post(
        "/api/v1/games/agent-vs-agent",
        headers=_auth(white_key),
        json={"white_model_id": "avaa-w", "black_model_id": "avaa-b"},
    )
    assert create.status_code == 200, create.text
    game_id = create.json()["game_id"]

    client.post(f"/api/v1/games/{game_id}/move/e2e4", headers=_auth(white_key))

    resp = client.get(f"/api/v1/games/{game_id}/moves", headers=_auth(white_key))
    assert resp.status_code == 403
    assert resp.json()["ok"] is False

    black_resp = client.get(f"/api/v1/games/{game_id}/moves", headers=_auth(black_key))
    assert black_resp.status_code == 403


def test_spectator_moves_all_game_types(moves_client, monkeypatch):
    client, _ = moves_client

    ave_key = _register_agent(client, "spec-ave")
    ave_create = client.post(
        "/api/v1/games",
        headers=_auth(ave_key),
        json={"opponent": LOW_OPPONENT, "agent_color": "white"},
    )
    assert ave_create.status_code == 200, ave_create.text
    ave_id = ave_create.json()["game_id"]
    client.post(f"/api/v1/games/{ave_id}/move/d2d4", headers=_auth(ave_key))

    ave_resp = client.get(f"/api/games/{ave_id}/moves")
    assert ave_resp.status_code == 200
    ave_body = ave_resp.json()
    assert ave_body["plies"] >= 1
    assert ave_body["plies_detail"][0]["san"] == "d4"
    assert ave_body["move_rows"][0]["white"] == "d4"

    client.post(f"/api/v1/games/{ave_id}/resign", headers=_auth(ave_key))

    game_id = _create_human_game(client, ave_key, monkeypatch)
    client.post(f"/api/v1/games/{game_id}/move/e2e4", headers=_auth(ave_key))

    resp = client.get(f"/api/games/{game_id}/moves")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["plies"] == 1
    assert body["move_rows"] == [{"num": 1, "white": "e4", "black": ""}]
    assert "fen" not in body
