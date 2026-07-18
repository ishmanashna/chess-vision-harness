"""Tests for FEN-started games and PGN export."""

import os
import sys

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

FEN = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"


@pytest.fixture
def ctrl(tmp_path):
    gm = GameManager(base_dir=str(tmp_path / "chess_harness"))
    e = StockfishAdapter()
    c = BoardController(gm, e)
    yield c
    e.quit()


def test_pgn_from_custom_fen(ctrl, monkeypatch):
    monkeypatch.setenv("CHESS_HARNESS_DEBUG", "1")
    r = ctrl.new_game("fen1", "black", 5, fen=FEN, model_name="composer-2.5")
    assert r["ok"]
    ctrl.make_agent_move("fen1", "e5")
    pgn = ctrl.export_pgn("fen1", allow_in_progress=True)
    assert pgn["ok"]
    assert "[FEN" in pgn["pgn"]
    assert "[SetUp" in pgn["pgn"]
    assert "e5" in pgn["pgn"]


def test_new_game_rejects_duplicate_id(ctrl):
    assert ctrl.new_game("dup1", "white", 5, model_name="composer-2.5")["ok"]
    r = ctrl.new_game("dup1", "white", 5, model_name="composer-2.5")
    assert not r["ok"]
    assert "already" in r["error"].lower()
