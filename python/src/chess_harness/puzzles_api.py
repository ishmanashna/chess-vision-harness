"""Authenticated agent puzzle API under /api/v1/puzzles/*
(select/start, board PNG, text fallback, submit move, abandon, review).

Puzzle attempts are not games: they never count against game or move caps,
never create PGNs, and never appear in ``results.jsonl``. Hidden puzzle
metadata (FEN, solution line, imported difficulty) is never exposed before
the attempt completes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

import chess
from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from .agent_brief import public_base_url
from .api_limits import ApiLimitEnforcer, AuthContext
from .board_text import bottom_color_for_board, format_board_text
from .puzzle_attempt import (
    PuzzleAttemptStore,
    apply_submission,
    session_exclude_sec,
)
from .puzzle_brief import render_puzzle_brief
from .puzzle_ratings import PuzzleRatingStore
from .puzzle_select import select_puzzle_for_agent
from .puzzle_store import PuzzleStore
from .render_pillow import ChessBoardRenderer
from .scope_auth import reject_scoped_auth
from .limits import load_limits

__all__ = ["register_puzzle_routes"]

_SCENED_REJECT = "Scoped child credentials cannot use puzzle endpoints"


class PuzzleMoveBody(BaseModel):
    move: str = Field(..., min_length=2)


def register_puzzle_routes(
    router: APIRouter,
    *,
    err: Callable[[int, str], JSONResponse],
    auth_context: Any = None,
    limits: ApiLimitEnforcer,
) -> None:
    if auth_context is None:
        raise ValueError("puzzle routes require an auth context dependency")

    def _store() -> PuzzleAttemptStore:
        return PuzzleAttemptStore()

    def _own(record: Dict[str, Any], auth: AuthContext) -> bool:
        return (
            record.get("key_fingerprint") == auth.key_fingerprint
            and record.get("model_id") == auth.model_id
        )

    def _open(attempt_id: str, auth: AuthContext):
        if auth.scoped is not None:
            return err(403, _SCENED_REJECT)
        record = _store().abandon_if_idle(
            attempt_id, float(load_limits().idle_timeout_sec)
        )
        if record is None or not _own(record, auth):
            return err(404, "Attempt not found")
        return record

    def _render(record: Dict[str, Any]) -> bytes:
        board = chess.Board(record["board_fen"])
        last_moves: list = []
        if record.get("submitted_moves"):
            last_moves.append(
                chess.Move.from_uci(record["submitted_moves"][-1])
            )
        if record.get("opponent_moves"):
            last_moves.append(
                chess.Move.from_uci(record["opponent_moves"][-1])
            )
        return ChessBoardRenderer().render_board_bytes(
            board,
            last_moves=last_moves,
            bottom_color=bottom_color_for_board(board),
        )

    def _safe_start_payload(
        attempt_id: str, record: Dict[str, Any], raw_key: str
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "ok": True,
            "attempt_id": attempt_id,
            "puzzle_id": record["puzzle_id"],
            "status": record["status"],
            "rating_min": record.get("rating_min"),
            "rating_max": record.get("rating_max"),
            "theme": record.get("theme"),
            "board_url": f"/api/v1/puzzles/{attempt_id}/board",
            "board_text_url": f"/api/v1/puzzles/{attempt_id}/board.txt",
            "move_url": f"/api/v1/puzzles/{attempt_id}/move/{{move}}",
            "review_url": f"/api/v1/puzzles/{attempt_id}/review",
            "abandon_url": f"/api/v1/puzzles/{attempt_id}/abandon",
        }
        if raw_key:
            payload["agent_brief"] = render_puzzle_brief(
                public_base_url(), attempt_id, raw_key
            )
        return payload

    @router.post("/puzzles/start")
    async def puzzle_start(
        rating_min: Optional[int] = None,
        rating_max: Optional[int] = None,
        theme: Optional[str] = None,
        auth: AuthContext = Depends(auth_context),
        authorization: Optional[str] = Header(None),
    ):
        denied = reject_scoped_auth(auth, err, _SCENED_REJECT)
        if denied:
            return denied
        if (
            rating_min is not None
            and rating_max is not None
            and rating_min > rating_max
        ):
            return err(400, "rating_min must be <= rating_max")
        store = _store()
        denied = limits.check_puzzle_attempt(store.active_count(auth.key_fingerprint), auth)
        if denied:
            return denied

        excluded = store.recent_puzzle_ids(
            auth.key_fingerprint, session_exclude_sec()
        )
        record = select_puzzle_for_agent(
            model_id=auth.model_id,
            rating_min=rating_min,
            rating_max=rating_max,
            theme=theme or None,
            exclusions=excluded,
        )
        if record is None:
            return err(404, "No eligible puzzle found for the requested filters")

        attempt = store.create(
            puzzle_id=record["puzzle_id"],
            key_fingerprint=auth.key_fingerprint,
            model_id=auth.model_id,
            rating_min=rating_min,
            rating_max=rating_max,
            theme=theme or None,
            start_fen=record["display_fen"],
            board_fen=record["display_fen"],
            solution_moves=list(record["solution_moves"]),
            puzzle_rating=int(record.get("rating") or 0),
            content_version=str(
                PuzzleStore().manifest().get("dataset_version") or "unknown"
            ),
        )
        raw_key = ""
        if authorization and authorization.lower().startswith("bearer "):
            raw_key = authorization[7:].strip()
        return _safe_start_payload(attempt["attempt_id"], attempt, raw_key)

    @router.get("/puzzles/{attempt_id}/board")
    async def puzzle_board(attempt_id: str, auth: AuthContext = Depends(auth_context)):
        record = _open(attempt_id, auth)
        if isinstance(record, JSONResponse):
            return record
        record = _store().ensure_agent_joined(attempt_id) or record
        try:
            png = _render(record)
        except Exception as exc:
            return err(500, f"Board render failed: {exc}")
        return Response(content=png, media_type="image/png")

    @router.get("/puzzles/{attempt_id}/board.txt")
    async def puzzle_board_text(
        attempt_id: str, auth: AuthContext = Depends(auth_context)
    ):
        record = _open(attempt_id, auth)
        if isinstance(record, JSONResponse):
            return record
        record = _store().ensure_agent_joined(attempt_id) or record
        board = chess.Board(record["board_fen"])
        return PlainTextResponse(
            content=format_board_text(
                board, bottom_color=bottom_color_for_board(board)
            ),
            headers={"Cache-Control": "no-store"},
        )

    @router.post("/puzzles/{attempt_id}/move/{move}")
    async def puzzle_move_path(
        attempt_id: str, move: str, auth: AuthContext = Depends(auth_context)
    ):
        return await _do_move(attempt_id, move, auth)

    @router.post("/puzzles/{attempt_id}/move")
    async def puzzle_move_body(
        attempt_id: str,
        body: PuzzleMoveBody,
        auth: AuthContext = Depends(auth_context),
    ):
        return await _do_move(attempt_id, body.move, auth)

    async def _do_move(attempt_id: str, move: str, auth: AuthContext):
        record = _open(attempt_id, auth)
        if isinstance(record, JSONResponse):
            return record
        move = (move or "").strip()
        if len(move) < 2:
            return err(400, "Move required")

        outcome: Dict[str, Any] = {}
        updated = _store().update(
            attempt_id, lambda rec: outcome.update(apply_submission(rec, move))
        )
        if updated is None:
            return err(404, "Attempt not found")
        if not outcome.get("ok"):
            return err(409, outcome.get("message", "Attempt is not active"))

        if updated["status"] == "finished" and updated["result"] in (
            "correct",
            "failed",
        ):
            rating_fields = PuzzleRatingStore().record_attempt(updated)
            if rating_fields:
                _store().update(attempt_id, lambda rec: rec.update(rating_fields))
                updated = _store().get(attempt_id)
            from .snapshot_leaderboard import request_public_snapshots_refresh

            request_public_snapshots_refresh()

        payload: Dict[str, Any] = {
            "ok": True,
            "attempt_id": attempt_id,
            "status": updated["status"],
            "result": updated["result"],
            "moves_played": len(updated["submitted_moves"]),
            "message": outcome.get("message"),
        }
        if updated["status"] != "active":
            payload["review_url"] = f"/api/v1/puzzles/{attempt_id}/review"
        return payload

    @router.post("/puzzles/{attempt_id}/abandon")
    async def puzzle_abandon(attempt_id: str, auth: AuthContext = Depends(auth_context)):
        record = _open(attempt_id, auth)
        if isinstance(record, JSONResponse):
            return record

        def _abandon(rec: Dict[str, Any]) -> None:
            if rec["status"] == "active":
                rec["status"] = "abandoned"
                rec["finished_at"] = datetime.now(timezone.utc).isoformat()

        updated = _store().update(attempt_id, _abandon)
        assert updated is not None
        return {
            "ok": True,
            "attempt_id": attempt_id,
            "status": updated["status"],
            "message": "Attempt abandoned",
        }

    @router.get("/puzzles/{attempt_id}/review")
    async def puzzle_review(attempt_id: str, auth: AuthContext = Depends(auth_context)):
        record = _open(attempt_id, auth)
        if isinstance(record, JSONResponse):
            return record
        if record["status"] == "active":
            return err(409, "Review unlocks only after the attempt ends")
        if record["status"] == "abandoned":
            return {
                "ok": True,
                "status": "abandoned",
                "result": None,
                "message": "Attempt was abandoned; no solution review.",
            }
        puzzle = PuzzleStore().get(record["puzzle_id"]) or {}
        return {
            "ok": True,
            "attempt_id": attempt_id,
            "puzzle_id": record["puzzle_id"],
            "status": record["status"],
            "result": record["result"],
            "failure_reason": record.get("failure_reason"),
            "first_wrong_move": record.get("first_wrong_move"),
            "submitted_moves": list(record["submitted_moves"]),
            "opponent_moves": list(record["opponent_moves"]),
            "solution_moves": list(record["solution_moves"]),
            "themes": list(puzzle.get("themes") or []),
            "source_link": puzzle.get("game_url") or "",
            "puzzle_rating": record.get("puzzle_rating"),
            "content_version": record.get("content_version"),
            "rating_before": record.get("rating_before"),
            "rating_after": record.get("rating_after"),
            "rating_change": record.get("rating_change"),
            "rating_deviation_before": record.get("rating_deviation_before"),
            "rating_deviation_after": record.get("rating_deviation_after"),
            "puzzle_rating_before": record.get("puzzle_rating_before"),
            "puzzle_rating_after": record.get("puzzle_rating_after"),
            "puzzle_rating_change": record.get("puzzle_rating_change"),
            "elapsed_seconds": record.get("elapsed_seconds"),
            "started_at": record["started_at"],
            "finished_at": record.get("finished_at"),
        }