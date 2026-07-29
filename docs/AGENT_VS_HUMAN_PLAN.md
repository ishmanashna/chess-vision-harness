# Agent vs Human

Unranked browser play: a human creates a game against an inscribed vision agent, pastes the agent brief into their agent, then plays on an interactive board. The agent still only sees the board PNG. Human games never change agent Elo.

## Product decisions (locked)

1. **Create Game third mode** — Add **Agent vs Human** beside Agent vs Engine and Agent vs Agent. One create flow: pick model → create → copy-paste agent brief → open the play board from the same result screen.
2. **Unranked** — Never call Elo updates for these games. Still show the agent’s ladder Elo (display only) and normal spectator metadata. **No evaluation bar** and no Elo-delta text.
3. **Colors** — Always random (same as AvaA).
4. **No lobby** — Direct create + invite. The human is the host; the agent joins via the brief.
5. **Agent contract unchanged** — PNG + `/api/v1` move/status/board/resign/pgn. Agent brief uses the AvaA-style turn loop (poll status until `your_turn`, then board → move).
6. **Human board is interactive** — Not the Pillow PNG. Simple click/drag board in the browser (chess.js for client hints + cm-chessboard or equivalent). Server python-chess remains authoritative.
7. **Separate play page** — Humans play on `/play/{game_id}`. Spectators watch on `/g/{game_id}` (PNG, no eval for this type).
8. **Human auth (v1)** — Opaque **play token** minted at create time, bound to `game_id` + human color. Optional nickname on create. Do not depend on Pages Google OAuth for game-server moves (OAuth stays cosmetic until a later shared-secret phase).
9. **Agent “confirm”** — Play page shows “Waiting for agent…” until the agent’s first authenticated board or status call sets `agent_joined`. Then the human can move when it is their turn.
10. **Results** — Still append one `results.jsonl` row with `game_type: "human_vs_agent"` for history. Rebuild / leaderboard counts / `record_game` skip these rows.

## Scope

In scope:

- `game_type: "human_vs_agent"` end to end (create, play, finish, spectator, Create Game UI).
- Human move API with play-token auth.
- Interactive `/play/{id}` with drag/click, promotion, resign, idle messaging.
- Agent brief + Create Game mode wiring.
- Elo exclusion and eval suppression.
- Pages proxy for `/play/`.

Out of scope:

- Human Elo / official ratings / human matchmaking.
- Requiring Google login to play.
- MCP/CLI create for human games (HTTP + Create Game UI only).
- Clock / timed games.
- Mobile-polished UX beyond “works on touch.”
- Live streaming.
- Extracting all of `spectator.py` (only split what this feature needs).

## Architecture (imprinted)

**Create (AvE-shaped):** Create Game UI registers/mints an agent API key, then `POST` a human-vs-agent create endpoint. Response: `game_id`, `agent_brief`, `play_url` (includes or sets play token), colors, nickname.

**Play core (AvaA-shaped):** Dual principals, no engine auto-reply, turn gating. Agent uses existing `/api/v1` with API key. Human uses `/api/play/...` with play token. Shared board state in `state.json`; agent still gets role-oriented PNG; human gets FEN (play API only).

**State shape (minimal):**

- `game_type: "human_vs_agent"`
- `model_name`, `model_display_name`, `agent_color`
- `human_nickname`, `human_color` (or derive from agent color)
- `agent_joined: false` until first agent auth hit
- No `opponent_id` / `opponent_uci_config` / engine fields
- On finish: result/reason/plies; **no** `elo_before` / `elo_after` / `elo_delta`

**Finish:** Append one results row; never `ELOLadder.record_game`. Filter `human_vs_agent` in `process_results_file` and `count_by_model`.

**Interactive board stack:** Vendored or CDN `chess.js` + `cm-chessboard` under `public-site/` (split JS files ≤300 lines). Client legal-move highlights only; every move POST revalidated server-side.

```
Create Game (AvH mode)
        │
        ├─► mint agent API key + play token
        ├─► create human_vs_agent game
        ├─► show agent_brief (copy)
        └─► link → /play/{id}?token=…  (or cookie)
                    │
        Agent (elsewhere)              Human browser
        GET board / status             wait agent_joined
        POST move when your_turn       drag/drop → POST /api/play/.../move
                    │                         │
                    └──────── state.json ─────┘
                              │
                    Spectator /g/{id} (PNG, no eval)
```

## Phases

### Phase 1 — Game type, create API, Elo exclusion

Add `GAME_TYPE_HUMAN_VS_AGENT` and `is_human_vs_agent_state()`. Implement `GameService` / controller path to create a human-vs-agent game (random colors, nickname, play-token hash stored on state or sibling file, render initial agent PNG, no engine). Wire finish/resign/idle: append results with `game_type`, skip `record_game`. Filter rebuild + `count_by_model`. Agent `/api/v1` participant check treats this type like “single agent model_name matches key,” with AvaA-style turn gating (no engine reply). Set `agent_joined` on first authenticated agent status/board/move.

**Done when:** Creating a game via API yields valid state + board PNG; finishing does not change `models.json` Elo; rebuild ignores these results rows; agent can status/board/move only on their turn.

**Verify:** Focused pytest for create, agent move turn gating, finish Elo skip, `process_results_file` skip. No full suite.

### Phase 2 — Human play API

New FastAPI router (keep modules ≤300 lines): play-token auth; `GET` position (fen, your_turn, agent_joined, game_over, side to move, optional legal UCI list); `POST` move (UCI/SAN); resign; status suitable for the play page poller. Reject wrong token, wrong turn, and finished games. Do not expose FEN on agent or public spectator surfaces.

**Done when:** With a play token, a human can complete a legal game against a scripted agent client (or test double) over HTTP.

**Verify:** Pytest for token auth, illegal move, off-turn, fen-only-on-play-api.

### Phase 3 — Agent brief + Create Game UI mode

`render_agent_brief_human` (AvaA poll loop + this game’s ids/colors). Create Game: third mode tab **Agent vs Human**, nickname field, submit → create endpoint → result panel with copy-brief + **Open play board** (same tab). Aside copy: unranked, interactive board, paste brief to agent. Proxy `/play/` and play API paths on Pages if needed for create→play handoff.

**Done when:** From the public Create Game page in AvH mode, an operator can create a game, copy a brief, and open `/play/{id}` from the result UI.

**Verify:** Manual create on local serve; brief contains correct base URL and game id; play link works.

### Phase 4 — Interactive `/play/{id}` page

FastAPI HTML page (shared header/nav) + JS: load position, orientation = human at bottom, click/drag moves, promotion, disable board while request in flight, poll while waiting for agent or opponent move, resign control, clear “Waiting for agent…” / “Agent’s turn…” / game-over states. No eval UI. Keep files under the line limit (split board widget vs page shell).

**Done when:** A human can finish a short game in the browser against a real agent using only the pasted brief + play page.

**Verify:** Manual playtest (create → paste brief into an agent session → drag moves → game ends). Touch: at least click-to-move works.

### Phase 5 — Spectator + list chrome

For `human_vs_agent`: suppress eval everywhere (`/eval`, `eval_ui`, cards, `/g/{id}` column). Labels: human nickname vs agent display name + agent Elo (display). No Elo-change line. `games-list.js` / active cards recognize the type. `/g/{id}` remains PNG spectator. Optional link from play page to spectate.

**Done when:** Active/completed spectator lists and `/g/{id}` show human games correctly with no eval bar and no rating delta.

**Verify:** Create a game, open `/g/{id}` and `/spectator/` — no eval; names/Elo display look right.

### Phase 6 — Hardening

Idle timeout messaging on play page; metrics counter for active human games; AGENTS.md / README / PRODUCT one-line updates (human play exists, unranked); Pages `_proxy.js` covers `/play/` and play APIs; quality_gate line limits on new files; regression smoke that AvE and AvaA paths still behave (targeted tests only).

**Done when:** Feature is operable on Pages→GAME_ORIGIN the same way Create Game is today; docs match behavior; no Elo leakage; line limit clean on touched/new modules.

**Verify:** Targeted tests + one full create→play→spectate pass through the public URL when the game host is online.

## Order

1 → 2 → 3 → 4 → 5 → 6  

Phases 3 and 5 can overlap after 2 only if needed; prefer strict sequence. One implementation subagent per phase.

## Estimated duration

- Phase 1 — Game type, create, Elo exclusion: 3–5 agent-hours
- Phase 2 — Human play API: 2–4 agent-hours
- Phase 3 — Brief + Create Game UI: 2–3 agent-hours
- Phase 4 — Interactive play page: 4–6 agent-hours
- Phase 5 — Spectator chrome: 2–3 agent-hours
- Phase 6 — Hardening + docs + proxy: 2–3 agent-hours
