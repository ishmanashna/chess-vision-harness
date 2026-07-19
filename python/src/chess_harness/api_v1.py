"""Public agent HTTP API (/api/v1)."""

from __future__ import annotations

import os
import random
from typing import Any, Callable, Dict, Optional

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from .api_keys import ApiKeyStore
from .api_limits import ApiLimitEnforcer, AuthContext, get_limit_enforcer, key_fingerprint
from .commands import resolve_agent_color
from .elo import ELOLadder
from .game_service import GameService
from .models import ModelRegistry
from .paths import resolve_base_dir

__all__ = ["mount_api_v1"]

_LEAK_KEYS = frozenset({"fen", "board_fen", "moves", "start_fen"})


class RegisterAgentBody(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    name: Optional[str] = None


class CreateGameBody(BaseModel):
    opponent: Optional[str] = None
    agent_color: Optional[str] = None


class MoveBody(BaseModel):
    move: str = Field(..., min_length=2)


def _err(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"ok": False, "error": message})


def _sanitize_agent_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key, value in data.items():
        if key in _LEAK_KEYS:
            continue
        if key == "board_path":
            game_id = data.get("game_id")
            if game_id:
                out["board_url"] = f"/api/v1/games/{game_id}/board"
            continue
        out[key] = value
    return out


def _new_game_id() -> str:
    return f"game-{os.getpid()}-{random.randint(1000, 9999)}"


def _game_model_id(game_service: GameService, game_id: str) -> Optional[str]:
    state = game_service.game_manager.load_state(game_id)
    if not state:
        return None
    return state.get("model_name")


def build_router(
    get_game_service: Callable[[], GameService],
    get_key_store: Optional[Callable[[], ApiKeyStore]] = None,
    limit_enforcer: Optional[ApiLimitEnforcer] = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1", tags=["api-v1"])
    key_store_fn = get_key_store or ApiKeyStore
    limits = limit_enforcer or get_limit_enforcer()

    def _keys() -> ApiKeyStore:
        return key_store_fn()

    def _svc() -> GameService:
        return get_game_service()

    def _auth_context(authorization: Optional[str] = Header(None)) -> AuthContext:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise _AuthError(401, "Missing or invalid Authorization header")
        raw = authorization[7:].strip()
        model_id = _keys().verify(raw)
        if not model_id:
            raise _AuthError(401, "Invalid API key")
        return AuthContext(model_id=model_id, key_fingerprint=key_fingerprint(raw))

    def _require_game_access(game_id: str, auth: AuthContext) -> JSONResponse | None:
        game_model = _game_model_id(_svc(), game_id)
        if game_model is None:
            return _err(404, f"Game {game_id} not found")
        if game_model != auth.model_id:
            return _err(401, "API key does not match this game")
        return None

    @router.get("/metrics")
    async def metrics():
        return {"ok": True, **limits.metrics(_svc())}

    @router.post("/agents")
    async def register_agent(body: RegisterAgentBody, request: Request):
        denied = limits.check_register_agent(request)
        if denied:
            return denied
        registry = ModelRegistry()
        if not registry.validate_id_format(body.id):
            return _err(400, f"Invalid model id '{body.id}'")
        if not registry.is_inscribed(body.id):
            try:
                registry.inscribe(body.id, body.name)
            except ValueError as exc:
                return _err(400, str(exc))
        model = registry.get(body.id)
        assert model is not None
        api_key = _keys().create(body.id)
        limits.record_register_agent(request)
        return {"ok": True, "model_id": body.id, "name": model.get("name", body.id), "api_key": api_key}

    @router.get("/agents")
    async def list_agents():
        registry = ModelRegistry()
        agents = [
            {
                "id": model["id"],
                "name": model.get("name", model["id"]),
                "elo": round(float(model.get("elo", 500))),
            }
            for model in registry.list_models()
        ]
        return {"ok": True, "agents": agents}

    @router.get("/leaderboard")
    async def leaderboard():
        ladder = ELOLadder(base_dir=str(resolve_base_dir()))
        return {"ok": True, "leaderboard": ladder.get_leaderboard()}

    @router.post("/games")
    async def create_game(body: CreateGameBody, auth: AuthContext = Depends(_auth_context)):
        denied = limits.check_create_game(_svc(), auth)
        if denied:
            return denied
        try:
            color = resolve_agent_color(body.agent_color)
        except ValueError as exc:
            return _err(400, str(exc))
        game_id = _new_game_id()
        result = _svc().new_game(
            game_id,
            color,
            model_name=auth.model_id,
            opponent_id=body.opponent,
        )
        if not result.get("ok"):
            return _err(400, result.get("error", "Failed to create game"))
        limits.record_create_game(auth)
        return {"ok": True, **_sanitize_agent_payload(result)}

    @router.get("/games/{game_id}/status")
    async def game_status(game_id: str, auth: AuthContext = Depends(_auth_context)):
        denied = _require_game_access(game_id, auth)
        if denied:
            return denied
        result = _svc().status(game_id)
        if not result.get("ok"):
            return _err(404, result.get("error", "Game not found"))
        return _sanitize_agent_payload(result)

    @router.get("/games/{game_id}/board")
    async def game_board(game_id: str, auth: AuthContext = Depends(_auth_context)):
        denied = _require_game_access(game_id, auth)
        if denied:
            return denied
        try:
            png = _svc().get_board_bytes(game_id)
        except ValueError as exc:
            return _err(404, str(exc))
        return Response(content=png, media_type="image/png")

    @router.post("/games/{game_id}/move")
    async def game_move(
        game_id: str, body: MoveBody, auth: AuthContext = Depends(_auth_context)
    ):
        denied = _require_game_access(game_id, auth)
        if denied:
            return denied
        denied = limits.check_move(_svc(), auth)
        if denied:
            return denied
        result = _svc().make_move(game_id, body.move)
        if not result.get("ok"):
            return _err(400, result.get("error", "Move failed"))
        limits.record_move(auth)
        return _sanitize_agent_payload(result)

    @router.post("/games/{game_id}/resign")
    async def game_resign(game_id: str, auth: AuthContext = Depends(_auth_context)):
        denied = _require_game_access(game_id, auth)
        if denied:
            return denied
        result = _svc().resign(game_id)
        if not result.get("ok"):
            return _err(400, result.get("error", "Resign failed"))
        return _sanitize_agent_payload(result)

    @router.get("/games/{game_id}/pgn")
    async def game_pgn(game_id: str, auth: AuthContext = Depends(_auth_context)):
        denied = _require_game_access(game_id, auth)
        if denied:
            return denied
        result = _svc().export_pgn(game_id)
        if not result.get("ok"):
            message = result.get("error", "PGN unavailable")
            status = 404 if "not found" in message.lower() else 400
            return _err(status, message)
        return {"ok": True, "pgn": result["pgn"]}

    return router


class _AuthError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message


def mount_api_v1(app, get_game_service: Callable[[], GameService]) -> None:
    router = build_router(get_game_service)
    app.include_router(router)

    @app.exception_handler(_AuthError)
    async def _handle_auth_error(_request, exc: _AuthError):
        return _err(exc.status, exc.message)
