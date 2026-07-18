"""Tests for ambiguous SAN handling."""

import os
import sys

import chess
import pytest

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


@pytest.fixture
def ctrl(tmp_path):
    gm = GameManager(base_dir=str(tmp_path / "chess_harness"))
    e = StockfishAdapter()
    c = BoardController(gm, e)
    yield c
    e.quit()


def test_ambiguous_san_returns_error_with_board(ctrl):
    ctrl.new_game("amb1", "white", 5, model_name="composer-2.5")
    state = ctrl.game_manager.load_state("amb1")
    # Two rooks can both move to e4
    state["board_fen"] = "8/8/8/8/3R1R2/8/4K2k/8 w - - 0 1"
    ctrl.game_manager.save_state("amb1", state)

    r = ctrl.make_agent_move("amb1", "Re4")
    assert not r["ok"]
    assert "Ambiguous" in r["error"]
    assert "board_path" in r
