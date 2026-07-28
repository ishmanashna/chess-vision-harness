"""Mount /api/v1 routers and shared auth errors."""

from __future__ import annotations

from typing import Callable

from fastapi.responses import JSONResponse

from .api_limits import get_limit_enforcer
from .api_v1 import _AuthError, _err, build_router
from .game_service import GameService

__all__ = ["mount_api_v1"]


def mount_api_v1(app, get_game_service: Callable[[], GameService]) -> None:
    from .lobbies_api import LobbyAuthError, build_lobby_router

    limits = get_limit_enforcer()
    router = build_router(get_game_service, limit_enforcer=limits)
    lobby_router = build_lobby_router(get_game_service, limit_enforcer=limits)
    app.include_router(router)
    app.include_router(lobby_router)

    @app.exception_handler(_AuthError)
    async def _handle_auth_error(_request, exc: _AuthError):
        return _err(exc.status, exc.message)

    @app.exception_handler(LobbyAuthError)
    async def _handle_lobby_auth_error(_request, exc: LobbyAuthError):
        return _err(exc.status, exc.message)
