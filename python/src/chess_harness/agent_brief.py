"""Paste-ready agent prompt for remote HTTP play."""

from __future__ import annotations

import os

__all__ = ["public_base_url", "render_agent_brief"]


def public_base_url() -> str:
    """Public harness URL for agent briefs (deploy override via env)."""
    return os.environ.get("CHESS_HARNESS_PUBLIC_URL", "http://127.0.0.1:8765").rstrip("/")


def render_agent_brief(base_url: str, game_id: str, api_key: str) -> str:
    """Self-contained agent prompt: auth, play loop, vision rules."""
    base = base_url.rstrip("/")
    auth = f"Authorization: Bearer {api_key}"
    board_url = f"{base}/api/v1/games/{game_id}/board"
    move_base = f"{base}/api/v1/games/{game_id}/move"
    pgn_url = f"{base}/api/v1/games/{game_id}/pgn"
    resign_url = f"{base}/api/v1/games/{game_id}/resign"
    status_url = f"{base}/api/v1/games/{game_id}/status"

    return f"""You are playing chess in the Chess Vision Harness over HTTP.
Vision-only benchmark — cheating invalidates the game.

Game ID: {game_id}
API base: {base}

Auth header (every request):
  {auth}

## Play loop

Repeat until the move response shows the game is finished, or you resign:

1. GET {board_url}
   - Response is image/png — open and read this image every turn.
   - The board PNG is the ONLY source of position information.

2. POST {move_base}/{{move}}
   - Put the move in the URL path (UCI or SAN). Example: .../move/e2e4
   - No request body. No JSON.
   - The JSON reply says whether the game is over and whether it is still your turn.
   - If not your turn yet (rare), wait briefly and GET the board again.

After the game ends: GET {pgn_url}

Optional resign: POST {resign_url} (no body)

Optional status (not required each turn): GET {status_url}
  — metadata only (your_turn, result). Not the board.

## Rules

- Board PNG is the ONLY source of position information.
- Never use FEN or move lists from JSON.
- Do NOT read game files on disk or call legacy /api/games/* spectator endpoints.
- Do NOT use chess engines or scripts to pick moves or list legal moves.

## Examples

# Board PNG
GET {board_url}
Header: {auth}
Save the response as an image and read it.

# Move (e2e4) — move is in the path, empty body
POST {move_base}/e2e4
Header: {auth}

# Same with curl.exe (Windows-safe; no JSON)
curl.exe -s -H "{auth}" "{board_url}" -o board.png
curl.exe -s -X POST -H "{auth}" "{move_base}/e2e4"
"""
