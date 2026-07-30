# Accuracy→Elo map, display, localhost speed, leaderboard sync

Replace the multi-estimator Elo bake-off with one static accuracy→Elo lookup built from calibrated engines. Show that estimate everywhere games and ladders are shown — **especially for agents**. Fix localhost navigation and slowness. Leaderboard is **live whenever the game server is up**; the snapshot file is **offline fallback only**.

## Product decisions (locked)

1. **Icebox the bake-off** — Stop fitting and showing estimators A–F, holdout MAE panel, Avg ±, champion picker, and per-engine multi-column estimation cells. Remove that work from `/api/calibration/status` so status stays light. Sample collection for accuracy may remain if needed to build the table; continuous auto-refit of many maps goes away.

2. **One static accuracy→Elo table** — Built only from calibrated floater engines we already trust: each engine’s mean move accuracy (from quality samples) paired with its calibrated ladder Elo. Fit a simple monotone lookup (piecewise-linear knots or equivalent). Persist under `elo_calibration/results/` (e.g. `accuracy_elo_map.json`). **Never** write ladder Elo. Scoring a side uses **accuracy only → table lookup**; never the player’s Elo.

3. **Map rebuild when the operator asks** — No background refit on every continuous game. Calibration keeps one button: **Rebuild accuracy→Elo table**. That is the only manual control for the map. Until pressed, the previous file stays in force.

4. **Display name: “Est. Elo (play)”** — Not ladder Elo. Show it **especially for agents**:
   - Leaderboard next to Elo (agent rows are the primary surface).
   - Game state / spectator **always**, both players, AvE / AvA / AvH.
   - **Agent-visible** surfaces too: include in `/api/v1` game status/finish (and any brief/summary that already shows Elo) so agents and their operators see Est. Elo (play) like ladder Elo. This is a post-move-quality rating estimate, not a board/FEN leak — allowed on the agent API. Still never expose raw engine eval traces or legal-move lists.

5. **Harness finish scoring** — After `analyse_game`, set each side’s estimate from that side’s accuracy through the static table. Replace the old Q-composite / play_rating_map default for this metric. Rename toward `elo_estimation` / `est_elo_play` with a short read-compat alias for `play_rating` / `*_play_rating` where stored.

6. **Calibration tab on localhost only, as a normal tab** — Do **not** probe `/api/calibration/status` to inject the link. On loopback hostnames (`127.0.0.1`, `localhost`), insert Calibration in the nav immediately. On the deployed Pages host, never show it. Pages continues to 404 `/calibration*`.

7. **Leaderboard is live when the server is up** — No “write snapshot” button. No “commit to update Pages Elo” as the normal path.
   - **Online** (game server reachable): UI loads leaderboard from a **live** origin API (same shape as today’s snapshot JSON). Localhost serve builds it on the fly from models + merged calibration. Pages, when Online, uses the proxied live endpoint via `GAME_ORIGIN` — same numbers as the PC.
   - **Sleeping / server down**: UI falls back to committed `public-site/data/leaderboard.json` only. That file exists so the public site still shows a ladder when the PC is off.
   - Refreshing the offline snapshot file is automatic maintenance when the server is running (e.g. after ratings change / on a light schedule / on serve lifecycle) — **not** an operator chore and **not** a calibration button. Human git commit of that file remains optional backup for offline visitors; it is not how you “publish” live Elos.

8. **Ladder Elo isolation unchanged** — Win/draw/loss only for `ratings.json` / `models.json`.

## Scope

In scope: icebox bake-off UI/status cost; static accuracy→Elo map + rebuild-map button only; finish-path scoring; spectator + **agent API** + leaderboard display; localhost nav without status probe; live leaderboard when online + snapshot as offline-only fallback with automatic file refresh while serve runs; slim status/perf; focused tests; DEPLOY wording for live-vs-offline.

Out of scope: Changing how ladder Elo is computed; Calibration on Pages; manual snapshot/publish buttons; resurrecting A–F bake-off; Chess.com-style estimators; exposing Stockfish eval / legal moves to agents.

## Architecture (imprinted)

```text
Calibrated floaters (mean accuracy, calibrated Elo)
  → operator Rebuild accuracy→Elo table (only map button)
  → accuracy_elo_map.json (static until next rebuild)

Harness game finishes
  → analyse_game (moves only) → accuracy per side
  → est = lookup(accuracy_elo_map, accuracy)
  → state + results + /api/v1 (agents see Est. Elo (play))
  → spectator shows both sides

While serve is up
  → GET live leaderboard API (agents + calibrated engines)
  → public-site JS: Online → live API; Sleeping → /data/leaderboard.json
  → optionally rewrite snapshot file in background for offline visitors

Localhost
  → nav: hostname ⇒ Calibration (no status fetch)
  → calibration status: light (no multi-estimator)

Pages
  → no Calibration tab; /calibration 404
  → Online + GAME_ORIGIN → live leaderboard via proxy
  → Sleeping → last snapshot file only
```

## Phases

### Phase 1 — Localhost nav + kill status probe (speed)

Remove `ensureCalibrationNav`’s fetch of `/api/calibration/status` from `public-site/js/common.js`. On loopback hosts only, insert the Calibration link synchronously after Leaderboard. On Pages hostname, never insert.

**Done when:** On `http://127.0.0.1:8765/`, Calibration is in the nav on first paint with no status request. On the deployed site, Calibration never appears.

**Verify:** Load Home on localhost; no `/api/calibration/status` from `common.js` for nav.

### Phase 2 — Slim calibration status (speed)

Strip multi-estimator columns, holdout/Avg±/champion panel, and heavy per-estimator sample scans from the hot status path. Rating table + continuous activity + cheap accuracy means only. Keep short TTL cache. Calibration UI: no A–F cells.

**Done when:** Idle status feels normal with no continuous games; bake-off UI gone.

**Verify:** Time idle status; eyeball `/calibration`.

### Phase 3 — Static accuracy→Elo map + Rebuild button

Build-from-calibrated-engines → monotone PWL → `accuracy_elo_map.json`. Calibration toolbar: **Rebuild accuracy→Elo table** only. Lookup helper for finish scoring. Disable continuous auto `fit_all_estimators`.

**Done when:** Button rebuilds map; lookup works; continuous play does not rewrite the map.

**Verify:** Unit tests on synthetic pairs; one localhost rebuild.

### Phase 4 — Show Est. Elo (play) everywhere agents matter

Wire finish scoring to the static map. Spectator always shows both sides. **`/api/v1` status/finish includes the estimate** for agent sides (and opponent when applicable), same visibility class as Elo — not stripped. Leaderboard column next to Elo uses agent mean Est. Elo (play). AvE / AvA / AvH covered.

**Done when:** Agents and humans see Est. Elo (play) on ladder and in game APIs/UI; label clear it is not ladder Elo.

**Verify:** Finished game payload on `/api/v1` includes the field; leaderboard column present; spectator both sides.

### Phase 5 — Live leaderboard when online; snapshot offline-only

Add a live leaderboard endpoint on the origin (same JSON shape as today’s snapshot). Public-site JS: if edge-health / Online, fetch that live endpoint (on Pages through the existing proxy); if Sleeping, keep `/data/leaderboard.json`. Origin may also serve live data for `/data/leaderboard.json` when hit directly on localhost. While serve runs, periodically or on rating changes, rewrite the on-disk snapshot so offline visitors are not ancient — **no UI button**. Remove any plan/UI for manual “write snapshot to publish.”

**Done when:** Calibration Elo changes appear on localhost and on Pages **while the PC is Online**, without git. Sleeping site still shows the last snapshot. No snapshot button on calibration.

**Verify:** Online Pages/localhost show new engine Elo after calibration without commit; stop serve → Sleeping still loads snapshot.

### Phase 6 — Cleanup + docs

Remove dead bake-off paths. Rename “Play rating” → “Est. Elo (play)”. DEPLOY: live ladder when Online; snapshot only for Sleeping; Calibration localhost nav rule; one Rebuild map button.

**Done when:** Docs match; no dual publish path; no bake-off UI.

**Verify:** DEPLOY readable; UI grep clean.

## Estimated duration

- Phase 1 — Localhost nav + kill status probe: 0.5–1 agent-hours
- Phase 2 — Slim calibration status: 1.5–3 agent-hours
- Phase 3 — Static accuracy→Elo map + Rebuild button: 2–4 agent-hours
- Phase 4 — Est. Elo for agents + all modes: 2–3.5 agent-hours
- Phase 5 — Live online leaderboard + offline snapshot only: 2.5–4 agent-hours
- Phase 6 — Cleanup + docs: 1–2 agent-hours
