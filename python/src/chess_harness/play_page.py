"""Interactive play page for human-vs-agent games."""

from __future__ import annotations

import html
from typing import TYPE_CHECKING, Callable

from fastapi import HTTPException
from fastapi.responses import HTMLResponse

from .game_types import is_human_vs_agent_state
from .ladder_display import (
    PUBLIC_SITE_HEADER,
    THEME_INIT_SCRIPT,
    THEME_TOGGLE_SCRIPT,
)

if TYPE_CHECKING:
    from fastapi import FastAPI

    from .game_manager import GameManager

__all__ = ["register_play_routes"]

CM_CHESSBOARD_VERSION = "8.7.2"
CM_CDN = f"https://cdn.jsdelivr.net/npm/cm-chessboard@{CM_CHESSBOARD_VERSION}"


def _esc(value: str) -> str:
    return html.escape(value, quote=True)


def render_play_page(game_id: str) -> str:
    gid = _esc(game_id)
    spectate = f"/g/{gid}"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Play — {gid}</title>
  {THEME_INIT_SCRIPT}
  <link rel="stylesheet" href="/css/site.css"/>
  <link rel="stylesheet" href="/css/play.css"/>
  <link rel="stylesheet" href="{CM_CDN}/assets/chessboard.css"/>
  <link rel="stylesheet" href="{CM_CDN}/assets/extensions/markers/markers.css"/>
  <link rel="stylesheet" href="{CM_CDN}/assets/extensions/promotion-dialog/promotion-dialog.css"/>
</head>
<body>
  <div class="wrap">
    {PUBLIC_SITE_HEADER}
    <main class="play-main" data-play-root>
      <header class="play-header">
        <h2>Play board</h2>
        <p class="play-matchup" data-play-matchup>Loading…</p>
        <p class="play-status" data-play-status aria-live="polite">Loading…</p>
      </header>
      <p class="play-error" data-play-error role="alert"></p>
      <div class="play-board-wrap" data-board-wrap>
        <div id="play-board" class="play-board"></div>
      </div>
      <div class="play-actions">
        <button type="button" class="btn btn-secondary" data-resign>Resign</button>
      </div>
      <p class="play-links">
        <a href="{spectate}">Spectate this game</a>
        · <a href="/create/?mode=human">Create another game</a>
      </p>
      <p class="play-meta">Game ID: <code>{gid}</code> · Unranked · paste the agent brief so your agent can join.</p>
    </main>
    <footer class="site-footer">
      <p>Chess Vision Harness</p>
    </footer>
  </div>
  <script src="/js/common.js"></script>
  {THEME_TOGGLE_SCRIPT}
  <script type="module" src="/js/play-page.js"></script>
</body>
</html>"""


def register_play_routes(
    app: FastAPI, get_game_manager: Callable[[], "GameManager"]
) -> None:
    @app.get("/play/{game_id}", response_class=HTMLResponse)
    async def play_page(game_id: str):
        state = get_game_manager().load_state(game_id)
        if state is None or not is_human_vs_agent_state(state):
            raise HTTPException(status_code=404, detail="Game not found")
        return HTMLResponse(render_play_page(game_id))
