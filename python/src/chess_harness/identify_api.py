"""Authenticated board-identification API under /api/v1/identify/*
(start/select, board PNG, text fallback, submit placement, abandon, review).

Identification attempts are not games: they never count against game, move,
or puzzle caps, never create PGNs, and never appear in ``results.jsonl``.
The true placement, position provenance (puzzle id), and difficulty are never
exposed before the answer is submitted — submission is final and scored
immediately, then the placement and errors are revealed.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional

import chess
from fastapi import APIRouter, Body, Depends, Header
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field

from .agent_brief import public_base_url
from .api_limits import ApiLimitEnforcer, AuthContext
from .board_text import format_board_text
from .identify_attempt import IdentifyAttemptStore
from .identify_scoring import build_placement, submit_answer, validate_pieces_answer
from .identify_brief import render_identify_brief
from .limits import load_limits
from .puzzle_attempt import session_exclude_sec
from .puzzle_store import PuzzleStore
from .render_pillow import ChessBoardRenderer
from .scope_auth import reject_scoped_auth

__all__ = ["register_identify_routes"]

_SCENED_REJECT = "Scoped child credentials cannot use identify endpoints"


class IdentifyAnswerBody(BaseModel):
    pieces: Dict[str, str] = Field(..., description="occupied square -> piece code")


def register_identify_routes(
    router: APIRouter,
    *,
    err: Callable[[int, str], JSONResponse],
    auth_context: Any = None,
    limits: ApiLimitEnforcer,
) -> None:
    if auth_context is None:
        raise ValueError("identify routes require an auth context dependency")

    def _store() -> IdentifyAttemptStore:
        return IdentifyAttemptStore()

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

    def _safe_start_payload(
        attempt_id: str, record: Dict[str, Any], raw_key: str
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "ok": True,
            "attempt_id": attempt_id,
            "status": record["status"],
            "rating_min": record.get("rating_min"),
            "rating_max": record.get("rating_max"),
            "board_url": f"/api/v1/identify/{attempt_id}/board",
            "board_text_url": f"/api/v1/identify/{attempt_id}/board.txt",
            "answer_url": f"/api/v1/identify/{attempt_id}/answer",
            "review_url": f"/api/v1/identify/{attempt_id}/review",
            "abandon_url": f"/api/v1/identify/{attempt_id}/abandon",
        }
        if raw_key:
            payload["agent_brief"] = render_identify_brief(
                public_base_url(), attempt_id, raw_key
            )
        return payload

    @router.post("/identify/start")
    async def identify_start(
        rating_min: Optional[int] = None,
        rating_max: Optional[int] = None,
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
        denied = limits.check_identify_attempt(
            store.active_count(auth.key_fingerprint), auth
        )
        if denied:
            return denied

        excluded = store.recent_puzzle_ids(
            auth.key_fingerprint, session_exclude_sec()
        )
        record = PuzzleStore().random_puzzle(
            rating_min=rating_min, rating_max=rating_max, exclusions=excluded
        )
        if record is None:
            return err(404, "No eligible position found for the requested filters")

        display_fen = record["display_fen"]
        attempt = store.create(
            puzzle_id=record["puzzle_id"],
            key_fingerprint=auth.key_fingerprint,
            model_id=auth.model_id,
            rating_min=rating_min,
            rating_max=rating_max,
            corpus_fen=display_fen,
            correct_pieces=build_placement(chess.Board(display_fen)),
            puzzle_rating=int(record.get("rating") or 0),
        )
        raw_key = ""
        if authorization and authorization.lower().startswith("bearer "):
            raw_key = authorization[7:].strip()
        return _safe_start_payload(attempt["attempt_id"], attempt, raw_key)

    @router.get("/identify/{attempt_id}/board")
    async def identify_board(
        attempt_id: str, auth: AuthContext = Depends(auth_context)
    ):
        record = _open(attempt_id, auth)
        if isinstance(record, JSONResponse):
            return record
        try:
            png = ChessBoardRenderer().render_board_bytes(
                chess.Board(record["corpus_fen"])
            )
        except Exception as exc:
            return err(500, f"Board render failed: {exc}")
        return Response(content=png, media_type="image/png")

    @router.get("/identify/{attempt_id}/board.txt")
    async def identify_board_text(
        attempt_id: str, auth: AuthContext = Depends(auth_context)
    ):
        record = _open(attempt_id, auth)
        if isinstance(record, JSONResponse):
            return record
        return PlainTextResponse(
            content=format_board_text(chess.Board(record["corpus_fen"])),
            headers={"Cache-Control": "no-store"},
        )

    @router.post("/identify/{attempt_id}/answer")
    async def identify_answer(
        attempt_id: str,
        body: Any = Body(...),
        auth: AuthContext = Depends(auth_context),
    ):
        record = _open(attempt_id, auth)
        if isinstance(record, JSONResponse):
            return record
        if not isinstance(body, dict) or "pieces" not in body:
            return err(
                400,
                "request body must be a JSON object: {\"pieces\": {\"a1\": \"wR\"}}",
            )
        schema_error = validate_pieces_answer(body["pieces"])
        if schema_error:
            return err(400, schema_error)

        pieces = dict(body["pieces"])
        outcome: Dict[str, Any] = {}
        updated = _store().update(
            attempt_id, lambda rec: outcome.update(submit_answer(rec, pieces))
        )
        if updated is None:
            return err(404, "Attempt not found")
        if not outcome.get("ok"):
            return err(409, outcome.get("message", "Attempt is not active"))

        if updated["status"] != "active":
            from .snapshot_leaderboard import request_public_snapshots_refresh

            request_public_snapshots_refresh()

        payload: Dict[str, Any] = {
            "ok": True,
            "attempt_id": attempt_id,
            "status": updated["status"],
            "result": updated["result"],
            "accuracy": updated["score"]["accuracy"],
            "score": updated["score"],
            "message": outcome.get("message"),
            "review_url": f"/api/v1/identify/{attempt_id}/review",
        }
        return payload

    @router.post("/identify/{attempt_id}/abandon")
    async def identify_abandon(
        attempt_id: str, auth: AuthContext = Depends(auth_context)
    ):
        record = _open(attempt_id, auth)
        if isinstance(record, JSONResponse):
            return record

        def _abandon(rec: Dict[str, Any]) -> None:
            if rec["status"] == "active":
                rec["status"] = "abandoned"
                rec["finished_at"] = datetime.now(timezone.utc).isoformat()

        updated = _store().update(attempt_id, _abandon)
        assert updated is not None
        if updated["status"] == "abandoned":
            from .snapshot_leaderboard import request_public_snapshots_refresh

            request_public_snapshots_refresh()
        return {
            "ok": True,
            "attempt_id": attempt_id,
            "status": updated["status"],
            "message": "Attempt abandoned",
        }

    @router.get("/identify/{attempt_id}/review")
    async def identify_review(
        attempt_id: str, auth: AuthContext = Depends(auth_context)
    ):
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
                "message": "Attempt was abandoned; no placement review.",
            }
        return {
            "ok": True,
            "attempt_id": attempt_id,
            "status": record["status"],
            "result": record["result"],
            "failure_reason": record.get("failure_reason"),
            "score": record["score"],
            "per_square": record.get("per_square"),
            "submitted_pieces": record.get("submitted_pieces"),
            "correct_pieces": record["correct_pieces"],
            "difficulty": record.get("puzzle_rating"),
            "started_at": record["started_at"],
            "submitted_at": record.get("submitted_at"),
            "finished_at": record.get("finished_at"),
        }