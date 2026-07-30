# Board vision, Imagine, Playground — plan

Ambitious product pass: fixed board orientation, prettier agent PNGs, Imagine lines, multi-premove UX, AvA direct pairing, chrome polish, and scrubbing a bad test game from metrics.

Do not implement until this plan is accepted.

## Goals

1. **White at bottom always** for every agent board image and every spectator board image (all modes). Human interactive Playground board may still put the human at the bottom. Server-side human PNG export may keep human-bottom via an explicit override.
2. **Imagine** — any participating agent can submit a move or move sequence (including opponent replies) from the current position and receive a PNG of the resulting board without changing game state.
3. **Premoves** — Lichess-style: ghost the queued move on the board and allow chaining further premoves while waiting.
4. **Agent/spectator PNGs** use the same Staunty piece assets as the Playground board (cleaner than Unicode glyphs).
5. Site footer **“Chess Vision Harness · Source on GitHub”** pinned to the bottom of the viewport on short pages, on **every** user-facing tab including `/play/` and `/g/`.
6. Rename nav/label **Play vs Agent → Playground** (routes stay `/human/`; product docs/copy updated too).
7. **AvA Direct** — operator picks both models, gets both prompts, waits until both agents have connected, then opens spectator — **no lobby**. Idle must not kill the game while waiting for joins.
8. Home lead paragraph uses the **same font size** as the other about-copy paragraphs.
9. Remove **`agent-test-1`** from the harness and all metrics (Games, Elo, accuracy, Estimated Elo, snapshots). Confirmed present under `.chess_harness/games/agent-test-1` with a `results.jsonl` row.

## Architectural decisions (locked)

- **Orientation:** `render_board` takes `bottom_color` (default `"white"`). Agent API, CLI, MCP, spectator `/g/.../board.png`, Imagine, and AvA agent files always white-bottom. **Exception:** `human_board_png_bytes` may pass the human’s color so Playground download stays human-bottom. Interactive cm-chessboard stays human-oriented.
- **AvA board files:** Prefer one canonical `board.png` (white-bottom); role paths may alias the same file instead of triple-rendering identical pixels. `refresh_board_image` for AvA must call `render_avaa_boards` (today KeyErrors on missing `agent_color` and fails silently).
- **Imagine:** Read-only. Clone FEN → push sequence with existing move parser → PNG response body (or non-game temp path). Never overwrite `board.png`, never `_touch_activity`, never set joined flags, never append moves/audit. Separate rate-limit bucket. Soft illegal-move errors only (no legal-move lists). Update AGENTS.md: Imagine PNG is **not** live position; committed moves still require reading the live board each turn.
- **Premoves:** Client-only queue. Keep `chess` / server FEN as truth. Ghost via a **virtual** board + `board.setPosition(virtualFen)` **without** `chess.load`. Validate next premove on the virtual position. Fire head on turn edge; drop illegal head quietly; continue while still your turn. Cancel clears entire queue and restores server position.
- **Pieces:** Vendor Staunty from the **same** cm-chessboard version as Playground (8.7.2). Pre-rasterize 12 piece PNGs for Pillow. Square colors aligned to play board.
- **AvA Direct:** Create Game has Find match (lobby) and Direct. Direct rejects identical model ids (400). Create UI mints **two** keys and builds **both** briefs in the operator response only (`{ game_id, white: { brief, key? }, black: { brief, key? } }` or mint locally then fill two templates — never expose the other key on agent `/api/v1` surfaces). Presence: `white_joined` / `black_joined` on first authenticated board/status/move per side (mirror AvH `ensure_agent_joined`). Wait UI clones AvH wait-poll pattern → `/g/{id}` when both joined. **Idle:** do not count idle toward timeout until both joined (defer touch / refresh while waiting / or start idle clock only after both joined).
- **Purge:** `chess-harness remove-game <id>`: dry-run → `remove_game_results` → `delete_game` → **`rebuild-elo`** → `export_leaderboard_snapshot`. Continuous calibration logs: grep that id; strip/rebuild estimation samples only if present (agent ladder metrics live in `results.jsonl`). Run for `agent-test-1`.

## Out of scope

- Same model playing itself in AvA (Direct rejects; keep).
- Changing idle timeout length (only when the clock starts for Direct wait).
- Legal-move lists for agents.
- Rewriting engine calibration pipelines.
- Renaming URL `/human/` (alias `/playground/` optional later).

---

## Phase 1 — Chrome: Playground, lead size, sticky footer

### Scope

- Replace visible **Play vs Agent** with **Playground** in `PUBLIC_SITE_HEADER`, all `public-site/*/index.html`, hub title/heading/unavailable banner, home body link text, play “create another” copy, and product wording in AGENTS.md / README / PRODUCT where users see the old label. Keep `href="/human/"`, `id="nav-human"`, APIs and `human_vs_agent` unchanged.
- Home: remove larger `.lead` font-size so the first about paragraph matches sibling `<p>` size.
- Sticky footer: flex column on `html`/`body`/`.wrap` with `main { flex: 1 }` and `.site-footer { margin-top: auto }`. **Required** identical string with GitHub link on static pages, `/play/`, and `/g/`. Check mobile + dark mode.
- Update tests that assert the old nav label.

### Done when

Nav and product copy say Playground; home lead size matches siblings; footer with GitHub link sits at the bottom on short pages including play and `/g/`.

---

## Phase 2 — White at bottom (orientation contract)

### Scope

- `render_board(..., bottom_color="white")` by default; stop flipping agent black for agent/spectator paths.
- Keep human PNG export override (`bottom_color=human`).
- AvE / AvH / AvA agent fetch + spectator `board.png` white-bottom; eval bar `white_at_bottom=True` for AvE/AvH too.
- AvA: fix `refresh_board_image` → `render_avaa_boards`; alias or unify role board files.
- Update AGENTS.md, agent briefs, roadmap AvA orientation claims.
- Tests: agent-black PNG is white-bottom (update/replace `test_flipped_for_black`); human export still human-bottom.

### Done when

Agent black, AvA both sides, and `/g/` show white at bottom; human download still human-bottom; AvA refresh works; docs match.

**Do not parallelize with Phase 3** (same `render_pillow.py`).

---

## Phase 3 — Staunty assets for server PNGs

### Scope

- Vendor cm-chessboard **8.7.2** Staunty assets; pre-rasterize 12 piece PNGs into package data.
- Pillow uses those pieces + play-board square colors; drop Unicode glyph path for production boards.
- License/note in vendor folder; ensure package data is included in installs.
- Visual parity check light + dark theme contexts if applicable.

### Done when

Fresh agent/spectator PNGs use Staunty pieces, not Unicode fonts.

---

## Phase 4 — Imagine

### Scope

- `POST /api/v1/games/{id}/imagine` with `{ "moves": ["e2e4", "e7e5", ...] }`. Auth = participant. Cap length (~12). New rate-limit bucket. No activity/joined/move side effects. Sanitize errors like other agent payloads.
- PNG body + `X-Imagine: 1`. Illegal ply → 400 with index, no PNG.
- MCP `chess_imagine_board`; CLI `chess-harness imagine` → temp path outside game dir.
- AGENTS.md: allowed-commands table + ground truth — Imagine is hypothetical; live board required before each real move.
- Tests: sequence OK; illegal mid-sequence; state/idle unchanged; all modes.

### Done when

AvE/AvH/AvA agents can Imagine a line safely; docs and MCP list updated.

---

## Phase 5 — Multi-premove ghost UX (Playground)

### Scope

- Queue API: enqueue / peek head / dequeue / clear (replace single `premoveUci`).
- Ghost: virtual FEN from server + queue; `setPosition` for display **without** loading into server `chess`.
- Next premove validated on virtual board (human to move); piece appears as if played.
- Turn edge: while `your_turn` and queue non-empty, fire head; illegal → drop quietly → try next.
- Cancel: Escape, right-click, Cancel button — clear queue, restore server position.
- If oversized for one agent: ship 5a queue+fire first, then 5b ghost polish — prefer one agent completing both if possible.

### Done when

Human can chain several premoves, see them on the board, cancel, and have legal heads auto-fire on turn edge.

---

## Phase 6 — AvA Direct (bypass lobby)

### Scope

- Create Game AvA: **Find match** (lobby) + **Direct** (new).
- Direct UI: white + black model selectors (must differ); mint two keys; create game; show **two** copyable briefs (`create-result.js` dual panel).
- API: reject same model id; operator create returns both briefs for that session only; agent surfaces stay single-key.
- `white_joined` / `black_joined` like AvH; wait poll until both → redirect `/g/{id}`.
- Idle clock starts only after both joined (or activity refreshed while waiting — pick one and test).
- Offline Create banner must still hide/disable Direct sensibly.

### Done when

Operator pairs two models without lobby, copies both prompts, and reaches spectator when both agents have connected; Find match unchanged.

---

## Phase 7 — Remove game from metrics (`agent-test-1`)

### Scope

- `chess-harness remove-game <game_id>` with `--dry-run`: results strip → delete dir → rebuild-elo → snapshot export.
- Run for `agent-test-1` on the game PC (id confirmed in this workspace).
- Grep continuous/play-rating logs for that id; scrub only if found.
- Commit updated `public-site/data/leaderboard.json` if Pages uses the snapshot offline.

### Done when

Game dir and results rows gone; Elo rebuilt; Games/accuracy/Estimated Elo ignore it; snapshot matches.

---

## Suggested order

1. Phase 1 — chrome  
2. Phase 2 — white-bottom (**serial before 3**)  
3. Phase 3 — Staunty  
4. Phase 4 — Imagine (after 2; Staunty preferred but not required for correctness)  
5. Phase 5 — premoves (independent of 3–4; may follow 2)  
6. Phase 6 — AvA Direct (independent of 3–4; may follow 2; don’t overlap Phase 1 copy files in the same wave)  
7. Phase 7 — purge `agent-test-1`

Never parallelize Phase 2 with 3. Phase 5 ∥ 6 only after Phase 2, different files.

## Verify

- Agent as black: PNG and `/g/` white-bottom; Playground human board + human PNG download human-bottom.  
- Agent PNG looks like Staunty Playground pieces.  
- Imagine three-move line → PNG; real board and idle unchanged; AGENTS.md documents Imagine.  
- Queue two+ premoves with ghosts; fire/clear correctly.  
- Footer with GitHub on Home, Playground hub, `/play/`, `/g/`; sticky on short pages; mobile OK.  
- Nav + docs say Playground; home first paragraph same size as next.  
- AvA Direct: two briefs, both join before idle kill, spectator opens; same-model rejected; Find match still works.  
- After remove-game, `agent-test-1` absent from results and leaderboard Games; Elo rebuilt.

## Review notes (folded in)

Two adversarial reviews: all nine feedback items map to phases; nothing fully missing. Must-fix locks above: footer on `/g/`+play, human PNG orientation exception, premove ghost without corrupting `chess`, AvA dual-brief + idle-before-joined, Imagine contract/rate limits, rename leftovers, purge requires rebuild-elo. `agent-test-1` confirmed on disk.

## Estimated duration

- Phase 1: 0.5–1.5 agent-hours  
- Phase 2: 1.5–2.5 agent-hours  
- Phase 3: 2–3.5 agent-hours  
- Phase 4: 1.5–2.5 agent-hours  
- Phase 5: 3–5 agent-hours (or 5a+5b split)  
- Phase 6: 2.5–4 agent-hours  
- Phase 7: 0.5–1 agent-hour  
