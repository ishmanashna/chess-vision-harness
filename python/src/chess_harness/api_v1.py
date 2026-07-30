"""Public agent HTTP API (/api/v1)."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from .activity_audit import record_activity
from .agent_brief import public_base_url, render_agent_brief
from .api_keys import ApiKeyStore
from .api_limits import ApiLimitEnforcer, AuthContext, client_ip, get_limit_enforcer, key_fingerprint
from .avaa_api import register_avaa_routes, require_game_participant
from .api_v1_avh import register_avh_agent_routes
from .chat_api import register_agent_chat_routes
from .human_vs_agent_api import register_human_vs_agent_routes
from .commands import resolve_agent_color
from .elo import ELOLadder
from .game_ids import new_game_id
from .game_service import GameService
from .models import ModelRegistry
from .paths import resolve_base_dir

__all__ = ["build_router", "_AuthError", "_err"]

_LEAK_KEYS = frozenset({"fen", "board_fen", "moves", "start_fen", "png_bytes"})


class RegisterAgentBody(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    name: Optional[str] = None


class CreateGameBody(BaseModel):
    opponent: Optional[str] = None
    agent_color: Optional[str] = None


class MoveBody(BaseModel):
    move: str = Field(..., min_length=2)


class ImagineBody(BaseModel):
    moves: List[str] = Field(default_factory=list)


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

    def _require_game_participant(
        game_id: str, auth: AuthContext
    ) -> JSONResponse | tuple[AuthContext, str]:
        return require_game_participant(_svc(), game_id, auth, _err)

    register_avaa_routes(
        router,
        svc_fn=_svc,
        limits=limits,
        err=_err,
        sanitize=_sanitize_agent_payload,
        new_game_id=new_game_id,
        auth_context=_auth_context,
        key_store_fn=_keys,
    )
    register_human_vs_agent_routes(
        router,
        svc_fn=_svc,
        limits=limits,
        err=_err,
        sanitize=_sanitize_agent_payload,
        new_game_id=new_game_id,
        auth_context=_auth_context,
    )

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
        try:
            record_activity(
                "inscribe",
                model_id=body.id,
                client_ip=client_ip(request),
                user_agent=request.headers.get("user-agent", ""),
            )
        except Exception:
            pass
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
    async def create_game(
        body: CreateGameBody,
        request: Request,
        auth: AuthContext = Depends(_auth_context),
        authorization: Optional[str] = Header(None),
    ):
        denied = limits.check_create_game(_svc(), auth)
        if denied:
            return denied
        try:
            color = resolve_agent_color(body.agent_color)
        except ValueError as exc:
            return _err(400, str(exc))
        game_id = new_game_id()
        result = _svc().new_game(
            game_id,
            color,
            model_name=auth.model_id,
            opponent_id=body.opponent,
        )
        if not result.get("ok"):
            return _err(400, result.get("error", "Failed to create game"))
        limits.record_create_game(auth)
        try:
            record_activity(
                "create_game",
                model_id=auth.model_id,
                game_id=str(result.get("game_id") or game_id),
                client_ip=client_ip(request),
                user_agent=request.headers.get("user-agent", ""),
            )
        except Exception:
            pass
        payload: Dict[str, Any] = {"ok": True, **_sanitize_agent_payload(result)}
        raw_key = ""
        if authorization and authorization.lower().startswith("bearer "):
            raw_key = authorization[7:].strip()
        if raw_key:
            payload["agent_brief"] = render_agent_brief(
                public_base_url(), str(result.get("game_id") or game_id), raw_key
            )
        return payload

    @router.get("/games/{game_id}/status")
    async def game_status(game_id: str, auth: AuthContext = Depends(_auth_context)):
        access = _require_game_participant(game_id, auth)
        if isinstance(access, JSONResponse):
            return access
        _, caller_color = access
        result = _svc().status(game_id, caller_color=caller_color)
        if not result.get("ok"):
            return _err(404, result.get("error", "Game not found"))
        return _sanitize_agent_payload(result)

    @router.get("/games/{game_id}/board")
    async def game_board(game_id: str, auth: AuthContext = Depends(_auth_context)):
        access = _require_game_participant(game_id, auth)
        if isinstance(access, JSONResponse):
            return access
        _, caller_color = access
        try:
            png = _svc().get_board_bytes(game_id, caller_color=caller_color)
        except ValueError as exc:
            return _err(404, str(exc))
        return Response(content=png, media_type="image/png")

    @router.post("/games/{game_id}/imagine")
    async def game_imagine(
        game_id: str,
        body: ImagineBody,
        auth: AuthContext = Depends(_auth_context),
    ):
        access = _require_game_participant(game_id, auth)
        if isinstance(access, JSONResponse):
            return access
        denied = limits.check_imagine(auth)
        if denied:
            return denied
        result = _svc().imagine_board(game_id, list(body.moves))
        if not result.get("ok"):
            content: Dict[str, Any] = {
                "ok": False,
                "error": result.get("error", "Imagine failed"),
            }
            if "index" in result:
                content["index"] = result["index"]
            return JSONResponse(status_code=400, content=content)
        limits.record_imagine(auth)
        return Response(
            content=result["png_bytes"],
            media_type="image/png",
            headers={
                "X-Imagine": "1",
                "X-Imagine-Plies": str(result.get("applied_count", 0)),
            },
        )

    @router.post("/games/{game_id}/move/{move}")
    async def game_move_path(
        game_id: str, move: str, auth: AuthContext = Depends(_auth_context)
    ):
        """Preferred agent move: no JSON body (OS/shell-safe)."""
        return await _do_move(game_id, move, auth)

    @router.post("/games/{game_id}/move")
    async def game_move_body(
        game_id: str, body: MoveBody, auth: AuthContext = Depends(_auth_context)
    ):
        """Legacy JSON body move — prefer /move/{{uci_or_san}}."""
        return await _do_move(game_id, body.move, auth)

    async def _do_move(game_id: str, move: str, auth: AuthContext):
        access = _require_game_participant(game_id, auth)
        if isinstance(access, JSONResponse):
            return access
        _, caller_color = access
        denied = limits.check_move(_svc(), auth)
        if denied:
            return denied
        move = (move or "").strip()
        if len(move) < 2:
            return _err(400, "Move required")
        result = _svc().make_move(game_id, move, caller_color=caller_color)
        if not result.get("ok"):
            return _err(400, result.get("error", "Move failed"))
        limits.record_move(auth)
        return _sanitize_agent_payload(result)

    @router.post("/games/{game_id}/resign")
    async def game_resign(game_id: str, auth: AuthContext = Depends(_auth_context)):
        access = _require_game_participant(game_id, auth)
        if isinstance(access, JSONResponse):
            return access
        _, caller_color = access
        result = _svc().resign(game_id, caller_color=caller_color)
        if not result.get("ok"):
            return _err(400, result.get("error", "Resign failed"))
        return _sanitize_agent_payload(result)

    register_avh_agent_routes(
        router,
        _svc,
        auth_context=_auth_context,
        require_game_participant=_require_game_participant,
        sanitize=_sanitize_agent_payload,
        err=_err,
    )

    @router.get("/games/{game_id}/pgn")
    async def game_pgn(game_id: str, auth: AuthContext = Depends(_auth_context)):
        access = _require_game_participant(game_id, auth)
        if isinstance(access, JSONResponse):
            return access
        result = _svc().export_pgn(game_id)
        if not result.get("ok"):
            message = result.get("error", "PGN unavailable")
            status = 404 if "not found" in message.lower() else 400
            return _err(status, message)
        return {"ok": True, "pgn": result["pgn"]}

    register_agent_chat_routes(
        router,
        _svc,
        auth_context=_auth_context,
        require_game_participant=_require_game_participant,
        err=_err,
    )

    return router


class _AuthError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        self.message = message
