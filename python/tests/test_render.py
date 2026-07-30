import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import chess
from PIL import Image
from chess_harness.render_pillow import ChessBoardRenderer, _PIECE_FILES, _STAUNTY_DIR


class TestRenderer:
    def setup_method(self):
        self.renderer = ChessBoardRenderer()

    def test_staunty_assets_present(self):
        assert _STAUNTY_DIR.is_dir()
        for stem in _PIECE_FILES.values():
            path = _STAUNTY_DIR / f"{stem}.png"
            assert path.is_file(), f"missing {path.name}"
            im = Image.open(path).convert("RGBA")
            assert im.size[0] > 0 and im.size[1] > 0
            alpha = im.getchannel("A")
            assert any(p > 0 for p in alpha.get_flattened_data()), (
                f"{path.name} has no opaque pixels"
            )

    def test_produces_png(self, tmp_path):
        board = chess.Board()
        out = tmp_path / "board.png"
        self.renderer.render_board(board, out, bottom_color="white")
        assert out.exists()
        assert out.stat().st_size > 1000

    def test_pieces_drawn_not_blank_squares(self, tmp_path):
        """Starting position must paint piece pixels distinct from bare squares."""
        board = chess.Board()
        empty = chess.Board(None)
        with_pieces = tmp_path / "with.png"
        bare = tmp_path / "bare.png"
        self.renderer.render_board(board, with_pieces, bottom_color="white")
        self.renderer.render_board(empty, bare, bottom_color="white")
        assert with_pieces.read_bytes() != bare.read_bytes()
        img = Image.open(with_pieces).convert("RGB")
        # a1 (white rook) sits bottom-left of the board area; sample near center of that square
        ox, oy = self.renderer.coord_margin, 0
        ss = self.renderer.square_size
        px = ox + ss // 2
        py = oy + 7 * ss + ss // 2
        pixel = img.getpixel((px, py))
        assert pixel not in (
            ChessBoardRenderer.LIGHT_SQUARE,
            ChessBoardRenderer.DARK_SQUARE,
        ), "expected a piece pixel on a1, not bare square color"

    def test_deterministic_size(self, tmp_path):
        board = chess.Board()
        out1 = tmp_path / "b1.png"
        out2 = tmp_path / "b2.png"
        self.renderer.render_board(board, out1, bottom_color="white")
        self.renderer.render_board(board, out2, bottom_color="white")
        assert out1.stat().st_size == out2.stat().st_size

    def test_last_move_highlight(self, tmp_path):
        board = chess.Board()
        board.push(chess.Move.from_uci("e2e4"))
        out = tmp_path / "board.png"
        self.renderer.render_board(
            board, out, bottom_color="white", last_move=chess.Move.from_uci("e2e4")
        )
        assert out.exists()

    def test_last_two_moves_highlight(self, tmp_path):
        board = chess.Board()
        m1 = chess.Move.from_uci("e2e4")
        m2 = chess.Move.from_uci("e7e5")
        board.push(m1)
        board.push(m2)
        out = tmp_path / "board.png"
        self.renderer.render_board(board, out, last_moves=[m1, m2])
        assert out.exists()
        assert out.stat().st_size > 1000

    def test_default_white_at_bottom(self, tmp_path):
        """Agent/spectator default is white-bottom; black-bottom differs."""
        board = chess.Board()
        default_out = tmp_path / "default.png"
        white_out = tmp_path / "white.png"
        black_bottom_out = tmp_path / "black_bottom.png"
        self.renderer.render_board(board, default_out)
        self.renderer.render_board(board, white_out, bottom_color="white")
        self.renderer.render_board(board, black_bottom_out, bottom_color="black")
        assert default_out.read_bytes() == white_out.read_bytes()
        assert default_out.read_bytes() != black_bottom_out.read_bytes()

    def test_play_board_square_palette(self):
        assert ChessBoardRenderer.LIGHT_SQUARE == (0xEC, 0xDA, 0xB9)
        assert ChessBoardRenderer.DARK_SQUARE == (0xC5, 0xA0, 0x76)

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
