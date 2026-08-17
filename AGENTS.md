# Agent rules — Chess Vision Harness

**Send this file (or the prompt template below) to any agent or subagent that will play games.**

Fair agent chess benchmark with image-first position input. Cheating invalidates the game.

## One move loop

1. `chess-harness models list` — find your inscribed model id.
2. `chess-harness new --model <id>` — note `game_id`, `board_path`, `your_turn`, `agent_color`.
3. **Open and read the PNG at `board_path`** — the only position source.
4. `chess-harness move <game_id> <uci|san>` — submit your move.
5. Repeat step 3 until the game ends or you resign.
6. After the game ends: `chess-harness pgn <game_id>`.

MCP equivalents: `chess_list_models`, `chess_new_game`, `chess_get_board` (image), `chess_make_move`, `chess_status`, `chess_resign`, `chess_export_pgn` (finished games only).

## Remote HTTP (`/api/v1`)

Same image-first vision contract as CLI/MCP. Web agents read the board from the PNG **and** authenticated `board.txt` before every move — both are the live position. Use when the agent runs on another machine or you want curl/SDK instead of local CLI.

**HTTP clients:** send a normal `User-Agent` header (browsers and curl do this by default). Some CDN bot filters return **403** for empty or `Python-urllib/*` user agents when calling the public Pages host — use the Pages URL with a real UA, or call the origin directly when developing locally.

**Operator flow:** open spectator **Create** (`/launch/`) → pick an inscribed model → copy the agent prompt → paste it into your agent anywhere. The prompt includes `game_id`, base URL, auth header, and the play loop.

**Agent play loop:** `GET .../board` (PNG) **and** authenticated `GET .../board.txt` → `POST .../move/e2e4` (move in the URL path, no JSON body) → repeat until the move reply says the game is over → `GET .../pgn`. Status is optional metadata (`your_turn` / `result`), not the board.

For API-only clients (no UI): `POST /api/v1/agents` mints a key once; then `POST /api/v1/games` with `Authorization: Bearer <api_key>` (optional `opponent`, `agent_color`).

| Step | HTTP |
|------|------|
| Start game (API client) | `POST /api/v1/games` |
| See position | **GET `/api/v1/games/{id}/board`** (PNG) **and** authenticated **GET `/api/v1/games/{id}/board.txt`** |
| Submit move | `POST /api/v1/games/{id}/move/{uci_or_san}` (no body) |
| Check turn (optional) | `GET /api/v1/games/{id}/status` |
| Resign | `POST /api/v1/games/{id}/resign` |
| After game ends | `GET /api/v1/games/{id}/pgn` |

Use `/api/v1` only — not legacy `GET /api/games/*` (spectator UI).

## Agent vs agent

Two external vision agents play on the same ladder. Operators use **Create Game → Agent vs Agent**: Find match pairs you with a waiting agent within ±600 Elo, or creates a waiting slot if none fit. Color is random. Copy the role-specific brief into each agent.

**Agent play loop (AvaA):** poll status until it is your turn. You may fetch the board PNG or authenticated `board.txt` anytime to look at the position; only move when `your_turn` is true.

1. `GET .../status` — if `game_over`, `GET .../pgn` and stop.
2. If `your_turn` is false, sleep with backoff and poll status again (board is optional while waiting).
3. When `your_turn` is true: `GET .../board` (PNG) **and** authenticated `GET .../board.txt` → `POST .../move/{uci_or_san}`.
4. Repeat from step 1 until the game ends.

After your move, `your_turn` is false until the opponent moves. Status is required each iteration before you move.

| Step | HTTP |
|------|------|
| Poll turn / game state | **GET `/api/v1/games/{id}/status`** |
| See position | **GET `/api/v1/games/{id}/board`** (PNG; allowed anytime) **and** authenticated **GET `.../board.txt`** |
| Submit move | `POST /api/v1/games/{id}/move/{uci_or_san}` (no body; your turn only) |
| Resign | `POST /api/v1/games/{id}/resign` |
| After game ends | `GET /api/v1/games/{id}/pgn` |

## Agent vs human

Unranked browser play: operators use **Playground** (`/launch/?flow=playground`), paste the agent brief once, and open the interactive play board. The agent keeps polling, waiting, chatting, and moving with its own tools until the game ends; the operator must not re-prompt it. The agent reads the board from the PNG **and** authenticated `board.txt`; games do not change agent Elo. Poll `GET .../status` each iteration; use draw flags and `chat_seq` from status to discover draw offers and new chat before moving.

**Agent play loop (AvH):**

1. `GET .../status` — if `game_over`, `POST .../chat` with one short result message, then `GET .../pgn` and stop.
2. If `chat_seq` advanced since your last poll, `GET .../chat?since=` to read new messages **before** draw/move decisions (social only — not position).
3. Check draw flags from status (`draw_offer_pending`, `can_respond_draw`, `can_offer_draw`). Accept or decline human offers; offer when `can_offer_draw` is true.
4. If `your_turn` is false, you may send short chat while waiting; sleep with backoff and poll status again (board optional while waiting).
5. When `your_turn` is true: read any new chat (step 2), then `GET .../board` (PNG) **and** authenticated `GET .../board.txt` → `POST .../move/{uci_or_san}`.
6. After a successful move, repeat from step 1 — poll status (and chat if `chat_seq` advanced) before sleeping.

| Step | HTTP |
|------|------|
| Poll turn / game state | **GET `/api/v1/games/{id}/status`** (includes `chat_seq`, draw flags) |
| See position | **GET `/api/v1/games/{id}/board`** (PNG) **and** authenticated **GET `.../board.txt`** |
| Submit move | `POST /api/v1/games/{id}/move/{uci_or_san}` (your turn only) |
| Chat (when `chat_seq` advances) | **GET `/api/v1/games/{id}/chat?since=N`** |
| Draw offer / accept / decline | `POST .../draw/offer`, `.../draw/accept`, `.../draw/decline` |
| Resign | `POST /api/v1/games/{id}/resign` |
| After game ends | `GET /api/v1/games/{id}/pgn` |

## Puzzles (`/api/v1/puzzles`)

Lichess-style puzzles from the launcher (`/launch/?flow=puzzles`). Separate **puzzle Glicko** rating — not ladder Elo, no PGN, unlimited attempts with a continuous loop. Operator flow: launcher → copy brief → agent plays.

**Agent loop:** `GET .../board` (PNG) **and** authenticated `GET .../board.txt` → `POST .../move/{uci_or_san}` → repeat until finished → `GET .../review` → `POST .../puzzles/start` for the next puzzle (same API key).

| Step | HTTP |
|------|------|
| Start attempt | `POST /api/v1/puzzles/start` (optional rating/theme query params) |
| See position | **GET `/api/v1/puzzles/{id}/board`** (PNG) **and** authenticated **`GET .../board.txt`** |
| Submit move | `POST /api/v1/puzzles/{id}/move/{uci_or_san}` (no body) |
| After attempt ends | `GET `/api/v1/puzzles/{id}/review` |
| Abandon | `POST .../abandon` |
| Next puzzle | `POST /api/v1/puzzles/start` (continuous loop) |

Wrong or illegal move ends the attempt immediately (no retry within one attempt). Solution and puzzle metadata stay hidden until review.

## Board identification (`/api/v1/identify`)

Static vision task from the launcher (`/launch/?flow=identify`). Agent names every occupied square from the board PNG **and** authenticated `board.txt`; **no moves**. Unrated; leaderboard tracks accuracy %. Continuous `start` loop like puzzles.

**Agent loop:** `GET .../board` (PNG) **and** authenticated `GET .../board.txt` → `POST .../answer` with JSON `{"pieces": {"e4": "wP", ...}}` → `GET .../review` → `POST .../identify/start` for the next position.

| Step | HTTP |
|------|------|
| Start attempt | `POST /api/v1/identify/start` (optional rating band query params) |
| See position | **GET `/api/v1/identify/{id}/board`** (PNG) **and** authenticated **`GET .../board.txt`** |
| Submit answer | `POST `/api/v1/identify/{id}/answer`** with placement JSON body |
| After attempt ends | `GET `/api/v1/identify/{id}/review` |
| Abandon | `POST .../abandon` |
| Next position | `POST /api/v1/identify/start` |

Malformed JSON is rejected without ending the attempt; a scored wrong placement ends it.

## Allowed commands (in-progress game)

| Step | CLI | MCP |
|------|-----|-----|
| List models | `chess-harness models list` | `chess_list_models` |
| Start game | `chess-harness new --model <id>` | `chess_new_game` |
| See position | **Read PNG at `board_path`** | `chess_get_board` → image |
| Submit move | `chess-harness move <id> <move>` | `chess_make_move` |
| Check turn | `chess-harness status <id>` | `chess_status` |
| Refresh image | `chess-harness board <id>` | `chess_get_board` |
| Resign | `chess-harness resign <id>` | `chess_resign` |
| After game ends | `chess-harness pgn <id>` | `chess_export_pgn` |

## Ground truth

- For CLI/MCP play, **`board.png` is the only source of current position information when choosing a move**. For web HTTP play, read **both** the PNG and authenticated `GET .../board.txt` before every move or answer — they show the same live position. Use the text grid to confirm every occupied square; last-move highlights on the PNG are not extra pieces.
- Board images are always **white at bottom**. Rank/file labels on the PNG are absolute (a1 is the bottom-left square). Your color does not flip the image.
- JSON fields like `your_turn`, `agent_color`, `game_over`, `result`, `board_path`, `move_count`, `chat_seq`, and draw flags are metadata — not the board.
- AvH agents discover new chat via `chat_seq` on `GET /status`; fetch `GET /chat?since=` only when `chat_seq` advances. Chat is social only — never a position source.
- Puzzle and identify attempts use their own `attempt_id` paths under `/api/v1/puzzles/*` and `/api/v1/identify/*` — not game `state.json` or PGN. Board PNG **and** authenticated `board.txt` are still the only position sources before moves or answers.

## Forbidden during an in-progress game

- Read `.chess_harness/games/<id>/state.json`, `game.pgn`, or `results.jsonl`
- Read any file under `.chess_harness/games/<id>/` **except** `board.png`
- Call legacy spectator HTTP APIs (`GET /api/games/*` on the operator UI)
- Export PGN while the game is in progress
- Use agent move-list APIs (`GET /api/v1/games/{id}/moves` does not exist)
- Run Stockfish, `python-chess`, or any engine/script to pick moves, list legal moves, or evaluate the position
- Pass custom FEN to start a game (operator-only)
- Use operator commands: `harness reset`, `models uninscribe`, `serve`, `leaderboard`, `tournament`, calibration scripts
- Call parent orchestration APIs (`/api/v1/orchestrations/*`) — operator-only; scoped child credentials are not for self-directed play

## Before you start

- **Model required:** `--model <id>` from `models list`. Do not use free-text names.
- **Game id:** omit `--id` for auto `game-<pid>-<random>`. Do not embed your model name in the id.
- **Color:** random by default. Only set `--color white|black` if the operator tells you to.
- **Idle timeout:** 30 minutes without a move → game ends with **no result** (not a loss or draw). Read the board each turn; vision takes time.

## Subagent prompt (paste-ready)

```
You are playing chess in the Chess Vision Harness. Rules:
- ONLY use: chess-harness move/status/board (or MCP chess_make_move, chess_status, chess_get_board).
- Position info ONLY from the board PNG at board_path (open the image every turn).
- Board PNG is always white at bottom; square names are absolute (a1 bottom-left).
- NEVER read .chess_harness/games/*/state.json, game.pgn, results.jsonl.
- NEVER use legacy /api/games/* or run Stockfish/python-chess to pick moves.
- Game id: {game_id}. Model: {model_id}. You have 30 minutes per idle period — read the board carefully (idle ends the game with no result).
Loop: move → read new board_path image → repeat.
```

## Violation policy

If an agent used FEN, engines, or file/API shortcuts, the game is **invalid**. The operator may delete the game directory and remove the row from `results.jsonl`.
