# Play and spectator UX (human-play feedback)

Fix the AvH play board, spectator game page, launcher nickname, agent continue-playing copy, and Home Strength wording from the human-play session. One shared last-move look. Chess-app annotation behavior. No layout-shifting header.

## Scope

- Last-move square colors (play, spectator, and puzzle watch; same treatment).
- Right-click arrows and square highlights (toggle, no stack, no preview, knight L-arrows, cleaner color).
- Play page chrome: drop the shifting matchup header; fix rail names when the human is Black; turn status lives somewhere that does not move the board.
- Playground nickname after inscribe.
- Agent brief + launcher copy: agent keeps polling with its own tools; human never re-prompts.
- Spectator Game ID: readable, not tiny ellipsis.
- Show chat / Show game placement.
- Move-list auto-scroll to the real bottom on a new ply (play, spectator at tip, puzzle live).
- Premove: piece lands like a real move, not a frozen drag ghost.
- Home Strength copy: accuracy-based, move-by-move Elo-scale estimate.

## Out of scope

- Imagine API deletion (already unpublished from agent prompts).
- Illegal-move error copy (stay silent).
- Changing Strength/Performance formulas or ladder Elo.
- New annotation colors beyond one default (no Lichess shift-click color cycle unless we already have it).
- Persisting arrows across refresh.

---

## Verified causes

**Ugly last-move colors**  
Shared in `public-site/css/watch.css`: `--last-move-from-fill: rgba(205, 210, 55, 0.58)` and `--last-move-to-fill: rgba(155, 199, 0, 0.62)` (dark theme similar). High-opacity neon yellow-green on filled `markerSquare`. Play and spectator already share `board-last-move.js` (`paintLastMoveMarkers`). Spectator is not a separate old-line path in HEAD; it looks bad because the palette is bad, and any leftover arrow/frame last-move must not come back. Puzzle and identify watch never call `paintLastMoveMarkers`. Play also sets `autoMarkers: MARKER_TYPE.square`, which can stack a faint drag square on the same last-move squares (spectator uses `autoMarkers: null`). Identify review calls `board.removeMarkers()` with no args and would wipe last-move if we add it there. Identify stays static (no last-move). Do not adopt cm-chessboard `RightClickAnnotator` (8.12): it still previews arrows and still draws knights as diagonals. Stay on 8.7.2 and fix `board-annotations.js`.

**Annotations unlike other chess apps** (`public-site/js/board-annotations.js`)

- Left-click clears everything (keep as the “get rid of them” action, plus per-item toggle).
- `addArrow` / `addMarker` always append. Same square or same from-to stacks.
- `onMouseMove` draws `ANNOTATION_PREVIEW_ARROW_TYPE` (user: no previsualization).
- Knight from-to is one straight cm-chessboard arrow (looks like a diagonal).
- Color is a saturated blue (`--annotation-arrow-color`).

**Layout-shifting header**  
`play/index.html` `[data-play-header-line]` is filled by `updatePlayHeader` as `Human vs Grok 4.6 High (500*) · you play black · Your turn`. Status and name length change the line height and shove the whole `play-layout` down.

**Wrong name on “my” rail**  
DOM is always Black label on top, White on bottom (`play/index.html`). Board orientation flips when the human is Black (`play-board.js` `orientation: humanSide`). Rails do not swap. Bottom label stays White = agent, so the tag next to the human’s pieces says the agent name.

**Nickname after inscribe**  
`#human-nickname` ships `disabled`. `launcher.js` `enableForm(online)` enables model selects, inscribe, and submit, but never `nicknameEl`. The field stays disabled even when the playground row is visible. Legacy `human-hub.js` already includes `humanNickname` in its enable list; copy that pattern. Server `POST /api/v1/games/human` already accepts `nickname`.

**Human re-prompting the agent**  
AvH brief tells the agent to sleep/poll, but never says the human will not send another chat. Launcher result: “Paste the brief into your agent.” Playground aside: “copy the brief into your agent, then wait here.” Operators re-prompt when the agent stops. Puzzle brief already has keep-playing language; AvH should match that tone.

**Tiny Game ID**  
Spectator `watch.css`: `.meta-game-id code { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 0.82em; }` inside a tight `meta-grid`. That was the shrink-to-fit fix.

**Show chat**  
Spectator: “Show chat” sits in `.info-col-footer` under the info stack; “Show game” sits in the chat header. Asymmetric and easy to miss.

**Move list not quite at the bottom**  
Play `renderMoveList` uses `scrollIntoView({ block: "nearest" })` on `.on`. Nearest scrolls the minimum to make the cell visible; the 14px bottom padding then looks like it stopped short. Spectator at tip uses `scrollTop = scrollHeight` plus one rAF, but `syncMovesScroll` runs before `syncHeights()`, and the board `ResizeObserver` resizes the column without re-pinning. Puzzle live `renderLiveMoves()` passes `interactive: false` and never scrolls at all.

**Premove freeze**  
`play-board-premove.js` `validateMoveInput`: on success `enqueue(..., { deferDisplay: true })` then **`return false`**. Comment: “Enqueue and snap the piece back.” `queueMicrotask` `syncDisplay(false)` can run before cm-chessboard finishes tearing down the drag sprite (`moveInputProcess`). Real moves in `play-board.js` wait on `moveInputProcess.then(() => syncDisplay(true))`. Premoves also paint `PREMOVE_MARKER` on both from and to, which looks like highlights rather than a piece that moved.

**Home Strength copy**  
`index.html` body: “Strength is a casual shorthand … (less precise than Elo).” Column title: “Shorthand strength estimate … less accurate than Elo.” That undersells the intent: accuracy mapped to the same numeric scale as Elo, move by move.

---

## Product decisions (locked)

1. **Last-move:** one filled-square style for play, spectator, and puzzle watch. Muted amber/gold (chess.com / Lichess last-move family), from slightly paler than to. No last-move arrows, frames, or neon lime. Dark theme uses the same hue at slightly lower opacity. Identify stays without last-move (static positions). Do not bump to RightClickAnnotator for this.
2. **Annotations (Lichess-like, simpler):**
   - Left-click empty board (or left-click that is not a piece drag): clear all marks.
   - Right-click a square: toggle that highlight (second click removes it).
   - Right-drag between squares: toggle that arrow (same from-to removes it). No stacking.
   - No ghost/preview arrow while dragging.
   - Knight: two-segment L (longer leg first: ±2 then ±1). Not a diagonal. First segment no arrowhead if the widget allows it; otherwise two full arrows through the corner square.
   - Cleaner default: one muted green or teal for arrows and square marks (not last-move gold, not neon blue). Same on play and spectator.
3. **Play header:** remove `[data-play-header-line]` / `.play-header`. Matchup lives only on the rails. Turn/result is a **fixed-height** chip under the board (same row as cancel-premove, or a dedicated slot that never changes height). Document title can still flash “Your turn”.
4. **Rails:** labels are near/far relative to orientation, not hardcoded White-bottom. Near = human when playing; names follow the pieces.
5. **Nickname:** enable `#human-nickname` whenever the launcher is online and flow is playground, including after inscribe. Keep optional.
6. **Agent autonomy:** AvH brief (and launcher wait copy) must say: paste once; the agent keeps polling, waiting, chatting, and moving with **its own tools**; the human must not re-prompt. Same idea in `AGENTS.md` AvH loop.
7. **Game ID:** normal body font. Wrap with `overflow-wrap: anywhere`. Optional Copy ID next to Copy PGN. No ellipsis, no `0.82em`.
8. **Show chat:** matching header actions. Game info card header: Chat. Chat panel header: Game. Remove the footer-only Show chat.
9. **Move list:** live-follow (play, spectator at tip, puzzle live) uses a shared `pinScrollToBottom(el)` (`scrollTop = scrollHeight`, then two rAF). Spectator also re-pins after `syncHeights()` / board resize when at tip. Scrub/replay keeps `scrollIntoView({ block: "center" })`. Never `block: "nearest"` for live follow.
10. **Premove:** keep `return false` so cm-chessboard does not commit a real move. Drop `deferDisplay` / `queueMicrotask`. After enqueue, wait on `event.chessboard.state.moveInputProcess` then `syncDisplay(true)` (same as a real move in `play-board.js`). Ghost FEN shows the piece on the destination. Drop destination `PREMOVE_MARKER` (origin-only cue optional). Server `chess` stays truth.
11. **Home Strength:** rewrite the Benchmark paragraph and the Strength `title` to: Strength is derived from move accuracy and aims to represent Elo on a move-by-move basis, on the same scale as regular Elo. It is not results-only ladder Elo and does not change ladder Elo. Keep Home column name Strength (Leaderboards stay Performance).

Copy: no extra bold in body paragraphs; prefer commas over em dashes.

---

## Phase 1 — Last-move and annotations (all boards)

**Goal:** One last-move look. Annotations behave like other chess apps.

**Work**

- Restyle `--last-move-*` and `--annotation-*` in `watch.css` (play already imports it). Cache-bust CSS.
- Wire `paintLastMoveMarkers` into `puzzle-watch.js` `goToStep` / live poll (UCI from replay plies). Identify: no last-move; change `paintReviewMarkers` to remove only review marker types, not `removeMarkers()`.
- Play: keep last-move distinct from `autoMarkers` drag squares (style or disable overlap).
- Rewrite `board-annotations.js` (stay on cm-chessboard 8.7.2):
  - Toggle via `getArrows` / `getMarkers` before add; never stack.
  - Delete preview mousemove path and `ANNOTATION_PREVIEW_ARROW_TYPE`.
  - Knight helper: if `|df|,|dr|` is `{1,2}`, corner = longer-leg first; two segments under one logical toggle.
  - Left-click still `clearAnnotations`.
- Arrow CSS: thinner line, less glow; preview class unused.
- Fix stale `test_spectator_board_widget.py` if it still asserts `MARKER_TYPE.frame`.

**Done when**

- Play, `/g/{id}`, and `/p/{id}` last-move squares look the same and are not neon lime.
- Drawing the same arrow twice removes it; drawing a knight is an L, not a diagonal.
- Dragging does not show a faint arrow before mouseup.
- Left-click clears all marks.

**Verify**

- Manual: play + spectator, light and dark.
- String tests: no `ANNOTATION_PREVIEW`, toggle/remove helpers exist, knight L helper covered if extracted.

---

## Phase 2 — Play chrome, rails, nickname, agent copy

**Goal:** Stable layout, correct names, nickname works, agent keeps playing alone.

**Work**

- Remove play header markup and `updatePlayHeader` matchup line. Put status in a fixed slot (`data-play-status`) under the board. Update `test_avh_play_polish.py` (it currently requires `data-play-header-line`).
- Rails: `data-play-near-label` / `data-play-far-label`, or swap the two existing nodes when `human_color === "black"`. Near shows human; far shows agent.
- `enableForm`: include `nicknameEl` (same list pattern as `human-hub.js`). After successful inscribe on playground, leave nickname enabled.
- AvH `render_agent_brief_human`: explicit rule that the loop is autonomous (poll/sleep with your own tools until `game_over`; the operator will not re-prompt). Mirror puzzle-brief “keep playing” tone. Same in `AGENTS.md` and playground launcher aside + `showHumanResult` wait text.
- Brief tests in `test_agent_brief.py`.

**Done when**

- Creating a playground game after inscribe lets you type a nickname.
- Playing Black: bottom rail is you, top rail is the agent; board does not jump when turn text changes.
- Brief contains a continue-without-reprompt sentence.

---

## Phase 3 — Spectator chrome (ID, chat toggle, last-move already phase 1)

**Goal:** Game ID readable. Chat toggle where people look.

**Work**

- Drop tiny/ellipsis Game ID CSS. Wrap at normal size; add Copy ID next to Copy PGN if the id still feels cramped in the grid.
- Put Chat / Game toggles in the two panel headers (same control, two placements). Remove `.info-col-footer` Show chat if it is redundant.
- Update `test_avh_play_polish.py` / `test_spectator_phase2_ux.py` selectors if IDs move.

**Done when**

- Full game id is readable without hover.
- Chat and Game toggles sit in matching headers.

---

## Phase 4 — Move list scroll and premove

**Goal:** New moves pin the list to the bottom. Premoves look like moves.

**Work**

- Shared helper `pinScrollToBottom(el)`: `scrollTop = scrollHeight`, then two rAF. Use from `play-page-ui.js` `renderMoveList`, spectator `syncMovesScroll` when at tip (and again after `syncHeights` / board resize), and `puzzle-watch.js` live `renderLiveMoves`.
- Scrub/replay: keep `scrollIntoView({ block: "center" })`. Never `nearest` for live follow.
- Premove: drop `deferDisplay`. On successful enqueue, `event.chessboard.state.moveInputProcess.then(() => syncDisplay(true))`. Keep `return false`. Same wait after promotion enqueue. Drop destination `PREMOVE_MARKER`.
- Manual check: queue two premoves; pieces sit on ghost squares; Escape restores server position.

**Done when**

- After each ply, the last move row is flush with the bottom of the moves panel (play, spectator at tip, puzzle live).
- A premove looks like the piece moved, not a stuck drag.

---

## Phase 5 — Home Strength copy

**Goal:** Strength is explained as accuracy → Elo-scale, move by move.

**Work**

- Rewrite the Benchmark paragraph in `public-site/index.html` (and the Strength `th` title). Do not call it a casual shorthand or “less precise than Elo.” Keep the phrase “flavor snapshot” (existing test). Draft:

  Strength estimates how strong the agent played move by move: mean move accuracy from Stockfish analysis, mapped through the calibration accuracy-to-Elo table. The number is on the same scale as regular Elo, but it reflects move quality rather than wins and losses, and it never changes ladder Elo.

- Leaderboards page stays Performance; no rename. Optional: align `PERFORMANCE_TIP` / spectator play-rating tip to the same framing.

**Done when**

- Home text states accuracy basis, move-by-move, same scale as Elo.

---

## Tests and cache

- Extend `test_avh_play_polish.py`, `test_spectator_phase2_ux.py`, `test_agent_brief.py`.
- Nickname: launcher JS test or HTML assert that enableForm includes the nickname input (string test is enough if there is no launcher unit harness).
- Bump `?v=` on play/spectator JS and `watch.css` / `play.css` where those pages link them.

## Suggested order

Phase 1 and 2 first (what you felt while moving). Phase 3–5 can land in the same PR if the diff stays readable.
