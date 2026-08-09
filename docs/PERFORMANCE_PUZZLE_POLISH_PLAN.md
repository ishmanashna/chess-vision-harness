# Performance rating map + puzzle/identify spectator polish

## Why

Two connected work items from playtest feedback:

1. The leaderboard **Performance** column (play rating) is wrong. It is derived from a composite per-move quality score (Q) fitted per engine tier (`python/src/chess_harness/play_rating.py`: `Q_ALPHA=8.0`, `Q_BETA=25.0`, `fit_map_knots`, `interpolate_map`). Q saturates: every tier at 2255 Elo and above lands in the 85.3–88.7 band, the per-sample empirical fit flattens around 2000, and high engines get absurd predictions (stockfish:20 at catalog 3190 Elo is predicted ~1936). Opponent anchors, in contrast, have clean, monotone, distinctive mean accuracies (85.0 → 96.1 across tiers). The fix is a **pure accuracy→Elo map with no additional parameters**: a game's play rating is `map(mean accuracy of that game)`.

   The legacy module `python/src/chess_harness/accuracy_elo_map.py` already implements accuracy→Elo mapping (floaters calibrated by expected score vs anchors; anchors fixed catalog Elo). It is stale (no production caller). The plan productions it and deletes the composite-Q path (replace, don't stack).

2. Puzzle/board-identification spectator experiences must match the normal game spectator UI. That means both the spectator hub (`/spectator/`) and the per-attempt watch pages (`/p/{id}`, `/i/{id}`): same 3-column layout family (info | board | moves), shortened move list, exposed solution to the human watcher, puzzle id and game state, controls to examine previous puzzles the agent played in the same run, puzzle **rating delta on success/failure** plus current puzzle metrics at all times, then auto-advance to the next puzzle (agents loop indefinitely). **Themes are never user-facing** — the data stays in the attempt/puzzle records, but today's user-facing theme surfaces (watch-page tags, the content leaderboard's Themes column) are removed by P2/P5. Board identification has **no Elo rating and must not get one**: it is scored by % of the board correctly identified (exact squares vs total) and % of pieces correctly classified (misidentified count vs total), plus full-position accuracy — those metrics, not a rating, are what the identify watch page shows. Leaderboard cleanup: drop the solve-rate column for agents (only puzzle rating matters), rename the leaderboard agents table's "Puzzle rating" header to "PUZZLES", verify the ACCURACY cell color matches other metric columns.

## Scope

- Play rating semantics: per-game play rating = monotone piecewise-linear map from mean move accuracy (the already-stored per-game `accuracy`) to Elo. One map for all engines, built from sample points (engine Elo, empirical mean accuracy). Single map, no Q, no per-engine fit, no extra parameters. Rebuild endpoint and continuous calibration keep working.
- Puzzle watch page redesign; identify watch page redesign (metrics-based: board % and pieces %, no rating for identify).
- Agent briefs updated so agents keep starting new attempts indefinitely after review.
- Spectator hub gains Puzzles and Identify tabs listing public attempts.
- Leaderboard column cleanup (header, solve-rate removal, accuracy color check).
- Out of scope: ladder Elo and engine calibration math (`elo_estimation.py` — the engine-Elo/accuracy map for floaters — is untouched), AvA/human game flows, MCP, `AGENTS.md`, core docs, playground/launcher of games, `.chess_harness` data migration (existing rows keep their stored `play_rating` fields until a map rebuild recomputes them).

## Phases

### P1 — Pure accuracy→Elo play rating

Files: `python/src/chess_harness/play_rating.py`, `accuracy_elo_map.py`, `quality_finish.py`, `results.py`, `calibration_view.py`, `spectator.py` (rebuild endpoint `POST /api/calibration/rebuild-play-rating-map`), `ladder_display.py` (Performance column + tooltip), `public-site/js/common.js`, `public-site/js/engines.js`; tests `test_play_rating.py`, `test_accuracy_elo_map.py`, `test_quality_finish.py`, `test_calibration_ratings.py`, `test_calibration_parity.py`, `test_calibration_view.py`, `test_continuous_calibration.py`, `test_live_leaderboard.py`.

Work:
- Productionize `accuracy_elo_map.py`: sample points = (engine Elo, mean accuracy) from finished rated games. Anchors (opponents with fixed catalog Elo) contribute fixed Elo; floaters (stockfish:*) contribute their expected-score-calibrated Elo (existing calibration). Only engines with ≥ `MIN_GAMES_FOR_SAMPLE` (101) games become sample points; the map still builds with fewer points. Note: the legacy `collect_engine_pairs` buckets engines with ≥1 game — the eligibility filter (the ≥101 rule, already encoded in `play_rating.is_sample_eligible`) must be added to the productionized collector.
- `play_rating.py` exposes a single lookup `play_rating_for_accuracy(accuracy) -> float` via monotone interpolation over sorted sample points, clamped at both ends (no extrapolation beyond first/last knot value). Per-game rating written at finish in `quality_finish.py` = this lookup of the game's mean accuracy (already computed per game). Keep the stored row field names (`play_rating`) so leaderboards/`results.py` aggregation is untouched.
- Remove the composite-Q machinery and per-engine refit: `Q_ALPHA`, `Q_BETA`, per-move quality scoring, and the per-engine Q-based sample fitting in the play-rating path. Check consumers of `game_quality.py`'s `COMPOSITE_Q_*` constants and `composite_q_value`; wherever they feed play rating they are deleted, anything with a different consumer stays (nobody may keep a parallel dead path). `fit_map_knots`/`interpolate_map` remain as shared generic helpers because `elo_estimation.py` (floaters' Elo calibration, its own `MIN_MAP_SAMPLES`, its own q-based estimator) imports them — that module is a separate map and is untouched. If `accuracy_elo_map.py` is superseded by a merged module, delete the old file and re-point imports (no deprecated fallbacks).
- Rebuild endpoint (`POST /api/calibration/rebuild-play-rating-map`) refits the accuracy map **and recomputes the stored per-game `play_rating` of every finished result row from its stored per-game accuracy** (rows written before this change hold Q-era values; leaving them makes the Performance column mix two semantics). The refit is operator-triggered only (the legacy `schedule_map_refit` hook has no callers — do not re-add one); continuous calibration only appends quality samples and refreshes snapshots, no change needed there. Public snapshots are re-exported after every rebuild.
- Tooltip text stays accurate ("move accuracy via the calibration accuracy→Elo table") — adjust only if wording no longer matches.

Done when:
- No composite-Q per-engine fitting remains in the play-rating/leaderboard path (the generic knot helpers and `elo_estimation.py`'s floater map are shared/untouched, not dead paths).
- `play_rating_for_accuracy` is strictly monotone over the observed accuracy range; rebuilt map from the live corpus gives sensible monotone Performance (e.g. stockfish:20 clearly above the strongest anchors, weakest engines at the bottom, no ~2000-flat region).
- Targeted tests updated and passing; legacy accuracy-map tests repurposed to the new single-map semantics.

### P2 — Puzzle watch page mirrors the game spectator layout

Files: `python/src/chess_harness/puzzle_observer.py` (template + styles + `public_attempt_row`), `spectator_game_page.py` + `public-site/js/spectator-game.js` (layout patterns to mirror: 3-column grid info | board | moves, syncHeights, board status line), `public-site/js/puzzle-watch.js`, `site.css`, `puzzle_api.py`, `puzzle_brief.py`, `python/src/chess_harness/puzzle_attempt.py` (attempt records: no session id, grouping via `key_fingerprint`); tests `test_puzzle_observer.py`, `test_puzzle_api.py`, `test_agent_brief.py`, `test_spectator_ui.py`.

Work:
- Rebuild the `/p/{id}` page on the game-spectator grid family: left info column, center board column (board + "White to move/Black to move" label), right moves column.
- Info column (watcher-facing): attempt id, agent name, puzzle id (visible only after finish, with solution), status ("Solved/Failed/in progress"), difficulty, and at all times the agent's current puzzle metrics (rating, deviation, attempts, solves). On finish: rating before → after with delta.
- Moves column: shortened SAN move list (same compact style as the game move list) for the agent's submitted moves; after finish the full solution line is shown as the replay list (existing `replay_payload` plies, re-rendered as the moves column instead of step chips), with the first wrong move flagged. The live observer state does not currently include the agent's moves (only `moves_played`); extend `observer_state` in `puzzle_observer.py` with `submitted_moves`/`opponent_moves` (SAN labels) — they are not secret, only the solution is.
- Themes are never rendered: remove the themes field from the public surfaces in `puzzle_observer.py` — `observer_state`, `public_attempt_row`, and `replay_payload` (the public replay endpoint serves it too) — and delete the theme-tag rendering from the watch page. The theme stays only inside attempt/puzzle records.
- Attempt chain: attempts carry no session id (`session_exclude_sec` is only a re-selection time window per key); attempts are grouped by the pseudonymous `key_fingerprint` on the record. Add `key` (the fingerprint) to `public_attempt_row` and a `?by_key=` filter on `/api/v1/puzzles/public/attempts`; the watch page renders a "Attempt chain" block — the agent's other puzzles in the same run (newest first, each linkable to `/p/{id}`), including the awkward case of a few concurrent attempts per key (chain is still correct, just interleaved).
- Auto-follow: when the attempt finishes, keep polling the public attempts list for the same `by_key`; when a newer attempt appears, show "Agent started the next puzzle" and re-point the page to it (URL replaceState + repoll) after a short delay (e.g. 10s) so the human can read the review first; the attempt chain keeps the history reachable.
- Brief: `puzzle_brief.py` appends the continuous-loop contract: after `review`, start a new attempt (`POST /api/v1/puzzles/start` with the same key) and keep going indefinitely; report the rating delta after each attempt.

Done when:
- `/p/{id}` layout matches the game spectator (same grid family, shortened move list, board left-center-right ordering); solution and puzzle id shown after finish; no themes anywhere in public payloads or UI; attempt-chain navigation and auto-follow work via `by_key`; live observer state includes the agent's SAN moves; `public_attempt_row` includes `key`; brief text covers the perpetual loop.

### P3 — Identify watch page mirrors game spectator (metrics-based, no rating)

Files: `python/src/chess_harness/identify_observer.py`, `public-site/js/identify-watch.js`, `identify_api.py`, `identify_brief.py`, `puzzle_leaderboard.py` (`build_identify_leaderboard` — reads the agent's running means), `public-site/js/puzzle-leaderboards.js`; tests `test_identify_api.py`, `test_puzzle_observer.py` (pattern), `test_agent_brief.py`, `test_puzzle_leaderboards.py`.

Work:
- **No rating for identify** — by design it is scored by correctness percentages. Rebuild `/i/{id}` on the same 3-column grid as P2: info column, board column, right column = the per-square results table (submitted vs expected per square, green/red status) rendered like a move list, plus the answer overlay on the board after finish.
- Info column: attempt id, agent name, status ("Submitted/In progress"), difficulty. At all times show the agent's current identify metrics (mean placement accuracy, full-position solve rate) from a NEW `GET /api/leaderboard/identify/live` endpoint (mirror of the existing puzzles live route: `build_identify_leaderboard` behind the 5s TTL cache, plus a proxy route in `public-site/functions/_proxy.js`); the watch page polls it and matches by agent name. On finish, show the attempt's score: board % (exact/total squares), pieces % (misidentified vs total), full-position hit/miss, missing/extra counts — drawn from the existing `score` dict (`total_pieces`, `exact`, `missing`, `extra`, `misidentified`, `full_position`, `accuracy`). No rating, no delta — the "progress" notion is the attempt score against the agent's running means.
- Attempt chain + auto-follow via `by_key`, same as P2 (add `key` — and, for the hub tables in P4, `full_position` + `total_pieces` — to `public_attempt_row` in `identify_observer.py`; `?by_key=` filter on `/api/v1/identify/public/attempts`).
- Brief: `identify_brief.py` continuous loop (after review → `POST /api/v1/identify/start` → repeat), reporting per-attempt percentages.

Done when:
- `/i/{id}` mirrors the P2 layout with the results table as the right column; the info column shows agent identify metrics at all times and attempt score percentages on finish; no rating concept added anywhere (leaderboard untouched in that respect); attempt chain and auto-follow work; brief updated.

### P4 — Spectator hub: Puzzles and Identify tabs

Files: `spectator.py` (`/spectator/` route), the spectator page template (panels `data-spec-panel` / tabs `data-spec-tab`), `public-site/js/spectator-tabs.js`, NEW `public-site/js/attempts-list.js` (or reuse `games-list.js` patterns), `public-site/js/table-sort.js`, `site.css`; tests `test_spectator_list.py`, `test_spectator_ui.py`.

Work:
- Add two tabs to the spectator hub alongside Active/Completed/My Games: "Puzzles" and "Identify". Each tab renders a sortable table fed by `/api/v1/puzzles/public/attempts` and `/api/v1/identify/public/attempts` (status optional filter; newest first): columns Attempt (link to `/p/{id}` or `/i/{id}`), Agent, Status, Result, Moves, Started; puzzles additionally show the puzzle rating, identify rows show accuracy % (and full-position %) after finish. Active and finished attempts shown with a status column (no extra sub-tab needed). Poll on tab activation like the games list; empty states with helpful text.
- No themes in these tables or anywhere else user-facing. Guard the public `by_key` parameter with the existing public-API rate limits (no unbounded scanning loops over attempts).

Done when:
- `/spectator/` shows the two extra tabs, tables sort and link into the watch pages, live-update on activation, and empty states render; no legacy endpoints used; no user-facing themes anywhere.

### P5 — Leaderboard metric cleanup

Files: `public-site/js/common.js` (header + row renderer, `puzzle_solve_rate` definitions), `public-site/js/puzzle-leaderboards.js` + `python/src/chess_harness/puzzle_leaderboard.py` (content-table Themes column), `public-site/leaderboard/index.html`, `snapshot_leaderboard.py` (agent row field), `site.css`; tests `test_snapshot_leaderboard.py`, `test_live_leaderboard.py`, `test_leaderboard_polish_phase1.py`, `test_puzzle_leaderboards.py`.

Work:
- Leaderboard-tab agents table (rendered through `common.js` `renderLeaderboardRows`; the home page has no puzzle columns — its unified stats are gated by `data-show-unified-stats`): rename the "Puzzle rating" header to "PUZZLES"; delete the solve-rate column. Keep the per-puzzle content leaderboard's solve rate (it is puzzle-level info, not an agent metric); keep identify columns untouched.
- Drop `puzzle_solve_rate` from agent snapshot rows (`snapshot_leaderboard.py`) and the row-mapping in `common.js`.
- Delete the Themes column from the puzzle content leaderboard (the `<th>Themes</th>` in `public-site/leaderboard/index.html`, the content `"themes"` field in `puzzle_leaderboard.py`'s content rows, and its rendering in `public-site/js/puzzle-leaderboards.js`). With P2's payload changes this makes themes fully non-user-facing while the data still lives in the records.
- Verify ACCURACY cell color: cells render as plain `<td>`; only `.elo` is bold by design. Confirm in code and in the rendered pages that the accuracy cell color equals other metric columns; fix only if a stray class/rule differs.

Done when:
- The leaderboard agents table shows "PUZZLES" and no solve-rate column anywhere agent-facing; the puzzle content table keeps its solve rate but loses its Themes column; rendered accuracy cells visually identical in color to the other metric columns.

## Order

P1 first (metric correctness is the foundation). Then one wave of P2 + P3 + P4 (independent: distinct pages/JS/templates; P4 links to URLs that P2/P3 do not change). P5 last (touches `common.js` and snapshots after P1's row fields settle). Run phases sequentially within the wave only if unexpected shared-file conflicts appear (e.g. `public_attempt_row` changes: P2 and P3 each update their own module's row; P4 consumes the result).

## Verify

Per phase, run its targeted test files (never the full suite):
- P1: `test_play_rating.py`, `test_accuracy_elo_map.py`, `test_quality_finish.py`, `test_calibration_ratings.py`, `test_calibration_parity.py`, `test_elo_estimation.py`, `test_live_leaderboard.py`.
- P2: `test_puzzle_observer.py`, `test_puzzle_api.py`, `test_agent_brief.py`, `test_spectator_ui.py`.
- P3: `test_identify_api.py`, `test_puzzle_observer.py`, `test_agent_brief.py`, `test_puzzle_leaderboards.py`.
- P4: `test_spectator_list.py`, `test_spectator_ui.py`.
- P5: `test_snapshot_leaderboard.py`, `test_live_leaderboard.py`.

Manual (one serve at the end): `chess-harness serve`, then:
- Calibration tab → rebuild play-rating map; check `/leaderboard/` Performance is monotone across engines (weakest < anchors < stockfish:20).
- Launcher → Puzzles and Identify flows; watch `/p/{id}` and `/i/{id}`: layout, solution/puzzle id after finish, puzzle rating delta (puzzles), attempt board/pieces percentages + running metrics (identify), attempt chain, and auto-follow to the next attempt while the agent keeps going.
- `/spectator/` Puzzles + Identify tabs: rows (no themes), links, sorting, empty state.
- Leaderboard tab: "PUZZLES" header, no solve-rate column, accuracy color identical to other cells.

## Estimated duration

- P1 (accuracy→Elo map rewrite + tests): 6–10 h
- P2 (puzzle watch page + attempt chain + auto-follow + brief): 6–9 h
- P3 (identify watch page + metrics + auto-follow + brief, no rating): 5–8 h
- P4 (spectator hub tabs + attempts lists): 4–6 h
- P5 (leaderboard cleanup): 1–2 h