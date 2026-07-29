"""Human play HTTP API (/api/play) — play-token auth, FEN for interactive board."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.responses import JSONResponse

from .game_service import GameService
from .game_types import is_human_vs_agent_state
from .human_vs_agent import verify_play_token

__all__ = ["build_play_router", "PlayAuthError", "_err"]


class PlayAuthError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message


def _err(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"ok": False, "error": message})


def _extract_play_token(
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None),
    x_play_token: Optional[str] = Header(None, alias="X-Play-Token"),
) -> str:
    """Resolve play token: Bearer, then X-Play-Token, then ?token= (Phase 3/4 docs)."""
    if authorization and authorization.lower().startswith("bearer "):
        raw = authorization[7:].strip()
        if raw:
            return raw
    if x_play_token and x_play_token.strip():
        return x_play_token.strip()
    if token and token.strip():
        return token.strip()
    raise PlayAuthError(401, "Missing or invalid play token")


def build_play_router(get_game_service: Callable[[], GameService]) -> APIRouter:
    router = APIRouter(prefix="/api/play", tags=["play"])

    def _svc() -> GameService:
        return get_game_service()

    def _require_human_game(game_id: str, play_token: str = Depends(_extract_play_token)) -> Dict[str, Any]:
        state = _svc().game_manager.load_state(game_id)
        if not state or not is_human_vs_agent_state(state):
            raise PlayAuthError(404, f"Game {game_id} not found")
        if not verify_play_token(play_token, state):
            raise PlayAuthError(401, "Invalid play token")
        return state

    @router.get("/{game_id}/position")
    async def play_position(game_id: str, _state: Dict[str, Any] = Depends(_require_human_game)):
        result = _svc().human_position(game_id)
        if not result.get("ok"):
            return _err(404, result.get("error", "Game not found"))
        return result

    @router.get("/{game_id}/status")
    async def play_status(game_id: str, _state: Dict[str, Any] = Depends(_require_human_game)):
        result = _svc().human_position(game_id)
        if not result.get("ok"):
            return _err(404, result.get("error", "Game not found"))
        return result

    @router.post("/{game_id}/move/{move}")
    async def play_move(
        game_id: str,
        move: str,
        _state: Dict[str, Any] = Depends(_require_human_game),
    ):
        move = (move or "").strip()
        if len(move) < 2:
            return _err(400, "Move required")
        result = _svc().make_human_move(game_id, move)
        if not result.get("ok"):
            message = result.get("error", "Move failed")
            status = 404 if "not found" in message.lower() else 400
            return _err(status, message)
        return result

    @router.post("/{game_id}/resign")
    async def play_resign(game_id: str, _state: Dict[str, Any] = Depends(_require_human_game)):
        result = _svc().human_resign(game_id)
        if not result.get("ok"):
            message = result.get("error", "Resign failed")
            status = 404 if "not found" in message.lower() else 400
            return _err(status, message)
        return result

    return router
