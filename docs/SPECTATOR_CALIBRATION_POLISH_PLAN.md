# Spectator, calibration & leaderboard polish plan

Fix broken puzzle watch URLs and empty replay panels, put identify review feedback on the main board only, unblock calibration full status, pin game moves scroll to the bottom, and simplify leaderboard puzzle/identify columns. Keep puzzle Glicko-2 (do not switch to ladder Elo).

## Scope

- Puzzle watch: missing attempt id in URL; finished attempts showing empty Played/Solution.
- Identify watch: remove stacked second board; green/red feedback on the primary board.
- Calibration localhost: ratings table stuck on “No calibration data yet.”; quality panel stuck on Loading / opaque failures.
- Game spectator (`/g/{id}`): moves list scroll pins to absolute bottom when following the live tip.
- Leaderboard: replace Pz att + Pz sol with one ratio column; remove Id att.
- Product lock: puzzles stay on Glicko-2 separate from ladder Elo (rationale below).

## Out of scope

- Changing ladder Elo math, engine calibration Elo, or Performance map formulas.
- Migrating historical puzzle ratings to Elo.
- Rewriting Pages hosting architecture beyond watch-shell redirect hardening already in place.
- Home mini-ladder column set (no unified puzzle columns today).

## Product decisions (locked)

1. **Puzzle ratings stay Glicko-2.** Ladder games use Elo; puzzles use Glicko-2 against fixed imported puzzle difficulty (Lichess-aligned, RD for sparse attempts, isolated from `models.json` / `reset_all_elo`). Switching to Elo would blur tactical vs game skill and force a ratings migration for little UX gain. Leaderboard/watch copy may say “puzzle rating (Glicko)” where helpful; do not reimplement as Elo.
2. **Identify review: one board.** Correct/wrong squares overlay the main position board. Delete the stacked “Identification board” image as a second board on all breakpoints.
3. **Leaderboard puzzle column:** one **Pz** ratio display (`solves/attempts`, e.g. `2/5`), sortable by solve rate. Remove separate Pz att, Pz sol, and Id att columns. Keep PUZZLES (Glicko), % pieces, % boards.
4. **Illegal / empty puzzle finishes:** spectators must always see what ended the attempt (including illegal tries) and the canonical solution after finish.

---

## Phase 0 — Puzzle watch: URL id + finished replay honesty

**Goal:** Opening a puzzle from Spectator never lands on “No puzzle attempt id”; finished attempts never show blank Played and Solution when data exists or can be reconstructed.

**Work**

- Harden `attemptIdFromPage` (and identify twin): `decodeURIComponent`, reject bare `p`/`i`, keep `index.html` rejection; if pathname is `/p/` with no id, error copy should mention the URL was stripped (not only “no id”).
- Confirm Pages middleware still returns 200 HTML via `fetchWatchShellHtml` for `/p/{id}` (no browser-visible 308 to `/p/`). If any remaining path returns the redirect to the client, fix that path; add a contract/regression test or documented curl check.
- Spectator list links: prefer `row.watch_url` when present, else `/p/{attempt_id}`; never emit `/p/` with empty id.
- Server: on illegal-move fail, append the attempted move into `submitted_moves` (or equivalent) so `moves_played` and replay `plies` are non-empty; keep `first_wrong_move` / `failure_reason`.
- Client `renderFinishedMoves`: if `plies` empty but `first_wrong_move` set, show that attempt under Played; if solution SAN arrays empty but `solution_moves` UCI present, derive or show UCI fallback; never claim “Solution not available” when the finished record has `solution_moves`.
- Abandoned attempts: clear copy that replay unlocks only for finished (already 404) — optional one-line Played from live state if useful.

**Done when**

- `/p/{valid_id}` on Pages and localhost always parses an id when the browser address bar still contains it.
- Illegal-move failed attempts show at least the failing try under Played and the full Solution after finish.
- Wrong-legal and solved attempts still show Played + Solution as today.

**Verify**

- Curl/browser: `/p/pz-…` → 200, no Location `/p/`.
- Finish via illegal move → spectator shows Played + Solution.
- Targeted puzzle API / observer tests for illegal-move recording + replay.

---

## Phase 1 — Identify review on the main board only

**Goal:** One board column; green/red feedback overlays the primary board; remove the second stacked board.

**Work**

- Prefer cm-chessboard Markers on `#board` from `replay.per_square` (exact = green, mismatch = red), matching game spectator marker usage where possible.
- Keep `GET /i/{id}/answer.png` for download/API if useful, but do not show it as a second board. Remove “Identification board” label and stacked `#answer-wrap` layout (or leave wrap only if used as an absolute overlay *inside* `#board-wrap` — not a sibling below).
- Unify CSS for all breakpoints: no desktop-only stacked second image.
- Update `renderReplay` / height sync accordingly.

**Done when**

- After identify finish, only one board is visible; squares show correct/wrong; Expected/Submitted table remains in the right column.

**Verify**

- Wide and narrow viewports: no second board under the main one.
- Overlay/markers match `per_square` from replay.

---

## Phase 2 — Calibration full status unblocks

**Goal:** `/calibration` paints the ratings table and quality panel when the worker is up; corrupt `games.jsonl` tails cannot 500 the full endpoint forever.

**Work**

- In `get_calibration_status` games.jsonl fallback: skip non-JSON lines (try/except per line); never crash the whole status build.
- On client `refreshFull` failure: update `#rating-table` (and summary) with an explicit error, not leave “No calibration data yet.”
- Use timeout on calibration fetches (same AbortController pattern as `fetchWithTimeout`).
- Ensure full status still builds `rating_table` / play-rating blocks when recent_games is empty but ratings files exist.
- Optional: surface parse-skip counts in logs only — no user-facing noise.

**Done when**

- With a healthy worker and existing ratings, full status returns 200 and the table leaves the initial placeholder.
- Corrupt tail lines in `continuous/games.jsonl` do not 500 `/api/calibration/status`.
- Worker down: visible error on summary *and* table, not eternal Loading / “No calibration data yet.” alone.

**Verify**

- `GET /api/calibration/status` vs `/status/live` on localhost.
- Open `/calibration` — quality text and ratings table populate or show errors within the client timeout.

---

## Phase 3 — Game moves scroll + leaderboard columns

**Goal:** Live game spectator moves stick to the true bottom; leaderboard puzzle columns match the locked product decision.

**Work**

- `spectator-game.js`: when following the tip (first load, new move, or `selectedPly` at tip), set `#mv` / `.moves-scroll` `scrollTop = scrollHeight` (after layout / rAF if needed). When scrubbing away from tip, scroll the selected row into view (center or nearest on the row).
- Adjust `.moves-scroll` bottom padding only if it still leaves a visual gap after `scrollTop` pin.
- `leaderboard/index.html` + `common.js`: remove Pz att, Pz sol, Id att headers/cells; add one ratio column from `puzzle_solves` / `puzzle_attempts` (display `solves/attempts`, sort by rate); fix colspan; update tooltips / rating explain if needed.
- Keep `identify_attempts` in JSON if other surfaces need it; do not show Id att on the unified table.

**Done when**

- New moves keep the moves panel scrolled to the absolute bottom while at tip.
- Leaderboard shows PUZZLES + one puzzle ratio + identify % columns; no Pz att / Pz sol / Id att.

**Verify**

- Long in-progress game: tip follow pins to bottom; scrubbing mid-game does not force bottom.
- Leaderboard visual + sort on the ratio column.

---

## Order

0 → 1 and 2 may run in parallel after 0 if needed → 3 last (small UI polish; safe after or with 1).

Prefer one subagent per phase. Phase 3 is small enough to attach to Phase 1 if capacity allows, but keep separate done-when.

## Implementation notes for agents

- Read `PRODUCT.md` and `ARCHITECTURE.md` at session start.
- Replace stacked identify board wiring; do not leave a second visible board path.
- Do not convert puzzle Glicko to Elo.
- Do not run git or the full test suite; use targeted tests only.
- Puzzle URL stripping and illegal-move empty replay are separate bugs — fix both in Phase 0.

---

## Estimated duration

- Phase 0: 3–5 agent-hours
- Phase 1: 2–4 agent-hours
- Phase 2: 2–3 agent-hours
- Phase 3: 1–2 agent-hours
