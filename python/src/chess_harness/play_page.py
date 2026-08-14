"""Interactive play page for human-vs-agent games."""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from .public_site_shell import watch_shell_response

if TYPE_CHECKING:
    from .game_manager import GameManager

__all__ = ["register_play_routes"]


def register_play_routes(
    app: FastAPI, get_game_manager: Callable[[], "GameManager"]
) -> None:
    @app.get("/play/{game_id}", response_class=HTMLResponse)
    async def play_page(game_id: str):
        """Static shell from public-site/play/; play state via /api/play/*."""
        return watch_shell_response("play")
