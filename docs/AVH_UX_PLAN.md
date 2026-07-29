# AvH UX, Spectator polish, local/prod parity, and security

Second-pass playtest fixes: separate Human play from Create Game, make Spectator mode-aware with correct Elo, fix the stuck board-input bug, widen play columns, and make agents discover chat and draw offers through status. Remove agent move-history access. Align localhost with production UI, and harden the public/proxied surface (honor-system agent registration kept as-is).

Audited against the live codebase before implementation. Blockers from that audit are locked below so AvE/AvaA create, live spectator, and play-token handoff are not broken by a literal reading of earlier drafts.

## Product decisions (locked)

1. **Human play is its own top-level surface** — New nav tab and hub at `/human/` (label: **Play vs Agent**). Move AvH create, waiting room, Your games, and aside copy out of Create Game. Create Game keeps only Agent vs Engine and Agent vs Agent. Keep `/play/{game_id}` as the live board route. Update play footer “create another” to `/human/`. **Server** redirect `/create/?mode=human` and `/create?mode=human` → `/human/` on origin and Pages (not JS-only).
2. **Extract before strip** — Before removing human mode from Create, move shared result helpers (`showBriefResult`, `requireBrief`, result DOM) out of `create-human.js` into a neutral module (e.g. `create-result.js`). Engine and AvaA must keep working with **zero** dependency on `CVH.createHuman`.
3. **Spectator Mode column** — Always emit `game_type` on list rows (`agent_vs_engine` when absent). Add a **Mode** column (AvE / AvA / AvH) and **remove** the old inline AvA/AvH badges from the Game id cell so badges are not duplicated. Update table headers, colgroups, and empty-row `colspan` together. Style `.tag` in `site.css`.
4. **Finished-game agent Elo** — Fix `_enrich_list_game` so AvE list Elo uses `elo_after` / `apply_elo_delta` / live `_elo_context`, not nonexistent `state.agent_elo`. Idle-timeout no-result games and AvH stay unranked (`—` / no delta). Prefer at-game-time Elo when `elo_before`/`elo_after` exist. (Provisional ladder `*` suffixes are unrelated.)
5. **Board click stuck** — One coordinator replaces the **pair** of `applyInputState` + `applyPremoveInputState` in `play-page.js`. Disable library input before switching handlers; set local refs only after successful enable. **Do not** call `disableMoveInput()` while a promotion dialog is open. On enable failure, leave input disabled and surface a real error (not the old moveInput spam).
6. **Wider side columns / download / chat polish** — Chat and moves roughly `minmax(260px, 320px)`. Download stays in `.play-actions` with Resign / Draw. `spellcheck="false"` and `autocomplete="off"` on chat. Remove play-page “Social only — not a position source.” Keep a short social-only line in the **agent brief** only.
7. **Agent notifications via status** — Add `chat_seq` to AvH `GET /status` (draw flags already exist). Brief wait loop priority: status → draw flags → if `chat_seq` advanced then `GET /chat?since=` → if your_turn then board → move. Do not bundle chat/draw into move responses. Do not teach both status discovery and a redundant “always poll chat” path without priority.
8. **Remove agent move history (breaking)** — Delete AvH `GET /api/v1/games/{id}/moves`. Coordinated sweep in the **same phase**: `agent_brief.py`, `AGENTS.md`, `PRODUCT.md`, `README.md`, `docs/AVH_PLAYTEST_PLAN.md` (or a one-line “superseded” note), `test_agent_brief.py`, `test_moves_api.py` agent cases. Keep shared `move_rows` helper, human play `move_rows`, and public `GET /api/games/{id}/moves`.
9. **Spectator moves policy (resolved)** — `GET /api/games/{id}/moves`: **finished** = full rows all types; **in-progress AvH** = full rows; **in-progress rated AvE/AvaA** = `plies` count only, empty `move_rows` and empty `plies_detail` (no UCI/SAN reconstruct). `/g/{id}` must tolerate empty rows (“No moves yet” while board PNG still updates). That empty panel for live rated games is **intentional**.
10. **Localhost ≈ production shell** — Origin serves `public-site/` for `/`, `/create/`, `/spectator/`, `/leaderboard/`, `/contact/`, `/human/` (both trailing-slash forms). Mount `/css`, `/js`, `/data`, favicons. **Keep on origin (Pages-proxied):** `/api/v1/*`, `/api/games*`, `/api/play/*`, `/g/*`, `/play/*`, `/health`, `/api/edge-health`. Calibration stays origin-only (Pages 404). Intentional diffs: snapshot ladder on Pages vs live ladder optional on origin; OAuth on Pages; `CHESS_HARNESS_PUBLIC_URL` in briefs.
11. **Hub and parity ship together** — Phase that adds `/human/` must also make origin serve that static path (and Create static), or land immediately after. Do not leave operators on legacy Python `/create` while Pages has `/human/`.
12. **Spectator My games** — Keep the Spectator **My games** tab as resume-from-`localStorage` (same registry). `/human/` owns create + waiting + Your games; Spectator My games is resume-only, not a second create flow.
13. **Nav everywhere** — “Play vs Agent” in every nav source: all `public-site/**/index.html` headers, `PUBLIC_SITE_HEADER` in `ladder_display.py`, and `common.js` `setActiveNav` (`/human` → `nav-human`). Play page active nav should not pretend to be Create.
14. **Agent key minting stays honor-system** — No ownership proof / CAPTCHA. Document as accepted risk.
15. **Security hygiene** — Subdirectory ignores (`.chess_harness/.gitignore`, `public-site/.dev.vars`); do **not** add a repo-root `.gitignore` unless ARCHITECTURE clean-root is amended. Default `CHESS_HARNESS_DEBUG` off. Stronger game ids via one shared `new_game_id()`. Escape `/g/` HTML. Fix logout `//` open redirect. Play-token: persist then strip. Calibration: **not** client-IP loopback (broken behind Cloudflare Tunnel) — use secret header and/or documented direct `127.0.0.1` path, plus optional env override.

## Scope

In scope: decisions above; `/human/` hub; spectator Mode + Elo; play input coordinator; play polish; status `chat_seq` + brief; remove agent `/moves`; local/prod shell parity; security items.

Out of scope: Proving ownership of inscribed models; OAuth-backed resume; WebSocket push; LLM chat backends; clocks; human Elo; full rewrite of every oversized legacy module beyond extractions required here.

## Architecture (imprinted)

**AvH hub:** `public-site/human/index.html` + origin static serve. Create drops human mode after `create-result.js` extraction.

**Create shared results:**

```text
create-result.js  ← showBriefResult, requireBrief (AvE + AvaA + hub)
human-hub / create-human*  ← waiting room, registry, AvH-only UI
create.js  ← engine + AvaA only; imports create-result, not createHuman
```

**Spectator list Elo (AvE finished):** as before — finished uses `elo_after` / replay / `_elo_context`; always emit `game_type`.

**Input coordinator:** single entry; skip disable while promotion dialog open; refs after successful enable.

**Spectator moves redaction:**

```text
in-progress AvE/AvaA → { plies, move_rows: [], plies_detail: [] }
in-progress AvH / finished any → full payload
```

**Play token (order matters):**

```text
read ?token= OR localStorage registry
→ write sessionStorage (and keep registry)
→ history.replaceState strip query
→ API calls use Bearer from memory/storage
update readPlayToken + playHref + create redirect together
wait-room poll already uses Bearer — leave it
```

**Calibration (tunnel-safe):**

```text
POST /api/calibration/* requires
  CHESS_HARNESS_CALIBRATION_SECRET header/field
  OR explicit CHESS_HARNESS_ALLOW_REMOTE_CALIBRATION=1
Document: direct http://127.0.0.1:port/calibration is the operator path.
Do not trust client IP behind Cloudflare Tunnel.
Pages continues to 404 /calibration*
```

**Game ids:** one `new_game_id()` used by `api_v1`, `lobby_handlers`, `commands`, `create_game_page` (until legacy create is gone).

## Phases

### Phase 1 — Spectator Mode column + finished Elo fix

Backend: always set `game_type`; fix AvE `agent_elo` in `_enrich_list_game`; no Elo delta for AvH / idle-timeout finishes. Frontend: Mode column; remove duplicate inline type badges from Game cell; fix colspan/headers/colgroup; `.tag` styles.

**Done when:** Every row shows Mode; finished AvE shows recoverable Elo; AvA white/black columns still work; AvH shows display Elo without rating-change chrome.

**Verify:** Focused spectator list tests (AvE finished Elo + mode field); eyeball mixed `/spectator/`.

### Phase 2 — Fix play board input (click + moveInput)

Replace dual enable calls with one coordinator; never disable during open promotion; refs only after success.

**Done when:** After agent reply, human can drag/click without reload; no `"moveInput already enabled"` in console or banner; promotion still works with premoves.

**Verify:** Manual full turn cycle as white and black, including a promotion.

### Phase 3 — Play page polish

Widen chat/moves; download with other actions; chat `spellcheck="false"`; remove social-only play banner.

**Done when:** Layout usable; download with Resign/Draw; no spellcheck; banner gone.

**Verify:** Visual `/play/{id}`; inspect textarea attributes.

### Phase 4 — `/human/` hub + Create extract (with origin static)

1. Extract `create-result.js`; rewire AvE/AvaA create to it.  
2. Add `public-site/human/index.html` (create, wait, Your games, aside).  
3. Strip human mode from Create.  
4. Nav + `common.js` + `PUBLIC_SITE_HEADER` + play footer.  
5. Server redirects for old human create URLs (Pages + origin).  
6. **Same phase:** origin serves static `/human/`, `/create/`, and preferably `/` from `public-site/` so localhost is not stuck on legacy create (full parity may finish in Phase 6, but `/human/` and Create static must work on `serve`).

**Done when:** AvH flow is `/human/` → `/play/{id}` on **both** Pages and local serve; Create is engine + AvaA only and still shows briefs after create/match; old human URLs redirect; Spectator My games still resumes from registry.

**Verify:** Local + (if available) Pages: create AvE, AvaA, AvH; Create has no AvH tab; `/create/?mode=human` redirects.

### Phase 5 — Agent status `chat_seq` + remove agent `/moves`

Add `chat_seq` to AvH agent `status()`. Rewrite human brief wait loop (status-first). Remove agent `/moves` route and full doc/test sweep listed in decision 8. Keep spectator + human move lists.

**Done when:** Brief has no `/moves`; status shows `chat_seq` after chat; AvE/AvaA briefs unchanged; CI agent move tests updated.

**Verify:** `test_agent_brief`, `test_moves_api` (agent AvH gone / 404; spectator still OK); manual status JSON after chat POST.

### Phase 6 — Finish localhost / production UI parity

Complete remaining static shells (`/`, `/leaderboard/`, `/contact/` if not done in Phase 4). Mount `/data` + favicons. Remove or redirect legacy Python home/create/leaderboard/contact templates. Keep all proxied API/`/g/`/`/play/` routes. Migrate or shim `test_create_game.py` if legacy `POST /create` is removed. Document intentional local≠prod diffs.

**Done when:** Local shared routes match Pages chrome; legacy card-grid `/` is gone; `/data/leaderboard.json` and favicons load locally; proxied live APIs still work through Pages.

**Verify:** Open local `/`, `/create/`, `/spectator/`, `/leaderboard/`, `/human/`; calibration still only on origin; focused create tests pass.

### Phase 7 — Security hygiene (ignore, debug, moves, ids)

Extend subdirectory ignores (`.chess_harness/`, `public-site/.dev.vars`, calibration dumps). Default debug off (`cmd_serve` must not `setdefault` to `1`). Redact in-progress rated spectator moves per decision 9; update `/g/{id}` expectations and `test_moves_api`. Single shared high-entropy `new_game_id()` at all mint sites. Verify `?debug=1` on `/state` does nothing without env.

**Done when:** Runtime data not casually commit-able; live AvE `/api/games/{id}/moves` has no reconstructable plies; new ids are unguessable; debug opt-in only.

**Verify:** `git check-ignore`; in-progress AvE moves redacted; AvH in-progress moves still full; create game id format; debug off checks.

### Phase 8 — XSS, logout, tokens, calibration

Validate + escape `/g/{game_id}` (and meta from state). Logout: allow only same-origin path; reject `//…`. Play token: persist-then-strip; update `readPlayToken`, `playHref`, create redirect together; `Referrer-Policy: no-referrer` on play. Calibration POSTs: secret or explicit allow-remote env — **not** IP loopback. Redact operator email in deploy docs if present.

**Done when:** No `/g/` XSS via id/names; no logout open redirect; refresh after strip still plays when registry/session has token; calibration POSTs fail remotely without secret/override.

**Verify:** Focused tests for logout, `/g/` validation, token read after strip, calibration deny; manual play handoff from wait room.

### Phase 9 — Hardening

Targeted regression: AvH hub, AvE/AvaA create briefs, play input, spectator Mode/Elo, status `chat_seq`, removed agent `/moves`, moves redaction, token strip, calibration gate. Line-limit pass on new/split files. Tiny PRODUCT/README if hub naming needs a public one-liner.

**Done when:** Smoke `/human/` → wait → play → chat/draw → spectator Mode/Elo; AvE create still works; security checks from 7–8 hold; new modules ≤300 lines.

**Verify:** Focused pytest set; one manual local pass (Pages after deploy).

## Order

1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9  

Phase 4 already includes minimum origin static for `/human/` and Create; Phase 6 finishes the rest. Do not reorder Phase 8 token work before Phase 4 hub redirect uses `playHref`. One implementation subagent per phase.

## Estimated duration

- Phase 1 — Spectator Mode column + Elo fix: 2–4 agent-hours
- Phase 2 — Play input coordinator fix: 2–3 agent-hours
- Phase 3 — Column widths + download + chat polish: 1–2 agent-hours
- Phase 4 — `/human/` hub + Create extract + origin static: 4–6 agent-hours
- Phase 5 — Status chat_seq + remove agent `/moves`: 2–4 agent-hours
- Phase 6 — Finish local/prod UI parity: 3–5 agent-hours
- Phase 7 — Security hygiene (ignore, debug, moves, ids): 3–5 agent-hours
- Phase 8 — XSS, logout, tokens, calibration: 3–5 agent-hours
- Phase 9 — Hardening + docs: 2–3 agent-hours
