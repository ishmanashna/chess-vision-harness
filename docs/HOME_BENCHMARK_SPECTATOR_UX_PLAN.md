# Home benchmark, board text, and spectator UX

Home ladder naming/metrics, agent board-text framing, blank spectator boards, AvH chat toggle placement, last-move highlighting, and right-click arrows on watch/play boards.

## Scope

- Home table: rename Leaderboard → Benchmark; replace Games with puzzle Elo; add % pieces.
- Site copy/nav: user-facing “Leaderboard” → “Benchmark” (Home heading, nav labels, `/leaderboard/` page title/heading). Keep URL path `/leaderboard/` (no route rename).
- Agent briefs (games, AvA, AvH, puzzles, identify) + `AGENTS.md` / shared board-text helper: PNG and authenticated `board.txt` are both valid ways to read the board; PNG preferred for vision; drop “fallback-only” framing.
- Spectator `/g/`: fix boards that appear empty; move AvH “Show chat”; last-move highlight via square colors; user-drawn arrows (and square marks) on `/g/`, `/p/`, `/i/`, and `/play/` (human side).

## Out of scope

- Renaming API paths (`/api/leaderboard/*`) or rewriting snapshot filenames.
- Changing puzzle Glicko or identify scoring formulas.
- Agent ladder Elo column removal on Home (Elo stays).
- Full `/leaderboard/` column redesign beyond the Benchmark rename.

## Product decisions (locked)

1. **Home columns:** `#`, Agent, Elo, Accuracy, Performance, **Puzzles** (puzzle Elo / `puzzle_rating`), **% pieces** (`identify_mean_accuracy`). Drop Games from Home only (full Benchmark page keeps its richer columns).
2. **Naming:** UI string “Benchmark”; path stays `/leaderboard/`.
3. **Board text:** Available in all modes including identify (already true). Prompt language: two ways to get the board — image (`…/board`) and compact text (`…/board.txt`); prefer the image; text is always allowed when authenticated — not a last-resort-only fallback.
4. **Blank spectator:** Treat collapsed board CSS (`calc(100vw - 560px)` can go ≤0) and zero-size cm-chessboard init as primary bugs; also ensure first paint always runs from moves payload when state loads. Idle `*` games with 0 moves still show the starting position (not a bug).
5. **Show chat:** Move toggle out of the info-column header that fights height sync — place it as a compact control on the board stack (near the top player label) or as a text link in the Game info card footer; default open = game info.
6. **Last move:** Stop using `MARKER_TYPE.frame` outlines. Use filled square highlights (distinct colors for from/to, readable on light and dark squares) via Markers square style / CSS — same approach on spectator boards; play board last-move should match.
7. **Arrows:** Lichess-style — right-click-drag draws an arrow; right-click square marks the square; left-click clears annotations. Implement with cm-chessboard Arrows + Markers (custom pointer handlers on 8.7.2, or bump CDN to a version that ships RightClickAnnotator if that is lower risk). Not persisted; clear on new tip position / scrub. Enable on game/puzzle/identify spectator and human `/play/`.

---

## Phase 0 — Home Benchmark + board-text framing

**Goal:** Home table and site labels say Benchmark with puzzle Elo + % pieces; agent prompts treat `board.txt` as a normal board channel.

**Work**

- `public-site/index.html`: heading/nav; Home thead Games → Puzzles (`data-sort="puzzle_rating"`); add % pieces column; adjust `data-*` / colspan expectations.
- `public-site/js/common.js`: Home row rendering for the new columns (not only when `data-show-unified-stats`); col counts for Home vs full page.
- Nav + `/leaderboard/` visible titles: Benchmark (keep href `/leaderboard/`).
- `agent_board_text.py`, `agent_brief.py`, `puzzle_brief.py`, `identify_brief.py`: reword; rename helper away from “fallback” if the name is user/agent-visible.
- `AGENTS.md` (and brief-adjacent operator lines if they repeat the fallback sentence): same framing for games, puzzles, identify.

**Done when**

- Home shows Puzzles Elo and % pieces for agents that have data; no Games column on Home.
- Nav/Home/`/leaderboard/` headings say Benchmark.
- Identify/puzzle/game briefs mention `board.txt` as an alternate board read, not “only if PNG fails.”

**Verify**

- Open `/` Online: columns match; puzzle Elo / % paint from live API.
- Grep briefs for “fallback” in agent-facing strings — none left in play-loop wording (internal code comments OK if needed).

---

## Phase 1 — Spectator blank board fix

**Goal:** `/g/{id}` always shows a usable board for games with moves (including `game-xlQLSXZHy6cwq4sMk9if_w`).

**Work**

- Fix `.spec-board-wrap` / `.watch-board-wrap` width so `100vw - 560px` cannot collapse the board (floor with `max(…, min-size)` or drop the hostile term on desktop).
- After cm-chessboard create + first `syncTip`, force a layout/resize once heights are known.
- Harden first-load path: if state fetch succeeds, always fetch moves and `syncTip` even when `move_count` is missing/null on list-derived views (state already has move_count for detail).
- Add a regression note/test or CSS assertion that board wrap width is never 0 under typical viewport math.

**Done when**

- Opening `game-xlQLSXZHy6cwq4sMk9if_w` shows pieces at the final position locally and on Pages.
- Mid-width desktop viewports still show a ≥~240px board.

**Verify**

- Manual `/g/game-xlQLSXZHy6cwq4sMk9if_w`; DevTools computed width of `#board` / wrap > 0.
- Spot-check one 0-move `*` game still shows starting setup.

---

## Phase 2 — Chat toggle, last-move colors, arrows

**Goal:** AvH chat control stops fighting the layout; last-move uses colors; arrows work on all watch boards + human play.

**Work**

- Relocate `#info-panel-toggle` per locked decision; update `watch.css` / `spectator-game.js` so info-col height sync no longer depends on that header row.
- `spectator-board.js` (+ play-board last-move): colored square markers instead of frames; theme-aware CSS.
- Shared annotation helper (new small module): Arrows + square marks, right-click draw, left-click clear; wire into spectator-board, puzzle/identify boards, play-board. Load arrows.css on those pages. Clear annotations on tip sync / scrub / human move apply.

**Done when**

- AvH spectator: chat toggle does not steal info-column header space or collapse layout.
- Last move reads as colored squares, not inner frames.
- Right-click arrows/marks work on `/g/`, `/p/`, `/i/`, `/play/`; left-click clears.

**Verify**

- AvH `/g/` and `/play/` chat still works.
- Draw arrow, scrub a ply (spectator) — annotations clear or stay consistent with locked behavior (clear on scrub/tip).
- Light and dark themes: last-move colors remain visible.

---

## Order

0 → 1 → 2 (sequential).

## Implementation notes for agents

- Read `PRODUCT.md` and `ARCHITECTURE.md` at session start.
- Do not run git or the full test suite; targeted tests only.
- Do not wipe harness data or change Elo formulas.
- Prefer one subagent per phase.

---

## Estimated duration

- Phase 0: 3–5 agent-hours
- Phase 1: 2–4 agent-hours
- Phase 2: 5–8 agent-hours
