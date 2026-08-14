"""Agent-facing API redaction tests."""

import json

import chess
import pytest
from fastapi.testclient import TestClient

from chess_harness.spectator import app


def test_status_no_fen_or_last_move_in_progress(ctrl):
    ctrl.new_game("surf1", "white", 5, model_name="composer-2.5")
    ctrl.make_agent_move("surf1", "e2e4")
    r = ctrl.status("surf1")
    assert r["ok"]
    assert "board_fen" not in r
    assert "last_move" not in r
    assert "move_count" in r


def test_status_finished_sets_game_over(ctrl):
    ctrl.new_game("surf-idle", "white", 5, model_name="composer-2.5")
    ended = ctrl.end_no_result("surf-idle", reason="inactivity")
    assert ended["ok"]
    r = ctrl.status("surf-idle")
    assert r["ok"]
    assert r["result"] == "*"
    assert r["game_over"] is True
    assert r["your_turn"] is False


def test_board_no_fen(ctrl):
    ctrl.new_game("surf2", "white", 5, model_name="composer-2.5")
    r = ctrl.get_board("surf2")
    assert r["ok"]
    assert "board_fen" not in r
    assert "board_path" in r


def test_pgn_blocked_in_progress(ctrl):
    ctrl.new_game("surf3", "white", 5, model_name="composer-2.5")
    r = ctrl.export_pgn("surf3")
    assert not r["ok"]
    assert "after the game ends" in r["error"].lower()


def test_ambiguous_san_no_uci_hints(ctrl):
    ctrl.new_game("surf4", "white", 5, model_name="composer-2.5")
    state = ctrl.game_manager.load_state("surf4")
    state["board_fen"] = "8/8/8/8/3R1R2/8/4K2k/8 w - - 0 1"
    ctrl.game_manager.save_state("surf4", state)
    r = ctrl.make_agent_move("surf4", "Re4")
    assert not r["ok"]
    assert "Ambiguous" in r["error"]
    import re

    assert not re.search(r"[a-h][1-8][a-h][1-8]", r["error"])


def test_spectator_state_no_fen(ctrl, monkeypatch):
    monkeypatch.setenv("CHESS_HARNESS_DEBUG", "")
    gm = ctrl.game_manager
    monkeypatch.setattr("chess_harness.spectator.game_manager", gm)
    ctrl.new_game("surf5", "white", 5, model_name="composer-2.5")
    client = TestClient(app)
    r = client.get("/api/games/surf5/state")
    assert r.status_code == 200
    data = r.json()
    assert "board_fen" not in data
    assert "moves" not in data
    assert "move_rows" not in data
    assert data.get("game_id") == "surf5"
    assert "board_path" not in data
    assert data.get("board_url") == "/g/surf5/board.png"


def test_debug_param_ignored_without_env(ctrl, monkeypatch):
    monkeypatch.delenv("CHESS_HARNESS_DEBUG", raising=False)
    gm = ctrl.game_manager
    monkeypatch.setattr("chess_harness.spectator.game_manager", gm)
    ctrl.new_game("surf-debug", "white", 5, model_name="composer-2.5")
    client = TestClient(app)
    r = client.get("/api/games/surf-debug/state?debug=1")
    assert r.status_code == 200
    data = r.json()
    assert "board_fen" not in data
    assert "moves" not in data
    assert "move_rows" not in data


def test_move_audit_recorded(ctrl):
    ctrl.new_game("surf6", "white", 5, model_name="composer-2.5")
    ctrl.make_agent_move("surf6", "e2e4")
    audit = ctrl.game_audit("surf6")
    assert audit["ok"]
    assert len(audit["move_audit"]) == 1
    assert audit["move_audit"][0]["move_input"] == "e2e4"
