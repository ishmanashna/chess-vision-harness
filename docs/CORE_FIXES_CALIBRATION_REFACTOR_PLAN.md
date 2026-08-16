# Core watch/leaderboard fixes and calibration refactor

Public puzzle watch, the unified leaderboard, and the calibration operator page are failing as core product paths. Fix those first. Then refactor calibration into clear layers without losing floating engine Elo, samples, or the accuracy map.

## Scope

- Make puzzle/identify watch pages load when opened from Spectator (and similar links).
- Remove the identify review legend text.
- Make identify activity visible on the unified leaderboard; stop HTML/JS column drift and stale cached JS.
- Unblock `/calibration`, then refactor how engine Elo, samples, the accuracy map, and the worker relate.

## Out of scope

- Changing agent ladder Elo or puzzle Glicko-2 formulas.
- Deleting `continuous/games.jsonl`, samples, ratings, or `accuracy_elo_map.json` (preserve; repair corrupt tails only).
- Tunnel / Pages hosting redesign beyond watch-shell id injection.
- Rewriting batch calibration CLI suites (keep; clarify vs continuous).

## Verified causes (from investigation)

**Puzzle “No puzzle attempt id…”**  
The error fires only when the browser path is bare `/p` or `/p/` (no id). Fresh Pages and FastAPI GET `/p/{valid_id}` return 200 today. Remaining failures: no `data-attempt-id` in the static shell (JS depends entirely on the URL); `watchHref` can return a truthy empty `/p/` if `watch_url` is bad; browsers may still follow **cached 308** redirects from before the shell fix.

**Identify “not on leaderboard”**  
Live API merge is correct (e.g. Composer has identify finishes). The Id att column was removed by an earlier plan, so attempt activity is not shown on the unified table. Sleeping/inline snapshots are often all zeros; live upgrade can leave stale zeros if JS is cached or upgrade fails.

**Two empty leaderboard columns**  
New HTML (10 headers) mixed with cached old `common.js` (12 cells). Repo HEAD is aligned; missing `?v=` cache busting lets the mismatch return after deploys.

**Calibration stuck**  
Running serve still served old code that 500s on corrupt `games.jsonl` tail lines when worker recent_games is empty (`/status` 500, `/status/live` 200). Workspace already skips bad lines — needs serve restart. Separately: full status spends ~8–9s scanning all play-rating samples; display GETs still RPC the worker for data that lives on disk; unlocked JSONL append/trim can corrupt the log again.

## Product / architecture decisions (locked)

1. Inject `data-attempt-id` / `data-attempt-id` into watch shell HTML on **local serve and Pages**. Path parsing is fallback only.
2. Unified leaderboard columns: 6 game columns + **PUZZLES** + **Pz** (`solves/attempts`) + **Id** (`full/attempts`) + **% pieces** + **% boards** (11 total). Cache-bust leaderboard/watch JS.
3. Calibration layers (never fold into agent Elo):
   - **A** Calibrated engine Elo — `elo_calibration/results/*/ratings.json` via `merge_calibration_ratings`
   - **B** Quality samples — `continuous/play_rating_samples.jsonl`
   - **C** Accuracy→Elo map — `accuracy_elo_map.json` (Performance)
   - **D** Agent ladder — `CHESS_HARNESS_DIR` models/results (unchanged)
4. Worker runs continuous games only. Serve builds Elo/map/quality **from files**; live activity may overlay from the worker status snapshot file — not enrich RPC on every GET.
5. `merged_ratings.json` is publish-only (keep writing; do not treat as read SSOT). Preserve `accuracy_elo_map.json` and continuous ratings/samples.

---

## Phase 0 — Public-site core fixes

**Goal:** Spectator puzzle/identify links load; identify shows on the ladder; columns align; legend gone.

**Work**

- Inject attempt id onto `<body>` in shell HTML:
  - FastAPI: `/p/{attempt_id}`, `/i/{attempt_id}` (and play if analogous) via `watch_shell_response` / callers.
  - Pages: after `fetchWatchShellHtml`, rewrite HTML with id from the path.
- Prefer `dataset.attemptId` in puzzle/identify watch JS; keep pathname parse as fallback.
- Fix `watchHref`: reject `/p/`, `/i/`, or any `watch_url` without a real id segment; build from `attempt_id` instead.
- Remove identify review legend string/UI (“Green = exact…”); keep square markers.
- Leaderboard: add **Id** ratio from identify leaderboard `full` / `attempts` (expose integer `full` on merged snapshot if missing); keep Pz ratio and % columns; make `leaderboardColCount`, headers, row cells, and loading colspan all **11**.
- Cache-bust `/js/common.js` and watch modules with `?v=` on leaderboard and watch pages.
- When Online, if live leaderboard upgrade fails, show a clear error rather than silently leaving Sleeping zeros for puzzle/identify cells.

**Done when**

- View-source of `/p/{id}` and `/i/{id}` includes `data-attempt-id="…"`.
- Bad/empty `watch_url` cannot produce a link to bare `/p/`.
- Online leaderboard shows Id / % values for agents with finished identify attempts in the live API.
- One agent row has exactly 11 `<td>` matching 11 `<th>` without hard-refresh tricks after deploy.
- Identify watch has no green/red legend caption.

**Verify**

- Local + Pages: open Spectator puzzle link; board loads.
- `GET /api/leaderboard/live` identify fields paint in the UI after upgrade.
- DevTools network: `common.js?v=…` requested.

---

## Phase 1 — Calibration immediate unblock

**Goal:** `/calibration` paints ratings and quality after a real serve restart; no 500 from corrupt JSONL; full status fits under the client timeout.

**Work**

- Restart path: document and perform `chess-harness serve --force` so Phase 2 `_recent_games_from_jsonl` is loaded; confirm `GET /api/calibration/status` → 200.
- Lock append + atomic trim for `continuous/games.jsonl` (and the same JSONL helpers used there); optional repair that drops non-JSON tail lines only.
- Precompute `continuous/engine_quality_summary.json` (or equivalent) on sample append (debounced); `play_rating_status_summary` reads aggregates, not 12k raw samples per request.
- Keep client timeout + errors on quality summary and ratings table; success must clear placeholders.

**Done when**

- Full status 200 with `rating_table` length matching calibratable engines when ratings exist.
- Corrupt tail lines do not 500.
- Full status cold path well under 12s (target &lt;2s cold, &lt;1s cached) at current sample volume.

**Verify**

- curl `/api/calibration/status` and `/status/live` codes and timings.
- Open `/calibration` — table and quality panel leave Loading / “No calibration data yet.”

---

## Phase 2 — Calibration read-path refactor

**Goal:** Display status does not need the worker process for Elo, samples, or the accuracy map.

**Work**

- Split assembly: file-based merge + rating table + quality aggregates + map warm flags on serve; live fields (activity, continuous, in-flight, recent_games) from worker status snapshot file or cheap health — not per-request enrich HTTP.
- Pure `enrich_rating_rows` equivalent over (table + snapshot).
- POST start/stop/pairing remain worker-backed.
- Module docstrings + operator docs (DEPLOY / home-pc): layers A–D; `merged_ratings.json` publish-only.
- Do not migrate or rewrite historical rating numbers; only change read/write wiring.

**Done when**

- Worker stopped → full status still returns rating_table + quality/map from disk with `calibration_worker_ok: false`.
- Worker running → activity fields populate; continuous start still works.
- Floating Elo from `continuous/ratings.json` unchanged aside from normal merge rules.

**Verify**

- Stop worker, hit full status 200 with table.
- Start worker, start one continuous engine, see activity on live/full.

---

## Phase 3 — Calibration clarity cleanup

**Goal:** Names and UI match the layered model; remove misleading dead ends.

**Work**

- API: rename `play_rating_map` → `accuracy_map` (temporary alias, remove by phase end).
- Stop writing legacy `play_rating_map.json` if still written; leave existing file on disk.
- `/calibration` copy: calibrated Elo vs Performance (map) vs agent ladder Elo.
- Drop iceboxed `elo_estimation` from any remaining UI hooks if present.

**Done when**

- Operator-facing labels match layers A–C.
- No remaining claim that `merged_ratings.json` is the runtime read SSOT in docs touched this phase.

**Verify**

- Read `/calibration` labels; grep operator docs updated in this phase for “merged” truth claims.

---

## Order

0 → 1 → 2 → 3. Sequential. Restart serve after Phase 0/1 code lands before claiming calibration fixed.

## Implementation notes for agents

- Read `PRODUCT.md` and `ARCHITECTURE.md` at session start.
- Do not treat this as cosmetic polish.
- Do not convert puzzle Glicko to Elo or fold calibration Elo into agent Elo.
- Do not wipe `elo_calibration/results/continuous/` or `accuracy_elo_map.json`.
- Do not run git or the full test suite; targeted tests only.
- One subagent per phase.

---

## Estimated duration

- Phase 0: 3–5 agent-hours
- Phase 1: 3–5 agent-hours
- Phase 2: 5–8 agent-hours
- Phase 3: 2–3 agent-hours
