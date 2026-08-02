"""Phase 1 tests for human-vs-agent games."""

from __future__ import annotations

import hashlib
import json
import shutil
from typing import Any

import pytest
from fastapi.testclient import TestClient

from conftest import FIXTURES

from chess_harness.elo import ELOLadder
from chess_harness.game_manager import GameManager
from chess_harness.game_types import GAME_TYPE_HUMAN_VS_AGENT
from chess_harness.models import ModelRegistry
from chess_harness.results import ResultsManager
from chess_harness.spectator import app


@pytest.fixture
def human_client(tmp_path, monkeypatch):
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


def _register_agent(client: TestClient) -> tuple[str, str]:
    resp = client.post("/api/v1/agents", json={"id": "human-agent", "name": "Human Agent"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    return data["api_key"], data["model_id"]


def _create_human_game(
    client: TestClient,
    api_key: str,
    *,
    nickname: str | None = "Alice",
    agent_color: str = "white",
    monkeypatch: pytest.MonkeyPatch | None = None,
) -> dict[str, Any]:
    if monkeypatch is not None:
        import chess_harness.human_vs_agent as hva

        monkeypatch.setattr(hva.random, "choice", lambda _items: agent_color.upper())
    create = client.post(
        "/api/v1/games/human",
        headers=_auth(api_key),
        json={"nickname": nickname} if nickname is not None else {},
    )
    assert create.status_code == 200, create.text
    return create.json()


def test_human_vs_agent_create(human_client, monkeypatch):
    client, harness_dir = human_client
    api_key, model_id = _register_agent(client)
    data = _create_human_game(client, api_key, monkeypatch=monkeypatch)

    assert data["ok"] is True
    assert data["game_type"] == GAME_TYPE_HUMAN_VS_AGENT
    assert data["model_name"] == model_id
    assert data["agent_color"] == "WHITE"
    assert data["human_color"] == "BLACK"
    assert data["human_nickname"] == "Alice"
    assert data["agent_joined"] is False
    assert data.get("your_turn") is True
    play_token = data.get("play_token")
    assert play_token
    assert len(play_token) > 20
    assert data.get("agent_brief")
    assert "agent vs human" in data["agent_brief"].lower()
    assert data.get("play_url") == f"http://127.0.0.1:8765/play/{data['game_id']}?token={play_token}"

    game_id = data["game_id"]
    state = GameManager(str(harness_dir)).load_state(game_id)
    assert state is not None
    assert state["game_type"] == GAME_TYPE_HUMAN_VS_AGENT
    assert state["model_name"] == model_id
    assert state.get("opponent_id") is None
    assert state.get("opponent_uci_config") is None
    assert state["play_token_hash"] == hashlib.sha256(play_token.encode()).hexdigest()
    assert state["agent_joined"] is False
    assert (harness_dir / "games" / game_id / "board.png").exists()


def test_human_vs_agent_agent_joined_and_turn_gating(human_client, monkeypatch):
    client, harness_dir = human_client
    api_key, _ = _register_agent(client)
    data = _create_human_game(client, api_key, monkeypatch=monkeypatch)
    game_id = data["game_id"]

    status_before = client.get(f"/api/v1/games/{game_id}/status", headers=_auth(api_key))
    assert status_before.status_code == 200
    status_json = status_before.json()
    assert status_json["agent_joined"] is True
    assert status_json["your_turn"] is True

    state = GameManager(str(harness_dir)).load_state(game_id)
    assert state is not None
    assert state["agent_joined"] is True

    move = client.post(f"/api/v1/games/{game_id}/move/e2e4", headers=_auth(api_key))
    assert move.status_code == 200, move.text
    assert move.json()["your_turn"] is False

    off_turn = client.post(f"/api/v1/games/{game_id}/move/e7e5", headers=_auth(api_key))
    assert off_turn.status_code == 400
    assert off_turn.json()["error"] == "Not your turn"


def test_human_vs_agent_off_turn_when_black(human_client, monkeypatch):
    client, _ = human_client
    api_key, _ = _register_agent(client)
    data = _create_human_game(client, api_key, agent_color="black", monkeypatch=monkeypatch)
    game_id = data["game_id"]
    assert data["agent_color"] == "BLACK"
    assert data["your_turn"] is False

    off_turn = client.post(f"/api/v1/games/{game_id}/move/e2e4", headers=_auth(api_key))
    assert off_turn.status_code == 400
    assert off_turn.json()["error"] == "Not your turn"


def test_human_vs_agent_resign_skips_elo(human_client, monkeypatch):
    client, harness_dir = human_client
    api_key, model_id = _register_agent(client)
    registry = ModelRegistry(models_file=harness_dir / "models.json")
    registry.set_elo(model_id, 540)
    elo_before = round(registry.get_elo(model_id))

    data = _create_human_game(client, api_key, monkeypatch=monkeypatch)
    game_id = data["game_id"]

    resign = client.post(f"/api/v1/games/{game_id}/resign", headers=_auth(api_key))
    assert resign.status_code == 200, resign.text
    assert resign.json()["result"] == "0-1"

    registry = ModelRegistry(models_file=harness_dir / "models.json")
    elo_after = round(registry.get_elo(model_id))
    assert elo_after == elo_before

    rows = [
        json.loads(line)
        for line in (harness_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    game_rows = [r for r in rows if r.get("game_id") == game_id]
    assert len(game_rows) == 1
    row = game_rows[0]
    assert row["game_type"] == GAME_TYPE_HUMAN_VS_AGENT
    assert row["model_name"] == model_id
    assert row["human_nickname"] == "Alice"
    assert "elo_before" not in row
    assert "opponent_elo" not in row

    state = GameManager(str(harness_dir)).load_state(game_id)
    assert state is not None
    assert "elo_before" not in state
    assert "elo_after" not in state


def test_human_vs_agent_excluded_from_rebuild_and_counts(human_client, monkeypatch):
    client, harness_dir = human_client
    api_key, model_id = _register_agent(client)
    registry = ModelRegistry(models_file=harness_dir / "models.json")
    registry.set_elo(model_id, 600)

    data = _create_human_game(client, api_key, monkeypatch=monkeypatch)
    game_id = data["game_id"]
    resign = client.post(f"/api/v1/games/{game_id}/resign", headers=_auth(api_key))
    assert resign.status_code == 200

    results = ResultsManager(base_dir=str(harness_dir))
    assert results.count_by_model().get(model_id, 0) == 0

    results_path = harness_dir / "results.jsonl"
    ave_row = {
        "ts": "2026-01-01T00:00:00",
        "game_id": "ave-only",
        "model_name": model_id,
        "agent_color": "WHITE",
        "opponent_id": "stockfish:0",
        "opponent_elo": 800,
        "result": "1-0",
        "reason": "checkmate",
        "plies": 10,
        "pgn_path": "games/ave-only/game.pgn",
    }
    with open(results_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(ave_row) + "\n")

    ladder = ELOLadder(base_dir=str(harness_dir), registry=registry)
    ladder.process_results_file()
    rebuilt_elo = round(registry.get_elo(model_id))
    assert rebuilt_elo != 600
    assert results.count_by_model().get(model_id, 0) == 1


def test_human_vs_agent_board_text_fallback(human_client, monkeypatch):
    client, _ = human_client
    api_key, _ = _register_agent(client)
    data = _create_human_game(client, api_key, monkeypatch=monkeypatch)
    game_id = data["game_id"]

    board = client.get(f"/api/v1/games/{game_id}/board.txt", headers=_auth(api_key))
    assert board.status_code == 200
    assert "8 r n b q k b n r" in board.text
    assert "side_to_move: white" in board.text

    move = client.post(f"/api/v1/games/{game_id}/move/e2e4", headers=_auth(api_key))
    assert move.status_code == 200
    updated = client.get(f"/api/v1/games/{game_id}/board.txt", headers=_auth(api_key))
    assert updated.status_code == 200
    assert "4 . . . . P . . ." in updated.text

    play_token = data["play_token"]
    browser_access = client.get(
        f"/api/play/{game_id}/position",
        headers={"Authorization": f"Bearer {play_token}"},
    )
    assert browser_access.status_code == 200
