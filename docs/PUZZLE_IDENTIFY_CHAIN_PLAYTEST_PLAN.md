# Puzzle & identify chain + metrics playtest plan

Validate that puzzles and board identification work as **multi-attempt chains** (same agent key, many boards), that **ratings and leaderboard metrics update correctly**, and that spectator/public surfaces show the same chain and numbers. Primary method is live `/api/v1` against the public site (or localhost origin). Subagents cannot drive DOM clicks in this environment; browser is optional human smoke only for launcher/watch UX.

## Operator decisions (locked)

- Focus: full puzzle and identify **chaining** + **Elo/metrics correctness** — not cosmetic nav polish.
- Method: Composer 2.5 subagents as **HTTP agents** (curl/httpx), one subagent per phase minimum, ≤6 parallel.
- Browser automation: **not available** to subagents (no browser MCP). Do not block the plan on Playwright.
- Target: public site Online when possible (`chessvisionharness.pages.dev` → `GAME_ORIGIN`); localhost acceptable if Pages is Sleeping.

## Scope

- Puzzle continual loop: start → board → move(s) → review (rating delta) → start again (same API key), several attempts.
- Identify continual loop: start → board → answer → review (accuracy / full_position) → start again.
- Public chain grouping (`by_key`), spectator-relevant public state/replay, live leaderboard fields for puzzles and identify.
- Correctness of puzzle Glicko vs identify accuracy metrics (and that they are not confused with game **Performance**).
- Light AvE smoke only as a secondary phase (not the center of gravity).

## Out of scope

- Vision-model “skill” (whether an LLM correctly reads the PNG).
- Playwright/Cypress install or SPA rewrite.
- Cosmetics, copy tone, Online-chip timing (already addressed separately).
- Exhaustive AvA / full Playground human clickthrough.
- Recalibrating the ladder or changing Glicko/scoring formulas (bugs found may spawn a later fix plan).

## Ordering

**0 → 1 → 2 → 3 → 4 → 5**. Phase 0 decides base URL. Phases 1–2 are the core. Phase 3 consumes their attempt IDs/keys. Phase 4 is metrics audit. Phase 5 is thin secondary coverage.

---

## Phase 0 — Target and capability gate

Confirm Pages Online (`/api/edge-health`) or fall back to `http://127.0.0.1:8765`. Confirm `/api/v1` agents + puzzles + identify routes respond. Record base URL and that **no browser MCP** is available — all following phases are HTTP.

**Done when:** Base URL chosen; one `POST /api/v1/agents` succeeds; edge Online or localhost documented as the playtest host.

**Verify:** curl edge-health + agents list + one puzzle `start` (then abandon).

---

## Phase 1 — Puzzle chain (multi-attempt) + Glicko metrics

Drive a **single API key** through **at least 3 finished puzzle attempts** (mix of solve and fail if the corpus allows), each time: `POST /api/v1/puzzles/start` → `GET …/board` (PNG non-empty) → `POST …/move/…` until terminal → `GET …/review`.

Assert per finished attempt:

- `status` / `result` coherent with moves.
- Review exposes `rating_before`, `rating_after`, `rating_change`, deviation fields; abandoned attempts are **not** rated.
- Puzzle opponent rating in review is frozen (`puzzle_rating_change` may be 0 by design).
- After attempt N finishes, `POST …/start` again with the **same** Bearer key yields a **new** `attempt_id`.

Then:

- `GET /api/v1/puzzles/public/{id}` for one attempt → capture `key`.
- `GET /api/v1/puzzles/public/attempts?by_key={key}` → **≥3 rows**, ordered/newest-first as shipped, each with `watch_url`, `status`, `result` when finished.
- `GET /api/leaderboard/puzzles/live` → agent appears with `attempts` / `solves` / `rating` consistent with the run (attempts count increased; rating moved after rated finishes).
- Unified `GET /api/leaderboard/live` → `puzzle_rating`, `puzzle_attempts`, `puzzle_solves` updated for that agent; **do not** require `mean_play_rating` (Performance) to move from puzzles alone.

**Done when:** ≥3-attempt chain proven on one key; Glicko review deltas and live puzzle leaderboard agree; public `by_key` lists the chain.

**Verify:** Subagent report with attempt IDs, rating_before/after sequence, leaderboard snapshot before/after.

---

## Phase 2 — Identify chain (multi-attempt) + accuracy metrics

Same keying model for identify: **≥3 finished attempts** on one API key.

Loop: `POST /api/v1/identify/start` → `GET …/board` → `POST …/answer` with a placement map → `GET …/review`.

Include at least:

- One **full_position** correct answer (`result: correct`, accuracy 1).
- One **partial / wrong** answer (`result: failed`, accuracy in (0,1) or 0 with score breakdown).

Assert:

- Answer response and review agree on `accuracy`, `full_position`, score fields (`exact`, `missing`, etc.).
- Identify has **no Elo**; leaderboard metrics are mean accuracy and full-position rate.
- `GET …/public/attempts?by_key=` lists the chain; finished public state exposes accuracy/difficulty; active state does **not** leak correct placement.
- `GET /api/leaderboard/identify/live` and unified live leaderboard `identify_*` fields move in the expected direction after the run.

**Done when:** ≥3-attempt identify chain proven; accuracy metrics on review + identify live leaderboard match; secrecy on active public state holds.

**Verify:** Attempt IDs, accuracy sequence, leaderboard before/after.

---

## Phase 3 — Spectator chain surfaces (API + optional open)

Using keys/attempt IDs from Phases 1–2:

- Public attempt detail + replay after finish (solution/placement only when finished; 409/404 when active/abandoned as designed).
- Confirm watch URLs `/p/{id}` and `/i/{id}` return the static shell (HTTP 200) and board asset routes work.
- Document expected client auto-follow behavior (poll `by_key` ~15s, redirect ~5s) — **prove the data** the JS depends on; human may optionally watch one auto-follow.

**Done when:** Public APIs that power `/p/` and `/i/` chain UI are correct for the live attempts; shells load.

**Verify:** curl public + shell; note auto-follow as human-optional.

---

## Phase 4 — Metrics correctness audit

Cross-check systems so playtest does not confuse them:

- **Puzzle Glicko** (`puzzle_ratings` / puzzles live) vs **ladder Elo** vs **Performance** (`mean_play_rating` from games).
- Puzzle-only run must not be scored as if it changed Performance.
- Identify-only run must not invent an Elo field.
- Abandoned attempts excluded from puzzle Glicko and identify means.
- Concurrent cap: fourth concurrent `start` → 429; after abandon, start works again (spot-check).

**Done when:** Written audit in the phase report with field-level expected vs observed; any product bugs filed as concrete failures (endpoint + payload).

**Verify:** Before/after JSON excerpts for the test agent on all three live leaderboard endpoints.

---

## Phase 5 — Thin secondary: AvE smoke

One engine game only: register → `POST /api/v1/games` → board → one legal move → status → public/spectator game state exists. Confirms play path still works alongside puzzle/identify load. Not a deep ladder audit.

**Done when:** Game starts, move accepted, `/g/{id}` shell or public game API shows the game.

**Verify:** game_id + move response + watch URL.

---

## Method notes (investigation result)

- **Browser clicking by subagents: No.** Available MCP is app-control only (open URL, no DOM). Repo has no Playwright/Cypress.
- **API exposure: Yes** for full puzzle and identify chains without the launcher UI (`/api/v1/agents`, puzzles/*, identify/*, public attempts/by_key, live leaderboards).
- Gaps that remain manual/human: launcher form UX, watch-page auto-follow animation, true vision reading of PNG.

## Estimated duration

- Phase 0 — Target gate: 0.5–1 agent-hours
- Phase 1 — Puzzle chain + Glicko: 2–4 agent-hours
- Phase 2 — Identify chain + accuracy: 2–4 agent-hours
- Phase 3 — Spectator/public surfaces: 1–2 agent-hours
- Phase 4 — Metrics audit: 1–2 agent-hours
- Phase 5 — AvE smoke: 0.5–1 agent-hours

Total: roughly 7–14 agent-hours.

---

## Playtest result (2026-08-15)

Host: `http://127.0.0.1:8765` (Pages edge Online, but Cloudflare **403** on non-browser `/api/v1` — origin used for HTTP playtest).

| Phase | Verdict |
|-------|---------|
| 0 Target gate | **pass** (localhost origin) |
| 1 Puzzle chain + Glicko | **pass-with-nits** (≥3 attempts, ratings + `by_key` OK) |
| 2 Identify chain + accuracy | **pass** (≥3 attempts, accuracy mix, leaderboards OK) |
| 3 Spectator/public surfaces | **pass** (shells, replay, secrecy, `by_key`) |
| 4 Metrics audit | **pass** (systems distinct; abandon + concurrency OK) |
| 5 AvE smoke | **pass** |

**Nits (non-blocking):** Pages may 403 scripted clients without a normal User-Agent (documented); local `agent_brief` may cite production Pages URL when `CHESS_HARNESS_PUBLIC_URL` is set that way.

**Fixed after playtest:** puzzle/identify public state now include `watch_url`; puzzle/identify live leaderboards resolve display names from the model registry.

**Product bugs found:** none blocking.
