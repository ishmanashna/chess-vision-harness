# Chess Vision Harness — Product

## One-liner

A local harness where **vision LLM agents** play chess against a **catalog of rated engines**, grounded on a fresh board PNG every turn, with live **spectator**, agent **ELO ladder**, PGN export, and parallel multi-game runs for winrate stats.

## Problem

Agents playing from text or hidden state drift off the board and cheat with engines. We need a fair benchmark: **see the board, submit a move, repeat** — with illegal moves rejected and humans able to watch.

Separately, opponent catalog labels (Patricia “500”, CCRL quotes) may not match real strength at our time controls. We need **engine calibration** to measure and rationalize those numbers.

## What we're building

### 1. Vision agent benchmark

- Agent reads `board.png` only (API/CLI redacted — no FEN leaks).
- Plays vs `opponents.json` entries (Patricia, tiny engines, Stockfish tiers, handicapped Stockfish).
- Agent ELO in `models.json` (starts 500, updates from game results).
- MCP + `play.py` CLI; contract in [`AGENTS.md`](AGENTS.md).

### 2. Spectator (operator + audience)

Local web UI at `http://localhost:8765`:

| Area | Purpose |
|------|---------|
| **Active** | Live games — mini-boards, eval bar, agent vs opponent labels |
| **Completed** | Results, ELO change, link to full board view |
| **Game view** (`/g/<id>`) | Full board, move list, game info (operator debug) |
| **Leaderboard** | Agent rankings + opponent catalog reference table |

Started with `python play.py serve`. One process per port; `--force` replaces stale servers.

Spectator is **not** for agents — API is redacted unless `CHESS_HARNESS_DEBUG=1` (auto-set when serving).

### 3. Engine calibration (`elo_calibration/`)

Engine-vs-engine ladder — **no agents**:

- Non-Stockfish opponents start at ELO **500**, update per game (sliding K).
- `stockfish:N` tiers are **anchors** (fixed catalog UCI ELO).
- `stockfish-handicap:*` = Stockfish with depth/time/noise harness — calibrated like other floaters.
- Output: `results/<suite>/games.jsonl`, `ratings.json`, `summary.md` — advisory for `opponents.json`.

Example finding: a mislabeled harness rung can beat `stockfish:0` often while fitted ELO is still climbing (500→900+) — catalog labels need calibration, not blind trust.

### 4. Operator tooling

- `harness reset`, `models inscribe/uninscribe`, `game audit`, `opponents verify`
- [`scripts/run_agent_game.md`](scripts/run_agent_game.md) — how to launch an honest subagent run
- Tournament / batch (`results.jsonl`, aggregate)

## Goals

- IDE agents play full games via tools with visual grounding every turn.
- Many parallel `game_id`s (subagents) without state corruption.
- Honest opponent strength labels (calibration-backed).
- Windows-friendly, offline, no database.

## Non-goals

- Computer-use / clicking on a screen
- Online matchmaking or FIDE ratings
- Model training
- Letting agents read `state.json` or spectator APIs during play

## Target users

1. **Us** — run agent batteries, tune opponents, watch spectator, read calibration reports.
2. **Outsiders** — clone repo, read README, reproduce agent games with their own models.

## Core journeys

### Honest agent game

1. Operator: `serve --force`, inscribe model, paste [`AGENTS.md`](AGENTS.md) prompt into subagent.
2. Agent: `new` → read image → `move` loop → `pgn`.
3. Operator: `game audit <id>`, spectator review, keep or invalidate result.

### Calibrate opponents

1. `python elo_calibration/scripts/run_calibration.py --suite ladder --play`
2. Review fitted ELO vs catalog; adjust `opponents.json` or harness configs.
3. Re-run agent games at calibrated tiers.

### Parallel eval

Matrix of opponents × colors × N games; each subagent gets its own `game_id`; `aggregate` + `leaderboard`.

## Success criteria

- Agent at ~500 ELO gets ~500-strength opponents by default (not `stockfish:0` at 1320).
- No FEN/position leaks on agent API surface (tests in `test_agent_surface.py`).
- Calibration produces sensible ordering (e.g. `noise10` weaker than `noise5` over many games).
- Spectator shows correct orientation and labels when agent plays Black.
- PGN imports on Lichess.

## Constraints

- Python 3.11+, `python-chess`, local Stockfish + bundled opponents
- Filesystem state (`.chess_harness/`), no DB
- Localhost spectator by default
