# Running an agent game (operator)

1. Ensure spectator is running: `chess-harness serve --force` (enables debug for operator UI).
2. Inscribe model if needed: `chess-harness models inscribe composer-2.5 --name "Composer 2.5"`.
3. Start game as operator or let subagent run `chess-harness new --model composer-2.5 --opponent stockfish-handicap:noise17`.
4. Give the subagent the Create Game paste brief (HTTP) or: play only via `chess-harness move/status/board` (or MCP `chess_*`); position from the PNG at `board_path`; game id and model id from `new`.
5. Subagent uses **only** `chess-harness move/status/board` or MCP `chess_*` — no Shell `curl`, no Read on `state.json`.
6. After game: `chess-harness game audit <id>`; if clean, keep result; else delete game dir and result row.

Prefer MCP (`chess_get_board` embeds PNG) over Shell to reduce temptation to read `state.json`.

Idle timeout is **30 minutes** — remind the subagent to read the board each turn. Idle ends the game with **no result** (not a resign/loss).

## Link-only (agent figures it out)

When the operator only gives the harness URL (no paste brief):

1. `GET /api/v1/agents` and look for a row that is already you (same model — `Grok 4.6` vs `Grok4.6` still counts if it is clearly you).
2. If found, `POST /api/v1/agents` with that existing `id` (remints a key). Do not invent a twin id.
3. If none match, inscribe a new id + display name, then create a game vs engine and play.
