import pytest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import chess
from pathlib import Path
from chess_harness.render_pillow import ChessBoardRenderer


class TestRenderer:
    def setup_method(self):
        self.renderer = ChessBoardRenderer()

    def test_produces_png(self, tmp_path):
        board = chess.Board()
        out = tmp_path / "board.png"
        self.renderer.render_board(board, out, agent_color="white")
        assert out.exists()
        assert out.stat().st_size > 1000

    def test_deterministic_size(self, tmp_path):
        board = chess.Board()
        out1 = tmp_path / "b1.png"
        out2 = tmp_path / "b2.png"
        self.renderer.render_board(board, out1, agent_color="white")
        self.renderer.render_board(board, out2, agent_color="white")
        assert out1.stat().st_size == out2.stat().st_size

    def test_last_move_highlight(self, tmp_path):
        board = chess.Board()
        board.push(chess.Move.from_uci("e2e4"))
        out = tmp_path / "board.png"
        self.renderer.render_board(board, out, agent_color="white", last_move=chess.Move.from_uci("e2e4"))
        assert out.exists()

    def test_last_two_moves_highlight(self, tmp_path):
        board = chess.Board()
        m1 = chess.Move.from_uci("e2e4")
        m2 = chess.Move.from_uci("e7e5")
        board.push(m1)
        board.push(m2)
        out = tmp_path / "board.png"
        self.renderer.render_board(board, out, agent_color="white", last_moves=[m1, m2])
        assert out.exists()
        assert out.stat().st_size > 1000

    def test_flipped_for_black(self, tmp_path):
        board = chess.Board()
        out = tmp_path / "board.png"
        self.renderer.render_board(board, out, agent_color="black")
        assert out.exists()

    def test_status_text(self, ctrl=None):
        board = chess.Board()
        text = self.renderer.render_status_only(board, "white")
        assert "Your move" in text

    def test_game_over_status(self):
        board = chess.Board()
        board.push_san("f3")
        board.push_san("e5")
        board.push_san("g4")
        board.push_san("Qh4")
        text = self.renderer.render_status_only(board, "white")
        assert "wins" in text or "Draw" in text
