"""Public puzzle watching and replay (/p/{attempt_id}, /api/v1/puzzles/public/*).

Observer-safe by construction: while an attempt is active the published state
contains only the attempt id, agent display name, imported difficulty, the
current visible board, the agent's submitted and opponent moves as plain SAN
(they are not secret — only the solution is), the attempt-chain key, and move
counts. The solution, hidden FENs, and puzzle id are never published before
completion; replay (solution line, submitted line, per-ply FENs, rating
changes, source link) unlocks only after the attempt ends. Themes are never
published on any public surface: they stay only inside attempt/puzzle records.
"""

from __future__ import annotations

from typing import Any, Dict, List

import chess

from .models import ModelRegistry
from .puzzle_leaderboard import puzzle_agent_summary
from .puzzle_store import PuzzleStore
from .render_pillow import ChessBoardRenderer

__all__ = [
    "observer_state",
    "replay_payload",
    "render_observer_board_png",
    "CM_CHESSBOARD_VERSION",
]

CM_CHESSBOARD_VERSION = "8.7.2"
CM_CDN = f"https://cdn.jsdelivr.net/npm/cm-chessboard@{CM_CHESSBOARD_VERSION}"


def san_moves(
    start_fen: str, submitted: List[str], opponent: List[str]
) -> tuple[List[str], List[str]]:
    """SAN labels for the submitted agent moves and opponent replies.

    Replays the known move history from the start position. Both lists were
    validated as legal when recorded, so ``board.san`` cannot raise here.
    """
    board = chess.Board(start_fen)
    agent_labels: List[str] = []
    opponent_labels: List[str] = []
    for index, uci in enumerate(submitted):
        try:
            agent = chess.Move.from_uci(uci)
            agent_labels.append(board.san(agent))
            board.push(agent)
        except ValueError:
            agent_labels.append(str(uci))
            break
        if index < len(opponent):
            try:
                reply = chess.Move.from_uci(opponent[index])
                opponent_labels.append(board.san(reply))
                board.push(reply)
            except ValueError:
                opponent_labels.append(str(opponent[index]))
                break
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


def observer_state(record: Dict[str, Any]) -> Dict[str, Any]:
    """Observer-safe live state (never leaks solution or puzzle id)."""
    finished = record.get("status") == "finished"
    submitted = list(record.get("submitted_moves") or [])
    opponent = list(record.get("opponent_moves") or [])
    agent_moves, opponent_moves = san_moves(
        record.get("start_fen", record.get("board_fen")), submitted, opponent
    )
    model_id = str(record.get("model_id") or "")
    state: Dict[str, Any] = {
        "ok": True,
        "attempt_id": record["attempt_id"],
        "key": record.get("key_fingerprint"),
        "model_id": record.get("model_id"),
        "agent_name": _agent_name(record),
        "status": record.get("status", "active"),
        "result": record.get("result") if finished else None,
        "moves_played": len(submitted),
        "submitted_moves": agent_moves,
        "opponent_moves": opponent_moves,
        "puzzle_rating": int(record.get("puzzle_rating") or 0),
        "fen": record.get("board_fen", chess.STARTING_FEN),
        "started_at": record.get("started_at"),
        "updated_at": record.get("updated_at"),
        "finished_at": record.get("finished_at") if finished else None,
        "watch_url": f"/p/{record['attempt_id']}",
    }
    if model_id:
        summary = puzzle_agent_summary(model_id)
        if summary:
            state["agent_summary"] = summary
    return state


def _build_plies(
    start_fen: str,
    submitted: List[str],
    opponent: List[str],
) -> List[Dict[str, Any]]:
    """Per-ply FEN + SAN labels for replay scrubbing (start -> final)."""
    board = chess.Board(start_fen)
    plies: List[Dict[str, Any]] = []
    count = len(submitted)
    for index in range(count):
        try:
            agent = chess.Move.from_uci(submitted[index])
            agent_label = f"{index + 1}. {board.san(agent)}"
            board.push(agent)
            plies.append(
                {
                    "fen": board.fen(),
                    "label": agent_label,
                    "uci": agent.uci(),
                }
            )
        except ValueError:
            plies.append(
                {
                    "fen": board.fen(),
                    "label": f"{index + 1}. {submitted[index]}",
                }
            )
            break
        if index < len(opponent):
            try:
                reply = chess.Move.from_uci(opponent[index])
                reply_label = f"{index + 1}... {board.san(reply)}"
                board.push(reply)
                plies.append(
                    {
                        "fen": board.fen(),
                        "label": reply_label,
                        "uci": reply.uci(),
                    }
                )
            except ValueError:
                plies.append(
                    {
                        "fen": board.fen(),
                        "label": f"{index + 1}... {opponent[index]}",
                    }
                )
                break
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
        "plies": _build_plies(start_fen, submitted, opponent),
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
    return ChessBoardRenderer().render_board_bytes(board)


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

