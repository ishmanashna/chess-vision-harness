"""Public board-identification watching and replay (/i/{attempt_id}, public API).

Public spectator state for operator watch pages: attempt id, agent display
name, attempt-chain key, the current visible board, submission progress, and
the correct placement map. Submitted placement, per-square errors, and
difficulty stay off the live observer until finish; replay adds full review
detail after the attempt ends.
"""

from __future__ import annotations

import io
from typing import Any, Dict

import chess
from PIL import Image, ImageDraw

from .board_text import bottom_color_for_board
from .models import ModelRegistry
from .puzzle_leaderboard import identify_agent_summary
from .render_pillow import ChessBoardRenderer

__all__ = [
    "observer_state",
    "replay_payload",
    "render_identify_board_png",
    "render_answer_overlay_png",
    "public_attempt_row",
]


def _agent_name(record: Dict[str, Any]) -> str:
    try:
        model = ModelRegistry().get(str(record.get("model_id") or ""))
        if model:
            return str(model.get("name") or model.get("id") or record["model_id"])
    except Exception:
        pass
    return str(record.get("model_id") or "unknown")


def _side_to_move(record: Dict[str, Any]) -> str:
    board = chess.Board(record.get("corpus_fen", chess.STARTING_FEN))
    return "white" if board.turn == chess.WHITE else "black"


def _square_overlay_xy(
    renderer: ChessBoardRenderer, square_name: str, *, flip_board: bool
) -> tuple[int, int]:
    file_index = chess.FILE_NAMES.index(square_name[0])
    rank_index = int(square_name[1]) - 1
    if flip_board:
        col = 7 - file_index
        row = rank_index
    else:
        col = file_index
        row = 7 - rank_index
    x = renderer.coord_margin + col * renderer.square_size
    y = row * renderer.square_size
    return x, y


def observer_state(record: Dict[str, Any]) -> Dict[str, Any]:
    """Public live state for spectators (correct placement included)."""
    finished = record.get("status") == "finished"
    state: Dict[str, Any] = {
        "ok": True,
        "attempt_id": record["attempt_id"],
        "key": record.get("key_fingerprint"),
        "model_id": record.get("model_id"),
        "agent_name": _agent_name(record),
        "agent_joined": bool(record.get("agent_joined", True)),
        "status": record.get("status", "active"),
        "result": record.get("result") if finished else None,
        "submitted_count": 1 if record.get("submitted_pieces") else 0,
        "correct_pieces": dict(record.get("correct_pieces") or {}),
        "fen": record.get("corpus_fen", chess.STARTING_FEN),
        "side_to_move": _side_to_move(record),
        "started_at": record.get("started_at"),
        "updated_at": record.get("updated_at"),
        "finished_at": record.get("finished_at") if finished else None,
        "watch_url": f"/i/{record['attempt_id']}",
    }
    if finished:
        score = record.get("score") or {}
        state["accuracy"] = score.get("accuracy")
        state["full_position"] = score.get("full_position")
        state["total_pieces"] = score.get("total_pieces")
        state["score"] = {
            "total_pieces": score.get("total_pieces"),
            "exact": score.get("exact"),
            "missing": score.get("missing"),
            "extra": score.get("extra"),
            "misidentified": score.get("misidentified"),
            "full_position": score.get("full_position"),
        }
        state["difficulty"] = record.get("puzzle_rating")
    model_id = str(record.get("model_id") or "")
    if model_id:
        summary = identify_agent_summary(model_id)
        if summary:
            state["agent_summary"] = summary
    return state


def replay_payload(record: Dict[str, Any]) -> Dict[str, Any]:
    """Full replay (submitted vs correct, per-square errors); only after finish."""
    return {
        "ok": True,
        "attempt_id": record["attempt_id"],
        "agent_name": _agent_name(record),
        "result": record.get("result"),
        "failure_reason": record.get("failure_reason"),
        "score": record.get("score"),
        "per_square": record.get("per_square"),
        "submitted_pieces": record.get("submitted_pieces"),
        "correct_pieces": record["correct_pieces"],
        "difficulty": record.get("puzzle_rating"),
        "started_at": record.get("started_at"),
        "submitted_at": record.get("submitted_at"),
        "finished_at": record.get("finished_at"),
    }


def render_identify_board_png(record: Dict[str, Any]) -> bytes:
    """Answer-safe board PNG: the visible position, no highlights."""
    board = chess.Board(record.get("corpus_fen", chess.STARTING_FEN))
    return ChessBoardRenderer().render_board_bytes(
        board, bottom_color=bottom_color_for_board(board)
    )


def render_answer_overlay_png(record: Dict[str, Any]) -> bytes:
    """Post-completion answer board: green = exact, red = wrong/missing/extra."""
    renderer = ChessBoardRenderer()
    board = chess.Board(record.get("corpus_fen", chess.STARTING_FEN))
    flip_board = bottom_color_for_board(board) == "black"
    base = renderer.render_board_bytes(
        board, bottom_color=bottom_color_for_board(board)
    )
    image = Image.open(io.BytesIO(base)).convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    size = renderer.square_size
    for entry in record.get("per_square") or []:
        square = str(entry.get("square") or "")
        if len(square) != 2:
            continue
        x, y = _square_overlay_xy(renderer, square, flip_board=flip_board)
        fill = (0, 200, 0, 80) if entry.get("status") == "exact" else (255, 45, 45, 90)
        draw.rectangle([x, y, x + size, y + size], fill=fill)
    buf = io.BytesIO()
    Image.alpha_composite(image, overlay).convert("RGB").save(buf, "PNG")
    return buf.getvalue()


def public_attempt_row(record: Dict[str, Any]) -> Dict[str, Any]:
    """One discovery row for the public browse list."""
    finished = record.get("status") == "finished"
    row: Dict[str, Any] = {
        "attempt_id": record["attempt_id"],
        "key": record.get("key_fingerprint"),
        "model_id": record.get("model_id"),
        "agent_name": _agent_name(record),
        "status": record.get("status"),
        "result": record.get("result") if finished else None,
        "submitted_count": 1 if record.get("submitted_pieces") else 0,
        "started_at": record.get("started_at"),
        "finished_at": record.get("finished_at") if finished else None,
        "watch_url": f"/i/{record['attempt_id']}",
    }
    if finished:
        score = record.get("score") or {}
        row["accuracy"] = score.get("accuracy")
        row["full_position"] = score.get("full_position")
        row["total_pieces"] = score.get("total_pieces")
        row["difficulty"] = record.get("puzzle_rating")
    return row
