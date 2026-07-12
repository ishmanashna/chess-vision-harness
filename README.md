# Chess Vision Harness

A local benchmark where **vision-capable LLM agents** play chess by reading board PNG images. Agents face a catalog of rated opponents; results feed an agent ELO ladder. A **spectator web UI** lets humans watch live games and run engine calibration.

For maintainers: [`product.md`](product.md) (goals), [`architecture.md`](architecture.md) (internals).

**Playing as an agent?** Read [`AGENTS.md`](AGENTS.md) — the full contract to paste into subagent prompts.

## Install

```bash
pip install -e ".[dev]"
cp models.json.example models.json    # optional: empty model registry
python scripts/fetch_opponents.py   # Stockfish + tiny engines → bin/
python play.py opponents verify
```

Requirements: **Python 3.11+**, [Node.js](https://nodejs.org/) (for Toledo opponent).

| Variable | Purpose |
|----------|---------|
| `STOCKFISH_PATH` | Stockfish binary (default `bin/stockfish-windows-x86-64.exe` on Windows) |
| `CHESS_HARNESS_DIR` | Runtime data dir (default `.chess_harness/`, gitignored) |

Engine binaries are **not** in git — see [`NOTICE.md`](NOTICE.md) for third-party licenses (Stockfish/Patricia are GPL-3).

## Quick start (human operator)

```bash
python play.py models inscribe my-agent --name "My Agent"
python play.py serve --force
# http://localhost:8765
```

Give an agent [`AGENTS.md`](AGENTS.md) and let it play:

```bash
python play.py new --model my-agent --opponent patricia:500
python play.py move <game_id> e2e4
```

## Opponents

Catalog: [`opponents.json`](opponents.json). Download binaries with `scripts/fetch_opponents.py`.

| Family | Examples | Rating source |
|--------|----------|---------------|
| Patricia tiers | `patricia:500` … `patricia:1200` | Patricia UCI_Elo |
| CCRL tiny engines | `minimalchess-0.2`, `toledo`, `minimalchess-0.3` | CCRL 40/4 |
| Random mover | `random` | Calibrated (builtin) |
| Stockfish tiers | `stockfish:0` … `stockfish:20` | Official UCI_Elo (anchors) |
| Stockfish handicaps | `stockfish-handicap:blitz50`, `depth6`–`depth12`, `noise5` | Skill 0 + time/depth harness |

Omit `--opponent` for an **ELO-weighted random** opponent matched to the agent's rating.

```bash
python play.py opponents list
python play.py opponents verify
```

Catalog ELO labels are **engine ratings**, not human FIDE ELO.

## Agent ELO

Inscribed models live in `models.json` (copy from `models.json.example`; starts at **500** ELO). Vision agents only — see [`AGENTS.md`](AGENTS.md).

```bash
python play.py models list
python play.py leaderboard
```

## Engine calibration (`elo_calibration/`)

Engine-vs-engine games to measure opponent strength. No agents, no board images.

- **Stockfish tiers** (`stockfish:N`) are fixed **anchors** at catalog UCI ELO.
- **Everything else** starts at **500** and updates after each game.
- Results go to `elo_calibration/results/` (gitignored).

**Spectator UI** (`/calibration`): per-engine Start/Stop, parallel games, live ratings.

**CLI batch** (separate from UI — don't run both at once):

```bash
python elo_calibration/scripts/run_calibration.py --suite quick --play --workers 4
```

See [`elo_calibration/README.md`](elo_calibration/README.md).

## Spectator

```bash
python play.py serve
python play.py serve stop
python play.py serve --force
```

| Tab | URL | Purpose |
|-----|-----|---------|
| Active | `/` | Live agent games |
| Completed | `/?tab=done` | Finished games |
| Calibration | `/calibration` | Continuous engine calibration |
| ELO Ladder | `/leaderboard` | Agent + opponent ratings |

## MCP (Cursor / IDE agents)

```bash
python -m chess_harness.mcp_server
```

Copy [`mcp.json.example`](mcp.json.example) to `.cursor/mcp.json` if you use Cursor.

Tools: `chess_list_models`, `chess_new_game`, `chess_get_board`, `chess_make_move`, `chess_status`, `chess_resign`, `chess_export_pgn`.

## CLI reference

| Command | Purpose |
|---------|---------|
| `play.py new --model <id>` | Start game |
| `play.py move <id> <move>` | Agent move (UCI or SAN) |
| `play.py status` / `board` | Metadata / refresh PNG |
| `play.py pgn <id>` | Export after game ends |
| `play.py harness reset --yes` | Wipe local data |
| `play.py game audit <id>` | Move audit log |

Workflows: [`scripts/run_agent_game.md`](scripts/run_agent_game.md).

## Tests

```bash
pytest
```

CI runs on Ubuntu + Windows (see `.github/workflows/test.yml`).

## License

MIT for harness source code — see [`LICENSE`](LICENSE). Engine binaries are third-party; see [`NOTICE.md`](NOTICE.md).
