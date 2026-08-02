"""Compact plaintext representation of a live chess board."""

from __future__ import annotations

import chess


def format_board_text(board: chess.Board) -> str:
    """Return an absolute, white-bottom board with one row per rank."""
    rows = ["  a b c d e f g h"]
    for rank in range(7, -1, -1):
        pieces = []
        for file_index in range(8):
            piece = board.piece_at(chess.square(file_index, rank))
            pieces.append(piece.symbol() if piece else ".")
        rows.append(f"{rank + 1} " + " ".join(pieces))
    rows.extend(
        [
            "side_to_move: " + ("white" if board.turn == chess.WHITE else "black"),
            "in_check: " + ("yes" if board.is_check() else "no"),
            "legend: White=uppercase, Black=lowercase, .=empty; K king, Q queen, R rook, B bishop, N knight, P pawn",
        ]
    )
    return "\n".join(rows) + "\n"
