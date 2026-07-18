# Agent rules — Chess Vision Harness

**Send this file (or the prompt template below) to any agent or subagent that will play games.**

Vision-only benchmark. Cheating invalidates the game.

## One move loop

1. `chess-harness models list` — find your inscribed model id.
2. `chess-harness new --model <id>` — note `game_id`, `board_path`, `your_turn`, `agent_color`.
3. **Open and read the PNG at `board_path`** — the only position source.
4. `chess-harness move <game_id> <uci|san>` — submit your move.
5. Repeat step 3 until the game ends or you resign.
6. After the game ends: `chess-harness pgn <game_id>`.

MCP equivalents: `chess_list_models`, `chess_new_game`, `chess_get_board` (image), `chess_make_move`, `chess_status`, `chess_resign`, `chess_export_pgn` (finished games only).

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

- **`board.png` is the only source of position information.**
- JSON fields like `your_turn`, `agent_color`, `game_over`, `result`, `board_path`, `move_count` are metadata — not the board.

## Forbidden during an in-progress game

- Read `.chess_harness/games/<id>/state.json`, `game.pgn`, or `results.jsonl`
- Read any file under `.chess_harness/games/<id>/` **except** `board.png`
- Call spectator HTTP APIs (`http://localhost:8765/api/...`)
- Export PGN while the game is in progress
- Run Stockfish, `python-chess`, or any engine/script to pick moves, list legal moves, or evaluate the position
- Pass custom FEN to start a game (operator-only)
- Use operator commands: `harness reset`, `models uninscribe`, `serve`, `leaderboard`, `tournament`, calibration scripts

## Before you start

- **Model required:** `--model <id>` from `models list`. Do not use free-text names.
- **Game id:** omit `--id` for auto `game-<pid>-<random>`. Do not embed your model name in the id.
- **Color:** random by default. Only set `--color white|black` if the operator tells you to.
- **Idle timeout:** 5 minutes without a move → auto-resign. Read the board each turn; vision takes time.

## Subagent prompt (paste-ready)

```
You are playing chess in the Chess Vision Harness. Rules:
- ONLY use: chess-harness move/status/board (or MCP chess_make_move, chess_status, chess_get_board).
- Position info ONLY from the board PNG at board_path (open the image every turn).
- NEVER read .chess_harness/games/*/state.json, game.pgn, results.jsonl.
- NEVER curl localhost:8765 or run Stockfish/python-chess or use any tool to pick moves, list legal moves, or know the evaluation.
- Game id: {game_id}. Model: {model_id}. You have 5 minutes per idle period — read the board carefully.
Loop: move → read new board_path image → repeat.
```

## Violation policy

If an agent used FEN, engines, or file/API shortcuts, the game is **invalid**. The operator may delete the game directory and remove the row from `results.jsonl`.
