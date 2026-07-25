# ARCHITECTURE

Technical reference for the Chess Vision Harness codebase. Read with [`PRODUCT.md`](PRODUCT.md). Agent play rules live in [`AGENTS.md`](AGENTS.md) — do not duplicate them here. Public hosting: [`DEPLOY.md`](DEPLOY.md).

## Stack

| Layer | Technology | Role |
|-------|------------|------|
| **Core** | **Python 3.11+** | Game rules, engines, CLI, MCP, spectator server, calibration |
| **Chess** | **python-chess** | Board state, move validation, PGN |
| **HTTP** | **FastAPI** + **Uvicorn** | Local spectator UI, `/api/v1`, operator APIs |
| **Public edge** | **Cloudflare Pages** + Functions | Always-on site (`public-site/`); proxies live traffic via `GAME_ORIGIN` |
| **Agents** | **MCP** (stdio) + **HTTP `/api/v1`** | IDE tools and remote play |
| **Images** | **Pillow** | Board PNG rendering |
| **Frontend** | **TypeScript** (`frontend/`) + static HTML/JS (`public-site/`) | Local UI tooling + public Pages shell |
| **Tooling** | **Node.js** (npm) | `tsc`, ESLint in `frontend/` |
| **Engines** | **Stockfish** (UCI binary) | Opponents, eval bar, inverse-SF, calibration |
| **Persistence** | **Filesystem** | No database — JSON, JSONL, PNG, PGN per game |

Python owns game logic. Public Pages and TypeScript are presentation / edge only.

## Repository layout

**The repo root contains only Markdown files and directories.** No exceptions — no dotfiles, no config, no lockfiles, no entry scripts, no `LICENSE` plain-text file at root.

```
chess-vision-harness/
  AGENTS.md
  ARCHITECTURE.md
  DEPLOY.md
  NOTICE.md
  ORCHESTRATOR.md
  PRODUCT.md
  README.md
  bin/
  config/
  deploy/
  docs/
  elo_calibration/
  frontend/
  public-site/
  python/
  scripts/
```

| Path | Contents |
|------|----------|
| `DEPLOY.md` | Operator deploy entry (Pages + game origin, backup, TLS alternatives) |
| `deploy/` | Runbooks + templates (`home-pc.md`, `pages.md`, Caddy, systemd, …) |
| `public-site/` | Cloudflare Pages app (HTML/CSS/JS + Functions); auto-deploy on push |
| `config/` | Committed catalogs and examples (`opponents.json`, `models.json.example`, `mcp.json.example`) |
| `python/` | `pyproject.toml`, `src/chess_harness/`, `tests/` |
| `frontend/` | `package.json`, `tsconfig.json`, `eslint.config.js`, TypeScript sources |
| `scripts/` | Operator scripts, quality gate, fetch, audits |
| `docs/` | Roadmap, plans, license text, extended docs |
| `bin/` | Downloaded engine binaries (gitignored via `bin/.gitignore`) |
| `.chess_harness/` | Runtime data (gitignored via `.chess_harness/.gitignore`): games, `models.json`, results |

Ignore rules live in **subdirectory** `.gitignore` files, not at repo root. Tooling is invoked from its home directory (`python/`, `frontend/`) so caches stay out of root.

## System shape

```
Agents (CLI / MCP / HTTP)                 Public site (Pages)
        |                                         |
        |              GAME_ORIGIN proxy          |
        +------------------+----------------------+
                           |
                           v
              +---------------------------+
              |  chess-harness serve      |
              |  FastAPI (127.0.0.1:8765) |
              +-------------+-------------+
                            |
        +-------------------+-------------------+
        v                                       v
 Agent surface (redacted)              Spectator + calibration
        |                                       |
        v                                       v
 +----------------------------------------------------+
 |  GameService / BoardController  (rules, PGN, ELO)  |
 |  GameManager (per-game files + lock)               |
 +------------------------+---------------------------+
                          |
          +---------------+---------------+
          v                               v
 OpponentEngineManager            catalogs + ratings
```

**Source of truth** per `game_id`: `state.json`, `board.png`, `game.pgn` under the data directory. Agents get a PNG and redacted status only. The public leaderboard snapshot is a published copy (`public-site/data/leaderboard.json`), not a second source of game state.

## Layers

| Layer | Responsibility |
|-------|----------------|
| Public edge | Pages static shell + Functions (`/api/edge-health`, live proxy, block `/calibration*`) |
| Adapters | CLI, MCP, spectator FastAPI, `/api/v1` |
| Agent surface | Redact payloads; block in-progress PGN for agents |
| Game logic | New game, move, resign, idle timeout, audit, agent ELO |
| Engines | Pooled Stockfish + catalog adapters |
| Persistence | Filesystem only |
| Calibration | `elo_calibration/` — engine-vs-engine, no agents (localhost only on public edge) |

**Entry-point parity:** CLI, MCP, and HTTP mutations for agent play (`new` / `move` / `resign` / `status` / `board` / `pgn`) go through `GameService`, which delegates to `BoardController`. Adapters stay thin; idle prune and engine `release()` after `new_game` / `make_move` live in `GameService`.

## Entry points

| Command | Role |
|---------|------|
| `chess-harness` / `python -m chess_harness` | CLI (from `python/` package) |
| `chess-harness-mcp` / `python -m chess_harness.mcp_server` | MCP |
| `chess-harness serve` | Local spectator + API on `127.0.0.1:8765` |
| `chess-harness snapshot-leaderboard` | Export Pages ladder snapshot |
| `python elo_calibration/scripts/run_calibration.py` | Calibration suites |

## Runtime paths

Resolved in `python/src/chess_harness/paths.py` (repo root = parent of `python/`):

| Resource | Location |
|----------|----------|
| Data dir | `CHESS_HARNESS_DIR` or `<repo>/.chess_harness/` |
| Opponent catalog | `config/opponents.json` |
| Model registry | `<repo>/.chess_harness/models.json` (from `config/models.json.example`) |
| Stockfish | `STOCKFISH_PATH` or `bin/stockfish*` |
| Public ladder snapshot | `public-site/data/leaderboard.json` |

## Principles

1. **Harness owns truth** — disk state wins; agents are clients.
2. **Vision contract** — position for agents comes only from the board image.
3. **Fail closed** — illegal or ambiguous moves are rejected.
4. **One mutation path** — adapters stay thin.
5. **Replace, don’t stack** — remove old paths in the same change.
6. **Clean root** — only `*.md` and directories at repo top level.
7. **One public hostname** — agents and humans use Pages; swap `GAME_ORIGIN` to move the game host.

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
