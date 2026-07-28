"""Spectator UI coverage for agent-vs-agent games."""

from __future__ import annotations

import shutil

import pytest
from fastapi.testclient import TestClient

from conftest import FIXTURES

from chess_harness.board_controller import BoardController
from chess_harness.game_manager import GameManager
from chess_harness.game_types import GAME_TYPE_AGENT_VS_AGENT
from chess_harness.spectator import _active_card, app


@pytest.fixture
def avaa_spectator_client(tmp_path, monkeypatch):
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


def _register_and_create(client: TestClient) -> str:
    white = client.post("/api/v1/agents", json={"id": "spec-white", "name": "White Agent"})
    black = client.post("/api/v1/agents", json={"id": "spec-black", "name": "Black Agent"})
    white_key = white.json()["api_key"]
    create = client.post(
        "/api/v1/games/agent-vs-agent",
        headers={"Authorization": f"Bearer {white_key}"},
        json={"white_model_id": "spec-white", "black_model_id": "spec-black"},
    )
    assert create.status_code == 200
    return create.json()["game_id"]


def test_format_avaa_elo_change_dual():
    state = {
        "white_display_name": "Alpha",
        "black_display_name": "Beta",
        "white_elo_before": 500,
        "white_elo_after": 512,
        "black_elo_before": 480,
        "black_elo_after": 468,
    }
    text = BoardController.format_avaa_elo_change(state)
    assert "Alpha 500 → 512 (+12)" in text
    assert "Beta 480 → 468 (-12)" in text


def test_side_labels_avaa():
    state = {
        "game_type": GAME_TYPE_AGENT_VS_AGENT,
        "white_display_name": "Alpha",
        "black_display_name": "Beta",
    }
    assert BoardController.side_labels(state) == {"white": "Alpha", "black": "Beta"}


def test_active_card_avaa_turn_label():
    state = {
        "game_type": GAME_TYPE_AGENT_VS_AGENT,
        "white_display_name": "White Agent",
        "black_display_name": "Black Agent",
        "white_model_id": "w",
        "black_model_id": "b",
        "board_fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",
        "moves": ["e2e4"],
        "status": "in_progress",
    }
    card = _active_card(state, "g-avaa")
    assert card["turn_label"] == "Black Agent to move"
    assert card["game_type"] == GAME_TYPE_AGENT_VS_AGENT
    assert card["eval_ui"]["black_at_bottom"] is False


def test_spectator_list_and_state_avaa(avaa_spectator_client):
    client, _ = avaa_spectator_client
    game_id = _register_and_create(client)

    listed = client.get("/api/games?status=in_progress")
    assert listed.status_code == 200
    games = listed.json()["games"]
    row = next(g for g in games if g["game_id"] == game_id)
    assert row["game_type"] == GAME_TYPE_AGENT_VS_AGENT
    assert row["white_display_name"] == "White Agent"
    assert row["black_display_name"] == "Black Agent"
    assert row["opponent_label"] == "Black Agent"
    assert "Agent to move" in row["turn"]

    state = client.get(f"/api/games/{game_id}/state")
    assert state.status_code == 200
    body = state.json()
    assert body["game_type"] == GAME_TYPE_AGENT_VS_AGENT
    assert body["white_display_name"] == "White Agent"
    assert body["black_display_name"] == "Black Agent"
    assert body["eval_ui"]["bottom_label"] == "White Agent"
