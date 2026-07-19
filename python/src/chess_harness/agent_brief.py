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
    status_url = f"{base}/api/v1/games/{game_id}/status"
    board_url = f"{base}/api/v1/games/{game_id}/board"
    move_url = f"{base}/api/v1/games/{game_id}/move"
    pgn_url = f"{base}/api/v1/games/{game_id}/pgn"
    resign_url = f"{base}/api/v1/games/{game_id}/resign"

    return f"""You are playing chess in the Chess Vision Harness over HTTP.
Vision-only benchmark — cheating invalidates the game.

Game ID: {game_id}
API base: {base}

Include this header on every /api/v1/games/{game_id}/* request:
  {auth}

## Play loop

Repeat until game_over or you resign:

1. GET {status_url}
   - Check your_turn, game_over, result (metadata only — not the board)

2. GET {board_url}
   - Response is image/png — open and read this image every turn.
   - The board PNG is the ONLY source of position information.

3. POST {move_url}
   - Content-Type: application/json
   - Body: {{"move": "e2e4"}}  (UCI or SAN)

After the game ends: GET {pgn_url}

Optional: POST {resign_url} to resign.

## Rules

- Board PNG is the ONLY source of position information.
- JSON status fields are metadata — not the board. Never use FEN or move lists.
- Do NOT read game files on disk or call legacy /api/games/* spectator endpoints.
- Do NOT use chess engines or scripts to pick moves or list legal moves.
- Idle timeout: 5 minutes without a move → game ends with no result (not a draw or loss).

## Example curl

# Status
curl -s -H "{auth}" \\
  {status_url}

# Board PNG (save and read the image every turn)
curl -s -H "{auth}" \\
  {board_url} -o board.png

# Move
curl -s -X POST -H "{auth}" \\
  -H "Content-Type: application/json" \\
  -d '{{"move":"e2e4"}}' \\
  {move_url}
"""
