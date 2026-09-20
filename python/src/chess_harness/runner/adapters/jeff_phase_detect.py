"""Classify opening / middlegame / endgame and material edge for Jeff J3."""

from __future__ import annotations

import chess

# Simple piece values in centipawns-ish integers.
_VALUES = {
    chess.PAWN: 1,
    chess.KNIGHT: 3,
    chess.BISHOP: 3,
    chess.ROOK: 5,
    chess.QUEEN: 9,
}


def material_score(board: chess.Board) -> tuple[int, int]:
    """Return (white_points, black_points) ignoring kings."""
    w = b = 0
    for sq, piece in board.piece_map().items():
        if piece.piece_type == chess.KING:
            continue
        val = _VALUES.get(piece.piece_type, 0)
        if piece.color == chess.WHITE:
            w += val
        else:
            b += val
    return w, b


def classify_phase(board: chess.Board) -> str:
    """Return opening | middle | end from piece count and queens/minors."""
    pieces = board.piece_map()
    n = len(pieces)
    queens = sum(1 for p in pieces.values() if p.piece_type == chess.QUEEN)
    minors = sum(
        1
        for p in pieces.values()
        if p.piece_type in (chess.KNIGHT, chess.BISHOP)
    )
    # Endgame: few pieces, or no queens and limited material.
    if n <= 12 or (queens == 0 and n <= 16):
        return "end"
    # Opening: early, many pieces still on board, both sides undeveloped-ish.
    if n >= 28 and board.fullmove_number <= 12:
        return "opening"
    if n >= 26 and board.fullmove_number <= 10:
        return "opening"
    return "middle"


def material_edge_for_side(board: chess.Board, side: chess.Color) -> str:
    """ahead | even | behind from side-to-move / agent side perspective."""
    w, b = material_score(board)
    ours = w if side == chess.WHITE else b
    theirs = b if side == chess.WHITE else w
    diff = ours - theirs
    if diff >= 2:
        return "ahead"
    if diff <= -2:
        return "behind"
    return "even"


def phase_key(board: chess.Board, *, side: chess.Color | None = None) -> str:
    """e.g. middle_ahead."""
    side = board.turn if side is None else side
    return f"{classify_phase(board)}_{material_edge_for_side(board, side)}"
