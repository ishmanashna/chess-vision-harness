"""AvaA-specific HTTP API helpers and routes."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .activity_audit import record_activity
from .agent_brief import public_base_url, render_agent_brief_avaa
from .api_keys import ApiKeyStore
from .api_limits import ApiLimitEnforcer, AuthContext, client_ip
from .avaa import is_avaa_state, participant_color
from .game_service import GameService
from .game_types import GAME_TYPE_AGENT_VS_AGENT, is_human_vs_agent_state


class CreateAvAAGameBody(BaseModel):
    white_model_id: str = Field(..., min_length=1, max_length=64)
    black_model_id: str = Field(..., min_length=1, max_length=64)
    # Optional peer key so Create Game Direct can return both briefs once (operator session only).
    peer_api_key: Optional[str] = Field(None, min_length=1, max_length=256)


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
    if is_human_vs_agent_state(state):
        if auth.model_id != state.get("model_name"):
            return err(401, "API key does not match this game")
        return auth, state.get("agent_color", "WHITE")
    game_model = state.get("model_name")
    if game_model != auth.model_id:
        return err(401, "API key does not match this game")
    return auth, state.get("agent_color", "WHITE")


def _side_brief(
    state: Dict[str, Any],
    game_id: str,
    color: str,
    raw_key: str,
) -> str:
    opponent = (
        state.get("black_display_name")
        if color == "WHITE"
        else state.get("white_display_name")
    ) or "Opponent"
    return render_agent_brief_avaa(
        public_base_url(),
        game_id,
        raw_key,
        color.lower(),
        str(opponent),
    )


def register_avaa_routes(
    router: APIRouter,
    *,
    svc_fn: Callable[[], GameService],
    limits: ApiLimitEnforcer,
    err: Callable[[int, str], JSONResponse],
    sanitize: Callable[[Dict[str, Any]], Dict[str, Any]],
    new_game_id: Callable[[], str],
    auth_context: Callable[..., AuthContext],
    key_store_fn: Optional[Callable[[], ApiKeyStore]] = None,
) -> None:
    keys_fn = key_store_fn or ApiKeyStore

    @router.post("/games/agent-vs-agent")
    async def create_agent_vs_agent_game(
        body: CreateAvAAGameBody,
        request: Request,
        auth: AuthContext = Depends(auth_context),
        authorization: Optional[str] = Header(None),
    ):
        from .models import ModelRegistry

        if body.white_model_id.strip() == body.black_model_id.strip():
            return err(400, "white_model_id and black_model_id must differ")

        registry = ModelRegistry()
        for model_id in (body.white_model_id, body.black_model_id):
            if not registry.is_inscribed(model_id):
                return err(400, f"Model '{model_id}' is not inscribed")
        if auth.model_id not in (body.white_model_id, body.black_model_id):
            return err(401, "API key must belong to white_model_id or black_model_id")

        peer_model_id: Optional[str] = None
        peer_raw = (body.peer_api_key or "").strip()
        if peer_raw:
            peer_model_id = keys_fn().verify(peer_raw)
            if not peer_model_id:
                return err(401, "Invalid peer_api_key")
            expected_peer = (
                body.black_model_id
                if auth.model_id == body.white_model_id
                else body.white_model_id
            )
            if peer_model_id != expected_peer:
                return err(401, "peer_api_key must belong to the other model in this game")

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
            payload["agent_brief"] = _side_brief(state, resolved_id, caller_color, raw_key)

        if peer_raw and peer_model_id and raw_key:
            white_key = raw_key if auth.model_id == body.white_model_id else peer_raw
            black_key = peer_raw if auth.model_id == body.white_model_id else raw_key
            payload["white"] = {
                "model_id": state.get("white_model_id") or body.white_model_id,
                "agent_brief": _side_brief(state, resolved_id, "WHITE", white_key),
            }
            payload["black"] = {
                "model_id": state.get("black_model_id") or body.black_model_id,
                "agent_brief": _side_brief(state, resolved_id, "BLACK", black_key),
            }
        return payload
