"""Public puzzle watching and replay (/p/{attempt_id}, /api/v1/puzzles/public/*).

Public spectator state for operator watch pages: attempt id, agent display
name, imported difficulty, the current visible board, submitted and opponent
moves as plain SAN, the full solution line (UCI + SAN labels), attempt-chain
key, and move counts. Hidden FENs and puzzle id stay off the live observer;
replay adds per-ply FENs, rating changes, and source link after finish.
Themes are never published on any public surface.
"""

from __future__ import annotations

from typing import Any, Dict, List

import chess

from .models import ModelRegistry
from .puzzle_leaderboard import puzzle_agent_summary
from .puzzle_store import PuzzleStore
from .board_text import bottom_color_for_board
from .render_pillow import ChessBoardRenderer

__all__ = [
    "observer_state",
    "replay_payload",
    "render_observer_board_png",
    "CM_CHESSBOARD_VERSION",
]

CM_CHESSBOARD_VERSION = "8.7.2"
CM_CDN = f"https://cdn.jsdelivr.net/npm/cm-chessboard@{CM_CHESSBOARD_VERSION}"

_MOVE_PARSE_ERRORS = (
    ValueError,
    chess.IllegalMoveError,
    chess.InvalidMoveError,
    chess.AmbiguousMoveError,
)


def _legal_uci_move(board: chess.Board, uci: str) -> chess.Move | None:
    """Parse UCI and return the move only when it is legal on *board*."""
    try:
        move = chess.Move.from_uci(uci)
    except ValueError:
        return None
    if not board.is_legal(move):
        return None
    return move


def san_moves(
    start_fen: str, submitted: List[str], opponent: List[str]
) -> tuple[List[str], List[str]]:
    """SAN labels for the submitted agent moves and opponent replies.

    Replays legal moves from the start position. Illegal or unparseable UCI is
    labeled with the raw token and does not advance the scratch board.
    """
    board = chess.Board(start_fen)
    agent_labels: List[str] = []
    opponent_labels: List[str] = []
    for index, uci in enumerate(submitted):
        move = _legal_uci_move(board, uci)
        if move is None:
            agent_labels.append(str(uci))
            break
        try:
            agent_labels.append(board.san(move))
        except _MOVE_PARSE_ERRORS:
            agent_labels.append(str(uci))
            break
        board.push(move)
        if index < len(opponent):
            reply = _legal_uci_move(board, opponent[index])
            if reply is None:
                opponent_labels.append(str(opponent[index]))
                break
            try:
                opponent_labels.append(board.san(reply))
            except _MOVE_PARSE_ERRORS:
                opponent_labels.append(str(opponent[index]))
                break
            board.push(reply)
    return agent_labels, opponent_labels


def _agent_name(record: Dict[str, Any]) -> str:
    try:
        model = ModelRegistry().get(str(record.get("model_id") or ""))
        if model:
            return str(model.get("name") or model.get("id") or record["model_id"])
    except Exception:
        pass
    return str(record.get("model_id") or "unknown")


def _puzzle(record: Dict[str, Any]) -> Dict[str, Any]:
    return PuzzleStore().get(str(record.get("puzzle_id") or "")) or {}


def _side_to_move(record: Dict[str, Any]) -> str:
    """Puzzle start side (white/black) for the static spectator turn label."""
    start_fen = record.get("start_fen", record.get("board_fen"))
    board = chess.Board(start_fen)
    return "white" if board.turn == chess.WHITE else "black"


def observer_state(record: Dict[str, Any]) -> Dict[str, Any]:
    """Public live state for spectators (solution line included; no puzzle id)."""
    finished = record.get("status") == "finished"
    start_fen = record.get("start_fen", record.get("board_fen"))
    submitted = list(record.get("submitted_moves") or [])
    opponent = list(record.get("opponent_moves") or [])
    agent_moves, opponent_moves = san_moves(start_fen, submitted, opponent)
    solution_uci = list(record.get("solution_moves") or [])
    sol_agent_uci, sol_opp_uci = _split_agent_opponent_uci(solution_uci)
    sol_agent_san, sol_opp_san = san_moves(start_fen, sol_agent_uci, sol_opp_uci)
    model_id = str(record.get("model_id") or "")
    state: Dict[str, Any] = {
        "ok": True,
        "attempt_id": record["attempt_id"],
        "key": record.get("key_fingerprint"),
        "model_id": record.get("model_id"),
        "agent_name": _agent_name(record),
        "agent_joined": bool(record.get("agent_joined", True)),
        "status": record.get("status", "active"),
        "result": record.get("result") if finished else None,
        "moves_played": len(submitted),
        "submitted_moves": agent_moves,
        "opponent_moves": opponent_moves,
        "solution_moves": solution_uci,
        "solution_agent_moves": sol_agent_san,
        "solution_opponent_moves": sol_opp_san,
        "puzzle_rating": int(record.get("puzzle_rating") or 0),
        "fen": record.get("board_fen", chess.STARTING_FEN),
        "side_to_move": _side_to_move(record),
        "started_at": record.get("started_at"),
        "updated_at": record.get("updated_at"),
        "finished_at": record.get("finished_at") if finished else None,
        "watch_url": f"/p/{record['attempt_id']}",
    }
    if model_id:
        summary = puzzle_agent_summary(model_id)
        if summary:
            state["agent_summary"] = summary
    if finished:
        state["failure_reason"] = record.get("failure_reason")
        state["first_wrong_move"] = record.get("first_wrong_move")
    return state


def _build_plies(
    start_fen: str,
    submitted: List[str],
    opponent: List[str],
    *,
    result: str | None = None,
) -> List[Dict[str, Any]]:
    """Per-ply FEN + SAN labels for replay scrubbing (start -> final)."""
    board = chess.Board(start_fen)
    plies: List[Dict[str, Any]] = []
    for index, uci in enumerate(submitted):
        pre_fen = board.fen()
        move = _legal_uci_move(board, uci)
        if move is None:
            plies.append(
                {
                    "fen": pre_fen,
                    "label": f"{index + 1}. {uci}",
                }
            )
            break
        try:
            agent_label = f"{index + 1}. {board.san(move)}"
        except _MOVE_PARSE_ERRORS:
            plies.append(
                {
                    "fen": pre_fen,
                    "label": f"{index + 1}. {uci}",
                }
            )
            break
        if result == "failed" and index == len(submitted) - 1:
            plies.append(
                {
                    "fen": pre_fen,
                    "label": agent_label,
                    "uci": move.uci(),
                }
            )
            break
        board.push(move)
        plies.append(
            {
                "fen": board.fen(),
                "label": agent_label,
                "uci": move.uci(),
            }
        )
        if index < len(opponent):
            reply = _legal_uci_move(board, opponent[index])
            if reply is None:
                plies.append(
                    {
                        "fen": board.fen(),
                        "label": f"{index + 1}... {opponent[index]}",
                    }
                )
                break
            try:
                reply_label = f"{index + 1}... {board.san(reply)}"
            except _MOVE_PARSE_ERRORS:
                plies.append(
                    {
                        "fen": board.fen(),
                        "label": f"{index + 1}... {opponent[index]}",
                    }
                )
                break
            board.push(reply)
            plies.append(
                {
                    "fen": board.fen(),
                    "label": reply_label,
                    "uci": reply.uci(),
                }
            )
    return plies


def _split_agent_opponent_uci(moves: List[str]) -> tuple[List[str], List[str]]:
    agent = [moves[i] for i in range(0, len(moves), 2)]
    opponent = [moves[i] for i in range(1, len(moves), 2)]
    return agent, opponent


def replay_payload(record: Dict[str, Any]) -> Dict[str, Any]:
    """Full replay; only call after the attempt finished."""
    puzzle = _puzzle(record)
    submitted = list(record.get("submitted_moves") or [])
    opponent = list(record.get("opponent_moves") or [])
    start_fen = record.get("start_fen", record.get("board_fen"))
    solution_uci = list(record.get("solution_moves") or [])
    sol_agent_uci, sol_opp_uci = _split_agent_opponent_uci(solution_uci)
    sol_agent_san, sol_opp_san = san_moves(start_fen, sol_agent_uci, sol_opp_uci)
    return {
        "ok": True,
        "attempt_id": record["attempt_id"],
        "puzzle_id": record["puzzle_id"],
        "agent_name": _agent_name(record),
        "result": record.get("result"),
        "failure_reason": record.get("failure_reason"),
        "first_wrong_move": record.get("first_wrong_move"),
        "submitted_moves": submitted,
        "opponent_moves": opponent,
        "solution_moves": solution_uci,
        "solution_agent_moves": sol_agent_san,
        "solution_opponent_moves": sol_opp_san,
        "start_fen": start_fen,
        "side_to_move": _side_to_move(record),
        "plies": _build_plies(
            start_fen, submitted, opponent, result=record.get("result")
        ),
        "source_link": puzzle.get("game_url") or "",
        "puzzle_rating": int(record.get("puzzle_rating") or 0),
        "rating_before": record.get("rating_before"),
        "rating_after": record.get("rating_after"),
        "rating_change": record.get("rating_change"),
        "started_at": record.get("started_at"),
        "finished_at": record.get("finished_at"),
    }


def render_observer_board_png(record: Dict[str, Any]) -> bytes:
    """Answer-safe board PNG: the current visible position, no move highlights."""
    board = chess.Board(record.get("board_fen", chess.STARTING_FEN))
    return ChessBoardRenderer().render_board_bytes(
        board, bottom_color=bottom_color_for_board(board)
    )


def public_attempt_row(record: Dict[str, Any]) -> Dict[str, Any]:
    """One discovery row for the public browse list."""
    finished = record.get("status") == "finished"
    return {
        "attempt_id": record["attempt_id"],
        "key": record.get("key_fingerprint"),
        "model_id": record.get("model_id"),
        "agent_name": _agent_name(record),
        "status": record.get("status"),
        "result": record.get("result") if finished else None,
        "moves_played": len(record.get("submitted_moves") or []),
        "puzzle_rating": int(record.get("puzzle_rating") or 0),
        "started_at": record.get("started_at"),
        "finished_at": record.get("finished_at") if finished else None,
        "watch_url": f"/p/{record['attempt_id']}",
    }

