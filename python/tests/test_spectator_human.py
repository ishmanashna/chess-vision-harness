"""Spectator UI coverage for human-vs-agent games."""

from __future__ import annotations

import shutil

import pytest
from fastapi.testclient import TestClient

from conftest import FIXTURES

from chess_harness.board_controller import BoardController
from chess_harness.game_types import GAME_TYPE_HUMAN_VS_AGENT
from chess_harness.spectator import _active_card, app
from test_human_vs_agent import _auth, _create_human_game, _register_agent, human_client


def test_side_labels_human():
    state = {
        "game_type": GAME_TYPE_HUMAN_VS_AGENT,
        "human_nickname": "Alice",
        "model_display_name": "Vision Agent",
        "agent_color": "WHITE",
    }
    assert BoardController.side_labels(state) == {
        "white": "Vision Agent",
        "black": "Alice",
    }


def test_active_card_human_show_eval():
    state = {
        "game_type": GAME_TYPE_HUMAN_VS_AGENT,
        "human_nickname": "Alice",
        "model_display_name": "Vision Agent",
        "model_name": "vision-agent",
        "agent_color": "WHITE",
        "human_color": "BLACK",
        "board_fen": "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1",
        "moves": ["e2e4"],
        "status": "in_progress",
    }
    card = _active_card(state, "g-human")
    assert card["game_type"] == GAME_TYPE_HUMAN_VS_AGENT
    assert card["turn_label"] == "Alice to move"
    assert card["show_eval"] is True
    assert card["eval_ui"] is not None
    assert card["agent_elo"] is not None


def test_spectator_list_state_and_eval_human(human_client, monkeypatch):
    client, _ = human_client
    api_key, _ = _register_agent(client)
    created = _create_human_game(client, api_key, nickname="Alice", monkeypatch=monkeypatch)
    game_id = created["game_id"]

    listed = client.get("/api/games?status=in_progress")
    assert listed.status_code == 200
    row = next(g for g in listed.json()["games"] if g["game_id"] == game_id)
    assert row["game_type"] == GAME_TYPE_HUMAN_VS_AGENT
    assert row["model_name"] == "Human Agent"
    assert row["opponent_label"] == "Alice"
    assert row["white_display_name"]
    assert row["black_display_name"] == "Alice"
    assert row["white_elo"] is not None
    assert row["black_elo"] is None
    assert "to move" in row["turn"]
    assert row.get("elo_change") in ("", None)
    card = row["active_card"]
    assert card["show_eval"] is True
    assert card["eval_ui"] is not None

    state = client.get(f"/api/games/{game_id}/state")
    assert state.status_code == 200
    body = state.json()
    assert body["game_type"] == GAME_TYPE_HUMAN_VS_AGENT
    assert body["show_eval"] is True
    assert body.get("eval_ui") is not None
    assert body["white_display_name"] == "Human Agent"
    assert body["black_display_name"] == "Alice"
    assert body["agent_elo"] is not None
    assert body.get("elo_change") in ("", None)

    eval_resp = client.get(f"/api/games/{game_id}/eval")
    assert eval_resp.status_code == 200
    eval_body = eval_resp.json()
    assert eval_body["ok"] is True
    assert eval_body.get("eval_ui") is not None
