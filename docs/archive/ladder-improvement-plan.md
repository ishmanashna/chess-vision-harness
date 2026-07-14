# Ladder improvement plan

> **Archived (2026-07-13).** Current ladder work lives in [`../ladder-coverage-plan.md`](../ladder-coverage-plan.md). Kept for historical context only.

Status: **superseded**  
Last updated: 2026-07-12  
Reviewed against live calibration data and codebase (`opponents.json`, `calibration_view.py`, `continuous_calibration.py`, `elo.py`, `elo_calibration/calibration/ratings.py`).

## Goals

1. Better **low-ELO** ladder coverage (noise / weak harnesses).
2. Better **high-ELO** coverage between strongest floaters and `stockfish:0` (1320 anchor).
3. **Benchmark** opponent move speed; compare Stockfish vs tiny engines.
4. A **sanity-check floater** near calibrated 1320 (distinct from the fixed anchor).
5. **Disable** opponents/agents from play without deleting ELO history.
6. **Faster rating convergence** for new agents and engines (shared math, not 100 games to settle).

---

## Current architecture (short)

| Layer | File | Behavior |
|-------|------|----------|
| Agent ELO | `src/chess_harness/elo.py` | K=32 fixed; stored in `models.json` |
| Engine calibration | `elo_calibration/calibration/ratings.py` | K=32; floaters start 500; `stockfish:N` anchors fixed |
| Agent pairing ELO | `calibration_view.ladder_elo_for_opponent()` | Calibrated when `games > 0`, else 500 |
| Continuous pairing | `continuous_calibration.pick_similar_opponent()` | Similar calibrated ELO; includes Stockfish anchors as opponents |

**Anchors:** `type: "stockfish"` only — never update in calibration.  
**Floaters:** everything else, including `stockfish_harness` and `random`.

---

## What calibration data actually shows (continuous suite)

Sorted floaters (approximate, from `elo_calibration/results/merged_ratings.json`):

| Calibrated ELO | Opponent |
|----------------|----------|
| -348 | `random` |
| 139 | `stockfish-handicap:noise20` |
| 284 | `stockfish-handicap:noise10` |
| 470 | `stockfish-handicap:depth4` |
| 496 | `patricia:500` |
| 515–652 | other patricia / harness / minimalchess-0.2 cluster |
| 874 | `toledo` |
| 1064 | `minimalchess-0.3` |
| **1320** | `stockfish:0` (anchor, fixed) |

**Corrections vs intuition:**

- Patricia UCI tiers **do not** space the ladder; all calibrate ~500–650 at 100 ms/move.
- `blitz200` and `depth14` landed at **652 / 756**, not in the 1064→1320 gap.
- Catalog CCRL / `elo` fields are hints only; calibrated values differ.

---

## Negative ELO (e.g. `random` at -348)

**Recommendation: do not floor negative calibrated ELO by default.**

Negative values are awkward in UI but **valid** in the Elo formula and **honest**: `random` loses almost every game vs the floating pool, so the rating system drags it below zero. Flooring would:

- Hide a real calibration outcome
- Desync agent pairing ELO from engine calibration ELO
- Paper over a design choice (whether `random` should be a calibration participant at all)

**Alternatives if negatives cause practical problems:**

- Exclude `random` from **agent** opponent selection (still calibrate engine-vs-engine).
- Show raw ELO in calibration UI and a separate “pairing ELO” only if we ever need one (not planned now).
- Retire `random` via `enabled: false` instead of clamping.

---

## Phase 0 — Engine speed benchmark

**Effort:** S–M | **Priority:** 1

Add `scripts/benchmark_opponents.py` using the same path as real games (`OpponentEngineManager` + `play_opponent_move`).

Per playable opponent:

- Median ms/move (startpos + optional FENs)
- UCI spawn / init cost
- Estimated games/hour at max plies
- Flag slow opponents (calibration wall-time risk)

**Acceptance:** JSON + markdown table; Stockfish vs harness vs Patricia vs tiny engines vs `random` compared.

**Tests:** Smoke on CI with `random` + one harness; full run optional with binaries.

---

## Phase 1 — Disable opponents / agents (retire without deleting ELO)

**Effort:** M | **Priority:** 2

Add optional `"enabled": false` to `opponents.json` and `models.json` (default `true`).

**CLI:** `play.py opponents disable|enable <id>`, `play.py models disable|enable <id>`

**Filter when disabled:**

- `select_by_elo`, `pick_similar_opponent`, agent `new_game`, MCP playable list, calibration Start, tournaments

**Preserve:**

- `merge_calibration_ratings()` rows
- `results.jsonl` / `games.jsonl`
- Agent ELO in `models.json`

**Distinct from** `models uninscribe` (destructive delete).

**UI:** Ladder shows “disabled” / “retired”; Start disabled.

**Tests:** Unit tests at each filter site.

---

## Phase 2 — Sanity reference floater ~1320

**Effort:** S | **Priority:** 3

Add catalog entry:

```json
{
  "id": "stockfish-handicap:reference",
  "type": "stockfish_harness",
  "uci_elo": 1320,
  "skill_level": 0,
  "harness": { "movetime_ms": 1000 }
}
```

| Role | ID | Updates? | Purpose |
|------|-----|----------|---------|
| Anchor | `stockfish:0` | No | Fixed 1320 for calibration math |
| Sanity floater | `stockfish-handicap:reference` | Yes | Should **converge** near 1320; detects drift |

Tune depth cap if it overshoots. Phase 0 benchmark estimates cost at 1000 ms/move.

**Acceptance:** After ≥50 games, calibrated ELO within ±80 of 1320 (or document expected band).

---

## Phase 3 — Ladder coverage harnesses (data-driven)

**Effort:** M | **Priority:** 4 (after Phase 0)

### Low range

Gaps between `random` (-348) → `noise20` (139) → `noise10` (284) → `depth4` (470) → `patricia:500` (496).

Candidate harnesses (validate with short YAML suites before keeping):

| ID | Harness |
|----|---------|
| `stockfish-handicap:noise25` | 25% noise, 100 ms |
| `stockfish-handicap:noise15` | 15% noise, 100 ms |
| `stockfish-handicap:noise12` | 12% noise, 100 ms |
| `stockfish-handicap:depth4-noise10` | depth 4 + 10% noise |

Do **not** add Patricia tiers for spacing.

### High range

Gap: strongest floaters ~874–1064 → anchor 1320.

Candidates (previous `blitz200` / `depth14` were too weak):

| ID | Harness |
|----|---------|
| `stockfish-handicap:blitz350` | 350 ms |
| `stockfish-handicap:blitz500` | 500 ms |
| `stockfish-handicap:blitz800` | 800 ms |
| `stockfish-handicap:depth16` | depth 16, 200 ms |
| `stockfish-handicap:depth18` | depth 18, 300 ms |

Run ~30-game mini-suites per candidate; **disable** entries that miss target or duplicate an existing floater.

**Acceptance:** No gap >150 ELO between adjacent floaters from 0–1300 (excluding anchors).

---

## Phase 4 — Faster rating convergence (agents + engines)

**Effort:** M (sliding K) → L (Glicko-2) | **Priority:** 5 (last)

Defer until opponent catalog stabilizes.

### 4a — Sliding K (recommended first)

New shared module `src/chess_harness/rating_math.py`:

- K=40 for games &lt;20
- K=32 for games 20–99
- K=16 for games ≥100

Wire into **both** `ELOLadder` and `CalibrationLadder`. Keep 500-scale; do not remap to 1500.

### 4b — Glicko-2 (optional)

Rating + RD (+ volatility). High RD for new entities → large early updates; provisional until ~15–20 games (RD below threshold). Anchors: RD=0.

**Touchpoints:** `elo.py`, `ratings.py`, `models.json`, `continuous/ratings.json`, replay via `process_results_file()`.

**Risk:** Historical leaderboard shifts after replay — document `rebuild-elo` behavior.

---

## Cross-cutting fixes

| Issue | Fix |
|-------|-----|
| `merge_calibration_ratings()` sets `anchor: false` for stockfish tiers | Set `anchor: true` when `type == "stockfish"` |
| Uncalibrated harness shows as 500* in agent pairing | Down-weight or exclude until `games >= N` (optional) |
| Patricia labels imply UCI_Elo = ladder ELO | Update `rating_note` in `opponents.json` |

---

## Implementation order

```
Phase 0  Benchmark
Phase 1  Disable/enable (no ELO floor)
Phase 2  Reference harness
Phase 3  Harness additions (empirical)
Phase 4  Sliding K → optional Glicko-2
```

---

## File map

| Phase | Primary files |
|-------|----------------|
| 0 | `scripts/benchmark_opponents.py`, `engine.py` |
| 1 | `opponents.py`, `models.py`, `calibration_view.py`, `continuous_calibration.py`, `commands.py`, `ladder_display.py` |
| 2 | `opponents.json`, `elo_calibration/README.md` |
| 3 | `opponents.json`, `elo_calibration/suites/*.yaml` |
| 4 | `rating_math.py`, `elo.py`, `elo_calibration/calibration/ratings.py` |

---

## References

- Glicko-2: [glicko.net](https://glicko.net/glicko/glicko2.pdf) — RD-driven provisional ratings (~15–20 games to stabilize).
- USCF sliding K — simpler alternative, less state.
