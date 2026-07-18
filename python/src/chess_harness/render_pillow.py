"""
Pillow-based chess board renderer (primary renderer).
"""

import os
from pathlib import Path
from typing import Optional

import chess
from PIL import Image, ImageDraw, ImageFont


class ChessBoardRenderer:
    """Renders chess boards as PNG images using Pillow."""

    LIGHT_SQUARE = (240, 217, 181)
    DARK_SQUARE = (181, 136, 99)
    LAST_MOVE_LIGHT = (205, 210, 106)
    LAST_MOVE_DARK = (170, 162, 58)
    CHECK_OUTLINE = (220, 50, 50)
    WHITE_PIECE = (245, 245, 245)
    BLACK_PIECE = (30, 30, 30)
    WHITE_OUTLINE = (80, 80, 80)
    BLACK_OUTLINE = (10, 10, 10)

    PIECE_UNICODE = {
        "P": "♙",
        "N": "♘",
        "B": "♗",
        "R": "♖",
        "Q": "♕",
        "K": "♔",
        "p": "♟",
        "n": "♞",
        "b": "♝",
        "r": "♜",
        "q": "♛",
        "k": "♚",
    }

    def __init__(self, board_size: int = 480, coord_margin: int = 22):
        self.board_size = board_size
        self.coord_margin = coord_margin
        self.square_size = board_size // 8
        self.image_size = (board_size + coord_margin, board_size + coord_margin)
        self.font = self._load_piece_font()
        self.coord_font = self._load_coord_font()

    def _load_piece_font(self):
        font_paths = [
            "C:/Windows/Fonts/seguisym.ttf",
            "C:/Windows/Fonts/seguiemj.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansSymbols.ttf",
            "/System/Library/Fonts/SFNSMono.ttf",
        ]
        for fp in font_paths:
            if os.path.exists(fp):
                try:
                    return ImageFont.truetype(fp, int(self.square_size * 0.82))
                except Exception:
                    continue
        return ImageFont.load_default()

    def _load_coord_font(self):
        try:
            return ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 13)
        except Exception:
            return ImageFont.load_default()

    def render_board(
        self,
        board: chess.Board,
        output_path: Path,
        last_move: Optional[chess.Move] = None,
        agent_color: str = "white",
        check_square: Optional[chess.Square] = None,
        status_text: Optional[str] = None,
        show_status: bool = False,
    ) -> Path:
        image = Image.new("RGB", self.image_size, (255, 255, 255))
        draw = ImageDraw.Draw(image)

        flip_board = agent_color.lower() == "black"
        ox, oy = self.coord_margin, 0

        for row in range(8):
            for col in range(8):
                square_row = 7 - row if flip_board else row
                square_col = 7 - col if flip_board else col

                is_light = (row + col) % 2 == 0
                square_color = self.LIGHT_SQUARE if is_light else self.DARK_SQUARE

                if last_move:
                    sq = chess.square(square_col, 7 - square_row)
                    if sq in (last_move.from_square, last_move.to_square):
                        square_color = self.LAST_MOVE_LIGHT if is_light else self.LAST_MOVE_DARK

                x1 = ox + col * self.square_size
                y1 = oy + row * self.square_size
                x2 = x1 + self.square_size
                y2 = y1 + self.square_size
                draw.rectangle([x1, y1, x2, y2], fill=square_color)

                piece = board.piece_at(chess.square(square_col, 7 - square_row))
                if piece:
                    symbol = self.PIECE_UNICODE[piece.symbol()]
                    cx = x1 + self.square_size // 2
                    cy = y1 + self.square_size // 2
                    if piece.color == chess.WHITE:
                        fill, outline = self.WHITE_PIECE, self.WHITE_OUTLINE
                    else:
                        fill, outline = self.BLACK_PIECE, self.BLACK_OUTLINE
                    for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                        draw.text(
                            (cx + dx, cy + dy),
                            symbol,
                            fill=outline,
                            font=self.font,
                            anchor="mm",
                        )
                    draw.text((cx, cy), symbol, fill=fill, font=self.font, anchor="mm")

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
                status_text = self._generate_status_text(board, agent_color)
            self._draw_status(draw, status_text, ox)

        image.save(output_path, "PNG")
        return output_path

    def _draw_coordinates(self, draw: ImageDraw.Draw, flip_board: bool, ox: int, oy: int):
        for col in range(8):
            fc = chr(ord("a") + (7 - col if flip_board else col))
            x = ox + col * self.square_size + self.square_size // 2
            y = oy + 8 * self.square_size + 4
            draw.text((x, y), fc, fill=(120, 120, 120), font=self.coord_font, anchor="mt")

        for row in range(8):
            rc = str(row + 1 if flip_board else 8 - row)
            x = ox // 2
            y = oy + row * self.square_size + self.square_size // 2
            draw.text((x, y), rc, fill=(120, 120, 120), font=self.coord_font, anchor="mm")

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
