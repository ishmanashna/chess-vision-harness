"""Board controller and game manager tests (consolidated from test_moves)."""

from pathlib import Path

import chess
import pytest

from chess_harness.board_controller import BoardController
from chess_harness.render_pillow import ChessBoardRenderer


class TestGameManager:
    def test_validate_game_id_valid(self, game_manager):
        assert game_manager.validate_game_id("game1") is True
        assert game_manager.validate_game_id("test_game") is True
        assert game_manager.validate_game_id("skill5-game1") is True
        assert game_manager.validate_game_id("default") is True

    def test_validate_game_id_invalid(self, game_manager):
        assert game_manager.validate_game_id("") is False
        assert game_manager.validate_game_id("game/../../../etc/passwd") is False
        assert game_manager.validate_game_id("game with spaces") is False
        assert game_manager.validate_game_id("a" * 65) is False

    def test_game_directories(self, game_manager):
        game_id = "test_game"
        game_dir = game_manager.get_game_dir(game_id)
        state_path = game_manager.get_state_path(game_id)
        assert state_path.name == "state.json"
        assert state_path.parent == game_dir
        game_manager.save_state(game_id, {"test": True})
        assert game_dir.exists()


class TestBoardController:
    def test_new_game_white(self, controller, game_manager):
        result = controller.new_game("test1", "white", 5, model_name="composer-2.5")
        assert result["ok"] is True
        assert result["game_id"] == "test1"
        assert result["your_turn"] is True
        assert "board_path" in result
        state = game_manager.load_state("test1")
        assert state is not None
        assert state["status"] == "in_progress"
        assert state["agent_color"] == "WHITE"
        assert game_manager.get_board_path("test1").exists()

    def test_new_game_black(self, controller, game_manager):
        result = controller.new_game("test2", "black", 5, model_name="composer-2.5")
        assert result["ok"] is True
        assert result["your_turn"] is True
        state = game_manager.load_state("test2")
        assert state["status"] == "in_progress"
        assert state["agent_color"] == "BLACK"
        assert len(state["moves"]) == 1

        board_path = game_manager.get_board_path("test2")
        board = chess.Board(state["board_fen"])
        highlights = controller.highlight_moves(state)
        check = board.king(board.turn) if board.is_check() else None
        ref_white = Path(game_manager.base_dir) / "_orient_white.png"
        ref_black = Path(game_manager.base_dir) / "_orient_black.png"
        renderer = ChessBoardRenderer()
        renderer.render_board(
            board, ref_white, last_moves=highlights, bottom_color="white", check_square=check
        )
        renderer.render_board(
            board, ref_black, last_moves=highlights, bottom_color="black", check_square=check
        )
        assert board_path.read_bytes() == ref_white.read_bytes()
        assert board_path.read_bytes() != ref_black.read_bytes()

    def test_invalid_game_id(self, controller):
        result = controller.new_game("invalid/id", "white", 5, model_name="composer-2.5")
        assert result["ok"] is False
        assert "Invalid game_id" in result["error"]

    def test_invalid_color(self, controller):
        result = controller.new_game("test3", "red", 5)
        assert result["ok"] is False
        assert "agent_color must be" in result["error"]

    def test_invalid_skill(self, controller):
        result = controller.new_game("test4", "white", 25, model_name="composer-2.5")
        assert result["ok"] is False
        assert "20" in result["error"]

    def test_make_move_legal(self, controller, game_manager):
        controller.new_game("test5", "white", 5, model_name="composer-2.5")
        result = controller.make_agent_move("test5", "e2e4")
        assert result["ok"] is True
        assert result["your_turn"] is True
        assert "board_path" in result
        assert len(game_manager.load_state("test5")["moves"]) == 2

    def test_make_move_illegal(self, controller, game_manager):
        controller.new_game("test6", "white", 5, model_name="composer-2.5")
        fen_before = game_manager.load_state("test6")["board_fen"]
        result = controller.make_agent_move("test6", "e2e5")
        assert result["ok"] is False
        assert "Illegal move" in result["error"]
        state = game_manager.load_state("test6")
        assert len(state["moves"]) == 0
        assert state["board_fen"] == fen_before

    def test_make_move_not_your_turn(self, controller, game_manager):
        controller.new_game("test7", "white", 5, model_name="composer-2.5")
        state = game_manager.load_state("test7")
        state["board_fen"] = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1"
        game_manager.save_state("test7", state)
        result = controller.make_agent_move("test7", "e7e5")
        assert result["ok"] is False
        assert "Not your turn" in result["error"]

    def test_move_after_game_over(self, controller):
        controller.new_game("m4", "white", 5, model_name="composer-2.5")
        controller.resign("m4")
        result = controller.make_agent_move("m4", "e2e4")
        assert result["ok"] is False
        assert "already over" in result["error"]

    def test_san_parsing(self, controller):
        controller.new_game("m5", "white", 5, model_name="composer-2.5")
        result = controller.make_agent_move("m5", "e4")
        assert result["ok"] is True
        assert result["your_turn"] is True

    def test_resign(self, controller, game_manager):
        controller.new_game("test8", "white", 5, model_name="composer-2.5")
        result = controller.resign("test8")
        assert result["ok"] is True
        assert result["result"] == "0-1"
        assert result["label"] == "Loss"
        state = game_manager.load_state("test8")
        assert state["status"] == "finished"
        assert state["result"] == "0-1"

    def test_black_resigns(self, controller):
        controller.new_game("r2", "black", 5, model_name="composer-2.5")
        result = controller.resign("r2")
        assert result["ok"] is True
        assert result["result"] == "1-0"
        assert result["label"] == "Loss"

    def test_export_pgn(self, controller, game_manager):
        controller.new_game("test9", "white", 5, model_name="composer-2.5")
        controller.make_agent_move("test9", "e2e4")
        result = controller.export_pgn("test9", allow_in_progress=True)
        assert result["ok"] is True
        assert "pgn" in result
        assert "[Event " in result["pgn"]
        assert "[White" in result["pgn"]
        assert "[Black" in result["pgn"]
        assert "[Result" in result["pgn"]
        assert "1." in result["pgn"]
        assert game_manager.get_pgn_path("test9").exists()


class TestAgentOutcome:
    def test_black_loss_shows_pgn_not_agent_win(self):
        outcome = BoardController.agent_outcome("BLACK", "1-0")
        assert outcome["outcome"] == "loss"
        assert outcome["label"] == "Loss"

    def test_white_loss(self):
        outcome = BoardController.agent_outcome("WHITE", "0-1")
        assert outcome["outcome"] == "loss"
        assert outcome["label"] == "Loss"

    def test_black_win(self):
        outcome = BoardController.agent_outcome("BLACK", "0-1")
        assert outcome["outcome"] == "win"
        assert outcome["label"] == "Win"


class TestSpectatorSummary:
    def test_black_agent_white_first(self, controller):
        state = {
            "game_id": "s1",
            "agent_color": "BLACK",
            "opponent_label": "Dika 0.42 (499)",
            "opponent_elo": 499,
            "model_display_name": "mimo-v2.5",
            "model_name": "mimo-v2.5",
            "status": "finished",
            "result": "1-0",
            "board_fen": chess.STARTING_FEN,
            "elo_before": 985,
            "elo_after": 978,
            "elo_delta": -7,
        }
        summary = controller.format_spectator_summary(state)
        assert summary.startswith("WHITE Dika 0.42 (499)")
        assert "vs BLACK mimo-v2.5 (978 ELO)" in summary
        assert summary.endswith("— 1-0")
        assert "985" not in summary
        assert "→" not in summary

    def test_white_agent_white_first(self, controller):
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
            "board_fen": chess.STARTING_FEN,
            "elo_before": 996,
            "elo_after": 985,
            "elo_delta": -11,
        }
        summary = controller.format_spectator_summary(state)
        assert summary.startswith("WHITE mimo-v2.5 (985 ELO)")
        assert "vs BLACK Stockfish 17.1 (1788)" in summary
        assert summary.endswith("— 0-1")


class TestParallelGames:
    def test_two_games_parallel(self, controller, game_manager):
        result1 = controller.new_game("parallel1", "white", 5, model_name="composer-2.5")
        result2 = controller.new_game("parallel2", "black", 5, model_name="composer-2.5")
        assert result1["ok"] is True
        assert result2["ok"] is True
        move1 = controller.make_agent_move("parallel1", "e2e4")
        move2 = controller.make_agent_move("parallel2", "e7e5")
        assert move1["ok"] is True
        assert move2["ok"] is True
        state1 = game_manager.load_state("parallel1")
        state2 = game_manager.load_state("parallel2")
        assert state1["agent_color"] == "WHITE"
        assert state2["agent_color"] == "BLACK"
        assert len(state1["moves"]) == 2
        assert len(state2["moves"]) == 3

    def test_save_state_replaces_valid_json(self, game_manager):
        game_manager.save_state("atomic", {"version": 1})
        game_manager.save_state("atomic", {"version": 2, "nested": {"ok": True}})
        assert game_manager.load_state("atomic") == {"version": 2, "nested": {"ok": True}}
