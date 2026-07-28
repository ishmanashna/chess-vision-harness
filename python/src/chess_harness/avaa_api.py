"""AvaA-specific HTTP API helpers and routes."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .activity_audit import record_activity
from .agent_brief import public_base_url, render_agent_brief_avaa
from .api_limits import ApiLimitEnforcer, AuthContext, client_ip
from .avaa import is_avaa_state, participant_color
from .game_service import GameService
from .game_types import GAME_TYPE_AGENT_VS_AGENT


class CreateAvAAGameBody(BaseModel):
    white_model_id: str = Field(..., min_length=1, max_length=64)
    black_model_id: str = Field(..., min_length=1, max_length=64)


def require_game_participant(
    game_service: GameService,
    game_id: str,
    auth: AuthContext,
    err: Callable[[int, str], JSONResponse],
) -> JSONResponse | tuple[AuthContext, str]:
    state = game_service.game_manager.load_state(game_id)
    if state is None:
        return err(404, f"Game {game_id} not found")
    if is_avaa_state(state):
        color = participant_color(state, auth.model_id)
        if color is None:
            return err(401, "API key does not match this game")
        return auth, color
    game_model = state.get("model_name")
    if game_model != auth.model_id:
        return err(401, "API key does not match this game")
    return auth, state.get("agent_color", "WHITE")


def register_avaa_routes(
    router: APIRouter,
    *,
    svc_fn: Callable[[], GameService],
    limits: ApiLimitEnforcer,
    err: Callable[[int, str], JSONResponse],
    sanitize: Callable[[Dict[str, Any]], Dict[str, Any]],
    new_game_id: Callable[[], str],
    auth_context: Callable[..., AuthContext],
) -> None:
    @router.post("/games/agent-vs-agent")
    async def create_agent_vs_agent_game(
        body: CreateAvAAGameBody,
        request: Request,
        auth: AuthContext = Depends(auth_context),
        authorization: Optional[str] = Header(None),
    ):
        from .models import ModelRegistry

        registry = ModelRegistry()
        for model_id in (body.white_model_id, body.black_model_id):
            if not registry.is_inscribed(model_id):
                return err(400, f"Model '{model_id}' is not inscribed")
        if auth.model_id not in (body.white_model_id, body.black_model_id):
            return err(401, "API key must belong to white_model_id or black_model_id")

        denied = limits.check_create_game(svc_fn(), auth)
        if denied:
            return denied

        game_id = new_game_id()
        result = svc_fn().new_agent_vs_agent_game(
            game_id,
            body.white_model_id,
            body.black_model_id,
        )
        if not result.get("ok"):
            return err(400, result.get("error", "Failed to create game"))
        limits.record_create_game(auth)
        try:
            record_activity(
                "create_game",
                model_id=auth.model_id,
                game_id=str(result.get("game_id") or game_id),
                game_type=GAME_TYPE_AGENT_VS_AGENT,
                white_model_id=body.white_model_id,
                black_model_id=body.black_model_id,
                client_ip=client_ip(request),
                user_agent=request.headers.get("user-agent", ""),
            )
        except Exception:
            pass

        resolved_id = str(result.get("game_id") or game_id)
        state = svc_fn().game_manager.load_state(resolved_id) or {}
        caller_color = participant_color(state, auth.model_id)
        payload: Dict[str, Any] = {"ok": True, **sanitize(result)}
        if caller_color:
            payload["agent_color"] = caller_color
            payload["your_turn"] = caller_color == "WHITE"
        raw_key = ""
        if authorization and authorization.lower().startswith("bearer "):
            raw_key = authorization[7:].strip()
        if raw_key and caller_color:
            opponent = (
                state.get("black_display_name")
                if caller_color == "WHITE"
                else state.get("white_display_name")
            ) or "Opponent"
            payload["agent_brief"] = render_agent_brief_avaa(
                public_base_url(),
                resolved_id,
                raw_key,
                caller_color.lower(),
                str(opponent),
            )
        return payload
