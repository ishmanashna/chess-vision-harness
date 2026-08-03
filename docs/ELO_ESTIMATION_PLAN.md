# Elo estimation bake-off and calibration UX

Improve the calibration / quality surface: clear naming, variance and reliability stats, unify activity labels, fix form-field warnings, and replace the single play-rating map with a small bake-off of ~5 Elo-estimation methods — then score games with the champion. Ladder Elo stays results-only forever.

Audited against live continuous data (~1100 samples): within-engine accuracy σ ≈ 15%, Pearson(accuracy, elo_before) ≈ 0.70, current map single-game residual MAE ≈ 220 / RMSE ≈ 290. Map knots reach ~1330 (not hard-capped at 1000); mid-engine “stuck under 1000” is fit/compression, not a clamp.

## Product decisions (locked)

1. **Ladder Elo unchanged** — Win/draw/loss only. Estimation code never writes `ratings.json` / `models.json` Elo.

2. **UI name: “Elo estimation”** — Replace “Play rating” in calibration, spectator `/g/`, and leaderboard. Tooltip / legend: not ladder Elo; move-quality estimate on the engine ladder scale. Internal JSON keys may migrate to `elo_estimation` with a short read-compat alias for `play_rating` where stored.

3. **Single-game scoring never sees the player’s Elo** — `analyse_game` + estimator maps use moves/evals only (accuracy, ACPL, blunders, optional ply weights). Training Y = calibration `elo_before` for floaters only; that Y is never an input when scoring an AvE/AvA/AvH side.

4. **No hard 1000 ceiling on estimation** — `WIN_PROB_CP_CAP` (1000) only clamps centipawns inside the accuracy win% curve. Estimation output follows the fitted map. If high-Elo engines compress, fix via better features / estimators — do not clamp.

5. **Five estimators; show all numbers; human picks later** — Fit all on the same continuous floater samples (`games_played >= 101`, anchors never). Persist every map plus holdout metrics. **Calibration UI must show all five Elo estimations per engine**, each with:
   - **Mean estimate** (average of per-sample map predictions for that estimator), and separately the **miss vs calibrated Elo** (`mean − calibrated Elo`) so you can see closeness.
   - **Consistency Δ / ±** = how much a **single-game** estimate typically differs from that engine’s **mean estimate for the same estimator** (population stdev of per-sample predictions; null if &lt;2 samples). This is **not** “miss vs Elo” — it answers stability at low sample size.
   Operator runs more calibration, reads closeness + consistency, then tells which id to keep. Until then, default scoring uses baseline **A** for harness games.

   Locked candidates:
   - **A `q_composite`** — current `Q = acc − α·nacpl − β·blunder_rate` → monotone PWL map (baseline default for harness until you choose).
   - **B `accuracy_only`** — accuracy → PWL map.
   - **C `acpl_only`** — normalized ACPL (inverted / negated) → PWL map.
   - **D `midgame_focus`** — composite Q with long quiet endgame plies down-weighted (material-low + low win% volatility).
   - **E `trimmed_moves`** — composite Q after dropping the most extreme win%-swing plies (robust to one-move outliers).

6. **Variance on calibration table** — Per engine from quality samples: mean ± stddev for Accuracy and Elo estimation (estimation from per-sample map predictions or stored sample fields). Status panel: global single-game reliability (Pearson, MAE, RMSE of champion vs `elo_before`).

7. **Eligibility uses cumulative Elo games** — Keep `games_played >= 101` after `record_game`. Engines that already had hundreds of continuous Elo games were eligible the moment move capture shipped; they do **not** need 100 new games. Do not reset counters. Historical games **without** stored moves cannot become samples — forward-only unless moves exist.

8. **Persist moves for future backfill** — Continuous `games.jsonl` records include `uci_moves` (capped if needed). CLI can rebuild samples from records that already have moves. No fake samples from Elo alone.

9. **Activity label** — If `continuous`: always show live count, e.g. `2 live` or `0 live` (never bare `running` vs `N games live` split). Idle non-continuous stays `—` / disabled.

10. **Form fields** — Parallel inputs (and buttons if needed) get stable `id`/`name` so browsers stop warning.

11. **No vision leak** — Estimation stays operator/spectator; not on agent `/api/v1` game payloads.

## Scope

In scope: calibration UX; rename; variance / reliability stats; move persistence + sample rebuild CLI; estimator framework + five fits + champion wiring; spectator/leaderboard label update; tests; light PRODUCT/DEPLOY wording.

Out of scope: Changing ladder Elo; Chess.com proprietary estimators; mid-game live estimation; agent-facing quality fields; inventing samples for move-less history.

## Architecture (imprinted)

```text
Continuous game
  worker → result + uci_moves
  record Elo (unchanged)
  append games.jsonl WITH uci_moves
  if floater games_played>=101 → analyse → samples (features per estimator)
  fit all maps under lock → pick champion by holdout MAE

Harness finish
  analyse_game(moves only) → side metrics
  elo_estimation = champion_map(features)   # never reads player Elo
  persist state + results upsert
```

## Phases

### Phase 1 — Calibration UX hygiene

Form `id`/`name` on parallel inputs. Unify activity to live counts. Rename Play rating → Elo estimation on calibration page copy/columns/tooltips (status panel title too).

**Done when:** No form-field console warning from calibration controls; activity never shows bare `running`; UI says Elo estimation.

**Verify:** Eyeball `/calibration`; focused assert on rendered HTML strings if cheap.

### Phase 2 — Variance + reliability on status API

Extend `play_rating_status_summary` (or rename module surface carefully) with per-engine `accuracy_std`, `elo_estimation_std` (and means). Add global `reliability` block (n, pearson, mae, rmse) for the active map/champion. Calibration table shows `55.5% ± 14` style; panel shows single-game reliability.

**Done when:** Status JSON + table expose stddevs; panel states that one game is noisy when RMSE is large.

**Verify:** Unit test on synthetic samples.

### Phase 3 — Persist moves + sample rebuild

Write `uci_moves` into continuous `games.jsonl`. CLI `chess-harness rebuild-estimation-samples` (name flexible) re-reads records with moves, re-appends eligible samples (idempotent strategy: rewrite samples file from games with moves, or skip duplicate game_index). Confirm eligibility uses ladder `games_played` (cumulative). Document: no backfill without moves.

**Done when:** New games store moves; rebuild CLI regenerates samples from those records; engines with games≥101 keep contributing without a fresh 100-game wait.

**Verify:** Integration test with temp suite dir; Elo `ratings.json` untouched by rebuild.

### Phase 4 — Estimator framework + five fits + calibration compare UI

Module(s) for estimator id → feature → fit PWL → holdout metrics. Fit A–E; write `elo_estimation_maps.json` with per-id knots + metrics. **No auto-champion.**

Status API + `/calibration` must expose **all five** per-engine estimates from per-sample map predictions: **mean estimate**, **consistency Δ** (stdev of single-game estimates around that mean), and **elo_miss** (mean − calibrated Elo). Compact five-way compare columns. Panel: per-estimator holdout MAE.

Default harness scoring still A until you explicitly set a champion (Phase 5 CLI) — this phase is about **seeing the numbers**.

**Done when:** All five fit; calibration table/panel shows five estimates + deltas vs calibrated Elo; no automatic winner.

**Verify:** Synthetic fit test; status JSON has five estimates + deltas; HTML shows them.

### Phase 5 — Optional champion wire + rename polish

CLI to set/clear champion after you decide. `quality_finish` / spectator / leaderboard use chosen id (else A). Rename leftover “Play rating” strings. Read-compat for old fields.

**Done when:** You can set champion once; until then baseline A; UI labels consistent.

**Verify:** Fallback A + explicit champion tests.

### Phase 6 — Hardening

Trim dead “play rating” user copy; PRODUCT one-liner; guard tests that scoring path does not read player Elo; line limits. Optional: calibration compare strip (per-estimator mean) only if Phase 5 left a clean hook — otherwise skip.

**Done when:** Focused tests green; PRODUCT mentions Elo estimation beside Elo.

**Verify:** Focused pytest only.

## Order

1 → 2 → 3 → 4 → 5 → 6  

One implementation subagent per phase. Phase 1–2 may be sequential; 3 can follow 2; 4 before 5.

## Estimated duration

- Phase 1 — Calibration UX hygiene: 1–2 agent-hours
- Phase 2 — Variance + reliability: 2–3 agent-hours
- Phase 3 — Persist moves + rebuild CLI: 2–4 agent-hours
- Phase 4 — Estimator framework + five fits: 4–6 agent-hours
- Phase 5 — Champion scoring + rename everywhere: 2–4 agent-hours
- Phase 6 — Hardening: 1–2 agent-hours
