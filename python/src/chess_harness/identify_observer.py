"""Public board-identification watching and replay (/i/{attempt_id}, public API).

Observer-safe by construction: while an attempt is active the published state
contains only the attempt id, agent display name, the attempt-chain key, the
current visible board, and submission progress. The true placement, submitted
placement, per-square errors, and difficulty are never published before
submission; replay unlocks only after the attempt ends.
"""

from __future__ import annotations

import io
from typing import Any, Dict

import chess
from PIL import Image, ImageDraw

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


def observer_state(record: Dict[str, Any]) -> Dict[str, Any]:
    """Observer-safe live state (never leaks placements or difficulty)."""
    finished = record.get("status") == "finished"
    state: Dict[str, Any] = {
        "ok": True,
        "attempt_id": record["attempt_id"],
        "key": record.get("key_fingerprint"),
        "model_id": record.get("model_id"),
        "agent_name": _agent_name(record),
        "status": record.get("status", "active"),
        "result": record.get("result") if finished else None,
        "submitted_count": 1 if record.get("submitted_pieces") else 0,
        "fen": record.get("corpus_fen", chess.STARTING_FEN),
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
    return ChessBoardRenderer().render_board_bytes(
        chess.Board(record.get("corpus_fen", chess.STARTING_FEN))
    )


def render_answer_overlay_png(record: Dict[str, Any]) -> bytes:
    """Post-completion answer board: green = exact, red = wrong/missing/extra."""
    renderer = ChessBoardRenderer()
    base = renderer.render_board_bytes(
        chess.Board(record.get("corpus_fen", chess.STARTING_FEN))
    )
    image = Image.open(io.BytesIO(base)).convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    size = renderer.square_size
    for entry in record.get("per_square") or []:
        square = str(entry.get("square") or "")
        if len(square) != 2:
            continue
        file_index = chess.FILE_NAMES.index(square[0])
        rank = int(square[1]) - 1
        x = renderer.coord_margin + file_index * size
        y = (7 - rank) * size
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
