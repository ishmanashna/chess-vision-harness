"""
Pillow-based chess board renderer (primary renderer).
"""

import io
from pathlib import Path
from typing import BinaryIO, Optional, Union

import chess
from PIL import Image, ImageDraw, ImageFont


_STAUNTY_DIR = Path(__file__).resolve().parent / "assets" / "staunty"

# chess.Piece.symbol() -> staunty asset stem (cm-chessboard sprite ids)
_PIECE_FILES = {
    "P": "wp",
    "N": "wn",
    "B": "wb",
    "R": "wr",
    "Q": "wq",
    "K": "wk",
    "p": "bp",
    "n": "bn",
    "b": "bb",
    "r": "br",
    "q": "bq",
    "k": "bk",
}


class ChessBoardRenderer:
    """Renders chess boards as PNG images using Pillow + Staunty piece assets."""

    # cm-chessboard 8.7.2 default theme (Playground board)
    LIGHT_SQUARE = (0xEC, 0xDA, 0xB9)  # #ecdab9
    DARK_SQUARE = (0xC5, 0xA0, 0x76)  # #c5a076
    LAST_MOVE_LIGHT = (205, 210, 106)
    LAST_MOVE_DARK = (170, 162, 58)
    PREV_MOVE_LIGHT = (186, 202, 168)
    PREV_MOVE_DARK = (140, 162, 110)
    CHECK_OUTLINE = (220, 50, 50)
    COORD_FILL = (0xB5, 0x93, 0x6D)  # #b5936d

    def __init__(self, board_size: int = 480, coord_margin: int = 22):
        self.board_size = board_size
        self.coord_margin = coord_margin
        self.square_size = board_size // 8
        self.image_size = (board_size + coord_margin, board_size + coord_margin)
        self.coord_font = self._load_coord_font()
        self._piece_images = self._load_staunty_pieces()

    def _load_coord_font(self):
        try:
            return ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 13)
        except Exception:
            return ImageFont.load_default()

    def _load_staunty_pieces(self) -> dict[str, Image.Image]:
        if not _STAUNTY_DIR.is_dir():
            raise FileNotFoundError(
                f"Staunty piece assets missing at {_STAUNTY_DIR}"
            )
        images: dict[str, Image.Image] = {}
        for symbol, stem in _PIECE_FILES.items():
            path = _STAUNTY_DIR / f"{stem}.png"
            if not path.is_file():
                raise FileNotFoundError(f"Missing Staunty piece PNG: {path}")
            images[symbol] = Image.open(path).convert("RGBA")
        return images

    def render_board(
        self,
        board: chess.Board,
        output_path: Union[Path, BinaryIO],
        last_move: Optional[chess.Move] = None,
        last_moves: Optional[list] = None,
        bottom_color: str = "white",
        check_square: Optional[chess.Square] = None,
        status_text: Optional[str] = None,
        show_status: bool = False,
        agent_color: Optional[str] = None,
    ) -> Union[Path, BinaryIO]:
        """Render board PNG. Default orientation is white at bottom.

        ``bottom_color`` controls which side sits at the bottom of the image.
        Agent/CLI/MCP/spectator paths always use the default (white). Playground
        human PNG export may pass the human's color. ``agent_color`` is only
        used for optional status text ("Your move").
        """
        image = self._compose_board_image(
            board,
            last_move=last_move,
            last_moves=last_moves,
            bottom_color=bottom_color,
            check_square=check_square,
            status_text=status_text,
            show_status=show_status,
            agent_color=agent_color,
        )
        image.save(output_path, "PNG")
        return output_path

    def render_board_bytes(
        self,
        board: chess.Board,
        last_move: Optional[chess.Move] = None,
        last_moves: Optional[list] = None,
        bottom_color: str = "white",
        check_square: Optional[chess.Square] = None,
        status_text: Optional[str] = None,
        show_status: bool = False,
        agent_color: Optional[str] = None,
    ) -> bytes:
        """Render board PNG into memory (e.g. Imagine API)."""
        buf = io.BytesIO()
        self.render_board(
            board,
            buf,
            last_move=last_move,
            last_moves=last_moves,
            bottom_color=bottom_color,
            check_square=check_square,
            status_text=status_text,
            show_status=show_status,
            agent_color=agent_color,
        )
        return buf.getvalue()

    def _compose_board_image(
        self,
        board: chess.Board,
        last_move: Optional[chess.Move] = None,
        last_moves: Optional[list] = None,
        bottom_color: str = "white",
        check_square: Optional[chess.Square] = None,
        status_text: Optional[str] = None,
        show_status: bool = False,
        agent_color: Optional[str] = None,
    ) -> Image.Image:
        image = Image.new("RGB", self.image_size, (255, 255, 255))
        draw = ImageDraw.Draw(image)

        flip_board = bottom_color.lower() == "black"
        ox, oy = self.coord_margin, 0

        highlight: dict = {}
        moves = list(last_moves) if last_moves else ([last_move] if last_move else [])
        if len(moves) >= 2 and moves[-2] is not None:
            for sq in (moves[-2].from_square, moves[-2].to_square):
                highlight[sq] = "prev"
        if moves and moves[-1] is not None:
            for sq in (moves[-1].from_square, moves[-1].to_square):
                highlight[sq] = "last"

        for row in range(8):
            for col in range(8):
                square_row = 7 - row if flip_board else row
                square_col = 7 - col if flip_board else col

                is_light = (row + col) % 2 == 0
                square_color = self.LIGHT_SQUARE if is_light else self.DARK_SQUARE

                sq = chess.square(square_col, 7 - square_row)
                kind = highlight.get(sq)
                if kind == "last":
                    square_color = self.LAST_MOVE_LIGHT if is_light else self.LAST_MOVE_DARK
                elif kind == "prev":
                    square_color = self.PREV_MOVE_LIGHT if is_light else self.PREV_MOVE_DARK

                x1 = ox + col * self.square_size
                y1 = oy + row * self.square_size
                x2 = x1 + self.square_size
                y2 = y1 + self.square_size
                draw.rectangle([x1, y1, x2, y2], fill=square_color)

                piece = board.piece_at(chess.square(square_col, 7 - square_row))
                if piece:
                    scaled, pad = self._piece_scaled(piece.symbol())
                    image.paste(scaled, (x1 + pad, y1 + pad), scaled)

        if check_square:
            crow = 7 - chess.square_rank(check_square)
            ccol = chess.square_file(check_square)
            if flip_board:
                crow = 7 - crow
                ccol = 7 - ccol
            cx1 = ox + ccol * self.square_size
            cy1 = oy + crow * self.square_size
            cx2 = cx1 + self.square_size
            cy2 = cy1 + self.square_size
            for i in range(4):
                draw.rectangle([cx1 + i, cy1 + i, cx2 - i, cy2 - i], outline=self.CHECK_OUTLINE)

        self._draw_coordinates(draw, flip_board, ox, oy)

        if show_status:
            if status_text is None:
                status_text = self._generate_status_text(
                    board, agent_color or bottom_color
                )
            self._draw_status(draw, status_text, ox)

        return image

    def _piece_scaled(self, symbol: str) -> tuple[Image.Image, int]:
        if not hasattr(self, "_scaled_cache"):
            self._scaled_cache: dict[str, tuple[Image.Image, int]] = {}
        cached = self._scaled_cache.get(symbol)
        if cached is not None:
            return cached
        pad = max(1, int(self.square_size * 0.06))
        size = self.square_size - 2 * pad
        scaled = self._piece_images[symbol].resize(
            (size, size), Image.Resampling.LANCZOS
        )
        self._scaled_cache[symbol] = (scaled, pad)
        return scaled, pad

    def _draw_coordinates(self, draw: ImageDraw.Draw, flip_board: bool, ox: int, oy: int):
        for col in range(8):
            fc = chr(ord("a") + (7 - col if flip_board else col))
            x = ox + col * self.square_size + self.square_size // 2
            y = oy + 8 * self.square_size + 4
            draw.text((x, y), fc, fill=self.COORD_FILL, font=self.coord_font, anchor="mt")

        for row in range(8):
            rc = str(row + 1 if flip_board else 8 - row)
            x = ox // 2
            y = oy + row * self.square_size + self.square_size // 2
            draw.text((x, y), rc, fill=self.COORD_FILL, font=self.coord_font, anchor="mm")

    def _draw_status(self, draw: ImageDraw.Draw, status_text: str, ox: int):
        bbox = draw.textbbox((0, 0), status_text, font=self.coord_font)
        tw = bbox[2] - bbox[0]
        x = ox + (self.board_size - tw) // 2
        y = self.board_size + self.coord_margin - 14
        draw.text((x, y), status_text, fill=(80, 80, 80), font=self.coord_font)

    def _generate_status_text(self, board: chess.Board, agent_color: str) -> str:
        if board.is_game_over():
            result = board.result()
            if result == "1-0":
                return "White wins"
            if result == "0-1":
                return "Black wins"
            return "Draw"
        agent = chess.WHITE if agent_color.lower() == "white" else chess.BLACK
        if board.turn == agent:
            status = "Your move"
        else:
            status = "Opponent's move"
        if board.is_check() and board.turn == agent:
            status += " (check)"
        status += f" · move {board.fullmove_number}"
        return status

    def render_status_only(
        self,
        board: chess.Board,
        agent_color: str = "white",
        last_move: Optional[chess.Move] = None,
    ) -> str:
        return self._generate_status_text(board, agent_color)
