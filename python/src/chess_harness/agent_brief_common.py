"""Shared sections for paste-ready agent briefs."""

from __future__ import annotations

import os

IDLE_TIMEOUT_RULE = (
    "- Idle timeout: 30 minutes without a move ends the game with no result "
    "(not a loss or draw)."
)

_ANOTHER_GAME_INTRO = """\
## Another game

Only when the operator explicitly asks you to play again — never start a new game on your own after fetching PGN.

Prefer finishing the current game first (or resign). A second live game is allowed only if server and API-key limits permit. Use the same auth header as above."""


def public_base_url() -> str:
    """Public harness URL for agent briefs (deploy override via env)."""
    return os.environ.get("CHESS_HARNESS_PUBLIC_URL", "http://127.0.0.1:8765").rstrip("/")


def another_game_ave(base: str, auth: str) -> str:
    create_url = f"{base}/api/v1/games"
    return f"""{_ANOTHER_GAME_INTRO}

1. POST {create_url}
   Header: {auth}
   Optional JSON body: {{"opponent": "<engine_id>", "agent_color": "white"|"black"}}
2. Read game_id from the JSON response. Replace {base}/api/v1/games/{{old_id}}/… with the new id in every play-loop URL (board, board.txt, move, status, pgn, resign).
3. Run the same play loop above with the new game_id.

# Create another AvE game (curl.exe)
curl.exe -s -X POST -H "{auth}" -H "Content-Type: application/json" -d "{{}}" "{create_url}"
"""


def another_game_avaa(base: str, auth: str) -> str:
    lobbies_url = f"{base}/api/v1/lobbies"
    return f"""{_ANOTHER_GAME_INTRO}

Find match (one agent cannot Direct-pair with itself; Direct still needs Create Game with two separate agents):

1. POST {lobbies_url}
   Header: {auth}
   Empty body or {{}}
2. If status is waiting, poll GET {base}/api/v1/lobbies/{{lobby_id}} (from lobby_id or poll_url) with the same auth header until status is matched.
3. Read game_id from the matched response. Replace {base}/api/v1/games/{{old_id}}/… with the new id in every play-loop URL.
4. Run the same agent-vs-agent play loop above with the new game_id.

# Find another AvA match (curl.exe)
curl.exe -s -X POST -H "{auth}" "{lobbies_url}"
curl.exe -s -H "{auth}" "{base}/api/v1/lobbies/{{lobby_id}}"
"""


def another_game_avh(base: str, auth: str) -> str:
    create_url = f"{base}/api/v1/games/human"
    return f"""{_ANOTHER_GAME_INTRO}

1. POST {create_url}
   Header: {auth}
   Optional JSON body: {{"nickname": "<human nickname>"}}
2. Read game_id and play_url from the JSON response. Tell the operator the play_url so they can open the human board.
3. Replace {base}/api/v1/games/{{old_id}}/… with the new game_id in every play-loop URL (board, board.txt, move, status, chat, draw, pgn, resign).
4. Run the same agent-vs-human play loop above with the new game_id.

# Create another AvH game (curl.exe)
curl.exe -s -X POST -H "{auth}" -H "Content-Type: application/json" -d "{{}}" "{create_url}"
"""
