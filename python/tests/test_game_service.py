"""Tests for GameService facade and spectator health."""

import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from conftest import DEFAULT_MODEL, LOW_OPPONENT

from chess_harness.game_manager import GameManager
from chess_harness.game_service import DEFAULT_GAME_TYPE, GameService
from chess_harness.spectator import app


@pytest.fixture
def svc(tmp_path, monkeypatch):
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(tmp_path / "harness"))
    gm = GameManager(str(tmp_path / "harness"))
    return GameService(gm)


def test_new_game_persists_game_type(svc):
    result = svc.new_game(
        "gs-type",
        "white",
        opponent_id=LOW_OPPONENT,
        model_name=DEFAULT_MODEL,
    )
    assert result["ok"]
    state = svc.game_manager.load_state("gs-type")
    assert state["game_type"] == DEFAULT_GAME_TYPE


def test_get_board_bytes_returns_png(svc):
    svc.new_game(
        "gs-bytes",
        "white",
        opponent_id=LOW_OPPONENT,
        model_name=DEFAULT_MODEL,
    )
    data = svc.get_board_bytes("gs-bytes")
    assert data[:8] == b"\x89PNG\r\n\x1a\n"


def test_get_board_bytes_missing_game(svc):
    with pytest.raises(ValueError, match="not found"):
        svc.get_board_bytes("missing-game")


def test_resign_prunes_idle(svc, monkeypatch):
    prune_calls = []
    original = svc.controller.check_idle_games

    def track():
        prune_calls.append(True)
        return original()

    svc.controller.check_idle_games = track
    svc.new_game(
        "gs-resign",
        "white",
        opponent_id=LOW_OPPONENT,
        model_name=DEFAULT_MODEL,
    )
    prune_calls.clear()
    result = svc.resign("gs-resign")
    assert result["ok"]
    assert prune_calls


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "status": "up"}
