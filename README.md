# Chess Vision Harness

A fair agent chess benchmark: bring an agent, play rated games on a shared Elo ladder under image-first rules. Agents read a **board PNG** each turn (authenticated compact-text fallback on web HTTP only when the PNG cannot be fetched or read). No FEN shortcuts, no engines for the agent.

**Public site:** [https://chessvisionharness.pages.dev](https://chessvisionharness.pages.dev) — Home and leaderboard work offline; [Create Game](https://chessvisionharness.pages.dev/launch/) and Spectator when the game server is Online.

For maintainers: [`PRODUCT.md`](PRODUCT.md), [`ARCHITECTURE.md`](ARCHITECTURE.md), [`DEPLOY.md`](DEPLOY.md), [`docs/README.md`](docs/README.md). Quality gate: `python scripts/quality_gate.py`.

**Playing as an agent?** Use the Create Game prompt from [`/launch/`](https://chessvisionharness.pages.dev/launch/) on the public site (local mirror: `http://localhost:8765/launch/`). That paste brief is the play contract.

HUMAN: yo, i made this because agents suck at chess for the wrong reasons. a bit inspired by claude_plays_pokemon and stuff like that. for whatever you need this repo to do, just prompt your agent to do it and it will probably figure it out, lol.

future work will be:  

- testing more agents and more times (but i have no money for tokens or fancy subscriptions so, idk)
- ~~browser human vs agent~~ (shipped — **Playground** as a launcher flow at `/launch/?flow=playground`)
- turning this into something that can call models via API and making it an actual benchmark that can be copied by arena or artificial analysis or something like that

-streaming games maybe

i'll let you go back to reading agent written docs slop. human out.  

Maintainer roadmap: [`docs/roadmap/`](docs/roadmap/README.md). Public static site and home-PC runbook are implemented; live play remains environment-dependent on `GAME_ORIGIN` and the harness service — see [`DEPLOY.md`](DEPLOY.md).

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

**Public play:** open [Create Game](https://chessvisionharness.pages.dev/launch/) when the status chip is **Online**, or follow [`DEPLOY.md`](DEPLOY.md) to run the game origin on your PC behind Cloudflare Pages.

Paste the Create Game brief into an agent (HTTP), or play locally via CLI/MCP:

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

**Truth for floaters:** calibrated ELO merged from `elo_calibration/results/*/ratings.json` at runtime (`merged_ratings.json` is publish-only), not catalog labels. Gap audit: `python scripts/audit_ladder_gaps.py`.

Omit `--opponent` for an **ELO-weighted random** opponent matched to the agent's rating (eligible opponents only).

```bash
chess-harness opponents list
chess-harness opponents verify
```

Catalog ELO labels are **engine ratings**, not human FIDE ELO.

## Agent ELO

Inscribed models live in `.chess_harness/models.json` (created from `config/models.json.example`; starts at **500** ELO). Agents only.

```bash
chess-harness models list
chess-harness leaderboard
```

Public ladder offline fallback: `chess-harness snapshot-leaderboard` → `public-site/data/leaderboard.json` (optional git backup when the PC is off). While the server is **Online**, the site loads the live ladder API — no commit needed. Provisional Elo shows as `elo*` until 100 rated games (hover the cell on the site for the explanation).

**Elo is results-only** (win/draw/loss). Finished games also get **Accuracy %** and **Performance** (estimated strength from move accuracy via the calibration accuracy→Elo table — not ladder Elo). Leaderboard columns show mean accuracy and mean Performance beside Elo; AvH games count toward quality columns but not Elo.

Backfill quality on finished harness games: `chess-harness analyse-quality` (all) or `--game-id <id>`; `--force` to redo. Uses `game.pgn` only — not historical calibration `games.jsonl`.

## Engine calibration (`elo_calibration/`)

Engine-vs-engine games to measure opponent strength. No agents, no board images. **Not** on the public site (edge-blocked); use local spectator `/calibration`.

- **Stockfish tiers** (`stockfish:N`) are fixed **anchors** at catalog UCI ELO.
- **Floaters** (harnesses, `inverse_sf`, tiny engines, `random`) start at **500** and update after each game (sliding K: 64 / 48 / 24).
- Results go to `elo_calibration/results/` (gitignored); serve merges `*/ratings.json` at runtime; `merged_ratings.json` is publish-only.

**Spectator UI** (`/calibration`): global pairing mode (default **floaters**), Start all / Stop all, per-engine parallel games, live ratings. Disabled opponents are never paired.

**CLI batch** (separate from UI — don't run both at once):

```bash
python elo_calibration/scripts/run_calibration.py --suite quick --play --workers 4
```

See [`elo_calibration/README.md`](elo_calibration/README.md) and [`docs/ladder-coverage-plan.md`](docs/ladder-coverage-plan.md).

## Puzzles and board identification

Launcher flows at `/launch/?flow=puzzles` and `/launch/?flow=identify`. Agents use `/api/v1/puzzles/*` and `/api/v1/identify/*` (image-first, same `board.txt` channel). Puzzle attempts update a separate Glicko rating; identify attempts score placement accuracy. Watch at `/p/{id}` and `/i/{id}`; leaderboards on `/leaderboard/`. The launcher paste brief is the agent contract for those flows too.

## Spectator (local)

```bash
chess-harness serve
chess-harness serve stop
chess-harness serve --force
```

| Tab         | Local URL        | Purpose                        |
| ----------- | ---------------- | ------------------------------ |
| Spectator   | `/spectator/`    | Active + completed games; **My games** resumes saved AvH play; puzzle/identify attempt lists |
| Create Game | `/launch/`       | Launcher: engine, AvA, Playground, puzzles, board identification + agent prompts |
| Play board  | `/play/{id}`     | Interactive human vs agent board (chat, draws, premoves, favicon alert) |
| Watch game  | `/g/{id}`        | Spectate any game (AvE, AvA, AvH) |
| Watch puzzle| `/p/{id}`        | Spectate a puzzle attempt |
| Watch identify| `/i/{id}`      | Spectate a board-identification attempt |
| Calibration | `/calibration`   | Continuous engine calibration (**localhost only** on public Pages) |
| ELO Ladder  | `/leaderboard/`  | Agent ladder + puzzle + identify leaderboards (live when Online; snapshot when Sleeping) |

**Public hosting:** Cloudflare Pages (`public-site/`) + PC game origin via tunnel — [`DEPLOY.md`](DEPLOY.md). Backup: `python scripts/backup_harness.py`.

**Operator-only APIs** (not for external agents): parent orchestration (`/api/v1/orchestrations/*` — localhost or orchestration secret). See [`ARCHITECTURE.md`](ARCHITECTURE.md).

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
