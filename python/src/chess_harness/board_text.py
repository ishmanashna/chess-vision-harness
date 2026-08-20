"""Compact plaintext representation of a live chess board."""

from __future__ import annotations

import chess


def bottom_color_for_board(board: chess.Board) -> str:
    """Return ``white`` or ``black`` for which side sits at the bottom of the view."""
    return "black" if board.turn == chess.BLACK else "white"


def format_board_text(board: chess.Board, *, bottom_color: str = "white") -> str:
    """Return an absolute board grid with one row per rank.

    Default (games): white at bottom, files a→h, ranks 8→1.
    Black at bottom (puzzles/identify when Black is to move): files h→a,
    ranks 1→8 top to bottom (moving side nearest the footer).
    """
    flip = bottom_color.lower() == "black"
    if flip:
        file_header = "h g f e d c b a"
        rank_order = range(8)
        file_indices = range(7, -1, -1)
    else:
        file_header = "a b c d e f g h"
        rank_order = range(7, -1, -1)
        file_indices = range(8)

    rows = [f"  {file_header}"]
    for rank in rank_order:
        pieces = []
        for file_index in file_indices:
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
