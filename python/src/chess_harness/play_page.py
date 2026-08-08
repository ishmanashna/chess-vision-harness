"""Interactive play page for human-vs-agent games."""

from __future__ import annotations

import html
from typing import TYPE_CHECKING, Callable

from fastapi import HTTPException
from fastapi.responses import HTMLResponse

from .game_types import is_human_vs_agent_state
from .ladder_display import PUBLIC_SITE_HEADER, FAVICON_LINKS, THEME_INIT_SCRIPT

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
  <meta name="referrer" content="no-referrer"/>
  <title>Play — {gid}</title>
  {FAVICON_LINKS}
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
        <p class="play-header-line" data-play-header-line aria-live="polite">Loading…</p>
      </header>
      <p class="play-error" data-play-error role="alert"></p>
      <div class="play-layout">
        <aside class="play-chat-col" aria-label="Chat">
          <div class="play-chat-panel" data-play-chat>
            <div class="play-chat-log" data-chat-log role="log" aria-live="polite"></div>
            <form class="play-chat-form" data-chat-form>
              <textarea
                class="play-chat-input"
                data-chat-input
                rows="1"
                maxlength="500"
                placeholder="Message…"
                aria-label="Chat message"
                spellcheck="false"
                autocomplete="off"
              ></textarea>
              <button type="submit" class="btn btn-secondary play-chat-send" data-chat-send>Send</button>
            </form>
          </div>
        </aside>
        <div class="play-center-col">
          <div class="play-board-wrap" data-board-wrap>
            <div id="play-board" class="play-board"></div>
          </div>
          <button type="button" class="btn btn-secondary play-clear-premove" data-clear-premove hidden>Cancel premoves</button>
          <div class="play-actions">
            <button type="button" class="btn btn-secondary" data-resign>Resign</button>
            <button type="button" class="btn btn-secondary" data-draw-offer>Offer draw</button>
            <button type="button" class="btn btn-secondary" data-draw-accept hidden>Accept draw</button>
            <button type="button" class="btn btn-secondary" data-draw-decline hidden>Decline draw</button>
          </div>
        </div>
        <aside class="play-moves-col" aria-label="Move list">
          <div class="play-panel play-moves-panel">
            <h2 class="play-panel-title">Moves</h2>
            <div class="play-moves-scroll" data-play-moves>
              <p class="play-placeholder">No moves yet.</p>
            </div>
          </div>
        </aside>
      </div>
      <p class="play-links">
        <a href="{spectate}">Spectate this game</a>
        · <a href="/launch/?flow=playground">Create another Playground game</a>
        <span class="play-download-slot" data-download-slot hidden>
          · <button type="button" class="export-link" data-download-board>Download position</button>
        </span>
      </p>
    </main>
    <footer class="site-footer">
      <p>Chess Vision Harness · <a href="https://github.com/ishmanashna/chess-vision-harness">Source on GitHub</a></p>
    </footer>
  </div>
  <script src="/js/common.js"></script>
  <script src="/js/human-games-registry.js"></script>
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
        return HTMLResponse(render_play_page(game_id), headers={"Referrer-Policy": "no-referrer"})
