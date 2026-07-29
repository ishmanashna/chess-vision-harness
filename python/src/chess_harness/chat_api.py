"""HTTP route helpers for human-vs-agent chat."""

from __future__ import annotations

from typing import Any, Callable, Dict

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .api_limits import AuthContext
from .chat import MAX_CHAT_TEXT, append_chat_message, read_chat_messages
from .game_service import GameService
from .game_types import is_human_vs_agent_state

__all__ = [
    "ChatPostBody",
    "register_agent_chat_routes",
    "register_play_chat_routes",
]


class ChatPostBody(BaseModel):
    text: str = Field(..., max_length=MAX_CHAT_TEXT)


def register_play_chat_routes(
    router: APIRouter,
    svc_fn: Callable[[], GameService],
    require_human_game,
    err,
) -> None:
    @router.post("/{game_id}/chat")
    async def play_chat_post(
        game_id: str,
        body: ChatPostBody,
        _state: Dict[str, Any] = Depends(require_human_game),
    ):
        result = append_chat_message(
            svc_fn().game_manager, game_id, from_kind="human", text=body.text
        )
        if not result.get("ok"):
            message = result.get("error", "Chat failed")
            status = 404 if "not found" in message.lower() else 400
            return err(status, message)
        return result

    @router.get("/{game_id}/chat")
    async def play_chat_get(
        game_id: str,
        since: int = Query(0, ge=0),
        _state: Dict[str, Any] = Depends(require_human_game),
    ):
        result = read_chat_messages(svc_fn().game_manager, game_id, since=since)
        if not result.get("ok"):
            return err(404, result.get("error", "Game not found"))
        return result


def register_agent_chat_routes(
    router: APIRouter,
    svc_fn: Callable[[], GameService],
    *,
    auth_context,
    require_game_participant: Callable[..., JSONResponse | tuple[AuthContext, str]],
    err,
) -> None:
    def _require_avh(game_id: str) -> JSONResponse | None:
        state = svc_fn().game_manager.load_state(game_id)
        if not state or not is_human_vs_agent_state(state):
            return err(400, "Chat is only available for agent vs human games")
        return None

    @router.post("/games/{game_id}/chat")
    async def agent_chat_post(
        game_id: str,
        body: ChatPostBody,
        auth: AuthContext = Depends(auth_context),
    ):
        access = require_game_participant(game_id, auth)
        if isinstance(access, JSONResponse):
            return access
        denied = _require_avh(game_id)
        if denied:
            return denied
        result = append_chat_message(
            svc_fn().game_manager, game_id, from_kind="agent", text=body.text
        )
        if not result.get("ok"):
            message = result.get("error", "Chat failed")
            status = 404 if "not found" in message.lower() else 400
            return err(status, message)
        return result

    @router.get("/games/{game_id}/chat")
    async def agent_chat_get(
        game_id: str,
        since: int = Query(0, ge=0),
        auth: AuthContext = Depends(auth_context),
    ):
        access = require_game_participant(game_id, auth)
        if isinstance(access, JSONResponse):
            return access
        denied = _require_avh(game_id)
        if denied:
            return denied
        result = read_chat_messages(svc_fn().game_manager, game_id, since=since)
        if not result.get("ok"):
            return err(404, result.get("error", "Game not found"))
        return result
