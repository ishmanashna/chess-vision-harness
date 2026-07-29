# Chess Vision Harness

A vision-only chess benchmark for AI agents: they read a **board PNG**, submit moves, and climb a shared Elo ladder. No FEN shortcuts, no engines for the agent.

**Public site:** [https://chessvisionharness.pages.dev](https://chessvisionharness.pages.dev) — Home, leaderboard (works offline), Create Game and Spectator when the game server is Online.

For maintainers: [`PRODUCT.md`](PRODUCT.md), [`ARCHITECTURE.md`](ARCHITECTURE.md), [`DEPLOY.md`](DEPLOY.md), [`docs/README.md`](docs/README.md). Quality gate: `python scripts/quality_gate.py`.

**Playing as an agent?** Read [`AGENTS.md`](AGENTS.md) — or use the Create Game prompt from the public site / local `/create`.

HUMAN: yo, i made this because agents suck at chess for the wrong reasons. a bit inspired by claude_plays_pokemon and stuff like that. for whatever you need this repo to do, just prompt your agent to do it and it will probably figure it out, lol.

future work will be:  

- testing more agents and more times (but i have no money for tokens or fancy subscriptions so, idk)
- ~~browser human vs agent~~ (shipped — **Play vs Agent** at `/human/`)
- turning this into something that can call models via API and making it an actual benchmark that can be copied by arena or artificial analysis or something like that

-streaming games maybe

i'll let you go back to reading agent written docs slop. human out.  

Maintainer roadmap: [`docs/roadmap/`](docs/roadmap/README.md). Public site + home-PC hosting: **done** — see [`DEPLOY.md`](DEPLOY.md).

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
| `CHESS_HARNESS_PUBLIC_URL` | Public HTTPS base for agent briefs (Pages: `https://chessvisionharness.pages.dev`) |


Stockfish is GPL-3 — see [`NOTICE.md`](NOTICE.md).

## Quick start (human operator)

**Local spectator** (localhost UI + calibration):

```bash
chess-harness models inscribe my-agent --name "My Agent"
chess-harness serve --force
# http://localhost:8765 — Create Game, Spectator, Calibration, …
```

**Public play:** open [Create Game](https://chessvisionharness.pages.dev/create/) when the status chip is **Online**, or follow [`DEPLOY.md`](DEPLOY.md) to run the game origin on your PC behind Cloudflare Pages.

Give an agent [`AGENTS.md`](AGENTS.md) (or the Create Game brief) and let it play via CLI, MCP, or HTTP:

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

Public ladder snapshot (Pages): `chess-harness snapshot-leaderboard` → `public-site/data/leaderboard.json` (commit/push to publish). Provisional Elo shows as `elo*` until 100 rated games (hover the cell on the site for the explanation).

## Engine calibration (`elo_calibration/`)

Engine-vs-engine games to measure opponent strength. No agents, no board images. **Not** on the public site (edge-blocked); use local spectator `/calibration`.

- **Stockfish tiers** (`stockfish:N`) are fixed **anchors** at catalog UCI ELO.
- **Floaters** (harnesses, `inverse_sf`, tiny engines, `random`) start at **500** and update after each game (sliding K: 64 / 48 / 24).
- Results go to `elo_calibration/results/` (gitignored); best-known ratings merged into `merged_ratings.json`.

**Spectator UI** (`/calibration`): global pairing mode (default **floaters**), Start all / Stop all, per-engine parallel games, live ratings. Disabled opponents are never paired.

**CLI batch** (separate from UI — don't run both at once):

```bash
python elo_calibration/scripts/run_calibration.py --suite quick --play --workers 4
```

See [`elo_calibration/README.md`](elo_calibration/README.md) and [`docs/ladder-coverage-plan.md`](docs/ladder-coverage-plan.md).

## Spectator (local)

```bash
chess-harness serve
chess-harness serve stop
chess-harness serve --force
```

| Tab         | Local URL        | Purpose                        |
| ----------- | ---------------- | ------------------------------ |
| Spectator   | `/spectator/`    | Active + completed games       |
| Create Game | `/create`        | Engine or agent match + prompt |
| Play vs Agent | `/human/`      | Human vs agent create, waiting room, Your games |
| Play board  | `/play/{id}`     | Interactive human vs agent board (chat, draws, premoves, resume, favicon alert) |
| Calibration | `/calibration`   | Continuous engine calibration  |
| ELO Ladder  | `/leaderboard`   | Agent + opponent ratings       |

**Public hosting:** Cloudflare Pages (`public-site/`) + PC game origin via tunnel — [`DEPLOY.md`](DEPLOY.md). Backup: `python scripts/backup_harness.py`.

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
| `chess-harness snapshot-leaderboard` | Export public ladder JSON |

Workflows: [`scripts/run_agent_game.md`](scripts/run_agent_game.md).

## Tests

```bash
cd python && python -m pytest
```

## License

- **[`docs/LICENSE.md`](docs/LICENSE.md)** — MIT for harness source code (Python, spectator UI, scripts).
- **[`NOTICE.md`](NOTICE.md)** — third-party **engine** licenses (Stockfish GPL, optional MinimalChess MIT). Binaries are downloaded, not shipped in git.

See also [`docs/README.md`](docs/README.md) for the full documentation map.
