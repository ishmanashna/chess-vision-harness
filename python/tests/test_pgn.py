import pytest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
STOCKFISH_PATH = os.path.join(os.path.dirname(__file__), "..", "bin", "stockfish-windows-x86-64.exe")
os.environ.setdefault("STOCKFISH_PATH", STOCKFISH_PATH)

import chess
import chess.pgn
from chess_harness.game_manager import GameManager
from chess_harness.board_controller import BoardController


@pytest.fixture
def ctrl(tmp_path):
    gm = GameManager(base_dir=str(tmp_path / "chess_harness"))
    c = BoardController(gm)
    yield c
    c.opponent_mgr.release()
    if c._eval_engine is not None:
        c._eval_engine.quit()
        c._eval_engine = None


class TestPGNExport:
    def test_seven_tag_roster(self, ctrl):
        ctrl.new_game("pgn1", "white", 5, model_name="composer-2.5")
        r = ctrl.export_pgn("pgn1", allow_in_progress=True)
        assert r["ok"]
        pgn = r["pgn"]
        for tag in ["Event", "Site", "Date", "Round", "White", "Black", "Result"]:
            assert f'[{tag}' in pgn
        assert "[Annotator" not in pgn

    def test_result_after_resign(self, ctrl):
        ctrl.new_game("pgn2", "white", 5, model_name="composer-2.5")
        ctrl.make_agent_move("pgn2", "e2e4")
        ctrl.resign("pgn2")
        r = ctrl.export_pgn("pgn2")
        assert "0-1" in r["pgn"]

    def test_pgn_file_written(self, ctrl):
        ctrl.new_game("pgn3", "white", 5, model_name="composer-2.5")
        ctrl.make_agent_move("pgn3", "e2e4")
        r = ctrl.export_pgn("pgn3", allow_in_progress=True)
        assert r["ok"]
        pgn_path = ctrl.game_manager.get_pgn_path("pgn3")
        assert pgn_path.exists()
        content = pgn_path.read_text()
        assert "[Event" in content
