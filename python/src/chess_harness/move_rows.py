"""SAN move rows from stored UCI plies (no FEN exposure)."""

from __future__ import annotations

from typing import Any

import chess

__all__ = [
    "fen_at_ply",
    "move_rows",
    "moves_payload",
    "plies_detail",
    "spectator_moves_payload",
]


def fen_at_ply(state: dict[str, Any], ply: int) -> str:
    """Rebuild FEN after N plies (server-side only; never return in agent APIs)."""
    moves = state.get("moves", [])
    n = max(0, min(int(ply), len(moves)))
    board = chess.Board(state.get("start_fen", chess.STARTING_FEN))
    for i in range(n):
        board.push(chess.Move.from_uci(moves[i]))
    return board.fen()


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
    """Spectator move list for /g/ UI (all modes, including live AvE/AvA).

    Includes start_fen so the spectator cm-chessboard can replay plies with chess.js.
    Agent APIs never expose this payload (no /api/v1/.../moves).
    """
    payload = moves_payload(state)
    payload["start_fen"] = state.get("start_fen") or chess.STARTING_FEN
    return payload
