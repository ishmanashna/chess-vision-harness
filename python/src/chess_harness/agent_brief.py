"""Paste-ready agent prompt for remote HTTP play."""

from __future__ import annotations

import os

__all__ = ["public_base_url", "render_agent_brief", "render_agent_brief_avaa"]


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


def render_agent_brief_avaa(
    base_url: str,
    game_id: str,
    api_key: str,
    color: str,
    opponent_name: str,
) -> str:
    """Self-contained agent prompt for agent-vs-agent lobby play."""
    base = base_url.rstrip("/")
    auth = f"Authorization: Bearer {api_key}"
    board_url = f"{base}/api/v1/games/{game_id}/board"
    move_base = f"{base}/api/v1/games/{game_id}/move"
    pgn_url = f"{base}/api/v1/games/{game_id}/pgn"
    resign_url = f"{base}/api/v1/games/{game_id}/resign"
    status_url = f"{base}/api/v1/games/{game_id}/status"

    return f"""You are playing chess in the Chess Vision Harness over HTTP (agent vs agent).
Vision-only benchmark — cheating invalidates the game.

Game ID: {game_id}
You play: {color}
Opponent: {opponent_name}
API base: {base}

Auth header (every request):
  {auth}

## Play loop

Repeat until the game is finished or you resign:

1. GET {status_url}
   - If game_over is true → GET {pgn_url} and stop.
   - If your_turn is false → wait (sleep with backoff, e.g. 2s then 5s) and poll status again.
     Do NOT call GET {board_url} while waiting — it returns 403 off-turn.

2. When your_turn is true: GET {board_url}
   - Response is image/png — open and read this image every turn.
   - The board PNG is the ONLY source of position information.

3. POST {move_base}/{{move}}
   - Put the move in the URL path (UCI or SAN). Example: .../move/e2e4
   - No request body. No JSON.
   - After your move, your_turn becomes false until the opponent moves — go back to step 1.

After the game ends: GET {pgn_url}

Optional resign: POST {resign_url} (no body)

## Rules

- Board PNG is the ONLY source of position information.
- Never use FEN or move lists from JSON.
- Poll status when it is not your turn; never fetch the board off-turn.
- Do NOT read game files on disk or call legacy /api/games/* spectator endpoints.
- Do NOT use chess engines or scripts to pick moves or list legal moves.

## Examples

# Poll status (do this first every iteration)
GET {status_url}
Header: {auth}

# Board PNG (only when your_turn is true)
GET {board_url}
Header: {auth}
Save the response as an image and read it.

# Move (e2e4) — move is in the path, empty body
POST {move_base}/e2e4
Header: {auth}

# Same with curl.exe (Windows-safe; no JSON)
curl.exe -s -H "{auth}" "{status_url}"
curl.exe -s -H "{auth}" "{board_url}" -o board.png
curl.exe -s -X POST -H "{auth}" "{move_base}/e2e4"
"""
