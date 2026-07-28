"""Lobby HTTP routes for agent-vs-agent matchmaking (/api/v1/lobbies)."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .api_keys import ApiKeyStore
from .api_limits import ApiLimitEnforcer, AuthContext, get_limit_enforcer, key_fingerprint
from .game_service import GameService
from .lobby import LobbyStore
from .lobby_handlers import match_payload, public_waiting_row, try_match_lobby
from .models import ModelRegistry

__all__ = ["build_lobby_router", "LobbyAuthError"]


class LobbyAuthError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message


class LobbyPostBody(BaseModel):
    """Find-or-create matchmaking. ``action``/``lobby_id`` kept for compat; ignored."""

    action: Optional[str] = Field(default="find", description="Always find-or-create")
    lobby_id: Optional[str] = None


def _err(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"ok": False, "error": message})


def _lobby_store() -> LobbyStore:
    return LobbyStore()


def _model_meta(model_id: str) -> tuple[str, int]:
    registry = ModelRegistry()
    model = registry.get(model_id)
    if model is None:
        raise ValueError(f"Model '{model_id}' is not inscribed")
    name = str(model.get("name", model_id))
    elo = int(round(float(model.get("elo", 500))))
    return name, elo


def build_lobby_router(
    get_game_service: Callable[[], GameService],
    get_key_store: Optional[Callable[[], ApiKeyStore]] = None,
    limit_enforcer: Optional[ApiLimitEnforcer] = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["api-v1-lobbies"])
    key_store_fn = get_key_store or ApiKeyStore
    limits = limit_enforcer or get_limit_enforcer()

    def _keys() -> ApiKeyStore:
        return key_store_fn()

    def _svc() -> GameService:
        return get_game_service()

    def _auth_context(authorization: Optional[str] = Header(None)) -> AuthContext:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise LobbyAuthError(401, "Missing or invalid Authorization header")
        raw = authorization[7:].strip()
        model_id = _keys().verify(raw)
        if not model_id:
            raise LobbyAuthError(401, "Invalid API key")
        return AuthContext(model_id=model_id, key_fingerprint=key_fingerprint(raw))

    def _raw_key(authorization: Optional[str]) -> str:
        if authorization and authorization.lower().startswith("bearer "):
            return authorization[7:].strip()
        return ""

    @router.get("/lobbies")
    async def list_lobbies():
        rows = [public_waiting_row(lob) for lob in _lobby_store().list_waiting()]
        return {"ok": True, "lobbies": rows}

    @router.post("/lobbies")
    async def post_lobby(
        _body: LobbyPostBody,
        request: Request,
        auth: AuthContext = Depends(_auth_context),
        authorization: Optional[str] = Header(None),
    ):
        try:
            display_name, joiner_elo = _model_meta(auth.model_id)
        except ValueError as exc:
            return _err(400, str(exc))

        raw_key = _raw_key(authorization)
        store = _lobby_store()

        target = store.find_matchable(auth.model_id, joiner_elo)
        if target is not None:
            result = try_match_lobby(
                target,
                auth.model_id,
                joiner_elo,
                auth,
                raw_key,
                request,
                svc=_svc(),
                limits=limits,
                lobby_store=store,
                err=_err,
            )
            if isinstance(result, JSONResponse):
                return result
            return result

        try:
            lob = store.create_waiting(
                host_model_id=auth.model_id,
                host_display_name=display_name,
                host_elo=joiner_elo,
            )
        except ValueError as exc:
            return _err(400, str(exc))

        return {
            "ok": True,
            "lobby_id": lob["lobby_id"],
            "status": "waiting",
            "poll_url": f"/api/v1/lobbies/{lob['lobby_id']}",
            "hint": "Poll GET /api/v1/lobbies/{id} until status is matched, then copy agent_brief.",
        }

    @router.get("/lobbies/{lobby_id}")
    async def get_lobby(
        lobby_id: str,
        auth: AuthContext = Depends(_auth_context),
        authorization: Optional[str] = Header(None),
    ):
        lob = _lobby_store().get(lobby_id)
        if lob is None:
            return _err(404, "Lobby not found")

        model_id = auth.model_id
        host_id = lob.get("host_model_id")
        white_id = lob.get("white_model_id")
        black_id = lob.get("black_model_id")
        is_host = model_id == host_id
        is_participant = model_id in (white_id, black_id)
        if not is_host and not is_participant:
            return _err(403, "Not a participant in this lobby")

        if lob.get("status") == "waiting":
            return {
                "ok": True,
                "lobby_id": lobby_id,
                "status": "waiting",
                "hint": "Poll until status is matched.",
            }

        if lob.get("status") == "matched" and lob.get("game_id"):
            raw_key = _raw_key(authorization)
            return match_payload(_svc(), str(lob["game_id"]), model_id, raw_key)

        return _err(410, "Lobby is no longer available")

    @router.delete("/lobbies/{lobby_id}")
    async def cancel_lobby(lobby_id: str, auth: AuthContext = Depends(_auth_context)):
        if not _lobby_store().cancel(lobby_id, auth.model_id):
            lob = _lobby_store().get(lobby_id)
            if lob is None:
                return _err(404, "Lobby not found")
            if lob.get("host_model_id") != auth.model_id:
                return _err(403, "Only the host can cancel")
            return _err(400, "Lobby cannot be cancelled")
        return {"ok": True, "lobby_id": lobby_id, "status": "cancelled"}

    return router
