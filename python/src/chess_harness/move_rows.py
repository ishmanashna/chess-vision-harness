"""SAN move rows from stored UCI plies (no FEN exposure)."""

from __future__ import annotations

from typing import Any

import chess

__all__ = ["move_rows", "moves_payload", "plies_detail", "spectator_moves_payload"]


def move_rows(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Build Lichess-style move rows (SAN) from stored UCI plies."""
    moves = state.get("moves", [])
    if not moves:
        return []
    board = chess.Board(state.get("start_fen", chess.STARTING_FEN))
    rows: list[dict[str, Any]] = []
    i = 0
    move_num = 1
    while i < len(moves):
        white = board.san(chess.Move.from_uci(moves[i]))
        board.push(chess.Move.from_uci(moves[i]))
        i += 1
        black = ""
        if i < len(moves):
            black = board.san(chess.Move.from_uci(moves[i]))
            board.push(chess.Move.from_uci(moves[i]))
            i += 1
        rows.append({"num": move_num, "white": white, "black": black})
        move_num += 1
    return rows


def plies_detail(state: dict[str, Any]) -> list[dict[str, str]]:
    """Per-ply UCI + SAN list (no FEN)."""
    moves = state.get("moves", [])
    if not moves:
        return []
    board = chess.Board(state.get("start_fen", chess.STARTING_FEN))
    detail: list[dict[str, str]] = []
    for uci in moves:
        move = chess.Move.from_uci(uci)
        detail.append({"uci": uci, "san": board.san(move)})
        board.push(move)
    return detail


def moves_payload(state: dict[str, Any]) -> dict[str, Any]:
    """Move list response: plies count, SAN rows, and UCI+SAN detail (no FEN)."""
    moves = state.get("moves", [])
    return {
        "plies": len(moves),
        "plies_detail": plies_detail(state),
        "move_rows": move_rows(state),
    }


def spectator_moves_payload(state: dict[str, Any]) -> dict[str, Any]:
    """Spectator moves with redaction for live rated (AvE/AvA) games."""
    from .game_types import GAME_TYPE_HUMAN_VS_AGENT

    moves = state.get("moves", [])
    plies = len(moves)
    if state.get("status") == "in_progress" and state.get("game_type") != GAME_TYPE_HUMAN_VS_AGENT:
        return {"plies": plies, "plies_detail": [], "move_rows": []}
    return moves_payload(state)
