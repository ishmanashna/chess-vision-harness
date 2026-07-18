# ELO calibration (operator-only)

Engine-vs-engine ladder. **No LLM agents**, no board images, no MCP.

## What it does

1. **Schedules** games from YAML suites (`suites/quick.yaml`, etc.).
2. **Stockfish tiers are anchors** — `stockfish:0` stays at 1320, `stockfish:5` at 1788, etc.
3. **Everything else starts at 500** — harness rungs, inverse_sf, MinimalChess, `random`, etc. Catalog labels are hints; calibration discovers strength by playing games.
4. **After each game**, floating engines get ELO gains/losses (sliding K: 64 / 48 / 24). You see ratings evolve game-by-game in `games.jsonl` and stabilize over many games.
5. **Stockfish harness** — per-game `black_harness` / `white_harness` can set `depth`, `movetime_ms`, `random_move_pct` to test weakened reference opponents (see `suites/stockfish-harness.yaml`).

Output is **advisory** for updating `opponents.json` labels after review.

## Setup

```bash
pip install -e ".[dev]"
set PYTHONPATH=src
```

## Commands

```bash
# Plan 50 games, show initial rating table — NO engines started
python elo_calibration/scripts/run_calibration.py --suite quick

# Actually play and update ratings
python elo_calibration/scripts/run_calibration.py --suite quick --play

# Wipe saved ratings and re-seed non-Stockfish at 500
python elo_calibration/scripts/run_calibration.py --suite quick --reset-ratings --play
```

Reports: `elo_calibration/results/<suite>/summary.md`, `ratings.json`, `games.jsonl`.

**Note:** `elo_calibration/results/` is gitignored except **`merged_ratings.json`**, **`continuous/ratings.json`**, and **`continuous/games.jsonl`** — commit those to restore calibration after clone. Per-suite `quick/` / `ladder/` outputs stay local.

**Spectator continuous calibration** (`chess-harness serve` → `/calibration`): per-engine Start/Stop, parallel games, writes to `results/continuous/`. Do not run the batch CLI and spectator calibration at the same time.

See `suites/schema.md` for YAML format.
