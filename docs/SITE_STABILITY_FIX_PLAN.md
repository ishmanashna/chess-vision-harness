# Site Stability & Snapshot Fix Plan

Status: implemented (P0–P8 complete, tests green)
Owner: agent session
Scope: web + localhost (same code, same fixes — unless stated otherwise)

## 0. Problem statement

- The web and localhost both show a stale leaderboard snapshot containing **2 models** while the harness registry has **9 inscribed models**.
- "Loading snapshot…" can stay on screen indefinitely on localhost; nothing ever times out. On localhost the origin is slower and the lag is very noticeable — the table stays empty for seconds.
- The status chip reports the server "down" intermittently.
- The calibration tab's anchor/engine performance ratings disagree with the leaderboard tab.
- The leaderboard tab has a useless puzzle-content section + table (both must be deleted).
- Puzzle attempt "moves" stays `0` for every failed/wrong-move attempt.
- Watch pages show a useless "white at bottom · a1 bottom-left" sub-label.
- Puzzle watch pages still don't deliver the requested spectator UX (chain history, auto-advance, rating deltas, current metrics) for attempts started before the last deploy.

## 1. Ground rules (non-negotiable)

1. **The snapshot is a fallback, not an optional feature.** It must always load instantly, in every environment, with zero server dependency. The UI must never render "snapshot unavailable".
2. **Snapshot data files are shipped artifacts**: `public-site/data/leaderboard.json` + `public-site/data/puzzles_leaderboard.json` are committed to the repo, served as static files by Pages, never generated on request by the origin. Only the operator export command (or the server's debounced background refresh) may rewrite them.
3. **Tests must never write into `public-site/data/` or `elo_calibration/results/`.** This is the recurring corruption bug: a pytest run overwrote the shipped snapshots with fixture models (cursor-auto, gemini-3.6-flash-high) and the calibration data files.
4. **One source of truth for performance ratings.** The calibration tab and the leaderboard tab must compute play ratings through the same function (`play_rating_status_summary`), from the same live samples. They cannot drift.

## 2. Root causes (verified)

| # | Symptom | Root cause | Evidence |
|---|---------|-----------|----------|
| 1 | Snapshot has 2 models | Shipped snapshot was generated before the registry reached 9 models; nobody re-exported it. Local copy was later overwritten by the test suite (fixture models). | `git show HEAD:public-site/data/leaderboard.json` = mimo/composer @ 23:06:27Z; `git status` shows both data files modified; `models list` = 9; fresh `export_public_snapshots()` = 9 agents |
| 2 | "Loading snapshot…" forever | Client fetches have **no timeout** (`fetchLeaderboardSnapshot` common.js:181, `mountTable` puzzle-leaderboards.js:168, home page `fetchLeaderboardSnapshot` common.js:475). Any slow/hung request keeps the initial row forever. | code: no AbortController on snapshot fetches |
| 3 | Server flapping to "down" | `edge-health` aborts after **3 s** (`edge-health.js` HEALTH_TIMEOUT_MS) over a tunnel; every page re-probes; a single slow probe = offline. | code; live probe currently online |
| 4 | Calibration ≠ leaderboard ratings | Calibration status payload and snapshot export compute play ratings via different paths; calibration data files were also stomped by tests. | `calibration_rebuild_play_rating_map` spectator.py:827 vs `play_rating_status_summary` snapshot_leaderboard.py:44 |
| 5 | Failed puzzle attempts show moves = 0 | `apply_submission` appends to `submitted_moves` only on **correct** moves (puzzle_attempt.py:113). `_fail` records the wrong move only in `first_wrong_move` (puzzle_attempt.py:137-140), never in `submitted_moves`. | code read |
| 6 | Useless puzzle-content section | `[data-puzzle-content-leaderboard]` section on leaderboard/index.html + mount at puzzle-leaderboards.js:201-212; no other consumer. | code read |
| 7 | "White at bottom" sub-label | Hardcoded `<span class="sub">` in puzzle_observer.py:260 and identify_observer.py:236. | code read |
| 8 | Watch page improvements missing for old attempts | Attempts started before the last deploy have no `key_fingerprint` → `by_key` chain empty → no history / auto-follow / rating deltas; also the local origin may still run the pre-deploy build (needs restart). | code read; deploy 8c3bedc shipped chain UI |

## 3. Phases

### Phase 0 — Immediate hotfix: ship the real snapshot (unblocks everything)

1. Working tree already contains a freshly regenerated snapshot (`export_public_snapshots()` run at 23:48:43Z, **9 agents**).
2. Commit `public-site/data/leaderboard.json` + `puzzles_leaderboard.json` (real data) and push — the deploy workflow runs automatically.
3. Verify live: `GET /api/leaderboard/live` and `GET /data/leaderboard.json` show 9 agents.
4. Acceptance: web leaderboard shows all 9 inscribed models.

### Phase 1 — Tests can never corrupt shipped data

1. In pytest conftest (or the snapshot/calibration fixtures), force `export_public_snapshots`, `export_leaderboard_snapshot`, and every calibration writer to redirect their output into a per-session temp dir (monkeypatch `default_output_path`, `default_puzzle_leaderboard_path`, calibration root).
2. Add a guard test: running the full snapshot-export path with the test registry writes **only** under `tmp_path`.
3. Acceptance: `pytest` leaves `public-site/data/` and `elo_calibration/results/` byte-identical to HEAD; `git status` stays clean after a full suite run.

### Phase 2 — Snapshot must always load, instantly

1. Add a shared `fetchJSON(url, { timeoutMs })` helper (AbortController) in `common.js`; use it for **all** leaderboard/snapshot fetches (common.js:181, 195, 451, 475; puzzle-leaderboards.js:158, 168; identify/puzzle watch metric fetches).
2. Snapshot fetch timeout: **10 s**, then paint the snapshot anyway from an inline copy if available; otherwise keep retrying in the background (poll every 15 s) — never a permanent "unavailable" state, never a forever-Loading row.
3. Ship a documented inline fallback: embed `leaderboard.json` content into `index.html`/`leaderboard/index.html` (small JSON blob) so the table paints from the page itself if the fetch fails — the snapshot is then mathematically always present.
4. Acceptance: with the origin killed and even the `/data/*.json` fetch failing (dev scenario), the leaderboard still renders the last snapshot from the inline copy; live site never shows "Loading snapshot…" beyond one paint cycle.

### Phase 3 — Health chip stops flapping

1. `edge-health.js`: HEALTH_TIMEOUT_MS 3 s → **10 s**.
2. `common.js checkEdgeHealth`: require **2 consecutive failures** before reporting offline; cache probe result for **20 s**; chip updates only on settled state.
3. ~~Same debounce in `puzzle-leaderboards.js` checkHealth.~~ (file deleted in Phase 5; `common.js checkEdgeHealth` is the surviving implementation)
4. Acceptance: a single slow probe never flips the chip; page reloads within 20 s reuse the cached probe.

### Phase 4 — Calibration tab parity

1. Rewire the calibration status payload to compute per-engine accuracy/play-rating through `play_rating_status_summary` (same as `build_opponent_snapshot_rows`, snapshot_leaderboard.py:44-53).
2. Regenerate calibration data files from real harness state (rebuild play-rating map + recompute rows via the existing `/api/calibration/rebuild-play-rating-map` path), and commit — they are test-stomped today (see Phase 1 guard).
3. Acceptance: calibration tab anchor ratings match the leaderboard opponent rows, engine by engine, after one refresh.

### Phase 5 — Delete puzzle-content section from leaderboard

1. Remove the `[data-puzzle-content-leaderboard]` section + table from `leaderboard/index.html` (the colspan-9 "Loading snapshot…" table, line ~145).
2. Remove its mount + helpers from `puzzle-leaderboards.js` (PUZZLES_CONTENT_SORT_KEY, contentCells, mount, lines 186-212); keep the file only if the agents table remains, else delete the script tag.
3. Public API data (`puzzles_leaderboard.json`, `/api/leaderboard/puzzles/live`) is kept — still consumed by watch-page agent metrics.
4. Update tests: no `data-puzzle-content-leaderboard` needles; remove content-table assertions.
5. Acceptance: leaderboard page renders only agents + opponents tables; `test_puzzle_leaderboards` green.

### Phase 6 — Puzzle "moves" column is truthful and clarified

1. `puzzle_attempt.py apply_submission`: on wrong/illegal move, append the terminal move to `submitted_moves` **before** failing (keep `first_wrong_move` + `failure_reason` for the replay step).
2. Rename the hub column "Moves" → **"Moves (puzzle)"** with tooltip "moves the agent played in this attempt" (attempts-list.js).
3. Add a **"Puzzles"** column: the agent's cumulative finished attempt count from `/api/leaderboard/puzzles/live` (per agent id), merged into hub rows via attempts-list.js.
4. Watch page chain rows already show moves; ensure they use the same `moves_played` (puzzle_observer.py:168) — verified after Phase 6.1.
5. Acceptance: a failed attempt (wrong move) shows Moves (puzzle) ≥ 1; the Puzzles column shows the agent's lifetime attempt count; hub + watch page agree.

### Phase 7 — Remove orientation sub-label

1. Delete `<span class="sub">white at bottom · a1 bottom-left</span>` from puzzle_observer.py:260 and identify_observer.py:236.
2. Acceptance: no "white at bottom" / "a1 bottom-left" text anywhere in served HTML (web + localhost).

### Phase 8 — Puzzle/identify continual loop + watch page UX

#### 8A — Server-side continual loop (not just prompts)

The indefinite loop depends on server-side constraints as much as the prompt. Verify and document each:

1. **Active concurrency cap**: `max_puzzle_attempts_per_key = 3` (limits.py:31), `max_identify_attempts_per_key = 3` (limits.py:32). Serial loops are fine (finish one → start next). No hourly or total cap on `/puzzles/start` or `/identify/start` — **already unbounded**. No changes needed here; document it.
2. **Session exclusion** (`session_exclude_sec`): prevents the same puzzle from being re-assigned within a window. If the pool is large this is fine. Add a log warning (not an error) when exclusion eliminates >80% of the pool so operators can see when the pool is getting tight.
3. **Pool exhaustion**: `random_puzzle()` returns `None` → 404 "No eligible puzzle found" (puzzles_api.py:139-140). The agent must handle this gracefully. Add to both briefs a final instruction: **"If you get a 404 on start, stop — the puzzle pool is exhausted."** This is the only natural end condition.
4. **No idle timeout on puzzle/identify attempts** (the 1800 s idle timeout only applies to games). Confirmed: puzzle attempts have no expiry. No changes needed.
5. **End-to-end test**: add `test_puzzle_continual_loop` — simulate an agent key completing 3 serial attempts (start → wrong move → finish → start again → finish → start again) via the real API. Assert: all 3 start successfully, chain has 3 rows, moves ≥ 1 for each, no rate-limit blocks, pool exhaustion returns 404 (not 429).

#### 8B — Brief placement

1. `puzzle_brief.py`: move the "## Continuous loop" section (lines 70-79) to the **top** of the brief, before the play loop, so agents never miss it.
2. `identify_brief.py`: same move (already has it, verify placement).
3. Both briefs gain the pool-exhaustion stop instruction (8A.3).

#### 8C — Watch page UX (chain, auto-follow, metrics)

1. **Chain fallback**: puzzle + identify public rows expose `key`; when a record has no `key_fingerprint` (pre-deploy attempts), group the chain by `agent_name` instead, so **every** attempt gets history + auto-follow.
2. **Auto-follow**: poll while finished (5 s interval, not 15 s), follow immediately on detecting a newer attempt (keep a 3 s override banner for humans to stay).
3. **Agent metrics card**: always visible (rating/deviation/attempts/solves for puzzles; accuracy/full-position for identify). Already implemented; verify it renders on every poll cycle.
4. **Rating deltas on finish**: `rating_before` / `rating_after` / `rating_change` shown in the state card when the attempt finishes. Already in `replay_payload` (puzzle_observer.py:145-147); verify it renders.
5. Operator action: restart the local origin to load the latest build before verification.

#### 8D — Acceptance

End-to-end local run via API (simulating a real agent):
1. Register key → start puzzle → submit wrong move → finish (failed) → chain shows 1 attempt, moves = 1, rating delta shown.
2. Start second puzzle → submit correct move → finish (solved) → chain shows 2 attempts, metrics card updated, auto-follow triggers → human redirected to attempt #2 within 5 s.
3. Start third puzzle → 404 if pool exhausted (assert), or finish → chain shows 3 attempts.
4. Watch page: all chain links work, solution shown after finish, puzzle id visible, "white at bottom" absent.
5. Hub table: "Moves (puzzle)" ≥ 1 for all attempts; "Puzzles" column shows cumulative count.

## 4. Test updates

- `test_identify_api.py`: chain-fallback-by-agent-name case.
- `test_puzzle_observer.py`: wrong-move attempt → `moves_played >= 1`; replay includes terminal move.
- `test_puzzle_leaderboards.py`: content-section removal; no "white at bottom" anywhere (new `test_no_orientation_sublabel_in_observer_pages`); guard test for data-file integrity.
- `test_snapshot_leaderboard.py`: 9-model fixture registry → 9 snapshot rows.
- New: `test_data_files_untouched.py` — full suite leaves shipped data files byte-identical.

## 5. Deployment & verification

1. `python -m pytest tests -q --ignore=tests/test_engine_integration.py` → green.
2. Commit + push → deploy workflow runs automatically.
3. Verify live: 9 models on leaderboard; `/api/edge-health` stable over 5 consecutive probes; `/data/leaderboard.json` instant; calibration parity; hub Moves/Puzzles columns; no orientation text; watch page chain on an old attempt.
4. Restart local origin; repeat verification on localhost.
5. **Note:** inline snapshot fallback (Phase 2.3) also fixes localhost lag — the table paints instantly from the embedded JSON even when the fetch is slow.

## 6. Out of scope (deliberately)

- No changes to Elo math, puzzle rating, or identify scoring.
- No new watch-page sections beyond the existing chain/metrics cards.
- No server-side caching layers for `/data/` (static hosting is the cache).