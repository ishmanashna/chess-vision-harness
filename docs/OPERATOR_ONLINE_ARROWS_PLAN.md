# Operator online, follow, arrows, and puzzle catalog

Playtest after the puzzle/identify watch work. Status chip, how to go live, identify chain follow while looping, chain chrome, finish arrows, imported puzzle catalog, footer spacing, attempt IDs, AvE watch redirect, and another game from the operator’s agent chat.

## Scope

- Status chip notices the public game server without a manual refresh (Pages).
- One desktop double-click starts localhost serve **and** the public tunnel (Pages Online).
- Auto-follow when the agent is on a newer **active** attempt (identify loops especially). No countdown when browsing finished history.
- Identify and puzzle chain chrome are the same compact panel. One shared helper so they cannot drift.
- Finish arrows look like user-drawn arrows (red wrong, green solution). Knight L is a full L. First-move fails get arrows. Overlay is only the last fail ply. **Puzzles only** — identify has no move arrows.
- Localhost catalog shows every imported puzzle, including never attempted, and you can open one.
- Footer line sits close to the bottom of the page (no leftover pad under “Source on GitHub”).
- Watch, play, and Create never print a game/attempt/puzzle id in the info card. One Copy ID button, always, copies the URL id.
- After an AvE agent actually starts, Create Game takes you to the watch page (same wait as playground / puzzles).
- If the person talking to the agent asks for another game (AvE, AvA, or AvH), the agent can create it, get a real new id, and play — without a second operator-approval API.
- Rebuild the stale accuracy→Elo map from live engine Elo. Lookup **extends linearly** below (and above) the fitted knots. Calibration shows that curve as a graph.

## Out of scope

- Named Cloudflare tunnel / custom domain.
- Rewriting NSSM or logon-task (pick one durability path; do not run both).
- Glicko, selection banding, puzzle/identify join-before-redirect (already shipped), live solutions.
- Publishing the full corpus table on Pages.
- Identify finish arrows / wrong-move overlay.
- Auto-starting a new **game** when the current one ends (puzzles/identify already loop; games do not).
- Teaching agents the localhost follow-up approval chain (`request-followup` / `approve-followup`). Chat with the operator is the approval.
- Public Pages chart of the accuracy map (graph is localhost Calibration only). Hiding Performance when accuracy is off the knots.

Implement **Phase 2 before Phase 3** on the same branch (both touch `puzzle-watch.js`).

---

## Verified causes

**Chip stays Sleeping until refresh**  
`common.js` `applyHealthUi` runs once. `fetchEdgeHealthNetwork` uses `cache: "default"`. `checkEdgeHealth()` returns an in-memory cache unless `{ force: true }`. No poll. Pages tabs stay Sleeping after `go-online`. Localhost `/api/edge-health` is always Online while serve is up — the Sleeping→Online check is a **Pages** test, not localhost. `launcher.js` also calls `applyHealthUi`; a naive interval inside it would double-poll `/launch/`. Spectator and Contact load `common.js` with **no** `?v=` cache-bust.

**Serve ≠ public Online**  
Serve binds `127.0.0.1:8765`. Pages needs Quick Tunnel + `GAME_ORIGIN` + deploy (`deploy/go-online.ps1`). No Desktop shortcut today. `go-online` needs `cloudflared`, `gh` (authenticated, repo write), and `chess-harness` on PATH. Fallback `serve --force` runs when there is **no NSSM service** and `/health` is down — a stuck process on `:8765` still gets `--force`. Do not combine NSSM with the logon-task `--force` path. NSSM start may need admin.

**Follow is the wrong predicate**  
Both `puzzle-watch.js` and `identify-watch.js` follow when **this page is `finished`** and `chain[0]` is a different id. `scheduleAutoFollow` early-returns `if (!finished || followCancelled || !newestRow)`. `renderChain` gates with `if (finished && all[0] && …)`. That countdowns on historical opens (newer **finished** row too — there is **no** `status === "active"` check today). It does **not** follow while this page is still `active`, so opening the live row never follows. `startChainTracking` on finish: when `chainTimer` already exists, the `else if (finished)` branch only calls `setChainPollInterval` — **no `refreshChain()`**. Identify one-shot loops make it obvious; puzzles share the same code.

**Older/Newer vs Stay**  
`navigateChain()` does `location.assign` (full reload). `followCancelled` is module-scoped and **resets on every load**. Stay-on-Older is a no-op unless suppression is persisted across navigation.

**Identify chain chrome**  
Repo HEAD `/p/` and `/i/` already share `#chain-panel` markup. A growing `<ul class="chain-list">` is leftover CSS / a **stale Pages bundle**, not current JS. Identify JS is a copy (`?v=9` vs puzzle `?v=10`). Shared helper still needs **parameters**: attempts URL, watch path `/p/` vs `/i/`, row label (`moves_played` vs `accuracy`). Chain JSON is `{ok, attempts, total}`; `chain[0]` is newest (`started_at` desc); live rows use `status: "active"`. Follow must use `status`, not `agent_joined` (chain rows omit `agent_joined`).

**Arrows unlike user marks (puzzles)**  
Custom `arrow-result-*` types vs `ANNOTATION_ARROW_*`. Last-move gold can sit on a failed freeze. Identify watch has **no** result arrows (square markers + placement table only).

**Knight L only second leg**  
Result shaft classes are not the annotation shaft class whose `.arrow-line` actually paints.

**First-move fail, no arrows**  
`wrongUciForReplay` prefers `first_wrong_move` (raw agent string: often SAN like `Rc8+`). `parseUciSquares` rejects it. Last `submitted_moves` is UCI except illegal garbage. `poll()` fires `setPosition(state.fen)` **without await**, then `loadReplay()`; the first `.then()` runs `clearResultArrows()`. On the finish transition, skip the live `setPosition` entirely and only load **replay** (interleaved UCI `solution_moves`).

**Arrows for the whole line**  
`paintResultArrows` uses `solution_moves[0]`. Fail index on interleaved UCI is `solution_moves[2 * (len(submitted) - 1)]` using **replay** `submitted_moves`. Board fen is the pre-fail ply.

**Catalog looks like attempts only**  
Spectator Puzzles/Identify tabs are `attempts-list.js` (no loopback branch). Puzzle set returns every import but unattempted rows show `"—"` (`watchLinks`). `watch_puzzle` / `watch_identify` are built only from **finished** attempts — an in-flight loop often has **no** watch link. Corpus rows omit `correct_pieces` / `display_fen`; an identify preview must **compute** placement, not look it up. Pages proxy contract only lists exact `/api/puzzle-set` — a preview subpath needs the contract updated so it stays origin-only.

**Footer sits too far from the page edge**  
`.wrap` pads **56px** under the footer (`padding: 20px … 56px`). `.site-footer p` still has the browser’s default paragraph margin. Recurs on every page (Home, Create, watch, Spectator). `margin-top: auto` still pins the footer on short pages — keep that; only the space **below** the GitHub line should shrink.

**Puzzle/identify IDs break the info card / IDs in the grid at all**  
Game, puzzle, and identify watch all print the long URL id in the meta grid **and** have Copy ID. Copy ID is in the HTML from first paint on `/g/`, `/p/`, `/i/` — it is not gated on game over. Copy **PGN** only fills after the game ends, which is easy to mix up. Play page has no Copy ID. Launcher prints `Game ID:` / `Attempt ID:` as wrapping `<code>`. Puzzle finish also unhides a corpus “Puzzle id”. Spectator tables keep ids as row links (navigation, not info-card chrome).

**Same Performance (−59) at 35% and 20% accuracy**  
Three stacked causes, not a spectator typo.

1. **Stale map.** `accuracy_elo_map.json` was fitted **2026-07-30**. Pair for `inverse-sf:worst-d16` is **40.77% / −65** (165 samples). Live calibration Elo for that engine is **−225** (thousands of games). The Calibration table’s −225 is layer A (results Elo). The map’s −65 is a snapshot from last rebuild. 42% would map near −225 **after a rebuild**, not on the committed file.

2. **Monotone pooling.** Lookup is piecewise-linear through **knots**, not raw engine pairs. If a slightly more accurate engine has a **lower** Elo, `fit_map_knots` merges them. On the stale file, worst-d10 / d16 / d18 (40.3–40.91%, Elo −52 / −65 / −59) collapse to **one knot ~40.66% → −58.67**, which rounds to **−59**. That is why 42% on the live table does not equal the map floor.

3. **Clamp, not slope.** `interpolate_map` returns the first knot for any accuracy **at or below** it, and the last knot above the top. 20% and 35% are both under ~40.7%, so they print the same number. The user-requested fix: extend with the **slope of the two lowest knots** (and the two highest above the top). One-knot degenerate maps still clamp.

Accuracy % on a terrible game can be 20–35%; that part is real. Do **not** hide Performance. Rebuild the map, then extrapolate. The graph must show pairs, knots, and the dashed extension so a flat inverse-SF cloud (many engines ~40–46% at ~−220 Elo) is visible if 20% vs 35% stay close after rebuild.

**AvE never waits for the agent**  
Playground waits for `agent_joined` then goes to `/play/`. Puzzles/identify wait then go to `/p/` or `/i/`. AvA Direct waits until **both** sides joined then goes to `/g/`. AvE `handleEngineSubmit` → `showBriefResult(..., matched=false)`: a “Spectate” link only, **no poll**. Engine games never set `agent_joined` (`BoardController.get_board` / `get_board_text` are read-only for AvE). Spectator `/api/games/{id}/state` has no AvE join flag to wait on.

**Agents cannot start another game from chat**  
Paste-ready briefs (AvE / AvA / AvH) only mention the **current** `game_id`. They never say how to create a new one. `POST /api/v1/games`, `POST /api/v1/lobbies`, and `POST /api/v1/games/human` already exist and return a new id (AvH also returns `play_url`). A separate follow-up approval API exists for localhost/secret operators — that is the wrong path when the person is already talking to the agent. `AGENTS.md` documents API-only `POST /games` but the briefs agents actually paste do not.

---

## Product decisions (locked)

1. **Operator run.** Serve stays localhost. Public Online is tunnel + secret + Pages. Desktop shortcut runs `go-online.ps1` with ExecutionPolicy Bypass, a visible window on failure, and the same tools as that script (`cloudflared`, `gh` logged in, `chess-harness` on PATH). No second server manager. Durability is NSSM **or** logon-task, not both. Shortcut does not start NSSM (that can need admin). `--force` still kills a stuck port when there is no service.

2. **Status chip polls** every ~15s with `{ force: true }`, `cache: "no-store"`, pause when the tab is hidden. One timer per page (launcher already calls `applyHealthUi` — do not double-poll). Acceptance for Sleeping→Online is **Pages**. Localhost chip is Online whenever serve answers. Cache-bust `common.js` on **every** page that loads it, including Spectator and Contact (add `?v=` where missing).

3. **Follow the live attempt.** Banner + ~5s + navigate only when `chain[0].status === "active"` and that id is not this page. This is **new logic**, not only deleting `finished`. Change both the `scheduleAutoFollow` early-return (`if (!finished || …)`) **and** the `renderChain` `finished &&` gate. If `chain[0]` stops being active, cancel the countdown. Do **not** follow when newest is finished/abandoned.
   - **Open the live row** (this page `active`): no follow (you are already there).
   - **Open an older row** while newest is **active**: follow (looping identify / spectator stale link). That is the bug.
   - **Open any row** while newest is finished: no follow.
   Stay this tab: no more follow until a full reload **without** the stay flag (Spectator open of a live chain still follows if stay was never set).
   **Older/Newer persist the same stay flag** in `sessionStorage` (keyed by puzzle vs identify + agent) **before** `location.assign` — module `followCancelled` dies on reload. Returning via Newer does not clear stay until reload from Spectator/catalog.
   On finish/abandon: when `chainTimer` already exists, **also call `refreshChain()`** (do not only `setChainPollInterval`).

4. **One chain panel.** Shared `watch-chain.js` parameterized (attempts URL, `/p/` vs `/i/`, row label). Same markup as today. Matching cache-bust on both watch scripts **and** the new helper. No list. Delete unused `.chain-list` CSS.

5. **Finish arrows = annotation arrows, two colors. Puzzles only.** Same L helper and shaft/head as right-click. Red = last **replay** `submitted_moves` UCI when squares parse (do **not** prefer `first_wrong_move`). Green = `solution_moves[2 * (submitted.length - 1)]` from the **replay** payload on the pre-fail fen. No last-move gold on a failed freeze. No arrows for earlier correct plies. Solved: play the line, last-move squares only. Identify watch unchanged.

6. **Localhost catalog.** Do not silently swap attempt columns on the Spectator table. Loopback Spectator **Puzzles and Identify** tabs both go to `/puzzle-set` (already has both watch columns), with a localhost-only subtitle. Keep the Puzzle set nav. Preview is `/puzzle-set/{id}` (loopback API + shell): board, side to move, difficulty, themes, solution; identify flavor is placement computed from `display_fen` (not a corpus field). Unattempted rows get a **Preview** link (replace `"—"`). Watch links remain finished-attempt-only; mid-loop follow is Phase 2 when a watch URL is opened, not a catalog guarantee. Pages Spectator tabs stay attempt lists. Add preview path to the Pages proxy contract so it cannot leak off origin. Watch URLs obey Decision 3 (Phase 2), not Phase 3.

7. **Footer padding.** Keep the footer pinned on short pages. Cut wrap bottom padding (~56px → ~16–24px) and zero the footer paragraph’s extra margin on **all** site pages. Do not leave a second spacer under the GitHub line.

8. **Copy ID only — never print the id.** Info cards on `/g/`, `/p/`, `/i/`, `/play/`, and Create result: no Game ID / Attempt ID / Puzzle id row, no wrapping `<code>`. One **Copy ID** control, visible from the first paint (not tied to finished / PGN). It copies the URL id (`game-*` / `pz-*` / `bi-*`). Copy PGN stays separate and may stay inert until the game has a PGN. Playground gets Copy ID too. Launcher drops the `Game ID:` / `Attempt ID:` lines in favor of the same button. Spectator **tables** still use ids as links into watch. Dead wrap CSS for `.meta-game-id` / `.meta-attempt-id` goes away with the rows.

9. **AvE redirect on join.** Same product as playground/puzzles: keep the brief, wait until the agent has actually started (first authenticated board PNG or `board.txt`), then go to `/g/{id}`. Do not redirect at create time. Set `agent_joined` on AvE like AvH/puzzles; expose it on spectator state for the launcher poll. AvA Direct already waits for both sides; Find match already jumps after a match — leave those.

10. **Another game when the person asks.** The operator’s message in the agent’s own chat **is** the approval. Never start a follow-up from game-over/PGN alone. Same API key already in the brief. Use the existing create endpoints (not `request-followup`):
    - AvE: `POST /api/v1/games` → new `game_id` → same AvE loop with the new URLs.
    - AvA: `POST /api/v1/lobbies` (Find match). One agent cannot Direct-pair itself; Direct stays Create Game. If waiting, poll the lobby; on match, use the new `game_id` and brief.
    - AvH: `POST /api/v1/games/human` → new `game_id` + `play_url`. Tell the operator that play link (human board). Then the same AvH loop.
    Prefer after the current game is finished (or resign first). A second live game is allowed only if server/key limits allow. Scoped child keys still cannot create. Put this in **all three** briefs and `AGENTS.md`. Do not send agents through the localhost follow-up approval API.

11. **Performance follows the map, including past the ends.** Rebuild `accuracy_elo_map.json` from **current** calibration Elo + quality samples (operator rebuild in this phase; commit the snapshot). Lookup: inside the knots, same piecewise-linear. **Below** the first knot, continue the line of knots[0]→knots[1]. **Above** the last knot, continue knots[-2]→knots[-1]. Still print a number — never “below map”, never clamp to −59. Calibration `/calibration` graph: scatter of engine pairs, solid knot polyline, dashed extrapolation. Loopback only. Caption: Performance is this map, not ladder Elo. If two inverse engines share ~40% accuracy and disordered Elo, monotone merge can still flatten the bottom — the graph shows that; do not fake extra engines.

---

## Phase 0 — Status chip without refresh

**Goal:** An open **Pages** tab notices Online after go-online.

**Work**

- `cache: "no-store"` on the health fetch. Poll ~15s with `checkEdgeHealth({ force: true })`. `visibilitychange` pause. Singleton so `/launch/` does not double-poll.
- Bump or add `common.js?v=` on every HTML that loads it (Home, Spectator, Contact, launch, watch shells).
- Do not let a cached Sleeping probe (memory or HTTP) block a later Online paint.

**Done when**

- Pages Home/Spectator left open as Sleeping, run go-online, chip becomes Online without reload. `/launch/` still one poll series.

**Verify**

- On Pages, not localhost. Network: repeated `/api/edge-health` with no-store.

---

## Phase 1 — Desktop double-click to go live

**Goal:** One icon starts serve (if needed) and public Online.

**Work**

- `deploy/Start-Online.bat` runs `go-online.ps1` from repo root with `-ExecutionPolicy Bypass`. Keep the window open on non-zero exit.
- Optional `-InstallShortcut` to Desktop. No admin for the click path (do not start NSSM from the shortcut).
- Operator note: needs `cloudflared`, `gh auth login` with repo access, `chess-harness` on the **Desktop** PATH; Calibration / Puzzle set stay on `http://127.0.0.1:8765`; do not run NSSM and logon-task together; `go-online` refreshes the Quick Tunnel URL and may redeploy twice; `--force` still applies if `/health` is down and there is no NSSM service.

**Done when**

- Shortcut with serve down: `/health` up and Pages Online.
- Shortcut with serve already healthy (NSSM or a answering process): does not `--force` kill a healthy `/health`; still refreshes tunnel/secret.

**Verify**

- Desktop click; Pages chip Online; localhost Puzzle set still loads. Failure (missing `gh`) stays visible.

---

## Phase 2 — Chain panel and live follow

**Goal:** Identify loops follow the **active** attempt. History does not. Same panel as puzzles.

**Work**

- New `watch-chain.js`: poll, panel, banner, Stay, Older/Newer. Callers pass attempts URL, watch prefix, row label.
- Follow only if `chain[0].status === "active"` and id ≠ this page. Rewrite `scheduleAutoFollow` early-return **and** `renderChain` finished gate. Do not only delete `finished`.
- Finish/abandon: `refreshChain()` in the existing-timer branch, then faster interval.
- Stay and Older/Newer write the same `sessionStorage` stay key before navigate.
- Cancel banner if newest is no longer active.
- Match cache-bust (`identify-watch.js` catch up); drop dead list CSS; fix stale “chain links only” file headers.
- Verify **both** identify and puzzle loops.

**Done when**

- Identify (and puzzle) loop of 3+: URL follows the latest **active** `/i/{id}` (or `/p/{id}`) after the delay unless Stay/Older.
- Opening the live row: no banner. Opening an older finished row while newest is active: banner. Finished-only chain: no banner.
- Older then wait: no yank (stay persisted). Identify info column stays a panel.

**Verify**

- Live identify run. Historical finished open with no active row: quiet. Older then wait: no yank. Same on a puzzle loop.

---

## Phase 3 — Result arrows (puzzles only)

**Goal:** Failed **puzzles** show one red and one green annotation-style arrow. Identify watch is unchanged.

**Work** (after Phase 2)

- On finish in `poll()`: **do not** call live `setPosition`; `await loadReplay()` only. Await `setPosition` inside replay/`goToStep`. Paint from **replay** UCI only.
- Wrong UCI = last replay `submitted_moves` when it parses as squares (ignore `first_wrong_move` for geometry); else no red. Green = `solution_moves[2 * (submitted.length - 1)]` on the pre-fail fen.
- Reuse annotation shaft/head; red/green color only. Hide last-move on failed freeze.
- Knight: annotation shaft class for the first leg.
- Illegal garbage: green only.

**Done when**

- Wrong rook vs mate: red/green, no gold extras.
- Knight fail: full L.
- Two-move fail on ply 1 and on ply 2: arrows only for the failing ply.

**Verify**

- Playtest `Rc8+` vs `Rd8#`. One knight fail. One mate-in-two each way. Confirm `/i/` still has no result arrows.

---

## Phase 4 — Catalog and preview

**Goal:** On localhost, every imported puzzle is visible and openable.

**Work**

- Loopback Spectator Puzzles **and** Identify tabs: go to `/puzzle-set`, labeled as the imported set. Do not reuse attempt-table columns.
- Loopback-gated `GET /api/puzzle-set/{id}/preview` (PNG + metadata + solution + computed identify placement; no Pages). Shell `/puzzle-set/{id}`. Add the subpath to `proxy-routes.contract.json` and contract tests.
- Puzzle set rows: Preview always; Pz/Id watch links only when a **finished** attempt exists. Mid-loop follow is Phase 2, not a new catalog field.
- Pages: attempts only. Tests for loopback 403/404 off-host.

**Done when**

- Never-attempted row opens a board (puzzle solution **and** identify placement). Count matches `puzzles stats`. Pages Spectator Puzzles/Identify unchanged (attempts).

**Verify**

- Preview a zero-attempt puzzle. Open an **older** watch URL while the agent is looping: Phase 2 follow. Open a watch URL when idle: stay. Contract: preview path not exposed on Pages.

---

## Phase 5 — Footer and Copy ID

**Goal:** Less empty pad under the GitHub line. No printed ids in info chrome.

**Work**

- Shrink `.wrap` bottom padding; zero `.site-footer p` margin. Site-wide (`site.css`).
- Remove Game ID / Attempt ID / Puzzle id from watch info grids. Copy ID always visible on `/g/`, `/p/`, `/i/`, `/play/`, Create result. Same control, copies the URL id. Copy PGN unchanged (hint if not ready). Drop launcher `game-id-line` codes. Delete unused wrap CSS.

**Done when**

- Footer sits close to the page bottom on Home, Create, watch.
- In-progress and finished `/g/` and `/p/` show Copy ID and **no** id string in the card. Playground Copy ID works. Create result has Copy ID, not a wrapping code line.

**Verify**

- Live AvE watch, live identify, playground, Create after start. Spectator game list still links by id.

---

## Phase 6 — AvE watch redirect on join

**Goal:** Create Game → Agent vs Engine takes you to `/g/{id}` when the agent starts, not only via a Spectate link.

**Work**

- Persist `agent_joined` on AvE `state.json` on first authenticated `GET board` or `board.txt` (same moment as AvH/puzzles). Spectator `/api/games/{id}/state` includes it for engine games.
- Launcher `showBriefResult` for unmatched AvE: waiting copy + poll until `agent_joined` (or game over), then `location.assign("/g/" + id)`. Reuse the existing join-poll helper; do not add a second timer stack.
- Idle timeout copy if the agent never comes.

**Done when**

- Paste AvE brief, agent reads the board, Create Game tab opens `/g/{id}` without a click. Creating the game alone does not redirect.

**Verify**

- AvE: wait → redirect on first board read. AvH and puzzle waits still work. AvA Direct still waits for both sides.

---

## Phase 7 — Another game from the operator’s chat

**Goal:** If the person tells the agent to play again, it can create the right kind of game and keep going.

**Work**

- AvE / AvA / AvH briefs: a short “Another game” section — **only when the operator asks**; never after PGN by itself. Exact create URL, same auth header, use the returned `game_id` (AvH: also show `play_url` to the operator). Then the same play loop with the new URLs.
- AvA: Find match (`POST /api/v1/lobbies`) + lobby poll. Direct is still Create Game with two prompts.
- `AGENTS.md`: same rules for HTTP play (all three modes). Do not document `request-followup` as the chat path.
- Tests: brief strings contain the create URLs; a finished-game key can `POST /games` (and human/lobby) and play the new id. Scoped keys still 403 on create.

**Done when**

- After an AvE game, the operator says “play another” in the same chat: agent creates, reports the new id, plays. Same for AvA Find match and AvH (operator gets a play link). No extra game when nobody asked.

**Verify**

- One finished AvE → operator asks → new `game-*` and a move. One AvA lobby wait/match. One AvH create with `play_url`. Finish without asking: no second game.

---

## Phase 8 — Rebuild map, extrapolate, graph

**Goal:** Performance uses live engine Elo and a straight-line extension past the knots. Operator can see the curve.

**Work**

- Rebuild accuracy map from current samples + live calibration Elo; persist `accuracy_elo_map.json`.
- `interpolate_map`: below knots[0], linear through knots[0] and knots[1]; above knots[-1], linear through the last two. Tests replace the old clamp-to-end assertions (30% must not equal the first knot if the slope is nonzero).
- Calibration status includes `knots` and `pairs`. `/calibration` SVG: scatter, knot line, dashed extension. No Pages chart.
- Do not add a “below map” label anywhere.

**Done when**

- After rebuild, worst-d16’s **pair** Elo matches live calibration (~−225), not −65.
- 20% and 35% accuracy produce **different** Performance values whenever the two lowest knots have a nonzero slope.
- Calibration graph shows pairs, knots, and the dashed tail.

**Verify**

- Rebuild on loopback; open the graph; confirm worst-d16 sits near −225. Lookup 20, 35, 42, 80. Replay the suspicious watch game: two accuracies, two Performances, neither stuck at −59 unless the slope is actually flat (then the graph explains it).

---

## Estimated duration

- Phase 0: 1.5–2.5h (health poll, force refresh, singleton, all cache-bust tags)
- Phase 1: 2–3.5h (shortcut, PATH/auth notes, failure window)
- Phase 2: 3–5h (shared chain, active follow, sessionStorage stay)
- Phase 3: 3–5h (puzzle arrows only; after Phase 2)
- Phase 4: 6–10h (preview API, placement, contract, spectator tabs, Preview links)
- Phase 5: 1.5–2.5h (footer pad, Copy ID only)
- Phase 6: 2.5–4h (AvE join flag, spectator field, launcher wait)
- Phase 7: 2.5–4h (briefs + AGENTS.md + create-from-key tests)
- Phase 8: 4–6h (rebuild map, linear extension, calibration graph)
