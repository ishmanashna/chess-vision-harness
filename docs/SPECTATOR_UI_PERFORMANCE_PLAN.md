# Spectator UI polish, Performance rebrand, interactive moves

Public and spectator UI pass: home ladder shape, sortable tables, `/g/` layout + engine name shortening, date format, **Estimated Elo → Performance**, Playground-like spectator board (Staunty + coordinates), and clickable move-list scrubbing with eval. Also fix agent-vs-agent **same-model** ladder handling (no Elo, not rated).

## Scope

- AvA when white and black are the **same model**: no Elo change; not rated for ladder Games / K-factor / provisional; still append results and run accuracy / Performance analysis.
- Home leaderboard: drop **Model id**, widen table, **Games** = scored games including AvH (exclude `*`); provisional `*` stays rated-only.
- Major HTML tables: click headers to sort (home, leaderboard agents/engines, spectator lists).
- `/g/` layout: info column full board-stack height; widen info + moves; retune board width formula.
- Engine names on `/g/`: same abbreviation as games list (`d1+62%`).
- Dates: `HH:mm D/MM/YY` (e.g. `22:24 1/08/26`) for game timestamps in public UI.
- Rebrand user-facing **Estimated Elo** → **Performance**. Internal fields (`play_rating`, `mean_play_rating`) stay.
- Games tables: Acc. + Performance columns; Performance not bold.
- `/g/` board: read-only **cm-chessboard** (Staunty, white-bottom, coordinates); download PNG stays Pillow tip.
- `/g/` move list: click ply → board + eval; on each new live move, **always** snap to tip.

## Out of scope

- Changing AvE / different-model AvA Elo math (already simultaneous via pre-game snapshots).
- Global `models.json` lock for concurrent finishes across unrelated games.
- Exposing FEN to agents (`/api/v1`).
- Changing Playground board config or agent-facing Pillow boards.
- Contact inbox timestamps; PGN Date tags.
- `docs/harness_vs_benchmarks.html` (optional one-line rename later, not blocking).
- Calibration CLI/operator table: include Performance rename if cheap in the rebrand phase; otherwise leave.

## Phase 1 — Same-model AvA: unrated, no Elo

Today `avaa_finish` snapshots both Elos then calls `record_game` twice. Different models correctly use each other’s **pre-game** rating. Same model applies **two** chained updates to one rating and double-counts toward `count_by_model()`.

- When `white_model_id == black_model_id`: do **not** call `record_game` (leave `white_elo_*` / `black_elo_*` unset or equal before=after; spectator Elo change shows no movement).
- Still write both results rows (quality upsert needs them). Mark unrated clearly: e.g. `rated: false` on both rows (prefer explicit flag over inferring forever).
- `count_by_model()` / rebuild (`process_results_file`, `elo_change_for_game`): skip unrated / same-model AvA rows. AvH exclusion unchanged.
- Quality path unchanged (still schedule analysis on real results).
- Focused tests: same-model finish → Elo unchanged, rated count +0 (not +2); different-model AvA still updates both from pre-game Elos; rebuild skips same-model rows.
- Operator note: after ship, `rebuild-elo` so past same-model games stop polluting the ladder.

**Done when:** same-model AvA never changes Elo or rated Games; quality still runs; different-model AvA unchanged; tests cover finish + count + rebuild.

## Phase 2 — Performance rebrand + dates + games-table chrome

Surfaces to rename:

- `public-site/index.html`, `leaderboard/index.html` (headers, tips, How ratings work / Engines prose, `<strong>` emphasis)
- `public-site/js/common.js` (tip constant / cell titles)
- `public-site/js/games-list.js` + spectator table headers (`Est. Elo` → Performance; `data-sort`)
- `/g/` Game state labels/tooltips (`spectator_game_page.py`)
- Tests asserting old strings (`test_spectator_list`, `test_spectator_phase3`, `test_leaderboard_polish_phase1`, `test_avh_play_polish`, etc.)
- PRODUCT.md column wording
- Calibration visible headers in `ladder_display.py` if cheap

Also:

- Strip `.elo` from Performance cells only (White/Black Elo stay bold via `.elo`).
- Shared `formatWhen` → `22:24 1/08/26`: `games-list.js`, `human-games-ui.js` (My games). Not contact inbox / not snapshot “generated at” unless trivial.

**Done when:** listed surfaces say Performance; games Performance column not bold; game list/My games dates match format; tests updated.

## Phase 3 — Home / leaderboard Games count + home table shape

- **Do not** change rated semantics of `count_by_model()` beyond Phase 1 (still rated-only for Elo K-factor + provisional; excludes AvH, `*`, and unrated same-model AvA).
- Add `count_scored_by_model()`: `result != "*"`, include AvH and same-model AvA; AvA per-row/per-side like rated (no quality dedupe). Not `quality_games`.
- Snapshot/live: `games` = scored display; `provisional` from rated count only; **always** emit boolean (client fallback `games < 100` must not use display Games).
- PRODUCT + leaderboard prose/tooltips: Games = scored (rated + AvH + unrated same-model AvA with a real result); `*` needs 100 rated.
- Home: drop Model id; widen table; fix `common.js` `renderLeaderboardRows` / colspan. Leaderboard page keeps Model id.
- Tests: scored vs rated; provisional stable when only AvH or same-model AvA grows.

**Done when:** home wider, no Model id; Games includes AvH; provisional still rated-only; Elo math unchanged aside from Phase 1.

## Phase 4 — Sortable tables

- **Reuse** spectator `games-list.js` sorter (extract to `table-sort.js` / `common.js`) — do not reinvent for Active/Completed.
- Greenfield: home mini-ladder, leaderboard agents, engines table (`data-sort`, aria-sort, sorted CSS).
- Numeric sort helpers for Elo/Games; Acc/Performance: sort by first numeric token or white value (document choice); `#` column non-sortable or recompute after sort.
- Persist keys; migrate `estimatedElo` → `performance` in localStorage if needed.
- Calibration `cal-table` out unless trivial.

**Done when:** header click sorts home, leaderboard agents/engines, and spectator lists; sorted state visible.

## Phase 5 — Spectator board widget (before final layout tune)

- Extract `/g/` client logic toward `public-site/js/` module(s) (Playground-style `type="module"`); keep thin HTML shell from `spectator_game_page.py`.
- Replace on-screen `<img>` with read-only **cm-chessboard** 8.7.2 + Staunty + Markers; pin same CDN as Playground.
- Config: `borderType: BORDER_TYPE.none`, **`showCoordinates: true`** (inline coords like Playground — do **not** use `BORDER_TYPE.frame` “for coords”). Orientation always `COLOR.white`.
- Last-move: **explicit** markers from last UCI after each `setPosition` (Playground autoMarkers do not cover server/`setPosition` updates).
- Position: replay `GET /api/games/{id}/moves` → `plies_detail` with chess.js. No FEN on `/api/v1`. Custom `start_fen`: spectator-only field on moves payload or tip-PNG fallback.
- Download board PNG remains tip Pillow `/g/.../board.png`.
- Load cm CSS on `/g/`; size mount like Playground wrap; update `syncHeights` for non-img board.

**Done when:** `/g/` shows Staunty + inline coordinates, white-bottom; download PNG works; agents/`/api/v1` unchanged.

## Phase 6 — `/g/` layout + engine abbreviation

- After board widget exists: stretch info column to board-stack height (extend `syncHeights` like moves); widen info (~400px) + moves (~320px); retune `#board` / mount `calc(100vw - …)` for new column sum.
- Extract `abbreviateListName` to shared helper; use in Game info, Game state quality labels, board chrome / eval labels for Stockfish tags.

**Done when:** info column matches board bottom; columns wider; engine names shortened like the list.

## Phase 7 — Interactive move list + ply eval

- Clickable move rows (`data-ply`); set `viewPly`; update cm-chessboard + last-move marker; fetch eval.
- `GET /api/games/{id}/eval?ply=N` (omit = tip): rebuild fen server-side; return score/`eval_ui` only (**no fen**); ignore `last_eval_cp` for historical N; fen cache; debounce clicks.
- **Auto-tip (product rule):** on every `move_count` increase, always set `viewPly` to tip and refresh (scrubbing is interrupted by new live moves — intentional).
- Selected-ply highlight; clickable white and black cells in a row; no move input on board.
- Tests: no fen in eval JSON; ply scores differ; `/api/v1/.../moves` 404; widget + `data-ply` markup.

**Done when:** click move → that position + eval; any new live move jumps view to tip; no FEN leakage.

## Order

1 → 2 → 3 → 4 → 5 → 6 → 7  

Phase 1 first (ladder correctness). Board widget (5) before layout tune (6). Scrubbing (7) last.

## Verify

- Same-model AvA: Elo unchanged; not in rated Games; quality still ok; rebuild skips them.
- Home: no Model id; wider; Games includes AvH; Performance; sortable; provisional still rated.
- Lists: Acc. + Performance; dates `22:24 1/08/26`; sortable; Performance not bold.
- `/g/`: cm-chessboard + coords; short engines; full-height info; wider columns; scrub + auto-tip; download PNG tip-only.
- Focused tests only.

## Estimated duration

- Phase 1 — Same-model AvA: unrated, no Elo: 1–2 agent-hours
- Phase 2 — Performance rebrand + dates + games-table chrome: 1.5–2.5 agent-hours
- Phase 3 — Games count + home table shape: 1.5–2.5 agent-hours
- Phase 4 — Sortable tables: 1.5–2.5 agent-hours
- Phase 5 — Spectator board widget: 2.5–4 agent-hours
- Phase 6 — `/g/` layout + engine abbreviation: 1–2 agent-hours
- Phase 7 — Interactive move list + ply eval: 2.5–4 agent-hours
