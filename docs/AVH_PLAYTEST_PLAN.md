# Agent vs Human playtest follow-ups

> **Superseded (2026):** Agent `GET /api/v1/games/{id}/moves` was removed in Phase 5 of `docs/AVH_UX_PLAN.md`. AvH agents discover chat via `chat_seq` on `GET /status`. Spectator `GET /api/games/{id}/moves` is unchanged.

Playtest-driven upgrades to Agent vs Human play. Board PNG remains the agent’s position image; illegal moves stay rejected with no penalty.

## Product decisions (locked)

1. **Create waiting room** — After AvH create: no Spectate / Open board buttons. Stay on Create with agent brief + **Waiting for agent…**. When `agent_joined` becomes true, auto-navigate to `/play/{id}`. Store play token client-side immediately so create can poll.
2. **Resume** — Persist active human games (game id + play token + labels) in `localStorage`. Surface **Your games** on Create (human mode) and a Spectator sub-tab **My games** with Resume → `/play/{id}` when a token exists locally. Never put tokens in spectator APIs.
3. **Human always at bottom** — Orientation never flips. Fix sparse move POST payload and stop unconditional `setOrientation` on poll.
4. **No flicker / no console spam** — Diff-guard FEN, orientation, and move-input enable; only enable/disable when state changes.
5. **Premoves** — Client-only queue while waiting; fire on turn if still legal; clear if illegal. Agent unaware.
6. **Theme** — One theme toggle handler on play (and fix `/g/{id}` the same way if duplicated).
7. **Play chrome** — Show agent ladder Elo (display only). Move list right of board. Chat left of board. Resign + draw offer/accept/decline for both sides.
8. **Chat** — Out-of-band messages either side anytime. Agent: `/api/v1/.../chat`. Human: `/api/play/.../chat`. Storage: `chat.jsonl` in the game dir. No LLM/IDE wiring — HTTP only. Chat must not be treated as position source (brief + UI copy).
9. **Draw** — Offer only on your turn; accept/decline by opponent; any move clears pending offer; agreement → `1/2-1/2` / `agreement`. Unranked for AvH. Resign already exists — keep and surface clearly.
10. **Tab attention** — When it becomes the human’s turn, update `document.title` and favicon (subtle ★ / alternate icon); only on turn edges; respect Page Visibility.
11. **Site favicon** — Real `public-site/favicon.ico` + `<link rel="icon">` on static pages and play/spectator HTML.
12. **Illegal moves copy** — Create aside, play footer, and agent briefs: illegal/off-turn moves return an error and play continues — no punishment. Cheating (FEN/engines/files) remains a separate invalidation rule.
13. **Export PNG** — After game over on play page: download a human-oriented board image (client export of the interactive board preferred; spectator PNG remains agent-oriented).
14. **Agent move list (AvH only)** — `GET /api/v1/games/{id}/moves` returns the complete ply list (UCI + SAN) anytime **only for `human_vs_agent`**. No FEN. Rated AvE/AvaA stay blocked (same as in-progress PGN). Update `AGENTS.md` and the human brief: AvH history is allowed for memory; **current position for choosing a move still comes from the board PNG**. Spectators get a public `GET /api/games/{id}/moves` for all modes (fixes empty moves panel without debug).

## Scope

In scope: items above for AvH play/create/spectator chrome; draw + chat for AvH; agent `/moves` for AvH only; spectator moves for all modes; site favicon; docs/brief updates.

Out of scope: Google login for resume; human Elo; clocks; engine auto-accept draws; LLM backends for chat; mobile polish beyond “works”; rewriting cm-chessboard styling for perfect dark-mode pieces (optional stretch only).

## Architecture (imprinted)

**Create wait:** On AvH success → save `{gameId, token, brief, …}` to `localStorage` → poll `GET /api/play/{id}/position` until `agent_joined` → `location.replace(/play/...?token=)`.

**Play sync:** Unify human move POST response with `human_position()` (full metadata). Client caches `human_color`; never default orientation to white on partial payloads. Poll only applies board updates when `fen` / turn / join flags change.

**Chat:** Append to `games/<id>/chat.jsonl`; `chat_seq` in `state.json`. GET `?since=`. Rate-limit + max length.

**Draw:** `state.draw_offer = {offered_by, at_ply} | null`. Parallel `/draw/offer|accept|decline` on agent and play routers. Status/position expose pending flags.

**Moves:** Shared helper builds `{plies, move_rows, plies_detail}` from `state["moves"]` without FEN. Agent and spectator endpoints both use it. Keep PGN export finished-only for agents.

```
Create (AvH) --wait agent_joined--> /play/{id}
     │                                │
     └─ localStorage registry ←───────┘ resume
                                      │
              chat.jsonl ←── /api/v1/chat + /api/play/chat
              draw_offer ←── /draw/* both planes
              moves[]    ←── /api/v1/.../moves (AvH only; AvE/AvaA 403)
```

## Phases

### Phase 1 — Play sync bugfixes + Elo

Fix board flicker (diff-guard FEN/orientation/input). Fix “moveInput already enabled”. Unify `_human_move_response` with full `human_position` (include `human_color`, `agent_joined`, `legal_moves_uci`, …). Add `agent_elo` to position; show in matchup. Remove duplicate `THEME_TOGGLE_SCRIPT` on play (and `/g/{id}` if same bug).

**Done when:** No periodic flip for black; no flicker on idle poll; theme toggles once; Elo visible; console clean of moveInput spam.

**Verify:** Manual AvH as black; watch poll; toggle theme; check console.

### Phase 2 — Create waiting room + resume + illegal-move copy

AvH create result: brief + Waiting for agent (poll join) → auto-redirect to play. Drop Spectate / Open board from that result. `localStorage` registry; **Your games** on Create human mode; Spectator **My games** tab with Resume. Copy on create aside + play footer + human brief: illegal moves rejected, no punishment.

**Done when:** Create → wait → auto play works; closing the tab and resuming from My games / Your games works with stored token.

**Verify:** Create, wait for agent join without clicking Open; leave tab; resume from list.

### Phase 3 — Play layout: moves + resign/draw chrome + tab alert + favicon

Play page grid: chat column (placeholder OK if Phase 5 not done) | board | move list. Move list from play position or `GET /api/play/.../moves` (SAN rows). Resign button already present — keep; add Draw offer / Accept / Decline UI wired in Phase 4 if draws land there, or stub disabled until Phase 4. Site `favicon.ico` + link tags everywhere. On human turn edge: title + favicon attention cue.

**Done when:** Moves update each ply; favicon shows on all main pages; background tab title marks your turn.

**Verify:** Play several plies; switch to another browser tab and confirm title/favicon cue; check favicon on Home/Create.

### Phase 4 — Draw offers + resign clarity

Implement draw offer/accept/decline for agent and human; clear on move; finish as agreement draw (unranked). Status/position flags. Briefs document draw + resign endpoints. Ensure agent resign and human resign remain obvious in UI and briefs.

**Done when:** Either side can offer/accept/decline a draw; resign still works both ways; agreement appears in results with `reason: agreement`.

**Verify:** Focused pytest + manual offer/accept and offer/decline/move-clears-offer.

### Phase 5 — Premoves + finished PNG export

Client premove queue while not your turn; submit when turn arrives if legal. After game over: Download position PNG (human-oriented client export).

**Done when:** Premoving a reply works against a slow agent; illegal premove clears quietly; finished game downloads a PNG matching human orientation.

**Verify:** Manual premove; download PNG as black human.

### Phase 6 — Chat

`chat.jsonl` + seq; agent and human POST/GET; play UI left panel; poll with position. Rate limits. Briefs include chat loop. Copy: chat is social, not a position source.

**Done when:** Human and agent can message anytime; transcript appears on play page; agent brief documents endpoints.

**Verify:** Pytest auth/length; manual back-and-forth while a game is in progress.

### Phase 7 — Agent move list (AvH only) + spectator moves

`GET /api/v1/games/{id}/moves`: allowed for `human_vs_agent` (in progress and finished); **403 for AvE/AvaA** with the same spirit as in-progress PGN. Response: UCI+SAN plies, no FEN. Update `AGENTS.md` and the human brief only (rated briefs keep “no move lists”). Public `GET /api/games/{id}/moves` for spectator `/g/{id}` move panel without debug (all game types). Human play may use the same helper.

**Done when:** An AvH agent can fetch full history mid-game; AvE/AvaA agents get 403; spectator move list works on `/g/{id}` without `CHESS_HARNESS_DEBUG`; docs match.

**Verify:** Focused tests AvH allow + AvE/AvaA deny; open `/g/{id}` and see SAN rows.

### Phase 8 — Hardening

Idle messaging still correct; line limits; proxy paths if new routes; PRODUCT/README one-liners for chat/draws/move history; smoke AvE/AvaA rated paths still play; quality on new modules only.

**Done when:** Feature set operable on Pages→origin; docs accurate; no Elo regression on AvH.

**Verify:** Targeted tests + one public create→wait→play→draw/chat→export pass.

## Order

1 → 2 → 3 → 4 → 5 → 6 → 7 → 8  

Phases 4 and 5 may swap if needed; 6 depends on play layout shell from 3; 7 is independent of chat but should land before final docs in 8. One implementation subagent per phase.

## Estimated duration

- Phase 1 — Play sync bugfixes + Elo: 2–4 agent-hours
- Phase 2 — Create wait + resume + copy: 3–5 agent-hours
- Phase 3 — Layout, moves, favicon, tab alert: 3–5 agent-hours
- Phase 4 — Draw offers: 3–4 agent-hours
- Phase 5 — Premoves + PNG export: 3–5 agent-hours
- Phase 6 — Chat: 4–6 agent-hours
- Phase 7 — AvH agent moves + spectator moves: 3–5 agent-hours
- Phase 8 — Hardening + docs: 2–3 agent-hours
