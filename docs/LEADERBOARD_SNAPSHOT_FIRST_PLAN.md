# Snapshot-first leaderboard loading

## Goal

The leaderboard tables on Home and `/leaderboard/` show "Loading snapshot…" for seconds, and wait up to ~28 s when the origin is slow (3 s edge-health probe + 25 s proxy timeout before the browser falls back to the committed snapshot). Fix: paint the static snapshot immediately and upgrade in place to live rows. This is a separate concern from the agent-orchestration/puzzles plan so each plan stays lean and independent.

## Shared decisions

- The committed `public-site/data/leaderboard.json` stays the offline/first-paint source: a plain static asset on the fast CDN path.
- Live data is always an upgrade, never required for first paint; the status chip and Create Game prompts continue to use `edge-health` independently.
- No backend change is part of this plan beyond what already exists (`/api/leaderboard/live`, snapshot build/refresh).

## Phase 1 — Snapshot-first paint with in-place live upgrade

1. On page load, fetch `/data/leaderboard.json` immediately and paint rows the moment the static asset resolves — for the Home ladder and the `/leaderboard/` agent table. Keep `mountLeaderboardTable`'s sort/render pipeline unchanged; only the fetch strategy changes.
2. After the snapshot paints, fetch `edge-health` and `/api/leaderboard/live` in the background and swap the live rows in place when they resolve.
3. Keep the semantics: online → live rows and the meta text "Live ladder · updated X"; offline or error → snapshot rows with "Snapshot from X"; the status chip logic is untouched.
4. Re-run the snapshot meta block on the upgrade too, not only on first paint.
5. Enforce a ~5–8 s client-side `AbortController` on the background live fetch; on timeout keep the painted snapshot. The edge proxy's 25 s timeout is irrelevant because we never wait on it.
6. Drop the sequential health gate: neither table ever shows a long-lived loading state while waiting on the origin.

**Done when:** a visitor always sees rows within the static snapshot fetch; live rows replace snapshot rows in place whenever the origin answers; no spinner on a slow or hanging origin.

## Phase 2 — Engines ladder re-paint and regression checks

1. The engines ladder (`mountEnginesTable`) currently paints exactly once from the first snapshot and never upgrades; give it a re-paint hook so it also swaps to live rows and shows the current sort/column semantics.
2. Confirm sort-state persistence (storage keys, `CVH.tableSort`) is preserved across the snapshot→live swap.
3. Verify online, sleeping, slow-origin, and fetch-error cases in browser when Engineering Pages smoke tests; confirm the status chip logic is unchanged and no table regresses to a spinner. Run unit tests and TS/client lint.

**Done when:** the engines table shows live rows after the swap and all leaderboard surfaces keep existing sort/meta semantics.

## Out of scope

- No change to the snapshot build, refresh cadence, or calibration.
- No change to the game server, `/api/leaderboard/live` shape, or the proxy timeout for real game traffic.
- Puzzle- and identification-leaderboard snapshot pipelines are in the main plan (Phase 9), not here.

## Estimated duration

- Phase 1 — Snapshot-first + live upgrade: 2–4 agent-hours
- Phase 2 — Engines re-paint + regression: 1–2 agent-hours