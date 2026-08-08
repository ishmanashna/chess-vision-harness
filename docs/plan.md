# Plan: Fix, Optimise, and Rationalise the Chess Vision Harness UI

## Problem summary

Six distinct issues surfaced from a single playtest pass:

1. **Runtime crash** — `esc is not defined` ReferenceError when starting a puzzle or board-identification attempt.
2. **Unwanted UI field** — "Difficulty band (optional)" on the Puzzles page that the user never requested.
3. **Broken puzzles tab layout** — Tab buttons take a full column instead of sitting inline like the leaderboard/create-game tabs.
4. **Slow localhost** — Leaderboard and calibration status endpoints rebuild data from scratch on every request, without caching, reading multi-MB JSONL files synchronously.
5. **Repo bloat** — The repo is ~250 MB, driven by engine binaries, node_modules, and a 30 MB calibration games.jsonl.
6. **Home table too wide** — The leaderboard table on `/` stretches to the full viewport width on large screens with no max-width constraint.
7. **Separate launcher pages** — Create Game (`/create/`), Playground (`/human/`), and Puzzles (`/puzzles/`) duplicate the same select-model → inscribe → start → brief pattern; merge them into one launcher (implemented in Phase G).

---

## Phase A — Fix "esc is not defined" crash (1 line)

**What:** `public-site/js/puzzle-launcher.js` function `showResult` (lines 134, 136, 141) calls `esc(...)` but that variable is never defined in its scope. The function `escapeHtml` is defined at line 7 and is the intended escape function.

**Fix:** Replace bare `esc(...)` with `escapeHtml(...)` on lines 134, 136, 141.

**Done when:** `node --check public-site/js/puzzle-launcher.js` passes, and a manual smoke test of starting a puzzle attempt shows the result panel without a console error.

**Files:**
- `public-site/js/puzzle-launcher.js` (lines 134, 136, 141)

---

## Phase B — Remove "Difficulty band (optional)" field

**What:** `public-site/puzzles/index.html` lines 65-70 render a `div.form-row[data-rating-band]` with min/max rating inputs labelled "Difficulty band (optional)". The user never asked for this. The backend `startAttempt` in puzzle-launcher.js (line 39-48) sends `rating_min`/`rating_max` query params; removing the UI fields means removing the form inputs and the backend's `data-rating-band` data attribute.

**Scope:**
- Remove the `<div class="form-row" data-rating-band>` block from `puzzles/index.html` (lines 65-70).
- Remove `ratingMin` and `ratingMax` variable references from `mountLauncherPage` in `puzzle-launcher.js` (lines 188-189, 200, 273).
- Keep the `startAttempt` function signature accepting `ratingMin`/`ratingMax` for backward compat (the backend defaults to no filter if omitted) — or simplify if the route no longer needs them.

**Done when:** The Puzzles page has no "Difficulty band" or "rating" inputs visible in the form. The backend API still works when called without those params.

**Files:**
- `public-site/puzzles/index.html`
- `public-site/js/puzzle-launcher.js`

---

## Phase C — Fix Puzzles tab layout

**What:** The puzzles page at `/puzzles/` uses `class="leaderboard-layout"` as its wrapper, which is a CSS grid layout originally designed for the leaderboard page. The tab buttons sit inside `.mode-tabs` (inline-flex) but the grid container's implicit column sizing pushes them into their own column. The create-game page (`/create/`) and playground (`/human/`) work correctly because they don't use `leaderboard-layout` — they use a simpler stacked layout.

**Scope:**
- Change the puzzles page wrapper from `leaderboard-layout` to a layout that matches the create-game pattern (the `create-layout` grid with `create-main` + `create-aside` columns, which is already present in the HTML).
- The `.mode-tabs` styling already exists and is correct (inline-flex, sits above the form). The problem is the parent grid. Since the puzzles page already has `create-layout` as the inner section, the fix is to remove the `leaderboard-layout` grid wrapper and let the natural flow of `create-layout` handle positioning.
- Alternatively, change the grid to `grid-template-columns: 1fr` with a `max-width` constraint, or remove the grid entirely and use a simple block layout.

**Done when:** The Puzzles and Board identification tabs sit inline next to each other as compact buttons (like the leaderboard tabs), not taking an entire column each. The page layout is consistent with the create-game page.

**Files:**
- `public-site/puzzles/index.html`
- `public-site/css/site.css` (if CSS changes are needed)

---

## Phase D — Cache leaderboard & calibration endpoints

**What:** The `/api/leaderboard/live`, `/api/leaderboard/puzzles/live`, `/api/leaderboard/identify/live`, `/data/leaderboard.json`, `/data/puzzles_leaderboard.json`, `/data/identify_leaderboard.json`, and `/api/calibration/status` endpoints all rebuild from scratch on every request by reading full JSONL files synchronously.

**Root causes:**
1. `spectator.py` lines 258-312: every leaderboard endpoint calls `load_live_*` which creates a fresh `ModelRegistry` + `ResultsManager` and reads the entire `results.jsonl` file.
2. `ResultsManager.load_results()` (results.py:90-102) reads the whole `results.jsonl` into memory on every call.
3. `get_calibration_status()` (calibration_view.py:187-302) reads `games.jsonl` (30 MB), `play_rating_samples.jsonl` (2.5 MB), and all `ratings.json` files, syncing on every status poll. It has a 4-second TTL cache but the frontend polls every 5 seconds so it rarely hits the cache.
4. Zero HTTP caching headers (`cache-control: no-store`).

**Scope:**
- Add a short TTL server-side cache (e.g. 5-10 seconds) for the leaderboard JSON responses. The existing `SNAPSHOT_REFRESH_MIN_INTERVAL_SEC = 30.0` lock in `snapshot_leaderboard.py` is only used for the disk-write snapshot path, not for the live HTTP endpoints.
- Add a TTL cache for `load_live_leaderboard`, `load_live_puzzle_leaderboard`, `load_live_identify_leaderboard` using a simple `(timestamp, data)` tuple with a lock, similar to what `calibration_view.py` already does for `merge_calibration_ratings` and `get_calibration_status`.
- Increase the calibration status cache TTL from 4s to 10s, or implement debouncing in the frontend so it doesn't poll faster than the cache.
- Add `cache-control: public, max-age=5` (or appropriate) to leaderboard responses.
- Optionally: move leaderboard and calibration endpoints to `asyncio.to_thread` to avoid blocking the event loop while reading files.

**Done when:** Repeated requests to `/api/leaderboard/live` and `/api/calibration/status` within the cache window return cached data (confirmed by response time dropping from ~500ms to <5ms). The page loads feel noticeably faster.

**Files:**
- `python/src/chess_harness/spectator.py`
- `python/src/chess_harness/snapshot_leaderboard.py`
- `python/src/chess_harness/calibration_view.py`
- `python/src/chess_harness/play_rating.py` (if `play_rating_status_summary` needs caching)

---

## Phase E — Reduce repo bloat (actual cleanup, not analysis)

**What (measured):** The working tree is ~250 MB. Breakdown after measuring the live repo:
- `bin/` ≈ 128 MB (Stockfish ~76 MB, minimalchess ~26 MB ×2) — **gitignored** (`bin/.gitignore`), local-only, re-fetchable (`bin/README.md`).
- `frontend/node_modules/` ≈ 38 MB — gitignored, local-only, re-installable.
- `elo_calibration/results/continuous/games.jsonl` ≈ 30 MB — **git-tracked and committed**; it is the calibration restore path (`elo_calibration/README.md`), so it must stay derivable, not be wiped.
- `.git/` ≈ 48 MB (large `games.jsonl` blobs in history).

This phase performs the cleanup the rules allow; it does not ship a memo.

**Scope (do it):**
1. **Verify and enforce ignore coverage** — run `scripts/check_clean_root.py` and `git status --ignored`; confirm `bin/` engines, `node_modules`, `__pycache__`, `.pytest_cache`, and calibration JSONL growth are never tracked. Fix any gap in the root `.gitignore` or `bin/.gitignore`.
2. **Delete re-creatable, gitignored local bloat** — remove `frontend/node_modules` (reinstallable via the committed lockfile), `.pytest_cache`, `__pycache__` dirs, and **legacy/duplicate engine binaries** in `bin/opponents` (e.g. `minimalchess-0.2` and any copy the running config does not reference). Before deleting any engine, verify against `config/` which engine paths the harness actually invokes, so the app still starts ("without breaking stuff").
3. **Bound the committed `games.jsonl`** — add a rotation/truncation at the append path (`continuous_calibration.py`) that keeps a bounded window of rows (> 30 rows, so the `recent_games[-20:]` display in `calibration_view.get_calibration_status` still works) and never drops `uci_moves` rows that the current `play_rating_samples.jsonl` was rebuilt from. The rotation must hold a per-path lock and write atomically (temp file → replace), because appends are threaded with up to `MAX_PARALLEL_GAMES` concurrent games. Truncate the current 30 MB file down to that window, then **run `play_rating.rebuild_estimation_samples` and require the new `sample_count` >= the pre-truncation count** so the play-rating map and accuracy columns don't regress; only the one-off first truncation is a full rewrite.
4. **Leave git history rewrite to the operator (manual, rule-bounded)** — the `.git/` ≈ 48 MB is only removable with `git-filter-repo`/BFG, which the agent is not allowed to run (ORCHESTRATOR.md: the human owns git). Prepare the exact command and expected `.git/` size as a handoff; do not run it.

**Done when (measured, not documented):** `du` of the repo excluding `.git/` is **under 100 MB**; `games.jsonl` is bounded by its rotation window with a lock-safe, atomic rotation; no tracked file was deleted (`git status` shows only intended changes); `scripts/check_clean_root.py` passes; the harness still starts with the engines `config/` references; the retained `games.jsonl` window still rebuilds `play_rating_samples.jsonl` with `sample_count` >= the pre-truncation count.

**Files:**
- `.gitignore` / `bin/.gitignore` (verify + fix gaps)
- `python/src/chess_harness/continuous_calibration.py` (bound the games log on append)
- `python/src/chess_harness/play_rating.py` (regenerate samples after truncation)
- `elo_calibration/results/continuous/games.jsonl` (truncate to window)
- Operator handoff: exact BFG/git-filter-repo command (not run by the agent)

---

## Phase F — Constrain Home table width

**What:** The Home page (`public-site/index.html`) has a leaderboard table that stretches to the full viewport width because:
- `.home-layout` has no `max-width` constraint (it's a grid with `grid-template-columns: 1fr`).
- `.leaderboard-table` has `width: 100%; max-width: none;`.
- The `.wrap` container has padding `clamp(20px, 3vw, 48px)` but no max-width.

**Scope:**
- Add `max-width: 48rem` (or similar) to `.home-layout` or `.home-ladder` to match the About section's text width.
- Or add `max-width: 48rem` to the `.leaderboard-table` when inside `.home-ladder`.
- The leaderboard page (`/leaderboard/`) intentionally uses full width, so the constraint should only apply to the Home page table.

**Done when:** The Home page table does not exceed ~48rem width on wide screens, while the dedicated leaderboard page retains its full-width layout.

**Files:**
- `public-site/css/site.css`

---

## Phase G — Implement the merged launcher (Create Game / Playground / Puzzles)

**What:** Replace the three separate launcher pages (`/create/`, `/human/`, `/puzzles/`) with one unified launcher at `/launch/` hosting **five** tabbed flows — **Agent vs Engine**, **Agent vs Agent**, **Playground (vs Human)**, **Puzzles**, **Board identification** (the Agent vs Agent flow moves out of `/create/` to become its own tab). Built on the pattern already proven on the Create Game page (inline `.mode-tabs` bar, `create-layout` grid, shared model select + inscribe panel). This phase **implements** the merge; it does not write a design document.

**Scope (build it):**
1. **Unified page** — new `/launch/` page with an inline `.mode-tabs` bar (the tab-layout fix from Phase C) that switches the launcher form across the five flows (engine, avaa, playground, puzzles, identify).
2. **Shared chrome** — one model select, one inscribe panel, one submit, and one status/message area shared by all tabs; each tab renders only its flow-specific options (opponent + colour, plus the AvA pairing sub-tabs, for engine/avaa; nothing for playground; only the start action for puzzles/identify). **Result handling is per-tab, not one identical panel**: engine shows brief + open-watch; AvA shows both briefs + open-watch; playground waits for the agent then goes to the play board; puzzles/identify redirect to their `/p/{id}` / `/i/{id}` watch pages. Reuse the existing JS (`create.js`, `create-human.js`, `puzzle-launcher.js`) behind the tabs rather than duplicating logic.
3. **Flow actions** — wire each tab's Start to its existing backend endpoint: agent-vs-engine → `POST /api/v1/games`; agent-vs-agent → `POST /api/v1/games` (Find match / Direct) + both briefs; playground → `POST /api/v1/games/human` (returns `agent_brief` + `play_token`; inscribe stays on `/api/v1/agents`); puzzles / identify → `POST /api/v1/puzzles/start` / `/identify/start`. Backend is unchanged.
4. **Routing & links** — `/create/`, `/human/`, `/puzzles/` keep working (redirect to `/launch/?type=...` or act as thin aliases); update nav/internal links so `/launch/` is reachable; the post-start watch/brief flow is unchanged.

**Done when:** One `/launch/` page lets a user start all five flows (engine / avaa / playground / puzzles / identify) from a single shared model/inscribe form; tab buttons are compact and inline (not full-column); legacy routes don't 404 and land sensibly; all five watch/brief flows work end-to-end; frontend smoke test of each flow's start passes.

**Files:**
- `public-site/launch/index.html` (new)
- `public-site/js/` (a small launcher orchestrator over the retained create/human/puzzle JS)
- `public-site/css/site.css` (reuse existing `.mode-tabs` / `create-layout`; only if a gap shows)
- `public-site/_routes.json` / `public-site/functions/_proxy.js` (route handling if needed)
- Existing `/create/`, `/human/`, `/puzzles/` pages (redirect/alias)

---

## Phase ordering

```
Phase A (1-line fix)  ── can be done first, trivial
Phase B (remove field) ── can be done independently
Phase C (fix layout)  ── can be done after B
Phase D (cache)       ── can be done independently of A/B/C
Phase E (bloat cleanup) ── can be done independently (backend + local tree)
Phase F (table width) ── can be done independently
Phase G (merge launcher) ── after C (builds on the Phase C tab-layout fix); frontend
```

Phases A, B, C, F, G are frontend-only. Phases D, E are backend-heavy (E also touches the local tree). They can be parallelised in two waves — frontend wave (A+B+C+F, add G once C lands) and backend wave (D+E) — with G following the frontend wave.

## How to verify

1. **Phase A**: Open the Puzzles page, select a model, click "Start attempt" — no console error, result panel shows.
2. **Phase B**: The puzzles form has no "Difficulty band" input.
3. **Phase C**: Tab buttons are compact inline buttons, not full-column blocks. Page layout matches create-game.
4. **Phase D**: `curl GET /api/leaderboard/live` returns in <5ms on the second call within 5 seconds. Calibration page loads visibly faster.
5. **Phase E**: `du` of the repo excluding `.git/` shows **<100 MB**. `games.jsonl` stays bounded by its rotation window. `scripts/check_clean_root.py` passes. Harness still starts.
6. **Phase F**: Home page table has a max-width and doesn't span the full monitor width on 1920px screens.
7. **Phase G**: `/launch/` starts all four flows (engine / playground / puzzles / identify) from one shared form; tab buttons are inline; legacy `/create/`, `/human/`, `/puzzles/` routes don't break.

## Estimated duration

- Phase A (fix esc bug): 0.25–0.5 agent-hours
- Phase B (remove difficulty band field): 0.25–0.5 agent-hours
- Phase C (fix puzzles layout): 0.5–1 agent-hour
- Phase D (cache leaderboard & calibration): 1–2 agent-hours
- Phase E (reduce bloat — actual cleanup + games.jsonl rotation): 2–4 agent-hours (operator git-history rewrite is separate, manual)
- Phase F (constrain Home table): 0.25–0.5 agent-hours
- Phase G (implement merged launcher): 4–8 agent-hours