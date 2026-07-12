import pytest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
STOCKFISH_PATH = os.path.join(os.path.dirname(__file__), "..", "bin", "stockfish-windows-x86-64.exe")

import chess
from chess_harness.game_manager import GameManager
from chess_harness.engine import StockfishAdapter
from chess_harness.board_controller import BoardController


@pytest.fixture(scope="module")
def engine():
    e = StockfishAdapter()
    yield e
    e.quit()


@pytest.fixture
def ctrl(tmp_path):
    gm = GameManager(base_dir=str(tmp_path / "chess_harness"))
    e = StockfishAdapter()
    c = BoardController(gm, e)
    yield c
    e.quit()


class TestNewGame:
    def test_white_starts(self, ctrl):
        r = ctrl.new_game("g1", "white", 5, model_name="composer-2.5")
        assert r["ok"]
        assert r["your_turn"] is True
        assert "board_path" in r

    def test_black_engine_first(self, ctrl):
        r = ctrl.new_game("g2", "black", 5, model_name="composer-2.5")
        assert r["ok"]
        assert r["your_turn"] is True
        state = ctrl.game_manager.load_state("g2")
        assert len(state["moves"]) == 1
        board = chess.Board(state["board_fen"])
        assert board.turn == chess.BLACK

    def test_invalid_color(self, ctrl):
        r = ctrl.new_game("g3", "red", 5)
        assert not r["ok"]

    def test_invalid_skill(self, ctrl):
        r = ctrl.new_game("g4", "white", 25, model_name="composer-2.5")
        assert not r["ok"]
        assert "0" in r["error"] and "20" in r["error"]

    def test_invalid_game_id(self, ctrl):
        r = ctrl.new_game("bad/id", "white", 5, model_name="composer-2.5")
        assert not r["ok"]


class TestMakeMove:
    def test_legal_move_uci_echo(self, ctrl):
        ctrl.new_game("m1", "white", 5, model_name="composer-2.5")
        r = ctrl.make_agent_move("m1", "e2e4")
        assert r["ok"]
        assert r["your_turn"] is True
        assert "board_path" in r
        assert len(ctrl.game_manager.load_state("m1")["moves"]) == 2

    def test_illegal_move_preserves_fen(self, ctrl):
        ctrl.new_game("m2", "white", 5, model_name="composer-2.5")
        fen_before = ctrl.game_manager.load_state("m2")["board_fen"]
        r = ctrl.make_agent_move("m2", "e2e5")
        assert not r["ok"]
        assert ctrl.game_manager.load_state("m2")["board_fen"] == fen_before

    def test_not_your_turn(self, ctrl):
        ctrl.new_game("m3", "white", 5, model_name="composer-2.5")
        # Corrupt state: set FEN to black's turn while agent is white
        state = ctrl.game_manager.load_state("m3")
        state["board_fen"] = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
        ctrl.game_manager.save_state("m3", state)
        r = ctrl.make_agent_move("m3", "e7e5")
        assert not r["ok"]
        assert "Not your turn" in r["error"]

    def test_move_after_game_over(self, ctrl):
        ctrl.new_game("m4", "white", 5, model_name="composer-2.5")
        ctrl.resign("m4")
        r = ctrl.make_agent_move("m4", "e2e4")
        assert not r["ok"]
        assert "already over" in r["error"]

    def test_san_parsing(self, ctrl):
        ctrl.new_game("m5", "white", 5, model_name="composer-2.5")
        r = ctrl.make_agent_move("m5", "e4")
        assert r["ok"]
        assert r["your_turn"] is True


class TestResign:
    def test_white_resigns(self, ctrl):
        ctrl.new_game("r1", "white", 5, model_name="composer-2.5")
        r = ctrl.resign("r1")
        assert r["ok"]
        assert r["result"] == "0-1"
        assert r["label"] == "Loss"

    def test_black_resigns(self, ctrl):
        ctrl.new_game("r2", "black", 5, model_name="composer-2.5")
        r = ctrl.resign("r2")
        assert r["ok"]
        assert r["result"] == "1-0"
        assert r["label"] == "Loss"


class TestAgentOutcome:
    def test_black_loss_shows_pgn_not_agent_win(self):
        o = BoardController.agent_outcome("BLACK", "1-0")
        assert o["outcome"] == "loss"
        assert o["label"] == "Loss"

    def test_white_loss(self):
        o = BoardController.agent_outcome("WHITE", "0-1")
        assert o["outcome"] == "loss"
        assert o["label"] == "Loss"

    def test_black_win(self):
        o = BoardController.agent_outcome("BLACK", "0-1")
        assert o["outcome"] == "win"
        assert o["label"] == "Win"


class TestSpectatorSummary:
    def test_black_agent_white_first(self, ctrl, tmp_path):
        from chess_harness.elo import ELOLadder

        state = {
            "game_id": "s1",
            "agent_color": "BLACK",
            "opponent_label": "Dika 0.42 (499)",
            "opponent_elo": 499,
            "model_display_name": "mimo-v2.5",
            "model_name": "mimo-v2.5",
            "status": "finished",
            "result": "1-0",
            "board_fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            "elo_before": 985,
            "elo_after": 978,
            "elo_delta": -7,
        }
        summary = ctrl.format_spectator_summary(state)
        assert summary.startswith("WHITE Dika 0.42 (499)")
        assert "vs BLACK mimo-v2.5 (978 ELO)" in summary
        assert summary.endswith("— 1-0")
        assert "985" not in summary
        assert "→" not in summary

    def test_white_agent_white_first(self, ctrl):
        state = {
            "game_id": "s2",
            "agent_color": "WHITE",
            "opponent_label": "Stockfish 17.1 (1788)",
            "opponent_elo": 1788,
            "skill": 5,
            "model_display_name": "mimo-v2.5",
            "model_name": "mimo-v2.5",
            "status": "finished",
            "result": "0-1",
            "board_fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            "elo_before": 996,
            "elo_after": 985,
            "elo_delta": -11,
        }
        summary = ctrl.format_spectator_summary(state)
        assert summary.startswith("WHITE mimo-v2.5 (985 ELO)")
        assert "vs BLACK Stockfish 17.1 (1788)" in summary
        assert summary.endswith("— 0-1")


class TestPGN:
    def test_pgn_headers(self, ctrl):
        ctrl.new_game("p1", "white", 5, model_name="composer-2.5")
        ctrl.make_agent_move("p1", "e2e4")
        r = ctrl.export_pgn("p1", allow_in_progress=True)
        assert r["ok"]
        assert "[Event" in r["pgn"]
        assert "[White" in r["pgn"]
        assert "[Black" in r["pgn"]
        assert "[Result" in r["pgn"]

    def test_pgn_contains_moves(self, ctrl):
        ctrl.new_game("p2", "white", 5, model_name="composer-2.5")
        ctrl.make_agent_move("p2", "e2e4")
        r = ctrl.export_pgn("p2", allow_in_progress=True)
        assert "1." in r["pgn"]
