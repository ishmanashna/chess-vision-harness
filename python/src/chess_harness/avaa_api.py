"""AvaA-specific HTTP API helpers and routes."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .activity_audit import record_activity
from .agent_brief import public_base_url, render_agent_brief_avaa
from .api_keys import ApiKeyStore
from .api_limits import ApiLimitEnforcer, AuthContext, client_ip, key_fingerprint
from .avaa import is_avaa_state, participant_color
from .game_service import GameService
from .game_types import GAME_TYPE_AGENT_VS_AGENT, is_human_vs_agent_state
from .scope_auth import reject_scoped_auth


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
        color = participant_color(state, auth.model_id, auth.key_fingerprint)
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

        denied = reject_scoped_auth(auth, err)
        if denied:
            return denied

        white_id = body.white_model_id.strip()
        black_id = body.black_model_id.strip()
        same_model = white_id == black_id

        registry = ModelRegistry()
        for model_id in (white_id, black_id):
            if not registry.is_inscribed(model_id):
                return err(400, f"Model '{model_id}' is not inscribed")
        if auth.model_id not in (white_id, black_id):
            return err(401, "API key must belong to white_model_id or black_model_id")

        raw_key = ""
        if authorization and authorization.lower().startswith("bearer "):
            raw_key = authorization[7:].strip()

        peer_model_id: Optional[str] = None
        peer_raw = (body.peer_api_key or "").strip()
        white_raw_key: Optional[str] = None
        black_raw_key: Optional[str] = None
        if peer_raw:
            if not raw_key:
                return err(401, "Missing or invalid Authorization header")
            if peer_raw == raw_key:
                return err(400, "peer_api_key must differ from Authorization key")
            peer_model_id = keys_fn().verify(peer_raw)
            if not peer_model_id:
                return err(401, "Invalid peer_api_key")
            if same_model:
                if peer_model_id != white_id:
                    return err(401, "peer_api_key must belong to the model in this game")
                # Direct same-model: Authorization is white, peer is black.
                white_raw_key = raw_key
                black_raw_key = peer_raw
            else:
                expected_peer = black_id if auth.model_id == white_id else white_id
                if peer_model_id != expected_peer:
                    return err(401, "peer_api_key must belong to the other model in this game")
                white_raw_key = raw_key if auth.model_id == white_id else peer_raw
                black_raw_key = peer_raw if auth.model_id == white_id else raw_key
        elif same_model:
            return err(
                400,
                "peer_api_key required when white_model_id equals black_model_id",
            )

        denied = limits.check_create_game(svc_fn(), auth)
        if denied:
            return denied

        game_id = new_game_id()
        create_kwargs: Dict[str, Any] = {}
        if white_raw_key and black_raw_key:
            create_kwargs["white_key_fp"] = key_fingerprint(white_raw_key)
            create_kwargs["black_key_fp"] = key_fingerprint(black_raw_key)
        result = svc_fn().new_agent_vs_agent_game(
            game_id,
            white_id,
            black_id,
            **create_kwargs,
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
                white_model_id=white_id,
                black_model_id=black_id,
                client_ip=client_ip(request),
                user_agent=request.headers.get("user-agent", ""),
            )
        except Exception:
            pass

        resolved_id = str(result.get("game_id") or game_id)
        state = svc_fn().game_manager.load_state(resolved_id) or {}
        caller_color = participant_color(state, auth.model_id, auth.key_fingerprint)
        payload: Dict[str, Any] = {"ok": True, **sanitize(result)}
        if caller_color:
            payload["agent_color"] = caller_color
            payload["your_turn"] = caller_color == "WHITE"
        if raw_key and caller_color:
            payload["agent_brief"] = _side_brief(state, resolved_id, caller_color, raw_key)

        if white_raw_key and black_raw_key:
            payload["white"] = {
                "model_id": state.get("white_model_id") or white_id,
                "agent_brief": _side_brief(state, resolved_id, "WHITE", white_raw_key),
            }
            payload["black"] = {
                "model_id": state.get("black_model_id") or black_id,
                "agent_brief": _side_brief(state, resolved_id, "BLACK", black_raw_key),
            }
        return payload
