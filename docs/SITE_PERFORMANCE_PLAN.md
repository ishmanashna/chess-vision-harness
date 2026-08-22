# Site feel: health, tabs, live pages

Make the public site feel instant when switching Home / Create / Spectator / Leaderboards, and honest-fast about Online vs Sleeping. Live watch and play must stop burning the game PC when the tab is in the background. Stay a normal multi-page site.

## Scope

- Status chip and `/api/edge-health`: fail fast when the origin is down; do not re-probe on every tab click if a fresh answer already exists.
- Checking vs Sleeping vs Online UI: offline banners and Create Game must not look failed while the chip still says Checking.
- Live lists and watch/play: do not wait 25 seconds on a dead tunnel; pause polling when the tab is hidden.
- Origin watch cost: Playground (human vs agent) eval must not run Stockfish on every spectator poll.

## Out of scope

- Turning the site into a single-page app or adding a service worker.
- Splitting `common.js` into many files as a fake speed win.
- Removing the inline Home/Leaderboards snapshot (it paints the table without the origin).
- Changing idle game timeout, runner, operator panel, Umami, or Pages hosting.
- Caching live game JSON on the CDN (`no-store` on proxied APIs stays).

## Product decisions (locked)

1. **Still full page loads.** Nav clicks reload the page. Speed comes from not repeating health and not hanging on Sleeping, not from a router.

2. **Fail fast when Sleeping.** Edge health should decide “origin not there” in a few seconds, not ten. Client timeout sits just above that. Proxied live APIs may keep a longer timeout for a slow *live* tunnel; the browser must not call them when the chip already knows Sleeping.

3. **Reuse a fresh health answer across tabs in the same session.** Optimistic chip paint already uses session storage (~90s). A load inside that window must not force a second origin probe. Force a probe on first visit, when the stored answer is stale, when the user comes back to a Sleeping tab that might have woken, and after Go Online from the operator desk.

4. **Checking is not Sleeping.** Offline banners and disabled Create Game wait until the probe finishes, unless a fresh stored Online lets them proceed. Do not show “launcher unavailable” under a Checking chip.

5. **Background tabs rest.** Watch, play, puzzle/identify watch, and Sleeping health polls pause while `document.hidden`. One in-flight poll at a time; no stacked intervals.

6. **Eval on watch is cached.** Human vs agent games show eval like other modes, but spectator must read a stored score when present instead of running Stockfish every 3s. Snapshot eval on AvH the same way as rated games.

## Verified current system (do not re-invent)

- Chip and poll live in `public-site/js/common.js`: `FETCH_TIMEOUT_MS` 12000, `HEALTH_POLL_SLEEPING_MS` 4000, `applyHealthUi` always `checkEdgeHealth({ force: true })`. Session storage only paints; it does not skip the network. Sleeping polls continue in hidden tabs; Online polls pause when hidden.
- `public-site/functions/api/edge-health.js`: `HEALTH_TIMEOUT_MS` 10000, `no-store`. Comment still talks about 3s probes.
- `public-site/functions/_proxy.js`: `PROXY_TIMEOUT_MS` 25000. Middleware does not block static HTML on health.
- Launch calls `applyHealthUi` again in `launcher.js` (`force: true` twice). Offline banners on Launch/Spectator are visible in HTML before health resolves.
- Spectator Active/Completed gate `/api/games` on health. Puzzles/Identify attempt lists, `/g/`, `/p/`, `/i/`, `/play/` do not.
- Watch poll: `spectator-game.js` `setInterval(poll, 3000)` serial state → moves → PGN → chat. Puzzle/identify watch same 3s interval. Play: 2.5s position + 2.5s chat. No `document.hidden` in those files.
- `BoardController._try_snapshot_eval` returns immediately for AvH. `show_eval_for_state` is always true, so `/api/games/{id}/state` evaluates AvH live on almost every poll.

## Phase 1 — Health chip and tab clicks

**Goal:** Changing site tabs does not feel like waiting for the home PC. Cold Sleeping shows Sleeping in a few seconds, not ten-plus. Checking does not look like failure.

**Work**

- Shorten the edge health probe timeout for “origin not answering.” Client abort sits slightly above it. Keep a normal fast path when origin is up.
- `applyHealthUi`: if session storage is fresh, paint that state and **do not** `force` a probe. Still start the existing poll loop so Sleeping can notice a wake.
- Launch: register `onHealth` without a second forced `applyHealthUi`.
- Hide Launch/Spectator offline banners until health is known (Checking ≠ Sleeping). Create Game stays disabled until Online, but not under a false offline banner.
- Pause Sleeping health polls when the tab is hidden (same idea as Online today).

**Done when**

- With a fresh Online in session storage, clicking Leaderboards then Create Game does not fire two back-to-back 10s origin probes; the chip is Online immediately.
- With origin down and empty storage, the chip becomes Sleeping in well under 10s (target ~3s class, not 10–12s).
- Launch cold load does not show “unavailable” while the chip still says Checking.
- One Launch load = one health request, not two.

**Verify**

- Browser network on Pages: Home → Leaderboards → Launch with origin Online and a fresh chip cache.
- Same path with origin Sleeping and cache cleared.

## Phase 2 — Do not hang live UI on a dead tunnel

**Goal:** Sleeping means lists and watch pages fail immediately (or stay on snapshot/offline empty), not after 25s per request.

**Work**

- Spectator Puzzles/Identify tabs: same health gate as Active/Completed games (`checkEdgeHealth`, skip fetch when Sleeping).
- `/g/`, `/p/`, `/i/`, `/play/`: if health is Sleeping, do not start (or continue) proxied polls; show the existing offline/empty treatment. When health becomes Online, resume.
- Do not lower the proxy timeout as the Sleeping fix — ungated clients are the bug. Online slow tunnel may still need ~25s.

**Done when**

- Spectator → Puzzles with origin Sleeping returns the empty/offline state without a ~25s wait.
- Open `/g/{id}` or `/play/{id}` while Sleeping: no 25s proxied storm; chip/page agrees the origin is down.

**Verify**

- Pages, origin down: Spectator Puzzles tab, a watch URL, a play URL. Network panel shows no long-aborted proxy pile.

## Phase 3 — Live pages rest in the background

**Goal:** An open watch or play tab in the background does not keep the game PC busy. Slow ticks do not overlap.

**Work**

- `/g/`, `/p/`, `/i/`, `/play/` (position + chat): pause timers when `document.hidden`; resume on visible. One in-flight poll; skip or coalesce if the previous tick is still running.
- Play chat loop stops when the game is over (position already does).
- Optional cheap skip: if FEN/status unchanged, puzzle/identify watch must not rebuild the whole DOM.

**Done when**

- Hide a live `/g/` tab: origin request rate for that game drops to idle. Show the tab: polling resumes.
- A slow tick cannot start a second overlapping poll.

**Verify**

- DevTools: hide tab, origin `/api/games/{id}/state` (or play position) stops. Show tab, it continues.

## Phase 4 — Playground watch must not eval every 3s

**Goal:** Watching human vs agent is as cheap as watching a rated game: eval is a stored number, not a Stockfish call per poll.

**Work**

- Snapshot eval onto AvH game state on moves (same as rated games). Spectator state reads `last_eval_cp` when present.
- Do not skip eval on the AvH board forever — only stop the per-poll live engine when a snapshot exists.

**Done when**

- Open `/g/{id}` on a live Playground game: repeated `GET .../state` does not launch Stockfish each time. Eval still appears in the watch UI after a move has been snapshotted.

**Verify**

- Localhost watch an AvH game; eval present; origin CPU/engine not spinning on every 3s poll (log or eval adapter call count in a test).

## Estimated duration

- Phase 1: 2.5–4 agent-hours
- Phase 2: 2–3.5 agent-hours
- Phase 3: 2–3.5 agent-hours
- Phase 4: 1.5–3 agent-hours
