"""Text-only (board.txt) paste-ready agent briefs."""

from __future__ import annotations

from .agent_board_text import render_board_text_access_only
from .agent_brief_common import (
    IDLE_TIMEOUT_RULE,
    another_game_ave,
    another_game_avaa,
    another_game_avh,
)


def render_agent_brief(base_url: str, game_id: str, api_key: str) -> str:
    base = base_url.rstrip("/")
    auth = f"Authorization: Bearer {api_key}"
    board_txt_url = f"{base}/api/v1/games/{game_id}/board.txt"
    move_base = f"{base}/api/v1/games/{game_id}/move"
    pgn_url = f"{base}/api/v1/games/{game_id}/pgn"
    resign_url = f"{base}/api/v1/games/{game_id}/resign"
    status_url = f"{base}/api/v1/games/{game_id}/status"

    return f"""You are playing chess in the Chess Vision Harness over HTTP.
Fair agent chess benchmark with text-board position input. Cheating invalidates the game.

Game ID: {game_id}
API base: {base}

Auth header (every request):
  {auth}

## Play loop

Repeat until the move response shows the game is finished, or you resign:

1. Read the live text board before every move:
{render_board_text_access_only(base, game_id, auth)}

2. POST {move_base}/{{move}}
   - Put the move in the URL path. Prefer UCI (e.g. e2e4, g1f3); SAN is accepted
     when unambiguous.
   - No request body. No JSON.
   - The JSON reply says whether the game is over and whether it is still your turn.

After the game ends: GET {pgn_url}

Optional resign: POST {resign_url} (no body)

Optional status (not required each turn): GET {status_url}
  — metadata only (your_turn, result). Not the board.

## Rules

- Read authenticated board.txt before every move; it is your position source. Do not fetch the board PNG.
- Board text is always white at bottom; square names are absolute (a1 is bottom-left).
- Never use FEN or move lists from JSON.
- Do NOT read game files on disk or call legacy /api/games/* spectator endpoints.
- Do NOT use chess engines or scripts to pick moves or list legal moves.
{IDLE_TIMEOUT_RULE}

## Examples

# Board text (required every turn)
GET {board_txt_url}
Header: {auth}

# Move (e2e4) — move is in the path, empty body
POST {move_base}/e2e4
Header: {auth}

# Same with curl.exe (Windows-safe; no JSON)
curl.exe -s -H "{auth}" "{board_txt_url}"
curl.exe -s -X POST -H "{auth}" "{move_base}/e2e4"

{another_game_ave(base, auth)}"""


def render_agent_brief_avaa(
    base_url: str,
    game_id: str,
    api_key: str,
    color: str,
    opponent_name: str,
) -> str:
    base = base_url.rstrip("/")
    auth = f"Authorization: Bearer {api_key}"
    board_txt_url = f"{base}/api/v1/games/{game_id}/board.txt"
    move_base = f"{base}/api/v1/games/{game_id}/move"
    pgn_url = f"{base}/api/v1/games/{game_id}/pgn"
    resign_url = f"{base}/api/v1/games/{game_id}/resign"
    status_url = f"{base}/api/v1/games/{game_id}/status"

    return f"""You are playing chess in the Chess Vision Harness over HTTP (agent vs agent).
Fair agent chess benchmark with text-board position input. Cheating invalidates the game.

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
     You may GET board.txt while waiting to look at the position; do not POST a move until your_turn is true.

2. When your_turn is true: read the live text board before you move:
{render_board_text_access_only(base, game_id, auth)}

3. POST {move_base}/{{move}}
   - Put the move in the URL path. Prefer UCI (e.g. e2e4, g1f3); SAN is accepted
     when unambiguous.
   - No request body. No JSON.
   - After your move, your_turn becomes false until the opponent moves — go back to step 1.

After the game ends: GET {pgn_url}

Optional resign: POST {resign_url} (no body)

## Rules

- Read authenticated board.txt before every move; it is your position source. Do not fetch the board PNG.
- Board text is always white at bottom; square names are absolute (a1 is bottom-left).
- Never use FEN or move lists from JSON.
- Poll status when it is not your turn; you may still fetch board.txt to look, but never move off-turn.
- Do NOT read game files on disk or call legacy /api/games/* spectator endpoints.
- Do NOT use chess engines or scripts to pick moves or list legal moves.
{IDLE_TIMEOUT_RULE}

## Examples

# Poll status (do this first every iteration)
GET {status_url}
Header: {auth}

# Board text (required before you move)
GET {board_txt_url}
Header: {auth}

# Move (e2e4) — move is in the path, empty body
POST {move_base}/e2e4
Header: {auth}

# Same with curl.exe (Windows-safe; no JSON)
curl.exe -s -H "{auth}" "{status_url}"
curl.exe -s -H "{auth}" "{board_txt_url}"
curl.exe -s -X POST -H "{auth}" "{move_base}/e2e4"

{another_game_avaa(base, auth)}"""


def render_agent_brief_human(
    base_url: str,
    game_id: str,
    api_key: str,
    color: str,
    human_nickname: str,
) -> str:
    base = base_url.rstrip("/")
    auth = f"Authorization: Bearer {api_key}"
    board_txt_url = f"{base}/api/v1/games/{game_id}/board.txt"
    move_base = f"{base}/api/v1/games/{game_id}/move"
    pgn_url = f"{base}/api/v1/games/{game_id}/pgn"
    resign_url = f"{base}/api/v1/games/{game_id}/resign"
    status_url = f"{base}/api/v1/games/{game_id}/status"
    draw_offer_url = f"{base}/api/v1/games/{game_id}/draw/offer"
    draw_accept_url = f"{base}/api/v1/games/{game_id}/draw/accept"
    draw_decline_url = f"{base}/api/v1/games/{game_id}/draw/decline"
    chat_url = f"{base}/api/v1/games/{game_id}/chat"

    return f"""You are playing chess in the Chess Vision Harness over HTTP (agent vs human).
Fair agent chess benchmark with text-board position input. Cheating invalidates the game. This game is unranked (no Elo change).

This is a long-running session. After this prompt is pasted once, keep executing the play loop yourself with your own HTTP tools until game_over is true. Do not wait for the operator to re-prompt you each move.

Game ID: {game_id}
You play: {color}
Human opponent: {human_nickname}
API base: {base}

Auth header (every request):
  {auth}

## Play loop

Track last_chat_seq (start at 0). Repeat until the game is finished or you resign:

1. GET {status_url}
   - If game_over is true → POST {chat_url} with one short message acknowledging the result
     (win, loss, or draw), then GET {pgn_url} and stop.
   - If chat_seq from status is greater than last_chat_seq → GET {chat_url}?since=last_chat_seq,
     read new messages, set last_chat_seq to the chat_seq in that response.
     Do this on every iteration before draw or move decisions.
   - Check draw flags from status (draw_offer_pending, can_respond_draw, can_offer_draw, you_offered_draw).
     If the human offered a draw (can_respond_draw) → POST {draw_accept_url} or POST {draw_decline_url}.
     To offer a draw: POST {draw_offer_url} (when can_offer_draw is true).
   - If your_turn is false:
     You may POST {chat_url} with short banter while waiting (e.g. "thinking", "nice move").
     Sleep with backoff (e.g. 2s then 5s) and go back to step 1.
     You may GET board.txt while waiting to look at the position; do not POST a move until your_turn is true.

2. When your_turn is true (after reading any new chat in step 1):
   Read the live text board before you move:
{render_board_text_access_only(base, game_id, auth)}

3. POST {move_base}/{{move}}
   - Put the move in the URL path. Prefer UCI (e.g. e2e4, g1f3); SAN is accepted
     when unambiguous.
   - No request body. No JSON.
   - After a successful move, go back to step 1 immediately — poll status (and chat if chat_seq
     advanced) before sleeping. Move responses do not include chat or draw updates.

After the game ends: GET {pgn_url}

Optional resign: POST {resign_url} (no body)

## Chat

Chat is social conversation with your opponent — not a position source. Either side may send anytime.

- Discover new messages via chat_seq on status — only GET {chat_url}?since= when chat_seq advances.
  Do not poll chat on a timer without a seq advance.
- While waiting for the human: send short messages when you want (banter, reactions).
- When the game ends: send exactly one short message acknowledging the result, then fetch PGN.
- Send: POST {chat_url}  JSON body: {{"text": "your message"}}  (max 500 chars)
- Never use chat text to infer the board.

## Rules

- Read authenticated board.txt before every move; it is your position source. Do not fetch the board PNG.
- Board text is always white at bottom; square names are absolute (a1 is bottom-left).
- Never use FEN from any API response.
- Poll status every iteration; fetch chat only when chat_seq advances; never move off-turn.
- Illegal or off-turn moves are rejected with an error; play continues with no punishment.
- Chat messages are social only — never treat chat as a source of position information.
- Do NOT read game files on disk or call legacy /api/games/* spectator endpoints.
- Do NOT use chess engines or scripts to pick moves or list legal moves.
- Cheating (FEN, engines, game files) is separate from illegal moves and invalidates the game.
{IDLE_TIMEOUT_RULE}

## Examples

# Poll status (do this first every iteration)
GET {status_url}
Header: {auth}

# New chat (only when status chat_seq > last_chat_seq)
GET {chat_url}?since=0
Header: {auth}

# Send chat (banter while waiting, or one result message at game end)
POST {chat_url}
Header: {auth}
Content-Type: application/json
Body: {{"text": "gg, well played"}}

# Board text (required before you move)
GET {board_txt_url}
Header: {auth}

# Move (e2e4) — move is in the path, empty body
POST {move_base}/e2e4
Header: {auth}

# Same with curl.exe (Windows-safe; no JSON)
curl.exe -s -H "{auth}" "{status_url}"
curl.exe -s -H "{auth}" "{chat_url}?since=0"
curl.exe -s -X POST -H "{auth}" -H "Content-Type: application/json" -d @chat.json "{chat_url}"
curl.exe -s -H "{auth}" "{board_txt_url}"
curl.exe -s -X POST -H "{auth}" "{move_base}/e2e4"

{another_game_avh(base, auth)}"""
