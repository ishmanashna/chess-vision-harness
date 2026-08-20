# Puzzle and identify watch (playtest)

Operator playtest of puzzles and board identification. Watch pages, selection, finish overlay, and agent briefs. Not polish: several items are backend contract changes.

## Scope

- Launcher must not dump the operator onto `/p/{id}` or `/i/{id}` until the agent has actually opened that attempt.
- Spectators see the puzzle solution (and identify placement map) while the attempt is live, not only after it ends.
- Puzzle Glicko line is readable (no unexplained plus-minus).
- After a finish, auto-follow the agent to the next attempt, with a delay so the result is visible first.
- Attempt ID wrap + Copy ID, same treatment as Game ID (do not shorten tokens).
- Attempt chain is a prev/next panel, not a growing list.
- Finish overlay on the board: correct move plays; wrong/illegal freeze the position; red/green arrows; static side-to-move label; illegal called out; moves column coloring.
- Puzzle (and identify) selection matches agent skill; new agents start easy and climb.
- Side to move sits at the bottom of the spectator board, the agent PNG, and `board.txt`.
- Public watch must not 500 after an illegal move.
- Identify Windows JSON curl example; stronger UCI preference; `board.txt` file-column check.
- Localhost-only panel: the imported puzzle set, with counts, difficulty spread, attempts, and solve rate.

## Out of scope

- Ladder Elo, Play rating, or Glicko-2 math (scale, tau, volatility). Only the **starting** agent puzzle rating and **which puzzle is picked**.
- Shortening `pz-` / `bi-` / `game-` token length.
- Forbidding SAN in the move API (UCI is preferred in prompts; SAN still parses).
- Recalculating ratings already stored in `puzzle_ratings.json`.
- Operator re-fetch of the Lichess dump (the localhost panel shows the floor; selection must degrade if the corpus is thin).
- Publishing the puzzle-set table to Pages or the public leaderboard.
- Imagine, AvH chat product, or engine calibration.

---

## Verified causes

**Redirect before the agent joins**  
`launcher.js` `showPuzzleResult` POSTs `/puzzles/start` or `/identify/start` and `location.assign`s `/p/{id}` or `/i/{id}` after 4s. Playground waits on `agent_joined` (`create-human-wait.js`). Puzzle and identify attempts have no join flag. `start` already picks the position, so the watch page exists before the agent has fetched the board.

**Solution hidden until replay**  
`puzzle_observer.observer_state` omits `solution_moves`. `identify_observer.observer_state` omits `correct_pieces`. Replay is 409 while active. `leak_guards.py` treats those keys as secrets. Watch JS only paints the solution after `/replay`. Identify’s board PNG already *is* the position; the JSON map is what is hidden.

**Confusing `858.4 ±167.3`**  
`puzzle-watch.js` `renderAgentMetrics` appends ` ±` + Glicko **rating deviation (RD)** next to the rating. New agents are `1500 ±350`. That is uncertainty, not a plus-score and not the puzzle’s imported difficulty (`#state-difficulty`).

**No auto-follow**  
Chain poll (`GET .../public/attempts?by_key=`, every 15s) only renders `<a>` links. Watch JS never navigates. `.follow-banner` CSS exists and is unused.

**Attempt ID line-breaks**  
IDs are `pz-` / `bi-` + `token_urlsafe(16)`, same length class as Game ID. Game page got `.meta-game-id` wrap-anywhere + Copy ID. Puzzle/identify `renderMeta` dumps the raw id into `<dd>` with generic `break-word`. Same visual bug, not a shorter-id bug.

**Chain is a list**  
`#chain` is a `<ul class="chain-list">`. API already returns newest-first rows keyed by fingerprint.

**Finish board fights the puzzle**  
On a **legal wrong** move, `apply_submission` does not update `board_fen` (correct). Then `replay_payload` `_build_plies` **pushes** that wrong move, `loadReplay` jumps to a position that never existed live, and `turnLabel` reads the scrub FEN so “Black to move” flips. Illegal well-formed UCI is stored, then `san_moves` calls `board.san(move)` without catching `IllegalMoveError` → **HTTP 500** on `GET /api/v1/puzzles/public/{id}` (“Could not load puzzle state”). Failure reason stays replay-only, so the spectator only sees “Failed”.

**Puzzles not tailored; too hard**  
`puzzle_start` / `identify_start` call `PuzzleStore.random_puzzle` with launcher-omitted `rating_min`/`rating_max` → uniform random over the whole imported set. Agent Glicko is never read. New agents start at **1500** (`puzzle_ratings._agent_record`) against a corpus fetched at `Rating <= 1500` (`puzzle_fetch` default). Vision agents miss a lot and fall (e.g. 858). Easy rows can exist in a `max_rating=1500` dump, but they are not preferred.

**Always white at bottom**  
Agent PNG (`puzzles_api._render`), public PNG, cm-chessboard (`orientation: COLOR.white`), and `format_board_text` are locked white-bottom. `render_pillow` already supports `bottom_color="black"`. Briefs and `AGENTS.md` say a1 is bottom-left. Lichess puzzles are often Black to move after the setup ply.

**Identify curl JSON on Windows**  
`identify_brief.py` example is `curl.exe -d "{\"pieces\": ...}"`. PowerShell treats `\"` as end-of-string; the body becomes `{\` → FastAPI 422 `json_invalid`. File-based `-d @answer.json` works. Malformed JSON does **not** end the attempt. AvH chat curl uses the same fragile inline JSON.

**SAN vs UCI**  
Briefs say “UCI or SAN” equally. Parsers try UCI first, then SAN. Ambiguous SAN and `+` in URLs fail. Agents already prefer UCI; prompts should say so.

**`board.txt` file columns**  
`format_board_text` is a fixed 8-file, one-char cell grid, files a→h, ranks 8→1, never flipped today. Tests assert 9 tokens per rank row. The “unreliable columns” claim after a failed identify is almost certainly model error. After we flip for Black to move, the legend must describe the **visible** file order or it *will* become a real bug.

**No way to see the imported set**  
`chess-harness puzzles stats` prints total, average rating, and theme counts — no min/max, no histogram, no per-puzzle attempts. The public puzzle leaderboard content view is the **25 most-attempted** puzzles only (`PUZZLE_CONTENT_LIMIT`), and never-played rows are invisible. Calibration is the only localhost operator page today (`common.js` `ensureCalibrationNav`). There is no table of “what is actually in the store.”

---

## Product decisions (locked)

1. **Join = first authenticated board read.** Set `agent_joined` on puzzle/identify when the owning key `GET`s `/board` or `/board.txt`. Not on `start`, not on the first move/answer. Launcher keeps the brief and waits (playground pattern). Watch page may still open; show “Waiting for agent…” until joined. Public observer includes `agent_joined`.

2. **Spectators see the answer live.** Public observer always includes puzzle `solution_moves` (UCI) and identify `correct_pieces`. This is an operator product; agents must not use `/api/v1/puzzles/public/*`, `/api/v1/identify/public/*`, or `/p/` `/i/` pages as a solving aid (add to the forbidden list). Replace “must not leak” tests with “solution is present on live observer” tests. Agent review/start APIs stay unchanged (agents still should not be *told* the solution in their own brief).

3. **Glicko headline is an integer rating.** Drop `±RD` from the visible line. If RD is still high (`> 200`), a quiet “provisional” (or equivalent) is enough. Tooltip may explain RD as uncertainty. Do not make it look like Elo ± error. Difficulty stays the imported puzzle rating.

4. **New puzzle agents start at 800**, deviation still 350. Glicko-2 conversion center stays 1500. Existing stored ratings are not rewritten. Identify has no Glicko.

5. **Selection follows the agent.** When the client omits `rating_min`/`rating_max`, `start` bands around the agent’s current puzzle rating (window about ±200, extra downward bias while RD is high). If the band is empty, widen until something in the corpus hits; never 404 a non-empty store just because the band was tight. Explicit query params still override. Identify start uses the same imported rating field: few finished identify attempts → prefer the easy end of the corpus, same widen-if-empty rule.

6. **Auto-follow after a visible result.** When the chain’s newest id is not the page you are on, wait ~5s (banner + Stay), then go. Poll the chain faster after finish. Identify same.

7. **Attempt IDs stay long.** Wrap + Copy ID, same as Game ID. Do not shrink `token_urlsafe`.

8. **Chain panel.** Prev / next (older / newer) and “n of m”. Optional compact label for the current attempt. No long link list.

9. **Finish overlay (puzzles).**
   - **Correct:** play the agent’s move on the board as today (including the puzzle’s auto-reply on the success path).
   - **Wrong (legal):** do **not** change the position. Red arrow = agent move, green arrow = first remaining solution move. Reuse annotation arrows with distinct colors.
   - **Illegal:** same freeze. If from/to parse, red arrow only; always label the outcome **Illegal move**. Green arrow still shows the correct move.
   - **“White/Black to move”** is the puzzle’s start side for the whole attempt, including after finish. It never follows a pushed ply.
   - Moves column: green/red (or existing `.is-wrong` plus a solved style) so the line matches the board.
   Identify finish stays square markers (already), not move arrows.

10. **Playing side at the bottom.** For puzzles and identify, `bottom_color` follows FEN side-to-move on **agent PNG, public PNG, spectator widget, and `board.txt`**. Square names stay absolute. Briefs must not say “a1 is always bottom-left”; they say the moving side is at the bottom and labels on the image match that view. Game ladder PNG stays white-bottom unless a later game plan says otherwise.

11. **Windows identify (and AvH chat) curl.** Primary example is `curl.exe -d @answer.json` (or equivalent file body). No inline PowerShell JSON. Schema in prose stays. 400/422 still do not end the attempt.

12. **Prefer UCI** in puzzle, game, and `AGENTS.md` move wording. SAN remains accepted.

13. **Localhost puzzle-set panel.** Same host gate as Calibration nav (loopback only, never on Pages). Path `/puzzle-set`. Summary plus a sortable table of **every imported puzzle**, not a top-25. Identify uses the same corpus, so each row can show puzzle-solve stats and identify stats side by side. No solutions in this table (open a watch link if you need the line). CLI `puzzles stats` can keep working; the page is the operator surface.

---

## Phase 0 — Watch 500 and replay truth

**Goal:** Public puzzle state never 500s on an illegal or wrong move. Replay FEN matches what the agent actually saw.

**Work**

- `san_moves` / `_build_plies` in `puzzle_observer.py`: never call `board.san` on an illegal move; catch `ValueError` and python-chess illegal/ambiguous errors; leave `board_fen` as the last legal position.
- Do not push a terminal wrong or illegal move onto replay plies. Replay final FEN equals `record["board_fen"]`.
- On finished attempts, put `failure_reason` and `first_wrong_move` on `observer_state` (needed by later overlay/copy).
- Wrap public puzzle/identify JSON routes so unexpected exceptions become a logged 500 with a stable body, not a framework traceback page.

**Done when**

- Illegal UCI (well-formed but not legal) and garbage tokens both return 200 public state, `fen` unchanged, `failure_reason: illegal_move`.
- Legal wrong move: public `fen` and replay last ply FEN match start (or last correct) position.
- Existing correct-solve replay still advances through solution plies.

**Verify**

- Targeted tests around `test_illegal_move_replay_records_attempt` plus a well-formed illegal UCI (e.g. a knight leap off-path) hitting `GET .../public/{id}` without 500.

---

## Phase 1 — Join before redirect

**Goal:** Create puzzle / identify behaves like playground: brief first, watch after the agent has looked at the board.

**Work**

- Persist `agent_joined` (bool + timestamp) on puzzle and identify attempt records. Set it in the authenticated `board` and `board.txt` handlers only.
- Expose `agent_joined` on public observer.
- `launcher.js`: after start, keep the copy-brief card and poll public state until `agent_joined` (same cadence spirit as `create-human-wait.js`). Then redirect. Timeout copy if the agent never comes (idle), do not silently sit forever without a line of status.
- Watch pages: if `!agent_joined` and still active, show a waiting chip; still render the board.

**Done when**

- Create puzzle/identify does not navigate to `/p/` or `/i/` before the agent’s first board GET.
- Identify has no move: board GET is enough.
- Public state includes `agent_joined`.

**Verify**

- Manual: start from launcher, confirm you stay on Create with the brief until a client hits board; then the watch page opens.
- API test: start → public `agent_joined` false → GET board with key → true.

---

## Phase 2 — Live solution for spectators

**Goal:** Operators see the answer for the whole attempt.

**Work**

- Add `solution_moves` to puzzle `observer_state` always (UCI; SAN labels optional if cheap).
- Add `correct_pieces` to identify `observer_state` always (board already shows the position; the map is for the table).
- Rewrite `leak_guards` / observer tests that forbade those keys.
- `puzzle-watch.js`: Solution column/panel from live state, not only replay. `identify-watch.js`: correct placement visible while waiting for the answer.
- Forbidden list in `AGENTS.md` and agent briefs: do not fetch public observer/replay/watch HTML to read the answer.

**Done when**

- Active public puzzle JSON includes the solution line; identify includes `correct_pieces`.
- Watch UI shows it before the agent moves/answers.
- Agent *authenticated* move/review payloads are unchanged in spirit (no new spoiler in the start payload).

**Verify**

- Start an attempt, `GET` public state before any move, solution present.
- Agent `GET .../board` still has no solution in the image or `board.txt`.

---

## Phase 3 — Finish overlay

**Goal:** After fail or success, the board and moves column tell the story without mutating a failed puzzle.

**Work**

- Cache puzzle side-to-move from `start_fen`. `#board-label-turn` uses only that.
- Success: existing ply play-out, last-move markers.
- Fail: `setPosition` to the frozen FEN; paint result arrows (red agent, green solution) via the annotation/arrow helper, not user-toggle teal. Knight legs use the same L-arrow helper as play annotations.
- Illegal: outcome text **Illegal move**; red arrow only if squares exist; green still on the correct move.
- Moves column colors match (wrong/illegal vs solved).
- Do not scrub the board on a failed attempt in a way that replays the bad ply; the list can still highlight the bad SAN/UCI.
- Identify: keep mismatch/exact square markers; they must survive orientation from Phase 6 (coordinate this in CSS/JS, implement flip in Phase 6).

**Done when**

- Failed legal move: pieces unmoved, red + green arrows, turn line still “Black to move” (or White) as at start.
- Illegal: same freeze, explicit illegal copy, no phantom piece on a destination square.
- Solved: move appears on the board as a normal ply.

**Verify**

- One Black-to-move fail, one White-to-move fail, one illegal, one mate-in-one success, watching the turn label and arrows.

---

## Phase 4 — Watch chrome (id, chain, follow, Glicko copy)

**Goal:** Readable ids, a chain you can step through, follow the agent, Glicko that does not look like a plus-score.

**Work**

- Puzzle and identify `renderMeta`: `.meta-attempt-id` + `<code>` wrap-anywhere + Copy ID (mirror game spectator).
- Replace `#chain` list with a panel: Newer / Older, index, current label. Keep using `by_key` (fallback `by_agent`).
- After finish, if chain[0] is a new attempt: show follow banner, ~5s delay, `location.assign`, Stay cancels. Faster chain poll while finished.
- Agent puzzle rating: integer, no `±deviation`. Provisional hint when RD is high. Keep Difficulty as imported rating.

**Done when**

- Long attempt ids wrap in the info column at normal type size; Copy ID works.
- Chain of 3+ attempts is stepped with buttons, not a tall list.
- Next puzzle (and next identify) auto-opens after the delay unless Stay was used.
- No `±` in the rating headline.

**Verify**

- Resize the info column; id does not overflow as a broken mid-token line without wrap.
- Two-browser: watch attempt A, agent starts B, page A shows the result then moves to B.

---

## Phase 5 — Tailored selection and an easy floor

**Goal:** Agents get puzzles near their rating; newcomers play easy ones and climb.

**Work**

- New agent puzzle rating **800** / RD 350 (`puzzle_ratings._agent_record` only; do not change `glicko2.DEFAULT_RATING`).
- Default `start` (no query band): pick using the agent’s Glicko, window ~±200, downward bias while RD > 200. Widen on empty. Honor explicit `rating_min`/`rating_max`/`theme`.
- Identify default start: if the model has few finished identify attempts, prefer lower imported `puzzle_rating` the same way.
- Puzzle brief “How selection works”: no longer “random from the whole corpus” as the default story.

**Done when**

- Bare `POST /puzzles/start` for a fresh agent returns a puzzle near the easy band, not a uniform 1500-class draw.
- Explicit `rating_min`/`rating_max` still pin the filter.
- Empty band on a non-empty corpus does not 404.
- Tests that assumed start rating 1500 are updated to 800.

**Verify**

- Fresh key: several starts, collected `puzzle_rating` values sit low.
- Agent at ~1200: starts cluster around 1200.
- Identify: first attempts prefer easier imported ratings than a saturated agent.

---

## Phase 6 — Playing side at the bottom

**Goal:** Black to move is viewed from Black. PNG, widget, and `board.txt` agree.

**Work**

- Pass `bottom_color` from FEN turn in puzzle/identify render paths (`puzzles_api`, `identify_api`, public observer PNGs).
- `format_board_text(board, bottom_color=...)`: when Black is at the bottom, files h→a left to right, ranks 1→8 top to bottom (moving side nearest the footer). Header row matches. Keep one-char cells.
- Spectator Chessboard `orientation` from the same side-to-move. Last-move markers, result arrows, identify square overlays use square names (absolute), so they follow the widget.
- Update `agent_board_text` legend, puzzle/identify briefs, `AGENTS.md`: white-at-bottom is **games**; puzzles/identify use moving-side-at-bottom; square names stay absolute; do not claim a1 is always the bottom-left pixel.
- Tests in `test_board_text.py` and render tests for both orientations.

**Done when**

- Black-to-move puzzle: agent PNG, public PNG, watch widget, and `board.txt` all have Black’s pieces at the bottom.
- White-to-move unchanged (white at bottom).
- File letters in `board.txt` match the image’s left-to-right files.

**Verify**

- Start a Black-to-move puzzle; open PNG and `board.txt`; confirm h-file is left, rank 8 nearest the bottom of the image.
- Identify position with `b` in FEN: same flip.
- Game board PNG still white-bottom.

---

## Phase 7 — Agent briefs (JSON, UCI, board.txt)

**Goal:** Copy-paste works on Windows; UCI is the recommended move form; `board.txt` files are explained, not “fixed” as if they were wrong today.

**Work**

- Identify brief: file-body curl (`-d @answer.json`) plus the JSON schema in prose. One line: PowerShell inline `-d "{...}"` will 422; that does not end the attempt.
- AvH brief chat example: same file-body (or drop JSON curl). Moves stay path-only.
- Puzzle + game briefs + `AGENTS.md`: **prefer UCI** (`g1f3`, `e2e4`); SAN accepted when unambiguous.
- Board-text legend: files are the letters on the header row, left to right, matching the PNG. After Phase 6 this must match the flipped header.

**Done when**

- Rendered identify brief has no inline `curl -d "{\"pieces\"..."`.
- Move sections say prefer UCI.
- Identify 422 still leaves the attempt active (already true; keep a regression test if missing).

**Verify**

- Brief snapshot tests.
- Mentally replay the playtest PowerShell line: the new example would not emit `{\`.

---

## Phase 8 — Localhost puzzle-set panel

**Goal:** On the machine that serves the harness, see what is imported: how many, how hard, what has been tried, what agents solve.

**Work**

- Enrich store stats (used by this page, fine if CLI picks them up too): count, rating min / median / mean / max, bucket counts (e.g. under 600, 600–800, 800–1000, 1000–1200, 1200–1500, 1500+), White-to-move vs Black-to-move, never-attempted count. Do not cap at 25.
- Operator JSON `GET /api/puzzle-set`: loopback Host only (reuse `host_is_loopback`). 403 elsewhere. Payload: the summary plus one row per imported puzzle: id, imported difficulty, side to move, themes (compact), puzzle attempts / solves / solve rate, identify attempts / full-position or mean accuracy, latest `/p/` and `/i/` watch links when any exist. No `solution_moves`, no FEN dump.
- Page `GET /puzzle-set`: loopback only (404 on Pages / tunnel host). Summary chips on top, then a sortable table (difficulty, attempts, solve rate). Filter by rating band is enough; no need for a second product.
- Nav: inject **Puzzle set** next to Calibration, same `isLoopbackHost()` helper. Not in the public header on Pages.
- Stay on serve HTML/CSS patterns already used (site header, tables like Leaderboards). Do not fold this into `/calibration`.

**Done when**

- `http://127.0.0.1:<port>/puzzle-set` shows every imported puzzle and the summary numbers.
- The same URL on the Pages host is absent (no nav, no page).
- A puzzle nobody has tried still appears (attempts 0).
- Opening the page does not require an API key.

**Verify**

- Local serve: open Puzzle set, confirm count matches `chess-harness puzzles stats`, and that easy vs hard buckets match the “puzzles feel too hard” question.
- After a few puzzle and identify runs, those rows show attempts and solve/accuracy, with a watch link.
- Pages or a non-loopback Host: `/puzzle-set` and `/api/puzzle-set` are not a public corpus leak.

---

## Estimated duration

- Phase 0: 1.5–3h (observer crash + replay FEN)
- Phase 1: 2–4h (join flag, launcher wait, watch chip)
- Phase 2: 2–4h (live solution, leak tests, forbidden copy)
- Phase 3: 3–6h (arrows, freeze, illegal, moves column)
- Phase 4: 2–4h (id, chain panel, follow, Glicko copy)
- Phase 5: 3–5h (start rating 800, banding, identify easy start)
- Phase 6: 4–7h (PNG + widget + board.txt + briefs/AGENTS)
- Phase 7: 1.5–3h (Windows JSON, UCI, legend)
- Phase 8: 2.5–4h (localhost puzzle-set summary + full table)
