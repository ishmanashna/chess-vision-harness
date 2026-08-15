# Public site reliability & watch UX plan

Fix localhost loads that hang, puzzle/identify watch clarity, attempt timeouts, leaderboard attempt visibility, Create Game layout, and the worst public-site slowness.

## Scope

- Localhost `chess-harness serve`: calibration page, engines leaderboard section, live leaderboard responsiveness.
- Puzzle and identify watch pages (`/p/{id}`, `/i/{id}`): no auto-follow, clear played vs solution, cleaner left column, reliable load errors, chain list honesty.
- Idle abandon for puzzles (parity with games/identify); on-read safety for both.
- Leaderboard/spectator: show attempt counts; refresh publish snapshots when puzzle/identify attempts finish.
- Create Game launcher: Game mode inside the create card above model select.
- Perf: stop refetching full leaderboards every 3s on watch pages; lazy spectator tab fetches; live leaderboard off the event loop.

## Out of scope

- Changing fair-play rules, Elo/Glicko formulas, or calibration math.
- Paid domain / tunnel architecture.
- Rewriting cm-chessboard or adding a custom stream stack.
- Full redesign of the leaderboard visual language beyond columns/copy needed here.
- Git history rewrites or one-off snapshot commits as a substitute for live refresh wiring.

## Product decisions (locked for this plan)

1. **Auto-follow off.** Finished (or in-progress) watch pages stay on the current attempt. No timer navigation and no “newer attempt” banner. Spectators move only via the attempt chain links (or the URL).
2. **Puzzle difficulty is one static field** — the Lichess/import puzzle rating frozen on the attempt (`puzzle_rating` on the attempt record). Agent Glicko is labeled **Agent puzzle rating** (not “Puzzle rating” / not a second Difficulty).
3. **Puzzle watch left column:** one outcome line (drop redundant Status+Result pair); keep Difficulty (static); Agent puzzle rating; Attempts / Solves; drop **Performance** (game play-rating) from puzzle/identify watch; **Deviation** only as a short subtitle/tooltip under Agent puzzle rating, not a peer row.
4. **Puzzle right column after finish:** clearly separate **Played** (agent + opponent replies) from **Solution** (canonical `solution_moves`); mark the first wrong move in SAN when possible.
5. **Idle timeout:** same `idle_timeout_sec` as games (default 30 minutes). Stale `active` puzzle/identify attempts become `abandoned` (no rating). Document in briefs.
6. **Identify watch:** same auto-follow and error-handling rules; milder left-column cleanup (one outcome; keep accuracy fields that are identify-specific).

---

## Phase 0 — Unblock localhost calibration & engines leaderboard

**Goal:** Engines table and calibration page finish loading on `chess-harness serve`; live leaderboard stops blocking the event loop.

**Work**

- Define `fetchWithTimeout` + `FETCH_TIMEOUT_MS` in `public-site/js/common.js` (currently referenced, never defined — engines path throws `ReferenceError`).
- Fix engines mount: register `onLiveLeaderboard` before snapshot fetch; do not consume/null the inline snapshot before opponents are painted (or pass opponents from the agents paint path). Wrap snapshot failures so live registration always happens.
- Serve live leaderboard JSON via `asyncio.to_thread` (mirror calibration status) so `/api/edge-health`, calibration polls, and other routes are not starved.
- Calibration UI: surface worker/API failures in `#play-rating-summary` / error banner instead of empty `catch`; when worker is down, show an explicit message (do not leave “Loading…” forever).

**Done when**

- Expanding Engines on `/leaderboard/` replaces “Loading snapshot…” with rows or a clear empty/error state.
- `/calibration` quality panel leaves “Loading…” with either data or a visible error within a bounded time when the worker is up or down.
- Opening leaderboard + calibration together does not freeze the status chip on “Checking…” for long stretches attributable to sync live-leaderboard work.

**Verify**

- Browser console on `/leaderboard/`: no `fetchWithTimeout is not defined`.
- `GET /api/leaderboard/live` and `GET /api/calibration/status` remain responsive under concurrent load (manual dual-tab).

---

## Phase 1 — Puzzle & identify idle timeout

**Goal:** Attempts cannot sit `active` forever or permanently consume the per-key concurrency cap.

**Work**

- Add `PuzzleAttemptStore.prune_idle_active(idle_sec)` mirroring `IdentifyAttemptStore` (`updated_at` / `started_at` → `abandoned`).
- Call puzzle prune from `spectator.py` `_idle_watcher` beside identify.
- On-read safety: when opening an active puzzle or identify attempt (agent API + public observer getters), abandon if idle past `load_limits().idle_timeout_sec` before serving.
- Update puzzle (and identify if missing) agent briefs: idle abandon after the same timeout as games; no rating.

**Done when**

- An untouched active puzzle attempt older than the idle limit becomes `abandoned` via watcher and via a subsequent board/state read.
- Identify keeps watcher behavior and gains on-read expiry.
- New `start` succeeds after idle slots were auto-abandoned (no stuck 429 from zombies).

**Verify**

- Targeted unit/API tests for puzzle prune + on-read; existing identify prune test still passes; no full suite.

---

## Phase 2 — Puzzle & identify watch UX

**Goal:** Spectators understand what happened; pages do not jump away; load failures are visible; chains are trustworthy.

**Work**

- Remove automatic `followTo` timers and any “newer attempt” auto-banner. Keep the attempt chain list only; navigation is via chain links or typing a URL.
- If residual follow helpers remain in the file, delete dead code (`followTimer`, `FOLLOW_DELAY_MS`, `#follow-banner` wiring) rather than leaving a second path.
- Chain tracking after manual navigation: when the spectator clicks a chain link (full navigation), normal page load re-inits; no in-page `followTo` required.
- Chain list: include abandoned rows (or at least the current abandoned attempt); honest empty copy when the API fails vs truly empty; surface chain fetch errors; do not silent-return on `!r.ok` for poll / replay / chain.
- Poll/replay failures: write `#poll-error` (or equivalent) for 404/502/503 — “attempt missing” vs “server offline”.
- Puzzle moves column: after finish, render **Played** from submitted/opponent plies and **Solution** from `solution_moves` (API already exposes it); SAN for wrong-move marker when feasible; column headers while live (Agent / Reply).
- Left column per locked product decisions (outcome, static Difficulty, Agent puzzle rating ± deviation tooltip, attempts/solves; no Performance; no duplicate Status+Result).
- Identify: same auto-follow/error/chain rules; collapse redundant Status+Result; keep Expected/Submitted review as-is.

**Done when**

- Watching a finished attempt never navigates away on its own; chain links are the only in-UI path to another attempt.
- Failed puzzle shows distinct played line vs solution line.
- Killing origin or opening a bad id shows an error instead of eternal Loading / empty board.
- First/last/abandoned attempts in a chain appear consistently for the same key (within the list limit).

**Verify**

- Manual: finish a short puzzle chain; stay on attempt 1; chain links still open other attempts.
- Manual: `/p/not-a-real-id` shows error; `/p/{finished}` shows solution vs played.

---

## Phase 3 — Leaderboard attempt visibility & snapshot freshness

**Goal:** Composer (and any agent) finished puzzle/identify work is visible on public leaderboards and spectator lists when Online; Sleeping snapshots catch up without waiting for a rated game move.

**Work**

- Render `puzzle_attempts` / `puzzle_solves` and `identify_attempts` (and keep accuracy columns) on the unified leaderboard table; sortable via existing numeric-key plumbing.
- Call `request_public_snapshots_refresh()` from puzzle finish paths and identify answer/abandon terminal paths (same debounce as games).
- Spectator attempts lists: merge cumulative totals by `model_id` (expose id on public attempt rows if needed), not display-name alone; identify tab gets a cumulative attempts column parity with puzzles.

**Done when**

- Live leaderboard shows non-zero puzzle/identify attempt fields for agents that finished attempts on that harness dir.
- Finishing a puzzle without playing a ladder game still triggers debounced snapshot export hooks.
- Spectator Puzzles/Identify tabs show Composer attempt rows and sensible cumulative counts when APIs return data.

**Verify**

- `GET /api/leaderboard/live` after a local puzzle finish includes `puzzle_attempts > 0` for that model.
- Leaderboard UI Online path paints those counts; Spectator tab lists the attempts.

---

## Phase 4 — Create Game layout

**Goal:** Game mode sits in the create card above model select.

**Work**

- Move `[data-launch-mode-row]` inside `form.card.create-form`, above `[data-single-model-row]` in `public-site/launch/index.html`.
- Adjust spacing only if needed; do not reintroduce `.leaderboard-layout` for the launcher.

**Done when**

- All launcher flows show Game mode as the first control inside the bordered create card; aside “How this works” aligns with the card, not a floating mode row.

**Verify**

- Visual check `/launch/?flow=engine` (and playground/puzzles) at desktop width.

---

## Phase 5 — Public-site responsiveness

**Goal:** Tables, tab switches, and watch pages feel usable; cut the worst redundant work.

**Work**

- Watch pages: do not call full `/api/leaderboard/*/live` on every 3s poll. Embed agent summary metrics on public attempt state (or fetch metrics once / on finish / ≤60s TTL). Prefer one client cache shared with `onLiveLeaderboard` where useful.
- Spectator hub: lazy-fetch games lists and attempts lists on first visible tab (not both attempt kinds on every refresh); avoid double `/api/games` mount work for hidden panels.
- Keep Phase 0 `to_thread` for live leaderboard; add short TTL cache already present — ensure heavy enrich paths stay off the loop.
- Optional small win: cache puzzle totals used by attempts-list for a short TTL.

**Done when**

- A single open puzzle watch tab does not hit full puzzle + unified leaderboard endpoints every 3 seconds.
- Switching Spectator tabs does not refetch inactive panels.
- Leaderboard/engines/calibration remain correct after Phase 0.

**Verify**

- Network panel: watch poll traffic is state (± replay once) and occasional chain, not dual leaderboards every 3s.
- Tab switch: one list request for the newly shown panel.

---

## Order

0 → 1 and 4 may run after 0 in parallel if needed → 2 → 3 → 5.

Prefer sequential implementation (one phase per subagent). Phase 4 is small enough to attach to Phase 0 or 3 if a wave has spare capacity, but still its own done-when.

## Implementation notes for agents

- Read `PRODUCT.md` and `ARCHITECTURE.md` at session start.
- Prefer fixing root wiring over stacking alternate loaders.
- Do not run the full test suite; use targeted tests for prune/API/JS contract only.
- Do not run git commands.
- Pages watch-shell redirect fix already shipped; remaining “puzzle won’t load” work is error surfacing + origin/API honesty (Phase 2), not another shell rewrite unless a new redirect regression is proven.

---

## Estimated duration

- Phase 0: 2–4 agent-hours
- Phase 1: 2–3 agent-hours
- Phase 2: 4–7 agent-hours
- Phase 3: 2–4 agent-hours
- Phase 4: 0.5–1 agent-hour
- Phase 5: 3–5 agent-hours
