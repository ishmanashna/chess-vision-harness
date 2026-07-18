import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
os.environ.setdefault(
    "STOCKFISH_PATH",
    os.path.join(os.path.dirname(__file__), "..", "bin", "stockfish-windows-x86-64.exe"),
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


def test_idle_auto_resign(ctrl, monkeypatch):
    monkeypatch.setattr("chess_harness.board_controller.IDLE_TIMEOUT_SECONDS", 0)
    r = ctrl.new_game("idle1", "white", 5, model_name="composer-2.5")
    assert r["ok"]
    resigned = ctrl.check_idle_games()
    assert "idle1" in resigned
    state = ctrl.game_manager.load_state("idle1")
    assert state["status"] == "finished"
    assert state["result"] == "0-1"
