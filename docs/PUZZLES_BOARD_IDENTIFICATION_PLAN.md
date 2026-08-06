# Puzzles + Board Identification — Launch Plan

Goal: fully functional puzzle play, static board identification, and one UI that
launches both — backed by a small native dataset of ~500 low-rated Lichess
puzzles, with agent-only Glicko-2 ratings and simple percentage metrics for
identification.

## Current state (verified, no changes needed)

- Puzzle import works end to end: range-slicing the Lichess CSV dump
  (`https://database.lichess.org/lichess_db_puzzle.csv.zst`, CC0, monthly) and
  `chess-harness puzzles import <csv>` was tested with 300 real rows (0
  rejected; dataset + manifest written; stats, ratings bands, board PNG/text,
  move, review, observer `/p/`, live leaderboard all verified).
- Board identification already does exactly the requested thing: it takes the
  puzzle's **starting position** (post-setup, pre-solution `display_fen`), never
  exposes the solution, submission is final, and it has **no rating** — the
  two metrics already tracked are `mean_accuracy` (% pieces exact) and
  `full_position_rate` (% boards exact). Only naming/copy needs aligning.
- Puzzle difficulty currently drifts via Glicko-2 on every attempt
  (agent 1500→1280 after one failed attempt; puzzle rating drifts too). Freeze
  the puzzle side (Phase B).
- There is no UI to start a puzzle/identify attempt: the paste-ready brief is
  only in the `POST /api/v1/puzzles/start` / `/api/v1/identify/start` payload.

## Phase A — Dataset: `puzzles fetch` + import (~500 low-rated)

- New command `chess-harness puzzles fetch --count 500 --max-rating 1300
  --out <csv>`: streams the Lichess CSV via HTTP range request + zstd decode
  (technique already proven: 8 MB downloaded → ~31 MB decompressed → 300 rows),
  keeps rows with `Rating <= max-rating`, stops once `count` collected (byte
  cap for safety), writes a standard CSV (same columns as the dump).
- Add `zstandard` to the dev/runtime extras in `python/pyproject.toml`.
- Import stays `chess-harness puzzles import <csv>` (idempotent; runtime store
  `$CHESS_HARNESS_DIR/puzzles/puzzles.json` + `manifest.json`; rows never
  committed — `config/puzzles_manifest.json` records source/version).
- Run once against the real harness dir; `puzzles stats` must show ~500
  puzzles with a low average rating.
- Tests: fetch filter/slice logic with a synthetic compressed stream (no
  network); flag validation.

## Phase B — Freeze puzzle difficulty (agent-only ratings)

- `puzzle_ratings.record_attempt`: agent rating still updates via Glicko-2
  **against the puzzle's fixed imported rating/RD**; puzzle records are never
  persisted anymore (a puzzle's displayed difficulty = import estimate
  forever). Abandon still never rates.
- Copy updates: leaderboard Puzzles tab ("Difficulty is the imported Lichess
  estimate and never changes here") + module docstring.
- Tests: `test_puzzle_ratings.py` — after N attempts the puzzle rating/RD stay
  exactly at the imported values while the agent rating moves.

## Phase C — Board identification: static, metrics-only

- No backend changes: identification already scores the puzzle's starting
  position with % pieces (`mean_accuracy`) and % boards (`full_position_rate`).
- Relabel leaderboard columns "Mean accuracy" → "% pieces correct" and
  "Full-position rate" → "% boards correct"; simplify the tab copy to say
  identification is unrated and measured by those two percentages.
- Tests: copy/column assertions updated in `test_puzzle_leaderboards.py`.

## Phase D — Puzzles UI (launcher for both flows, one place)

- New page **`/puzzles/`** (nav item "Puzzles" added to every header:
  `public-site/{index,leaderboard,create,spectator,human,contact}/index.html`
  and `ladder_display.PUBLIC_SITE_HEADER` used by `/p/` + `/i/` watch pages).
- Two tabs on the page (same pattern as `/leaderboard/`, `?tab=puzzles|identify`
  URL state): **Puzzles** | **Board identification**.
- Per tab: model select (`GET /api/v1/agents`) → mint key
  (`POST /api/v1/agents {id}`, existing pattern from `create.js`) → start via
  `POST /api/v1/puzzles/start` or `/api/v1/identify/start` (optional rating
  band) → show the returned paste-ready **agent brief** (copy button) →
  prominent "Open watch page" link + auto-redirect to `/p/{attempt_id}` or
  `/i/{attempt_id}` (observer page already polls live state and unlocks the
  replay/answer when the attempt ends).
- Cross-links to the leaderboard tabs (`/leaderboard/?tab=puzzles|identify`).
- New files: `public-site/puzzles/index.html`,
  `public-site/js/puzzle-launcher.js`. No proxy change (`/api/v1/*`, `/p/`,
  `/i/` already routed; `/puzzles/` is static).
- Verification: `node --check`, lint/typecheck, `GET /puzzles/` 200 on the
  running server, brief + watch redirect smoke in a browser.

## Phase E — Verification and rollout

- Gates: full `pytest` suite, `scripts/check_line_limits.py` (no new files over
  300), `npm run lint`, `npm run typecheck`, `node --check` on new JS.
- Real-harness: fetch+import ~500 puzzles; restart serve; smoke `/puzzles/`,
  a puzzle attempt, an identify attempt, `/p/` + `/i/` watch pages, live
  leaderboards; `snapshot-leaderboard` refreshes the three JSON snapshots.
- Commit + push (auto-deploys Pages) + restart the harness service.

## Out of scope

- Engine-based puzzle calibration; puzzle-side rating changes; identify rating;
  puzzle authoring/voting/races; variants; anything beyond standard chess.

## Files touched (expected)

- New: `docs/PUZZLES_BOARD_IDENTIFICATION_PLAN.md` (this), `public-site/puzzles/index.html`,
  `public-site/js/puzzle-launcher.js`, fetch/import tests.
- Edit: `commands.py` (+`cmd_puzzles_fetch`), `pyproject.toml` (zstandard),
  `puzzle_ratings.py` (freeze), `leaderboard/index.html` + `puzzle-leaderboards.js`
  (copy/columns), all header navs + `ladder_display.py`, `test_puzzle_ratings.py`,
  `test_puzzle_leaderboards.py`.
