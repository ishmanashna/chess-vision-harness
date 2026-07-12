# Running an agent game (operator)

1. Ensure spectator is running: `python play.py serve --force` (enables debug for operator UI).
2. Inscribe model if needed: `python play.py models inscribe composer-2.5 --name "Composer 2.5"`.
3. Start game as operator or let subagent run `python play.py new --model composer-2.5 --opponent patricia:500`.
4. Paste subagent prompt from `AGENTS.md` with `{game_id}`, `{model_id}`, `{board_path}` filled in.
5. Subagent uses **only** `python play.py move/status/board` or MCP `chess_*` — no Shell `curl`, no Read on `state.json`.
6. After game: `python play.py game audit <id>`; if clean, keep result; else delete game dir and result row.

Prefer MCP (`chess_get_board` embeds PNG) over Shell to reduce temptation to read `state.json`.

Idle timeout is **5 minutes** — remind the subagent to read the board each turn.
