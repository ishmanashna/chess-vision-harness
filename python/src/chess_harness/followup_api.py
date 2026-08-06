"""HTTP routes for approval-gated follow-up game creation (/api/v1).

An agent that finished a game can request a follow-up; nothing is created
until an operator explicitly approves. The existing POST /api/v1/games path
stays approval-free by design.
"""

from __future__ import annotations

import os
import secrets
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .activity_audit import record_activity
from .agent_brief import public_base_url, render_agent_brief
from .api_limits import ApiLimitEnforcer, AuthContext, client_ip
from .calibration_auth import host_is_loopback
from .commands import resolve_agent_color
from .followup import FollowupApprovalError, FollowupApprovalStore
from .game_service import GameService

__all__ = ["register_followup_routes"]

_APPROVAL_SECRET_ENV = "CHESS_HARNESS_FOLLOWUP_APPROVAL_SECRET"
_APPROVAL_SECRET_HEADER = "X-Chess-Harness-Followup-Secret"


class FollowupGameBody(BaseModel):
    previous_game_id: str = Field(..., min_length=1, max_length=64)
    model: str = Field(..., min_length=1, max_length=64)
    opponent: Optional[str] = None
    agent_color: Optional[str] = None


def _store() -> FollowupApprovalStore:
    return FollowupApprovalStore()


def _require_operator(
    request: Request, err: Callable[[int, str], JSONResponse]
) -> Optional[JSONResponse]:
    """Operator gate: loopback host header or a configured secret."""
    if host_is_loopback(request):
        return None
    configured = os.environ.get(_APPROVAL_SECRET_ENV, "").strip()
    provided = request.headers.get(_APPROVAL_SECRET_HEADER, "").strip()
    if configured and provided and secrets.compare_digest(configured, provided):
        return None
    return err(
        403,
        "Follow-up approval is only available on localhost or with the follow-up approval secret",
    )


def _require_finished_game(
    svc: GameService, game_id: str, err: Callable[[int, str], JSONResponse]
):
    """Validate the id, load state, and require a finished game."""
    if not svc.game_manager.validate_game_id(game_id):
        return err(404, f"Game {game_id} not found")
    state = svc.game_manager.load_state(game_id)
    if state is None:
        return err(404, f"Game {game_id} not found")
    if state.get("status") != "finished":
        return err(409, "The previous game must be finished before a follow-up is possible")
    return state


def register_followup_routes(
    router: APIRouter,
    *,
    svc_fn: Callable[[], GameService],
    limits: ApiLimitEnforcer,
    err: Callable[[int, str], JSONResponse],
    sanitize: Callable[[Dict[str, Any]], Dict[str, Any]],
    new_game_id: Callable[[], str],
    auth_context: Callable[..., AuthContext],
    require_game_participant: Optional[Callable[..., Any]] = None,
) -> None:
    def _require_participant(game_id: str, auth: AuthContext):
        from .avaa_api import require_game_participant as _classic

        return require_game_participant(game_id, auth) if require_game_participant \
            else _classic(svc_fn(), game_id, auth, err)

    @router.post("/games/{game_id}/request-followup")
    async def request_followup(game_id: str, auth: AuthContext = Depends(auth_context)):
        if not svc_fn().game_manager.validate_game_id(game_id):
            return err(404, f"Game {game_id} not found")
        access = _require_participant(game_id, auth)
        if isinstance(access, JSONResponse):
            return access
        finished = _require_finished_game(svc_fn(), game_id, err)
        if isinstance(finished, JSONResponse):
            return finished
        try:
            record = _store().request(game_id, auth.model_id)
        except FollowupApprovalError as exc:
            return err(exc.status, exc.message)
        return {
            "ok": True,
            "game_id": record["game_id"],
            "model_id": record["model_id"],
            "state": record["state"],
        }

    @router.post("/games/{game_id}/approve-followup")
    async def approve_followup(game_id: str, request: Request):
        denied = _require_operator(request, err)
        if denied is not None:
            return denied
        if not svc_fn().game_manager.validate_game_id(game_id):
            return err(404, f"Game {game_id} not found")
        try:
            record = _store().approve(game_id)
        except FollowupApprovalError as exc:
            return err(exc.status, exc.message)
        return {
            "ok": True,
            "game_id": record["game_id"],
            "model_id": record["model_id"],
            "state": record["state"],
            "approved_at": record.get("approved_at"),
            "expires_at": record.get("expires_at"),
        }

    @router.post("/games/followup")
    async def create_followup_game(
        body: FollowupGameBody,
        request: Request,
        auth: AuthContext = Depends(auth_context),
        authorization: Optional[str] = Header(None),
    ):
        from .scope_auth import reject_scoped_auth

        denied_scoped = reject_scoped_auth(auth, err, "Scoped child credentials cannot create follow-up games")
        if denied_scoped:
            return denied_scoped
        previous_game_id = body.previous_game_id.strip()
        if not svc_fn().game_manager.validate_game_id(previous_game_id):
            return err(404, f"Game {previous_game_id} not found")
        if body.model != auth.model_id:
            return err(400, "model must match the model the API key belongs to")
        finished = _require_finished_game(svc_fn(), previous_game_id, err)
        if isinstance(finished, JSONResponse):
            return finished
        try:
            color = resolve_agent_color(body.agent_color)
        except ValueError as exc:
            return err(400, str(exc))
        denied = limits.check_create_game(svc_fn(), auth)
        if denied:
            return denied
        try:
            _store().consume(previous_game_id, auth.model_id)
        except FollowupApprovalError as exc:
            return err(exc.status, exc.message)
        game_id = new_game_id()
        result = svc_fn().new_game(
            game_id,
            color,
            model_name=auth.model_id,
            opponent_id=body.opponent,
        )
        if not result.get("ok"):
            _store().revert(previous_game_id)
            return err(400, result.get("error", "Failed to create game"))
        limits.record_create_game(auth)
        try:
            record_activity(
                "create_followup",
                model_id=auth.model_id,
                game_id=str(result.get("game_id") or game_id),
                client_ip=client_ip(request),
                user_agent=request.headers.get("user-agent", ""),
            )
        except Exception:
            pass
        payload: Dict[str, Any] = {"ok": True, **sanitize(result)}
        payload["previous_game_id"] = previous_game_id
        raw_key = ""
        if authorization and authorization.lower().startswith("bearer "):
            raw_key = authorization[7:].strip()
        if raw_key:
            payload["agent_brief"] = render_agent_brief(
                public_base_url(), str(result.get("game_id") or game_id), raw_key
            )
        return payload