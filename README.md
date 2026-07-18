# Chess Vision Harness

A local benchmark where **vision-capable LLM agents** play chess by reading board PNG images. Agents face a catalog of rated opponents; results feed an agent ELO ladder. A **spectator web UI** lets humans watch live games and run engine calibration.

For maintainers: [`PRODUCT.md`](PRODUCT.md) (goals), [`ARCHITECTURE.md`](ARCHITECTURE.md) (system design), [`docs/README.md`](docs/README.md) (doc index), [`docs/ladder-coverage-plan.md`](docs/ladder-coverage-plan.md) (opponent ladder — in progress). Quality gate: `python scripts/quality_gate.py`.

**Playing as an agent?** Read `[AGENTS.md](AGENTS.md)` — the full contract to paste into subagent prompts.

HUMAN: yo, i made this because agents suck at chess for the wrong reasons. a bit inspired by claude_plays_pokemon and stuff like that. for whatever you need this repo to do, just prompt your agent to do it and it will probably figure it out, lol.

future work will be:  

- testing more agents and more times (but i have no money for tokens or fancy subscriptions so, idk)  maybe make it so people can contact this via API or the web or whatever to inscribe agents and make them play against our engines and save those games as our own. probably that involves deploying. and maybe having my computer as a server.
- agent vs agent play  
- browser human vs agent  
- turning this into something that can call models via API and making it an actual benchmark that can be copied by arena or artificial analysis or something like that

-streaming games maybe

i'll let you go back to reading agent written docs slop. human out.  

Maintainer roadmap (separate from this file): `[docs/roadmap/](docs/roadmap/README.md)`.

## Install

```bash
pip install -e "python/[dev]"
python scripts/fetch_opponents.py   # Stockfish → bin/
chess-harness opponents verify
```

First run creates `.chess_harness/models.json` from `config/models.json.example`.

Requirements: **Python 3.11+**. Node.js only for `python scripts/quality_gate.py` (TypeScript + ESLint).


| Variable            | Purpose                                                                  |
| ------------------- | ------------------------------------------------------------------------ |
| `STOCKFISH_PATH`    | Stockfish binary (default `bin/stockfish-windows-x86-64.exe` on Windows) |
| `CHESS_HARNESS_DIR` | Runtime data dir (default `.chess_harness/`, gitignored)                 |


Stockfish is GPL-3 — see `[NOTICE.md](NOTICE.md)`.

## Quick start (human operator)

```bash
chess-harness models inscribe my-agent --name "My Agent"
chess-harness serve --force
# http://localhost:8765
```

Give an agent `[AGENTS.md](AGENTS.md)` and let it play:

```bash
chess-harness new --model my-agent --opponent stockfish-handicap:noise17
chess-harness move <game_id> e2e4
```



## Opponents

Catalog: [`config/opponents.json`](config/opponents.json). Download binaries with `scripts/fetch_opponents.py`.

Opponents can be **`enabled: false`** to remove them from agent pairing and calibration without deleting ELO history (`chess-harness opponents disable <id>`).

| Family | Examples | Rating source |
|--------|----------|---------------|
| Stockfish anchors | `stockfish:0` … `stockfish:20` | Official UCI_Elo (fixed in calibration) |
| Stockfish harness | `stockfish-handicap:noise10`, `noise52`, … | Skill 0 + noise / depth / movetime |
| Inverse Stockfish | `inverse-sf:worst-d4`, `bottom5`, … | Full-strength eval, deliberately bad moves |
| MinimalChess harness | `minimalchess-0.2:noise15`, `:noise30` | Backup rungs when SF noise overlaps |
| Random mover | `random` | Calibrated floor (~60) |

**Truth for floaters:** calibrated ELO in `elo_calibration/results/merged_ratings.json`, not catalog labels. Gap audit: `python scripts/audit_ladder_gaps.py`.

Omit `--opponent` for an **ELO-weighted random** opponent matched to the agent's rating (eligible opponents only).

```bash
chess-harness opponents list
chess-harness opponents verify
```

Catalog ELO labels are **engine ratings**, not human FIDE ELO.

## Agent ELO

Inscribed models live in `.chess_harness/models.json` (created from `config/models.json.example`; starts at **500** ELO). Vision agents only — see [`AGENTS.md`](AGENTS.md).

```bash
chess-harness models list
chess-harness leaderboard
```



## Engine calibration (`elo_calibration/`)

Engine-vs-engine games to measure opponent strength. No agents, no board images.

- **Stockfish tiers** (`stockfish:N`) are fixed **anchors** at catalog UCI ELO.
- **Floaters** (harnesses, `inverse_sf`, tiny engines, `random`) start at **500** and update after each game (sliding K: 64 / 48 / 24).
- Results go to `elo_calibration/results/` (gitignored); best-known ratings merged into `merged_ratings.json`.

**Spectator UI** (`/calibration`): global pairing mode (default **floaters**), Start all / Stop all, per-engine parallel games, live ratings. Disabled opponents are never paired.

**CLI batch** (separate from UI — don't run both at once):

```bash
python elo_calibration/scripts/run_calibration.py --suite quick --play --workers 4
```

See `[elo_calibration/README.md](elo_calibration/README.md)` and `[docs/ladder-coverage-plan.md](docs/ladder-coverage-plan.md)`.

## Spectator

```bash
chess-harness serve
chess-harness serve stop
chess-harness serve --force
```


| Tab         | URL            | Purpose                       |
| ----------- | -------------- | ----------------------------- |
| Active      | `/`            | Live agent games              |
| Completed   | `/?tab=done`   | Finished games                |
| Calibration | `/calibration` | Continuous engine calibration |
| ELO Ladder  | `/leaderboard` | Agent + opponent ratings      |




## MCP (Cursor / IDE agents)

```bash
python -m chess_harness.mcp_server
```

Copy [`config/mcp.json.example`](config/mcp.json.example) to `.cursor/mcp.json` if you use Cursor.

Tools: `chess_list_models`, `chess_new_game`, `chess_get_board`, `chess_make_move`, `chess_status`, `chess_resign`, `chess_export_pgn`.

## CLI reference


| Command | Purpose |
| ----------------------------- | ----------------------- |
| `chess-harness new --model <id>` | Start game |
| `chess-harness move <id> <move>` | Agent move (UCI or SAN) |
| `chess-harness status` / `board` | Metadata / refresh PNG |
| `chess-harness pgn <id>` | Export after game ends |
| `chess-harness opponents list` | Catalog (enabled/disabled) |
| `chess-harness opponents disable/enable <id>` | Toggle opponent |
| `chess-harness harness reset --yes` | Wipe local data |
| `chess-harness game audit <id>` | Move audit log |


Workflows: `[scripts/run_agent_game.md](scripts/run_agent_game.md)`.

## Tests

```bash
cd python && pytest
```

Or from repo root: `python scripts/quality_gate.py` (full gate).

## License

- **[`docs/LICENSE.md`](docs/LICENSE.md)** — MIT for harness source code (Python, spectator UI, scripts).
- **[`NOTICE.md`](NOTICE.md)** — third-party **engine** licenses (Stockfish GPL, optional MinimalChess MIT). Binaries are downloaded, not shipped in git.

See also [`docs/README.md`](docs/README.md) for the full documentation map.