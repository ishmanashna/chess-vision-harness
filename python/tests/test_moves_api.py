"""Tests for spectator /api/games/{id}/moves (agent /api/v1/.../moves removed)."""

from __future__ import annotations

import re
import shutil

import pytest
from fastapi.testclient import TestClient

from conftest import FIXTURES, LOW_OPPONENT

from chess_harness.game_manager import GameManager
from chess_harness.spectator import app

_GAME_ID_RE = re.compile(r"^game-[A-Za-z0-9_-]{16,}$")


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


def test_avh_agent_moves_route_removed(moves_client, monkeypatch):
    client, _ = moves_client
    api_key = _register_agent(client)
    game_id = _create_human_game(client, api_key, monkeypatch)

    client.post(f"/api/v1/games/{game_id}/move/e2e4", headers=_auth(api_key))

    resp = client.get(f"/api/v1/games/{game_id}/moves", headers=_auth(api_key))
    assert resp.status_code == 404


def test_ave_agent_moves_route_removed(moves_client):
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
    assert resp.status_code == 404


def test_avaa_agent_moves_route_removed(moves_client):
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
    assert resp.status_code == 404

    black_resp = client.get(f"/api/v1/games/{game_id}/moves", headers=_auth(black_key))
    assert black_resp.status_code == 404


def test_spectator_moves_all_game_types(moves_client, monkeypatch):
    client, _ = moves_client

    ave_key = _register_agent(client, "spec-ave")
    white_key = _register_agent(client, "spec-avaa-w")
    black_key = _register_agent(client, "spec-avaa-b")

    ave_create = client.post(
        "/api/v1/games",
        headers=_auth(ave_key),
        json={"opponent": LOW_OPPONENT, "agent_color": "white"},
    )
    assert ave_create.status_code == 200, ave_create.text
    ave_id = ave_create.json()["game_id"]
    assert _GAME_ID_RE.match(ave_id), ave_id
    client.post(f"/api/v1/games/{ave_id}/move/d2d4", headers=_auth(ave_key))

    ave_resp = client.get(f"/api/games/{ave_id}/moves")
    assert ave_resp.status_code == 200
    ave_body = ave_resp.json()
    assert ave_body["plies"] >= 1
    assert ave_body["move_rows"] == []
    assert ave_body["plies_detail"] == []

    client.post(f"/api/v1/games/{ave_id}/resign", headers=_auth(ave_key))

    ave_finished = client.get(f"/api/games/{ave_id}/moves")
    assert ave_finished.status_code == 200
    finished_body = ave_finished.json()
    assert finished_body["plies"] >= 1
    assert finished_body["plies_detail"][0]["san"] == "d4"
    assert finished_body["move_rows"][0]["white"] == "d4"

    avaa_create = client.post(
        "/api/v1/games/agent-vs-agent",
        headers=_auth(white_key),
        json={"white_model_id": "spec-avaa-w", "black_model_id": "spec-avaa-b"},
    )
    assert avaa_create.status_code == 200, avaa_create.text
    avaa_id = avaa_create.json()["game_id"]
    client.post(f"/api/v1/games/{avaa_id}/move/e2e4", headers=_auth(white_key))

    avaa_resp = client.get(f"/api/games/{avaa_id}/moves")
    assert avaa_resp.status_code == 200
    avaa_body = avaa_resp.json()
    assert avaa_body["plies"] == 1
    assert avaa_body["move_rows"] == []
    assert avaa_body["plies_detail"] == []

    game_id = _create_human_game(client, ave_key, monkeypatch)
    client.post(f"/api/v1/games/{game_id}/move/e2e4", headers=_auth(ave_key))

    resp = client.get(f"/api/games/{game_id}/moves")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["plies"] == 1
    assert body["move_rows"] == [{"num": 1, "white": "e4", "black": ""}]
    assert body["plies_detail"] == [{"uci": "e2e4", "san": "e4"}]
    assert "fen" not in body
