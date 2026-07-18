# ARCHITECTURE

Technical reference for the Chess Vision Harness codebase. Read with [`PRODUCT.md`](PRODUCT.md). Agent play rules live in [`AGENTS.md`](AGENTS.md) — do not duplicate them here.

## Stack

| Layer | Technology | Role |
|-------|------------|------|
| **Core** | **Python 3.11+** | Game rules, engines, CLI, MCP, spectator server, calibration |
| **Chess** | **python-chess** | Board state, move validation, PGN |
| **HTTP** | **FastAPI** + **Uvicorn** | Spectator UI and operator APIs |
| **Agents** | **MCP** (stdio) | IDE tool surface for vision agents |
| **Images** | **Pillow** | Board PNG rendering |
| **Frontend** | **TypeScript** | UI (extracted from inline HTML over time) |
| **Tooling** | **Node.js** (npm) | `tsc`, ESLint in `frontend/` |
| **Engines** | **Stockfish** (UCI binary) | Opponents, eval bar, inverse-SF, calibration |
| **Persistence** | **Filesystem** | No database — JSON, JSONL, PNG, PGN per game |

Python owns game logic. TypeScript is presentation only.

## Repository layout

**The repo root contains only Markdown files and directories.** No exceptions — no dotfiles, no config, no lockfiles, no entry scripts, no `LICENSE` plain-text file at root.

```
chess-vision-harness/
  AGENTS.md
  ARCHITECTURE.md
  NOTICE.md
  ORCHESTRATOR.md
  PRODUCT.md
  README.md
  bin/
  config/
  docs/
  elo_calibration/
  frontend/
  python/
  scripts/
```

| Path | Contents |
|------|----------|
| `config/` | Committed catalogs and examples (`opponents.json`, `models.json.example`, `mcp.json.example`) |
| `python/` | `pyproject.toml`, `src/chess_harness/`, `tests/` |
| `frontend/` | `package.json`, `tsconfig.json`, `eslint.config.js`, TypeScript sources |
| `scripts/` | Operator scripts, quality gate, fetch, audits |
| `docs/` | Roadmap, plans, license text, extended docs |
| `bin/` | Downloaded engine binaries (gitignored via `bin/.gitignore`) |
| `.chess_harness/` | Runtime data (gitignored via `.chess_harness/.gitignore`): games, `models.json`, results |

Ignore rules live in **subdirectory** `.gitignore` files, not at repo root. Tooling is invoked from its home directory (`python/`, `frontend/`) so caches stay out of root.

Implementation: [`docs/plan.md`](plan.md).

## System shape

```
Agents (CLI / MCP / future HTTP)          Operator (serve UI)
              |                                    |
              v                                    v
     +------------------+                 +------------------+
     |  Agent surface   |  redaction      |  Spectator app   |
     |  (no FEN leaks)  |                 |  + calibration   |
     +--------+---------+                 +--------+---------+
              |                                    |
              v                                    v
     +----------------------------------------------------+
     |  GameService / BoardController  (rules, PGN, ELO)  |
     |  GameManager (per-game files + lock)               |
     +------------------------+---------------------------+
                              |
              +---------------+---------------+
              v                               v
     OpponentEngineManager            catalogs + ratings
```

**Source of truth** per `game_id`: `state.json`, `board.png`, `game.pgn` under the data directory. Agents get a PNG and redacted status only.

## Layers

| Layer | Responsibility |
|-------|----------------|
| Adapters | CLI, MCP, spectator FastAPI, future `/api/v1` |
| Agent surface | Redact payloads; block in-progress PGN for agents |
| Game logic | New game, move, resign, idle timeout, audit, agent ELO |
| Engines | Pooled Stockfish + catalog adapters |
| Persistence | Filesystem only |
| Calibration | `elo_calibration/` — engine-vs-engine, no agents |

Target (roadmap Plan 0): thin `GameService` as the single mutation path.

## Entry points

| Command | Role |
|---------|------|
| `chess-harness` / `python -m chess_harness` | CLI (from `python/` package) |
| `chess-harness-mcp` / `python -m chess_harness.mcp_server` | MCP |
| `chess-harness serve` | Spectator on localhost |
| `python elo_calibration/scripts/run_calibration.py` | Calibration suites |

## Runtime paths

Resolved in `python/src/chess_harness/paths.py` (repo root = parent of `python/`):

| Resource | Location |
|----------|----------|
| Data dir | `CHESS_HARNESS_DIR` or `<repo>/.chess_harness/` |
| Opponent catalog | `config/opponents.json` |
| Model registry | `<repo>/.chess_harness/models.json` (from `config/models.json.example`) |
| Stockfish | `STOCKFISH_PATH` or `bin/stockfish*` |

## Principles

1. **Harness owns truth** — disk state wins; agents are clients.
2. **Vision contract** — position for agents comes only from the board image.
3. **Fail closed** — illegal or ambiguous moves are rejected.
4. **One mutation path** — adapters stay thin.
5. **Replace, don’t stack** — remove old paths in the same change.
6. **Clean root** — only `*.md` and directories at repo top level.

## Coding conventions

### Line limit (hard)

**Every coding file ≤ 300 lines** (Python, TypeScript, JavaScript; not Markdown, JSON catalogs, lockfiles).

```bash
python scripts/quality_gate.py
```

Runs: line limit → `tsc` (in `frontend/`) → pytest (from `python/`) → ESLint.

### Python

3.11+; package under `python/src/chess_harness/`; `snake_case` modules.

### TypeScript

Under `frontend/`; strict `tsc`; no game rules in TS.

### Dependencies

Add only when needed; offline-friendly.
