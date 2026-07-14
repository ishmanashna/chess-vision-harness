# Ladder coverage plan (1300 → −600)

Status: **in progress**  
Last updated: 2026-07-14  
Supersedes [`archive/ladder-improvement-plan.md`](archive/ladder-improvement-plan.md) for opponent catalog work.

**Not a product roadmap item** — this is the active maintainer mission for opponent calibration. Future product work: [`roadmap/`](roadmap/README.md).

### Progress snapshot (2026-07-14)

| Area | Status |
|------|--------|
| `inverse_sf` modes + abyss / worst / exclude-top1 rungs | **Done** |
| Overlap prune (blitz blob, duplicate depth rungs) | **Mostly done** |
| Sliding K 64/48/24 | **Done** |
| 38 opponents with calibrated ELO, adjacent gaps ≤100 | **Done** (among rated rungs) |
| Full **1300 → −600** span with rungs at each ~100 ELO step | **Not done** — rated band today is ~44–1224 |
| Sub-random / **negative ELO** rungs | **Not done** — weakest calibrated ~44 (`worst-d10`) |
| Engine cache / unified SF subprocess per worker | **Not done** |
| Success criteria checklist below | **Open** |

---

## Mission

Build a **Stockfish-only** calibration ladder where **no two adjacent rungs are more than ~100 ELO apart** from **1300 down to −600**, including rungs **weaker than random**.

| Anchor | Role |
|--------|------|
| `stockfish:0` @ **1320** | Fixed top anchor (`type: stockfish`) |
| `random` @ **≈ 60** (calibrated) | Floor reference — harnesses must calibrate below this |

Everything between is a **floater** (`stockfish_harness`, `inverse_sf`) whose catalog `elo` is a hint only; calibrated ELO is truth.

**Removed from catalog:** Patricia, Toledo (binaries + fetch). **Optional backup:** MinimalChess harness rungs. Use `scripts/fix_ladder_catalog.py` / `scripts/prune_ladder_catalog.py`.

---

## Spacing rule

Target rungs every **~100 ELO** (±25 tolerance after calibration):

```
1300  1200  1100  1000   900   800   700   600   500   400
 300   200   100     0  −100  −200  −300  −400  −500  −600
```

**21 nominal points → 20 intervals → ~20 active opponents** in the mission band (plus anchors and `random`).

After calibration, any interval **> 100 ELO** between sorted floaters is a **gap** and gets a new opponent. Any pair **< 50 ELO apart** is **overlap** — disable the slower/redundant one.

---

## What overnight calibration proved (2026-07-13)

Fixed pairing vs `stockfish:0` collapsed most harnesses into a **1230–1380 blob**. Only noise + `random` spread below ~1100.

| Cal ELO | Opponent | Verdict |
|--------:|----------|---------|
| 1334 | `depth10`, `reference` | Overlap — disable |
| 1327–1377 | `blitz200`–`blitz800`, `depth16` | Overlap — disable |
| 1292–1305 | `blitz50`, `blitz100`, `depth12` | Overlap — disable |
| 1277 | `minimalchess-0.2` (uncapped) | Overlap — disable or harness |
| 1232–1254 | `depth6`, `depth8`, `patricia:1000` | Overlap — disable |
| 1083–1144 | `patricia:500`, `noise5`, `noise10` | Partial spread |
| 864–976 | `noise12`, `noise15`, `depth4-noise10` | Partial spread |
| 664 | `noise20` | Useful |
| 417 | `noise25` | Useful |
| −429 | `random` | Floor |

**Lessons:**

1. **Movetime / depth caps on Stockfish skill-0 do not weaken it enough** for the 900–1300 band.
2. **`random_move_pct` is the only harness lever that reliably weakens SF** in the 400–1100 band today.
3. **Noise tops out at ~417 ELO** before the cliff to `random` (−429) — a **~850 ELO hole** with no rungs from ~400 down to ~0, and nothing in **0 → −200**.
4. Patricia UCI labels do not predict calibrated strength.

---

## Phase 1 — Prune (disable, do not delete)

Set `"enabled": false` on opponents that overlap the blob or sit outside 1300→−600. Preserve IDs and calibration history.

### Disable — high overlap (calibrated 1230+)

| ID | Cal ELO |
|----|--------:|
| `stockfish-handicap:blitz50` | 1292 |
| `stockfish-handicap:blitz100` | 1294 |
| `stockfish-handicap:blitz200` | 1352 |
| `stockfish-handicap:blitz350` | 1327 |
| `stockfish-handicap:blitz500` | 1348 |
| `stockfish-handicap:blitz800` | 1377 |
| `stockfish-handicap:depth6` | 1232 |
| `stockfish-handicap:depth8` | 1254 |
| `stockfish-handicap:depth10` | 1334 |
| `stockfish-handicap:depth12` | 1305 |
| `stockfish-handicap:depth14` | 1299 |
| `stockfish-handicap:depth16` | 1355 |
| `stockfish-handicap:depth18` | 1342 |
| `stockfish-handicap:reference` | 1334 |
| `minimalchess-0.2` (uncapped) | 1277 |

### Disable — outside mission band

| ID | Cal ELO | Reason |
|----|--------:|--------|
| `minimalchess-0.3` | 1799 | Above 1300 mission |
| `toledo` | 1602 | Above 1300 mission |
| `patricia:800` | 1173 | Overlaps cluster; UCI label wrong |
| `patricia:1000` | 1238 | Overlaps cluster |
| `patricia:1200` | 1313 | Overlaps cluster |

### Keep active (starting set)

| ID | Cal ELO | Notes |
|----|--------:|-------|
| `stockfish:0` | 1320 | Anchor |
| `random` | −429 | Floor reference |
| `stockfish-handicap:noise5` | 1144 | Re-evaluate after upper rungs exist |
| `stockfish-handicap:noise10` | 1046 | |
| `stockfish-handicap:noise12` | 976 | |
| `stockfish-handicap:noise15` | 864 | |
| `stockfish-handicap:noise20` | 664 | |
| `stockfish-handicap:noise25` | 417 | |
| `stockfish-handicap:depth4` | 1179 | Re-tune or replace (see Phase 3) |
| `stockfish-handicap:depth4-noise10` | 872 | |
| `patricia:500` | 1083 | Keep one Patricia; disable if redundant after Phase 3 |

---

## Phase 2 — Target grid vs current coverage

Sorted by **target** ELO. `—` = no opponent within 100 ELO; `~` = existing but needs re-tune.

| Target | Nearest today | Gap | Action |
|-------:|---------------|-----|--------|
| 1300 | `stockfish:0` ✓ | — | Anchor |
| 1200 | cluster @ 1230+ | **~120** | New harness (noise 3–4% or `exclude_top1`) |
| 1100 | `patricia:500` @ 1083 | ~20 | OK; may shift |
| 1000 | `noise10` @ 1046 | ~50 | OK |
| 900 | `noise12` @ 976 | ~80 | OK |
| 800 | `noise15` @ 864 | **~60** | `noise17` or `noise18` if interval widens |
| 700 | — | **~140** | New: `noise22`–`noise28` between noise20/25 |
| 600 | `noise20` @ 664 | ~60 | OK |
| 500 | — | **~160** | New: `noise30`–`noise32` |
| 400 | `noise25` @ 417 | ~20 | OK |
| 300 | — | **~120** | New: `inverse_sf` variant |
| 200 | — | **~220** | New: `inverse_sf` variant |
| 100 | — | **~320** | New: `inverse_sf` variant |
| 0 | — | **~420** | New: `inverse_sf` variant |
| −100 | — | **~330** | New: `inverse_sf` variant |
| −200 | — | **~230** | New: `inverse_sf` variant |
| −300 | — | **~130** | New: `inverse_sf` variant |
| −400 | — | **~30** | Near `random`; `inverse_sf` or accept random as proxy |
| −500 | — | — | New: `inverse_sf` variant (worse than random) |
| −600 | — | — | New: `inverse_sf` variant (worse than random) |

**Priority:** fill **0 → −200** and **300 → 700** first — largest holes.

---

## Phase 3 — Stockfish noise harnesses (400 → 1300)

Extend `stockfish_harness` entries. All use `skill_level: 0`, `uci_elo: 1320`, `movetime_ms: 50` unless calibration shows otherwise.

### Upper band (1200–1300)

Movetime/depth failed; use **light noise** to step down from anchor:

| Proposed ID | `random_move_pct` | Target |
|-------------|------------------:|-------:|
| `stockfish-handicap:noise3` | 0.03 | ~1250 |
| `stockfish-handicap:noise4` | 0.04 | ~1220 |
| `stockfish-handicap:noise6` | 0.06 | ~1180 |

### Mid band (700–1100)

Interpolate between existing noise10/12/15/20:

| Proposed ID | `random_move_pct` | Target |
|-------------|------------------:|-------:|
| `stockfish-handicap:noise17` | 0.17 | ~820 |
| `stockfish-handicap:noise22` | 0.22 | ~720 |
| `stockfish-handicap:noise28` | 0.28 | ~620 |
| `stockfish-handicap:noise32` | 0.32 | ~520 |
| `stockfish-handicap:noise36` | 0.36 | ~460 |

### Lower band (400–500)

| Proposed ID | `random_move_pct` | Target |
|-------------|------------------:|-------:|
| `stockfish-handicap:noise30` | 0.30 | ~480 |
| `stockfish-handicap:noise38` | 0.38 | ~420 |

**Retune existing:** `depth4` and `depth4-noise10` — try `depth: 1–2`, `movetime_ms: 10–20` in probe games; disable if they still calibrate > 1100.

**Probe before bulk calibration:** 20 games each vs `noise25` and `random` to bracket strength (`scripts/match_opponents.py`).

---

## Phase 4 — `inverse_sf` opponents (400 → −600)

Sub-400 spacing cannot be done with `random_move_pct` alone — high noise ≈ random (−429), not graduated steps through **0, −100, −200**.

Use a new opponent type: **`inverse_sf`** — Stockfish evaluates legal moves, then plays a **deliberately bad** move by a defined rule. Strength is tuned by **which bad move** and **search depth**, not by mixing with random (which collapses to noise).

### Implementation sketch

New `type: "inverse_sf"` in `opponents.json`:

```json
{
  "id": "inverse-sf:worst-d10",
  "type": "inverse_sf",
  "elo": 0,
  "rating_source": "inverse_sf",
  "inverse": {
    "mode": "worst",
    "depth": 10,
    "movetime_ms": 100
  }
}
```

New handler in `src/chess_harness/engine.py` (and `elo_calibration/calibration/engine_player.py` path):

1. `engine.analyse(board, Limit(depth=D))` with MultiPV or per-move eval.
2. Rank legal moves by SF score (white-centric).
3. Apply `mode` (below).
4. Return chosen move.

### `inverse` modes (variations)

All modes are **structurally different from `random_move_pct`** — they always use SF eval to pick *which* bad move, not whether to play randomly.

| Mode | Rule | Expected strength |
|------|------|-------------------|
| `exclude_top1` | Uniform among legal moves **except** SF best | Weakest “structured” blunder; ~−50 to +100 |
| `exclude_top2` | Exclude 2 best, uniform rest | ~−100 to 0 |
| `exclude_top3` | Exclude 3 best, uniform rest | ~−150 to −50 |
| `second_worst` | Play move ranked **2nd worst** by eval | ~0 to −100 |
| `third_worst` | Play 3rd worst | ~+50 to −50 |
| `worst` | Play single worst move by eval | ~−200 to −400 |
| `bottom3` | Uniform among 3 worst moves | ~−150 to −300 |
| `bottom5` | Uniform among 5 worst moves | ~−100 to −250 |
| `bottom_half` | Uniform among worse half of legal moves | ~−50 to −150 |
| `worst_depth4` | `worst` at depth 4 (noisier eval) | ~−100 to −300 |
| `worst_depth6` | `worst` at depth 6 | ~−150 to −350 |
| `worst_depth12` | `worst` at depth 12 | ~−300 to −500 |
| `worst_depth16` | `worst` at depth 16 | ~−400 to −600 |

Exact ELO is unknown until calibration — modes are listed strongest → weakest within the inverse family.

### Proposed catalog entries for 300 → −600 band

Initial guess at catalog `elo` (calibration will correct):

| ID | Mode | depth | Target |
|----|------|------:|-------:|
| `inverse-sf:exclude-top1` | `exclude_top1` | 10 | ~300 |
| `inverse-sf:exclude-top2` | `exclude_top2` | 10 | ~200 |
| `inverse-sf:second-worst` | `second_worst` | 10 | ~100 |
| `inverse-sf:exclude-top3` | `exclude_top3` | 10 | ~0 |
| `inverse-sf:bottom-half` | `bottom_half` | 10 | ~−100 |
| `inverse-sf:bottom5` | `bottom5` | 10 | ~−200 |
| `inverse-sf:worst-d8` | `worst` | 8 | ~−300 |
| `inverse-sf:worst-d10` | `worst` | 10 | ~−400 |
| `inverse-sf:worst-d12` | `worst` | 12 | ~−500 |
| `inverse-sf:worst-d14` | `worst` | 14 | ~−600 |

**0 → −200 coverage:** `exclude-top3`, `bottom-half`, `bottom5`, `second-worst` — four modes stepping through that band; add/remove after probe games.

**Below random (−430):** `worst` at depth ≥ 12 should lose more than random to weak opponents; calibrate down to −600.

### Rejected approaches

| Idea | Why rejected |
|------|----------------|
| `blunder_mix` (X% random + Y% SF) | Equivalent to `noise` harness; no independent spacing |
| `random_capture` / `random_check` | Not eval-guided; poor spacing control |
| High `random_move_pct` (> 45%) | Converges to `random`; no rungs between 400 and −430 |

---

## Phase 5 — MinimalChess harness (optional gap filler)

Add `uci_harness` type (same `harness` dict as `stockfish_harness`) for `minimalchess-0.2` **only where SF noise cannot place a rung** after probe games. Not a calibration-speed preference — use when a harness is needed and MC happens to land on a missing target.

Example entries (enable only if probes show distinct ELO):

| ID | Harness | Role |
|----|---------|------|
| `minimalchess-0.2:noise15` | 15% noise | Backup ~850 if `noise17` fails |
| `minimalchess-0.2:noise30` | 30% noise | Backup ~500 if SF noise30 overlaps |

---

## Phase 6 — Engine spawn optimization

**Finding:** Stockfish is **not** spawned per move. It is spawned **once per side per game** (and on timeout retry). Each calibration worker game creates two `EnginePlayer` instances → two subprocess boots (~0.5–1.3 s each) → released at game end.

| When | Behavior |
|------|----------|
| Within a game | Same `OpponentEngineManager` subprocess for all plies |
| Opponent ID change | New spawn (even `stockfish-handicap:blitz50` → `noise20` = new process, same binary) |
| Calibration pool | `ProcessPoolExecutor`; each worker cold-starts engines per game |

### Changes (no change to move loop semantics)

1. **Worker-scoped engine cache** — module-level `dict[opponent_id → OpponentEngineManager]` in `calibration/worker.py` / `engine_player.py`; reuse across games in the same worker process.
2. **Unified Stockfish subprocess per worker** — one SF process per worker; switch harness via `configure_opponent_strength` + harness override when opponent is `stockfish` or `stockfish_harness` (different catalog IDs, same binary).
3. **Warm start on `start_all`** — optional: pre-spawn one SF per worker before game loop.

**Expected gain:** ~15–25% wall time on SF-heavy calibration (spawn ≈ 1 s vs game ≈ 8–10 s).

---

## Phase 7 — Calibration protocol

1. **Pairing:** `floaters` mode (not fixed-vs-`stockfish:0`) so weak engines play each other and spread.
2. **K-factor:** sliding 64 / 48 / 24 (already implemented).
3. **New opponent acceptance:** after ~50 games, keep iff calibrated ELO is **> 50 ELO** from nearest neighbor.
4. **Overlap cull:** if two active opponents within **50 ELO**, disable the slower one (benchmark: [`archive/opponent-benchmark.json`](archive/opponent-benchmark.json)).
5. **Gap audit:** script or ladder UI highlight any interval **> 100 ELO** in 1300→−600; file issue per gap.
6. **Re-merge:** `rebuild_merged_ratings_file()` after catalog changes; do not reset history.

---

## Implementation checklist

| # | Task | Files | Effort |
|---|------|-------|--------|
| 1 | Disable Phase 1 prune list | `opponents.json` | S |
| 2 | Add noise3–6, noise17–38 harness entries | `opponents.json` | S |
| 3 | Implement `inverse_sf` type + modes | `engine.py`, `opponents.py`, `engine_player.py` | M |
| 4 | Add Phase 4 inverse catalog entries | `opponents.json` | S |
| 5 | Probe script batch (20 games × new ID) | `scripts/match_opponents.py` or new | S |
| 6 | `uci_harness` for minimalchess (if needed) | `engine.py`, `opponents.json` | S |
| 7 | Worker engine cache | `calibration/worker.py`, `engine_player.py` | M |
| 8 | Unified SF subprocess per worker | `engine.py`, `engine_player.py` | M |
| 9 | Ladder gap audit in UI or script | `ladder_display.py` or `scripts/audit_ladder_gaps.py` | S |
| 10 | Run floaters calibration overnight; gap audit | — | run |

---

## Success criteria

- [ ] Every ELO interval in **1300 → −600** has at least one active opponent within **100 ELO** of each boundary.
- [ ] **0 → −200** has ≥ 3 distinct calibrated rungs (not counting `random`).
- [ ] No two active opponents within **50 ELO** unless intentionally paired (document exception).
- [ ] Sub-400 rungs use **`inverse_sf` only** (no high-noise harness duplicates).
- [ ] Pruned opponents disabled but history preserved.
- [ ] Engine cache reduces mean game setup time measurably in benchmark rerun.

---

## References

- Calibrated ratings: `elo_calibration/results/merged_ratings.json`
- Speed benchmark: [`archive/opponent-benchmark.json`](archive/opponent-benchmark.json)
- Harness play path: `src/chess_harness/engine.py` (`play_opponent_move`)
- Calibration game loop: `elo_calibration/calibration/resilient_game.py`
- Prior work: [`archive/ladder-improvement-plan.md`](archive/ladder-improvement-plan.md) (Phases 0–4, K-factor, UI)
