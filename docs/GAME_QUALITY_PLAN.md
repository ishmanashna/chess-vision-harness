# Post-game accuracy and calibrated play rating

Add two **display** metrics on finished games, separate from ladder Elo: **Accuracy %** (open, Lichess-inspired) and **Play rating** (approx strength-from-moves, on the same numeric scale as our engine ladder). Show both on spectator game info; aggregate per agent on the leaderboard **beside** (never instead of) results-only Elo.

Audited against the live codebase. Blockers locked below: calibration workers today return no moves; map samples must be persisted; map refits must be serialized; `results.jsonl` needs a quality upsert; eligibility/aggregation counters must be explicit.

## Product decisions (locked)

1. **Ladder Elo stays results-only** — Agent Elo and engine calibration Elo remain win/draw/loss only. Quality code never calls `ELOLadder.record_game`, `CalibrationLadder.record_game`, or writes Elo into `models.json` / `ratings.json`. Play rating is a **different column** that uses Elo-like numbers for readability only.

2. **Two metrics** — Accuracy % = move quality (0–100). Play rating = “this move quality looks like ~X on our engine ladder,” from a map fitted only on eligible calibration engines. Agents and humans are **scored** with the same analyser + map; they never contribute training samples.

3. **Accuracy formula (open)** — Lichess-inspired: eval → win% → per-move accuracy → game accuracy (volatility-weighted mean averaged with harmonic mean). Document constants. No opening book in v1. Short games mark `quality_thin: true`.

4. **Play-rating map (not Elo)** — Code/docs say **play-rating map**; file `elo_calibration/results/continuous/play_rating_map.json` (avoid “curve/Elo” in UI labels).
   - `Q = accuracy − α·normalized_acpl − β·blunder_rate` (fixed small α, β).
   - Monotone map `Q → play_rating` (piecewise-linear or isotonic).
   - **Training games = Elo-calibration engine–engine games** (v1: **continuous `/calibration` only**; batch suites deferred until the same move-capture + sample append exists).
   - **Y target** = that side’s calibration ladder **`elo_before`** for the game just recorded (floaters). Never agent Elo, never catalog labels for floaters.
   - **Fit-eligible:** floating engines only, with `games_played >= 101` **after** `record_game` on the continuous ladder (strict `> 100`). Stockfish **anchors never contribute samples** (`games_played` never increments for them). Agent provisional display stays at 100 games — do not conflate thresholds.
   - **Samples file:** append to `play_rating_samples.jsonl` (`engine_id`, `game_index`, `q`, `calibration_elo_before`, `accuracy`, `acpl`, `blunder_rate`, `ts`). Refit reads samples; writes `play_rating_map.json`. Whitelist both for commit next to `continuous/ratings.json`.
   - **Cold start:** expose play rating only when `sample_count >= 30` (and `fitted_at` present); else `play_rating: null`. Accuracy still shows when computed.
   - **Refit locking:** serialize/debounce map writes under a file lock (same spirit as continuous ratings save). Never concurrent multi-thread map writes (`MAX_PARALLEL_GAMES` can be large).

5. **Calibration move capture (required for Phase 4)** — Workers today return only `{white_id, black_id, result}`. Extend return with `uci_moves` (or PGN). Parent runs quality analysis **immediately** after each finished calibration game. Do **not** rely on replaying historical `games.jsonl` (no moves). Historical map samples accumulate **forward** only.

6. **When to analyse harness games** — Real results only (not `*`). Single `schedule_game_quality(game_id)` after PGN write from every scored finish: AvE `_finish_game` / resign-with-result, AvA after `_auto_save_pgn`, AvH after `_auto_save_pgn`. Background thread; use `GameManager.game_lock` for state patches.

7. **Persistence** — `state.json` quality fields + `ResultsManager.upsert_quality_fields(game_id, model_id, fields)` under a `results.jsonl` file lock (append-only is insufficient). AvA: `white_*` / `black_*` in state; **each** of the two results rows patched by `(game_id, model_name)`. AvE/AvH: `agent_accuracy` / `agent_play_rating` convenience keys. Meta: `quality_depth`, `quality_thin`, `quality_at`.

8. **Spectator `/g/{id}`** — Separate labeled rows **Accuracy** and **Play rating** per side — never parenthesize play rating next to Elo like `Name (1234)`. Poll until `quality_at` or give up. Missing → `—`. Phase 3 ships Accuracy first; Play rating row may show `—` with tooltip “not ladder Elo” until map exists.

9. **Leaderboard** — Beside Elo: mean Accuracy, mean Play rating, `quality_games`.
   - **`quality_games`:** count of finished real-result quality rows per `model_id` with non-null accuracy; **include AvH**; exclude `*`; AvA dedupe `(game_id, model_id)`. Do **not** reuse `count_by_model()` (that excludes AvH and counts `*`).
   - Aggregation source: quality fields on upserted `results.jsonl` rows (and/or finished `state.json` — pick results upsert as canonical for snapshot).
   - Extend `build_snapshot`, `/api/v1/leaderboard`, CLI leaderboard, and `/leaderboard/` table. Pages publish via snapshot; local serve should match columns.

10. **CPU** — `QUALITY_STOCKFISH_DEPTH` env (default 8), shared intent with spectator eval; persist `quality_depth` on each analysis.

11. **No vision leak** — Spectator/operator only; no agent `/api/v1` quality fields.

## Scope

In scope: analysis; harness finish hooks; continuous calibration move capture + samples + locked map fit; spectator + leaderboard; upsert results quality; tests; light docs; agent/human PGN backfill CLI.

Out of scope: Changing Elo; batch calibration map fitting (deferred); backfilling map from old `games.jsonl`; Chess.com proprietary estimator; mid-game accuracy; agent API quality.

## Architecture (imprinted)

```text
Continuous calibration game          Harness game (AvE/AvA/AvH)
  worker returns uci_moves             PGN on disk
  record_game (Elo unchanged path)     schedule_game_quality
  analyse sides                        analyse sides
  if floater games_played>=101           map(Q) if map ready
    append play_rating_samples.jsonl     upsert results + state
  debounced locked refit → map.json
```

**Modules:** `game_quality.py`, `play_rating.py`, thin `quality_finish.py` orchestrator; continuous worker payload + parent hook; `ResultsManager.upsert_quality_fields`.

## Phases

### Phase 1 — Analysis core

`analyse_game(pgn_or_moves, depth) →` per-side accuracy / acpl / blunder_rate. Depth from `QUALITY_STOCKFISH_DEPTH` (default 8). Unit tests on synthetic PGNs; document constants.

**Done when:** Pure replay+score works in tests.

**Verify:** Blunder game scores lower; depth recorded.

### Phase 2 — Harness finish + persistence

`schedule_game_quality` on all real-result finish paths; background analyse; patch state; `upsert_quality_fields` for AvE/AvA/AvH (AvA both rows). No play_rating yet unless map file already present (usually null).

**Done when:** Finished harness games get accuracy fields; `*` skipped; Elo files unchanged.

**Verify:** Stub analyser integration test; AvA dual-row upsert test.

### Phase 3 — Spectator Accuracy UI

Labeled Accuracy rows on `/g/{id}`; Play rating row present but `—` until later; never Elo-style parentheses; poll until `quality_at`.

**Done when:** Finished games show Accuracy when analysed.

**Verify:** Eyeball + key asserts.

### Phase 4 — Continuous calibration: moves, samples, map

Extend worker `uci_moves`; parent analyses; append eligible samples; debounced locked refit; write `play_rating_map.json` + whitelist samples/map in gitignore allow-list. Assert quality path never mutates `ratings.json` Elo logic.

**Done when:** Playing continuous games with eligible floaters grows samples and a map with `sample_count` / `fitted_at`.

**Verify:** Synthetic fit; Elo ratings byte-stable when only quality runs; no concurrent corrupt map in a short parallel smoke.

### Phase 5 — Apply play rating on harness games

After accuracy, `play_rating = map(Q)` when `sample_count >= 30`; else null. Same for AvH human/agent sides on spectator.

**Done when:** Agent games get play_rating once map is warm.

**Verify:** Fixture map test.

### Phase 6 — Leaderboard + snapshot

Mean accuracy / mean play rating / `quality_games` on snapshot, live API, CLI, and `/leaderboard/` UI. Document AvH inclusion in quality columns vs Elo games.

**Done when:** Snapshot JSON + page show columns for agents with quality data.

**Verify:** Snapshot unit test; eyeball.

### Phase 7 — Backfill + hardening

CLI backfill **agent/human `game.pgn` only** (not historical calibration). Docs: Elo ≠ play rating. Tests: quality never imports/writes Elo record paths. Line-limit on new modules.

**Done when:** Backfill one finished game; focused tests green; PRODUCT/README one-liners.

**Verify:** Focused pytest; manual finish → `/g/` → leaderboard.

## Order

1 → 2 → 3 → 4 → 5 → 6 → 7  

One implementation subagent per phase.

## Estimated duration

- Phase 1 — Analysis core: 3–5 agent-hours
- Phase 2 — Finish hook + upsert persistence: 3–5 agent-hours
- Phase 3 — Spectator Accuracy UI: 1–2 agent-hours
- Phase 4 — Calibration moves + samples + map: 4–6 agent-hours
- Phase 5 — Apply play rating: 1–2 agent-hours
- Phase 6 — Leaderboard + snapshot: 2–4 agent-hours
- Phase 7 — Backfill + hardening: 2–3 agent-hours
