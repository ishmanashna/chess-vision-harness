# Architecture — Chess Vision Harness

Internal technical reference.

## Overview

```
IDE subagents (many)                  Operator
   |  MCP stdio / play.py CLI            | serve, calibration, reset
   v                                     v
+----------------------------------------------------------+
|  commands.py → BoardController + GameManager (file lock)  |
|    state.json, board.png, game.pgn per game_id            |
|    agent_surface.py — redacted CLI/MCP/spectator API      |
|    results.jsonl + ELOLadder (models.json)                |
|    spectator.py (FastAPI, lazy Stockfish eval)           |
+----------------------------------------------------------+
|  OpponentEngineManager + configure_opponent_strength()    |
|  Catalog: opponents.json                                  |
+----------------------------------------------------------+
|  elo_calibration/ — engine-only games, floating ELO       |
+----------------------------------------------------------+
```

## Principles

- Harness is source of truth per `game_id`.
- **Agents:** board PNG only; API omits FEN, moves, legal-move hints.
- Fail closed on illegal/ambiguous moves.
- `game_lock` serializes same `game_id`; different ids run in parallel.
- Stockfish full-strength = eval/spectator only; opponents from catalog.

## Path resolution

| Variable | Purpose |
|----------|---------|
| `CHESS_HARNESS_DIR` | Data directory (default `.chess_harness`) |
| `STOCKFISH_PATH` | Stockfish binary |
| `CHESS_HARNESS_DEBUG` | Spectator full state (`serve` sets this) |

## Entry points

| Entry | Use |
|-------|-----|
| `play.py` | Canonical CLI |
| `python -m chess_harness.mcp_server` | MCP for IDE agents |
| `elo_calibration/scripts/run_calibration.py` | Engine calibration |

## Agent surface (`agent_surface.py`)

Redacted responses for `status()`, `get_board()`, spectator `GET /api/games/*/state`. Full state via `?debug=1` + `CHESS_HARNESS_DEBUG`.

`export_pgn()` blocked in-progress for agents; `allow_in_progress` for operator/spectator.

`move_audit` in `state.json` for post-game `play.py game audit`.

## MCP tools

| Tool | Notes |
|------|-------|
| `chess_list_models` | Inscribed models |
| `chess_new_game` | `model_id` required; optional `opponent` |
| `chess_get_board` | PNG path + embedded image; no FEN |
| `chess_make_move` | UCI/SAN |
| `chess_status` | Turn metadata only |
| `chess_export_pgn` | After game ends |
| `chess_resign` | |

Contract: [`AGENTS.md`](AGENTS.md).

## Opponents (`opponents.json`)

| Type | Play | Calibration |
|------|------|-------------|
| `uci` | Full-strength binary | Floating from 500 |
| `uci_elo` | Patricia: `UCI_Elo` + `Skill_Level` | Floating from 500 |
| `stockfish` | `UCI_Elo` tier 0–20 | **Anchor** (fixed ELO) |
| `stockfish_harness` | Skill 0 + `harness` dict (`depth`, `movetime_ms`, `random_move_pct`) | Floating from 500 |

`configure_opponent_strength()` in `engine.py` — shared with `elo_calibration/calibration/engine_player.py`.

`play_opponent_move()` applies harness before UCI `play()`.

## Agent ELO (`elo.py` + `models.json`)

Per inscribed model; default 500. Updated from agent game results only. Operator: `harness reset --yes`, `rebuild-elo`.

## Engine calibration (`elo_calibration/`)

| Module | Role |
|--------|------|
| `calibration/ratings.py` | `CalibrationLadder` — per-game ELO, anchors vs floating |
| `calibration/runner.py` | YAML suite → schedule; `--play` or dry-run |
| `calibration/game_loop.py` | `python-chess` loop, no PNG |
| `calibration/engine_player.py` | Wraps `OpponentEngineManager` |
| `suites/*.yaml` | Pairings, round-robin, harness overrides |

Persistence: `results/<suite>/ratings.json`, `games.jsonl`.

## Spectator (`spectator.py` + `serve_utils.py`)

- Port check, `spectator.json` PID metadata, `--force` kill/restart
- Background idle watcher → auto-resign (300s)
- Eval cache TTL 2s; board orientation by `agent_color`
- List API: no raw `state` blob; game page uses `?debug=1`

## Concurrency

`GameManager.game_lock(game_id)` — load → mutate → render → save. Timeout → "Game busy".

## Security

- Spectator binds `127.0.0.1`
- `game_id` = `[a-zA-Z0-9_-]+`

## Package layout

```
play.py, opponents.json, models.json, AGENTS.md
src/chess_harness/
  agent_surface.py, board_controller.py, game_manager.py
  engine.py, opponents.py, models.py, elo.py
  tools_mcp.py, mcp_server.py, spectator.py, serve_utils.py
  harness_reset.py, opponent_verify.py, commands.py
elo_calibration/
  calibration/{ratings,runner,game_loop,engine_player,report}.py
  suites/*.yaml, scripts/run_calibration.py
scripts/fetch_opponents.py, run_agent_game.md
tests/
```
