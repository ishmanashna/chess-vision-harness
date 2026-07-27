# Running an agent game (operator)

1. Ensure spectator is running: `chess-harness serve --force` (enables debug for operator UI).
2. Inscribe model if needed: `chess-harness models inscribe composer-2.5 --name "Composer 2.5"`.
3. Start game as operator or let subagent run `chess-harness new --model composer-2.5 --opponent stockfish-handicap:noise17`.
4. Paste subagent prompt from `AGENTS.md` with `{game_id}`, `{model_id}`, `{board_path}` filled in.
5. Subagent uses **only** `chess-harness move/status/board` or MCP `chess_*` — no Shell `curl`, no Read on `state.json`.
6. After game: `chess-harness game audit <id>`; if clean, keep result; else delete game dir and result row.

Prefer MCP (`chess_get_board` embeds PNG) over Shell to reduce temptation to read `state.json`.

Idle timeout is **30 minutes** — remind the subagent to read the board each turn. Idle ends the game with **no result** (not a resign/loss).
