"""Agent vs human routes on /api/v1 (draw offers)."""

from __future__ import annotations

from typing import Any, Callable, Dict

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from .api_limits import AuthContext
from .game_service import GameService
from .game_types import is_human_vs_agent_state
__all__ = ["register_avh_agent_routes"]


def register_avh_agent_routes(
    router: APIRouter,
    svc_fn: Callable[[], GameService],
    *,
    auth_context,
    require_game_participant: Callable[..., JSONResponse | tuple[AuthContext, str]],
    sanitize: Callable[[Dict[str, Any]], Dict[str, Any]],
    err,
) -> None:
    def _require_avh_game(game_id: str) -> JSONResponse | None:
        state = svc_fn().game_manager.load_state(game_id)
        if not state or not is_human_vs_agent_state(state):
            return err(400, "Draw offers are only available for agent vs human games")
        return None

    def _draw_err(result: Dict[str, Any]) -> JSONResponse:
        message = result.get("error", "Draw action failed")
        status = 404 if "not found" in message.lower() else 400
        return err(status, message)

    @router.post("/games/{game_id}/draw/offer")
    async def game_draw_offer(game_id: str, auth: AuthContext = Depends(auth_context)):
        access = require_game_participant(game_id, auth)
        if isinstance(access, JSONResponse):
            return access
        denied = _require_avh_game(game_id)
        if denied:
            return denied
        result = svc_fn().agent_draw_offer(game_id)
        if not result.get("ok"):
            return _draw_err(result)
        return sanitize(result)

    @router.post("/games/{game_id}/draw/accept")
    async def game_draw_accept(game_id: str, auth: AuthContext = Depends(auth_context)):
        access = require_game_participant(game_id, auth)
        if isinstance(access, JSONResponse):
            return access
        denied = _require_avh_game(game_id)
        if denied:
            return denied
        result = svc_fn().agent_draw_accept(game_id)
        if not result.get("ok"):
            return _draw_err(result)
        return sanitize(result)

    @router.post("/games/{game_id}/draw/decline")
    async def game_draw_decline(game_id: str, auth: AuthContext = Depends(auth_context)):
        access = require_game_participant(game_id, auth)
        if isinstance(access, JSONResponse):
            return access
        denied = _require_avh_game(game_id)
        if denied:
            return denied
        result = svc_fn().agent_draw_decline(game_id)
        if not result.get("ok"):
            return _draw_err(result)
        return sanitize(result)
