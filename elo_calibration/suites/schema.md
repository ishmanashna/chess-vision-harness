# Suite YAML fields

## `defaults`

| Field | Meaning |
|-------|---------|
| `movetime_ms` | UCI movetime per move (unless `depth` set) |
| `max_plies` | Draw adjudication after N half-moves |
| `k_factor` | ELO update sensitivity (default 32) |
| `initial_elo_non_stockfish` | Starting rating for Patricia, MinimalChess, etc. (default **500**) |

Stockfish tiers (`stockfish:0`–`20`) always start at their **catalog UCI ELO** and stay fixed (anchors).

**Stockfish handicaps** (`stockfish-handicap:*`, type `stockfish_harness`) use UCI skill 0 plus a play harness (`depth`, `movetime_ms`, `random_move_pct`). They start at **500** and are calibrated like Patricia — their catalog `elo` is only a matching hint.

## `pairs`

```yaml
pairs:
  - white: patricia:800
    black: stockfish:0
    games: 20
    colors: alternate   # swap colors each game
    white_harness:      # optional per-side overrides
      movetime_ms: 150
    black_harness:
      depth: 8
      random_move_pct: 0.05
```

`white_harness` / `black_harness` are mainly for weakening or tuning **Stockfish** reference runs (`depth`, `random_move_pct`, `movetime_ms`).

## `round_robin`

```yaml
round_robin:
  opponents: [patricia:500, patricia:800, patricia:1000]
  games_per_pair: 40
  colors: alternate
```

## Rating model

After **each game**, floating engines get standard ELO deltas. Stockfish anchors do not move.

Example: `patricia:800` (starts 500) beats `stockfish:0` (fixed 1320) → Patricia gains ELO; Stockfish stays 1320.

Results: `results/<suite>/ratings.json`, `games.jsonl`, `summary.md`.

## CLI

```bash
# Plan only (no engines) — default
python elo_calibration/scripts/run_calibration.py --suite quick

# Run games and update ratings
python elo_calibration/scripts/run_calibration.py --suite quick --play

# Fresh 500 ELO seeds
python elo_calibration/scripts/run_calibration.py --suite quick --reset-ratings --play
```
