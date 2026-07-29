"""Spectator list enrichment: game_type and finished AvE Elo."""

from __future__ import annotations

import shutil

import pytest
from fastapi.testclient import TestClient

from conftest import FIXTURES, LOW_OPPONENT

from chess_harness.game_manager import GameManager
from chess_harness.game_service import GameService
from chess_harness.game_types import DEFAULT_GAME_TYPE, GAME_TYPE_AGENT_VS_AGENT
from chess_harness.limits import HarnessLimits
from chess_harness.models import ModelRegistry
from chess_harness.spectator import _enrich_list_game, app


@pytest.fixture
def list_client(tmp_path, monkeypatch):
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
    try:
        spec._get_controller().opponent_mgr.release()
    except Exception:
        pass


def test_enrich_list_game_defaults_game_type():
    row = _enrich_list_game(
        {
            "game_id": "legacy-ave",
            "state": {
                "status": "in_progress",
                "agent_color": "WHITE",
                "model_name": "composer-2.5",
                "board_fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
                "moves": [],
                "pgn_headers": {},
            },
        }
    )
    assert row["game_type"] == DEFAULT_GAME_TYPE


def test_spectator_list_ave_finished_agent_elo(list_client):
    client, harness_dir = list_client
    registry = ModelRegistry(harness_dir / "models.json")
    start_elo = round(registry.get_elo("composer-2.5"))
    svc = GameService(GameManager(str(harness_dir)))

    created = svc.new_game(
        "ave-finished",
        "white",
        opponent_id=LOW_OPPONENT,
        model_name="composer-2.5",
    )
    assert created.get("ok") is True, created

    resigned = svc.resign("ave-finished")
    assert resigned["ok"] is True

    listed = client.get("/api/games?status=finished")
    assert listed.status_code == 200
    row = next(g for g in listed.json()["games"] if g["game_id"] == "ave-finished")
    assert row["game_type"] == DEFAULT_GAME_TYPE
    assert row["agent_elo"] is not None
    assert row["agent_elo"] != start_elo
    assert row["elo_change"]
    assert str(row["agent_elo"]) in row["elo_change"]


def test_spectator_list_ave_idle_timeout_unranked(list_client, monkeypatch):
    client, harness_dir = list_client
    monkeypatch.setattr(
        "chess_harness.board_controller.load_limits",
        lambda: HarnessLimits(idle_timeout_sec=0),
    )
    svc = GameService(GameManager(str(harness_dir)))
    created = svc.new_game(
        "ave-idle",
        "white",
        opponent_id=LOW_OPPONENT,
        model_name="composer-2.5",
    )
    assert created.get("ok") is True, created

    svc.prune_idle_games()

    listed = client.get("/api/games?status=finished")
    assert listed.status_code == 200
    row = next(g for g in listed.json()["games"] if g["game_id"] == "ave-idle")
    assert row["game_type"] == DEFAULT_GAME_TYPE
    assert row.get("agent_elo") is None
    assert row.get("elo_change") in ("", None)


def test_spectator_list_avaa_white_black_columns(list_client):
    client, harness_dir = list_client
    white = client.post("/api/v1/agents", json={"id": "list-white", "name": "White Agent"})
    black = client.post("/api/v1/agents", json={"id": "list-black", "name": "Black Agent"})
    white_key = white.json()["api_key"]
    create = client.post(
        "/api/v1/games/agent-vs-agent",
        headers={"Authorization": f"Bearer {white_key}"},
        json={"white_model_id": "list-white", "black_model_id": "list-black"},
    )
    assert create.status_code == 200
    game_id = create.json()["game_id"]

    listed = client.get("/api/games?status=in_progress")
    row = next(g for g in listed.json()["games"] if g["game_id"] == game_id)
    assert row["game_type"] == GAME_TYPE_AGENT_VS_AGENT
    assert row["white_display_name"] == "White Agent"
    assert row["black_display_name"] == "Black Agent"
    assert row["white_elo"] is not None
    assert row["black_elo"] is not None
    assert row["agent_elo"] == row["white_elo"]
