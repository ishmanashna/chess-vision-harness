"""Elo and results.jsonl behavior for agent-vs-agent games."""

from __future__ import annotations

import json
import shutil

import pytest
from fastapi.testclient import TestClient

from conftest import FIXTURES, LOW_OPPONENT

from chess_harness.game_manager import GameManager
from chess_harness.game_types import GAME_TYPE_AGENT_VS_AGENT
from chess_harness.game_service import GameService
from chess_harness.models import ModelRegistry
from chess_harness.spectator import app


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
    return create.json()["game_id"]


def test_avaa_resign_dual_elo_and_results(avaa_client):
    client, harness_dir = avaa_client
    white_key, _, white_id, black_id = _register_pair(client)
    registry = ModelRegistry(models_file=harness_dir / "models.json")
    registry.set_elo(white_id, 520)
    registry.set_elo(black_id, 480)

    white_elo_before = round(registry.get_elo(white_id))
    black_elo_before = round(registry.get_elo(black_id))
    game_id = _create_avaa(client, white_key, white_id, black_id)

    resign = client.post(
        f"/api/v1/games/{game_id}/resign",
        headers=_auth(white_key),
    )
    assert resign.status_code == 200, resign.text
    resign_data = resign.json()
    assert resign_data["result"] == "0-1"
    assert resign_data.get("outcome") == "loss"

    registry = ModelRegistry(models_file=harness_dir / "models.json")
    white_elo_after = round(registry.get_elo(white_id))
    black_elo_after = round(registry.get_elo(black_id))
    assert white_elo_after != white_elo_before
    assert black_elo_after != black_elo_before
    assert white_elo_after < white_elo_before
    assert black_elo_after > black_elo_before

    results_path = harness_dir / "results.jsonl"
    rows = [json.loads(line) for line in results_path.read_text(encoding="utf-8").splitlines()]
    game_rows = [r for r in rows if r.get("game_id") == game_id]
    assert len(game_rows) == 2

    white_row = next(r for r in game_rows if r["agent_color"] == "WHITE")
    black_row = next(r for r in game_rows if r["agent_color"] == "BLACK")
    assert white_row["game_type"] == GAME_TYPE_AGENT_VS_AGENT
    assert black_row["game_type"] == GAME_TYPE_AGENT_VS_AGENT
    assert white_row["model_name"] == white_id
    assert black_row["model_name"] == black_id
    assert white_row["opponent_model"] == black_id
    assert black_row["opponent_model"] == white_id
    assert white_row["opponent_elo"] == black_elo_before
    assert black_row["opponent_elo"] == white_elo_before
    assert white_row["result"] == "0-1"
    assert black_row["result"] == "0-1"
    assert white_row["reason"] == "resignation"

    state = GameManager(str(harness_dir)).load_state(game_id)
    assert state is not None
    assert state["white_elo_before"] == white_elo_before
    assert state["white_elo_after"] == white_elo_after
    assert state["black_elo_before"] == black_elo_before
    assert state["black_elo_after"] == black_elo_after


def test_ave_still_one_row_one_elo_update(tmp_path, monkeypatch):
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    models_file = harness_dir / "models.json"
    shutil.copy(FIXTURES / "models.json", models_file)
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness_dir))
    monkeypatch.setenv("MODELS_FILE", str(models_file))

    gm = GameManager(str(harness_dir))
    registry = ModelRegistry(models_file)
    registry.inscribe("agent-a", "Agent A")
    start_elo = round(registry.get_elo("agent-a"))
    svc = GameService(gm)

    created = svc.new_game("ave-1", "white", opponent_id=LOW_OPPONENT, model_name="agent-a")
    assert created.get("ok") is True, created

    resigned = svc.resign("ave-1")
    assert resigned["ok"] is True
    assert resigned["result"] == "0-1"

    rows = [
        json.loads(line)
        for line in (harness_dir / "results.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 1
    assert rows[0]["model_name"] == "agent-a"
    assert rows[0].get("game_type") != GAME_TYPE_AGENT_VS_AGENT

    end_elo = round(ModelRegistry(models_file).get_elo("agent-a"))
    assert end_elo != start_elo
    assert end_elo < start_elo
