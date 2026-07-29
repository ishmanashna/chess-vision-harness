"""Human-vs-agent HTTP API helpers and routes."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .activity_audit import record_activity
from .agent_brief import public_base_url, render_agent_brief_human
from .api_limits import ApiLimitEnforcer, AuthContext, client_ip
from .game_service import GameService
from .game_types import GAME_TYPE_HUMAN_VS_AGENT


class CreateHumanGameBody(BaseModel):
    nickname: Optional[str] = Field(None, max_length=64)


def register_human_vs_agent_routes(
    router: APIRouter,
    *,
    svc_fn: Callable[[], GameService],
    limits: ApiLimitEnforcer,
    err: Callable[[int, str], JSONResponse],
    sanitize: Callable[[Dict[str, Any]], Dict[str, Any]],
    new_game_id: Callable[[], str],
    auth_context: Callable[..., AuthContext],
) -> None:
    @router.post("/games/human")
    async def create_human_vs_agent_game(
        body: CreateHumanGameBody,
        request: Request,
        auth: AuthContext = Depends(auth_context),
        authorization: Optional[str] = Header(None),
    ):
        from .models import ModelRegistry

        registry = ModelRegistry()
        if not registry.is_inscribed(auth.model_id):
            return err(400, f"Model '{auth.model_id}' is not inscribed")

        denied = limits.check_create_game(svc_fn(), auth)
        if denied:
            return denied

        game_id = new_game_id()
        result = svc_fn().new_human_vs_agent_game(
            game_id,
            auth.model_id,
            human_nickname=body.nickname,
        )
        if not result.get("ok"):
            return err(400, result.get("error", "Failed to create game"))
        limits.record_create_game(auth)
        try:
            record_activity(
                "create_game",
                model_id=auth.model_id,
                game_id=str(result.get("game_id") or game_id),
                game_type=GAME_TYPE_HUMAN_VS_AGENT,
                client_ip=client_ip(request),
                user_agent=request.headers.get("user-agent", ""),
            )
        except Exception:
            pass

        resolved_id = str(result.get("game_id") or game_id)
        payload: Dict[str, Any] = {"ok": True, **sanitize(result)}
        play_token = result.get("play_token")
        if play_token:
            payload["play_token"] = play_token
            payload["play_url"] = f"{public_base_url()}/play/{resolved_id}?token={play_token}"
        raw_key = ""
        if authorization and authorization.lower().startswith("bearer "):
            raw_key = authorization[7:].strip()
        if raw_key:
            agent_color = str(result.get("agent_color") or "WHITE").lower()
            nickname = str(result.get("human_nickname") or "Human")
            payload["agent_brief"] = render_agent_brief_human(
                public_base_url(),
                resolved_id,
                raw_key,
                agent_color,
                nickname,
            )
        return payload
