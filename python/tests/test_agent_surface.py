"""Agent-facing API redaction tests."""

import json
import os
import sys

import chess
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault(
    "STOCKFISH_PATH",
    os.path.join(
        os.path.dirname(__file__), "..", "bin", "stockfish-windows-x86-64.exe"
    ),
)

from chess_harness.board_controller import BoardController
from chess_harness.engine import StockfishAdapter
from chess_harness.game_manager import GameManager
from chess_harness.spectator import app


@pytest.fixture
def ctrl(tmp_path):
    gm = GameManager(base_dir=str(tmp_path / "chess_harness"))
    e = StockfishAdapter()
    c = BoardController(gm, e)
    yield c
    e.quit()


def test_status_no_fen_or_last_move_in_progress(ctrl):
    ctrl.new_game("surf1", "white", 5, model_name="composer-2.5")
    ctrl.make_agent_move("surf1", "e2e4")
    r = ctrl.status("surf1")
    assert r["ok"]
    assert "board_fen" not in r
    assert "last_move" not in r
    assert "move_count" in r


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


def test_move_audit_recorded(ctrl):
    ctrl.new_game("surf6", "white", 5, model_name="composer-2.5")
    ctrl.make_agent_move("surf6", "e2e4")
    audit = ctrl.game_audit("surf6")
    assert audit["ok"]
    assert len(audit["move_audit"]) == 1
    assert audit["move_audit"][0]["move_input"] == "e2e4"
