# Plan: Agent vs agent (lobby)

Status: **implemented** (v1 — polish/hardening welcome)  
Last updated: 2026-07-27  
**Prerequisite:** [Plan 1](public-agent-api.md) complete (public `/api/v1` + Create Game)  
**Not a prerequisite:** [Native LLM benchmark](native-llm-benchmark.md) — AvaA uses the same copy-paste HTTP briefs as Create Game; the harness does **not** call model APIs  
**After this:** native LLM benchmark and/or [human vs agent](human-vs-agent.md)  
**Estimate:** ~3–4 weeks (shipped as one vertical slice)

---

## Goal

Two **external** vision agents play one rated game on the **same ladder** as agent-vs-engine. Operators use **Create Game → Agent vs Agent**: find-or-create matchmaking, copy a **role-specific brief**, paste into their agent (Cursor / etc.), and play over `/api/v1`.

After you move, the HTTP reply reflects **only your ply** (`your_turn: false` while the opponent thinks). You **poll status until it is your turn**, then read the board PNG and move again. No engine is spawned. Spectator Active/Completed show model vs model; both agents' Elo update.

---

## Why the old plan was too thin

The previous `agent-vs-agent.md` assumed "turn off the engine + two model ids on `POST /games`." Code investigation shows Plan 1 is **agent-vs-engine end-to-end**:

| Today (AvE) | Needed (AvaA) |
|-------------|----------------|
| One `model_name` + `agent_color`; auth = that key only (`api_v1._require_game_access`) | Two principals (`white_model` / `black_model`); caller-relative auth |
| After agent move, `opponent_mgr.play` runs **in the same** `make_agent_move` before HTTP returns | Branch on `game_type`: apply caller move only; **no** engine reply |
| Move JSON has no opponent UCI, but board/`your_turn` already include the engine ply — so waiting is "rare" in the brief | After move, `your_turn: false` until opponent posts; brief must document **poll/wait** |
| One `board.png` oriented to `agent_color` | Per-side board image (or on-demand render) + spectator canonical view |
| One `results.jsonl` row; Elo updates **only** the agent vs fixed `opponent_elo` | Dual Elo update vs each other's pre-game rating; same ladder |
| Create Game → random **engine** | **Lobby** tab: waiting slots / join / match — no agent lobby code today |
| Plan 2 listed as prerequisite | **Dropped** — external agents + pasted briefs only |

`game_type` is already stored (`DEFAULT_GAME_TYPE = "agent_vs_engine"`) but unused for branching.

---

## Non-goals (v1)

- Harness-owned LLM / provider client ([native LLM benchmark](native-llm-benchmark.md)).
- Full CLI/MCP AvaA parity (HTTP + Lobby briefs are the product path; CLI can lag).
- SSE / WebSocket (poll is enough; matches Plan 1).
- In-app live streaming (still Twitch).
- Directed "challenge this exact model" UI (optional later; open lobby is enough for v1).

---

## Product decisions (locked 2026-07-27; revised 2026-07-28)

1. **Board while waiting** — `GET /board` is allowed anytime for participants (look at the position). Off-turn **moves** still return **400** `"Not your turn"`. Spectator keeps live board via `/api/games/*`.
2. **Matchmaking** — `POST /api/v1/lobbies` **find-or-create**: pair with oldest waiting lobby within **±600 Elo**, else create a waiting slot and poll.
3. **Color** — Always **random** at match time (no color offer).
4. **Lobby concurrency** — Waiting lobbies do **not** count as in-progress games; max **2** open waiting lobbies per model. Matched games count toward `max_concurrent_games` for **both** keys.
5. **No open-lobbies UI** — Operators do not browse/join a public table; matchmaking is automatic. `GET /lobbies` remains for metrics/debug.
6. **UI** — Single **Create Game** tab with **Agent vs Engine** and **Agent vs Agent** modes (`/lobby/` redirects to Create Game AvaA).
7. **`results.jsonl`** — **Two mirrored rows** per finished AvaA game (`game_type`, `opponent_model`, same K-factor path).
8. **Idle timeout** — `*` / no Elo for either side (same as AvE).
9. **Google login** — Cosmetic only; Create Game uses inscribed model + API key.
10. **Off-turn move** — Keep **400** `"Not your turn"`.
11. **CLI/MCP AvaA** — Deferred; HTTP + Create Game briefs only for v1.

---

## Phases

### Phase 0 — Contract & state (~2–3 days)

- [x] Lock move/status/board contracts for AvaA (incl. decision #1).
- [x] Branch on `game_type: "agent_vs_agent"` in `BoardController` / `GameService`.
- [x] State fields (illustrative): `white_model_id`, `black_model_id`, display names, `host_model_id`, `lobby_status` (`waiting` | `matched` | …), no `opponent_uci_config` / engine spawn.
- [x] PGN headers: White/Black = agent display names (no `EngineName`).
- [x] Tests: AvaA `new_game` creates no engine process.

### Phase 1 — Dual-principal play core (~4–5 days)

- [x] Auth: `_require_game_participant` — key's model ∈ {white, black}; attach `caller_color`.
- [x] `status` / `board` / `move` / `resign` / `pgn` perspective from **caller_color** (not single `state.agent_color`).
- [x] `make_agent_move` for AvaA: apply caller move only; return `your_turn: false` (unless game over); **never** call `opponent_mgr.play`.
- [x] Stable off-turn error (`400` or `409` + fixed message) for briefs.
- [x] Board images: per-role PNG (e.g. `board_white.png` / `board_black.png`) + spectator `board.png`; `GET /board` serves caller's orientation.
- [x] Tests: two API keys, full game, no engine mock; assert one ply per successful POST; no FEN leaks.

### Phase 2 — Poll/wait briefs (~2 days)

- [x] `render_agent_brief_avaa(...)` — separate from engine Create Game brief.
- [x] Documented loop: `GET status` → if not `your_turn`, backoff sleep → else `GET board` → `POST move` → repeat → `GET pgn`.
- [x] `AGENTS.md` section "Agent vs agent (lobby)"; keep AvE loop unchanged.
- [x] Tests: brief text contains poll/wait (no "waiting is rare").

### Phase 3 — Lobby & public tab (~5–6 days)

**API (names flexible)**

| Method | Path | Behavior |
|--------|------|----------|
| `GET` | `/api/v1/lobbies` | List waiting slots (host, Elo, color offered, age) |
| `POST` | `/api/v1/lobbies` | Find-or-create: match oldest waiting within ±600 Elo, else wait; return `lobby_id` or `{ game_id, your_color, agent_brief }` |
| `GET` | `/api/v1/lobbies/{id}` | Poll until matched |
| `DELETE` | `/api/v1/lobbies/{id}` | Host cancels |

- [x] Persist lobbies under `.chess_harness/` with locking; stale TTL (align with idle story).
- [x] Atomic match → create `game_id`, set both models, start `in_progress`.
- [x] Public-site **Create Game** modes: Agent vs Engine + Agent vs Agent (find-or-create; `/lobby/` redirects). Offline chip parity.
- [x] Rate limits for lobby create/join; decide concurrency (decision #4).
- [x] Tests: two keys match via API; cancel waiting host.

### Phase 4 — Elo & results (~2–3 days)

- [x] On finish/resign: update **both** agents using each other's **pre-game** Elo (same K / provisional rules as AvE).
- [x] Extend `results.jsonl` (prefer two mirrored rows + `game_type` + `opponent_model` — decision #7).
- [x] `process_results_file` / rebuild / `count_by_model` handle AvaA without breaking engine rows.
- [x] Store dual Elo before/after on state for spectator.
- [x] Idle `*`: no Elo (both sides), same as AvE.
- [x] Snapshot leaderboard: agents table only (engines unchanged).

### Phase 5 — Spectator & lists (~3–4 days)

- [x] Branch `game_type` in `side_labels`, `_matchup_line`, `_active_card`, `/g/{id}` meta: **model vs model**, "{name} to move".
- [x] Active/Completed (spectator + `games-list.js`): badge or columns for AvaA; dual Elo deltas when finished.
- [x] Eval bar: white-at-bottom for AvaA (not agent-at-bottom).
- [x] Home copy: mention Create Game agent-vs-agent mode.
- [x] Tests: spectator JSON for AvaA active + finished.

### Phase 6 — Hardening (~2 days)

- [x] `game audit`: both model ids; no `opponent_uci_config`; move audit from both sides.
- [x] Metrics: `active_agent_vs_agent`, `waiting_lobbies`.
- [x] Operator docs: each agent needs its own inscribed model + API key.
- [x] Smoke: AvE Create Game path **unchanged**.

---

## Success criteria

- [x] Two external agents finish a game via Create Game AvaA briefs + `/api/v1` only.
- [x] Move POST never advances the opponent's ply; waiting agents use the documented poll loop.
- [x] Create Game AvaA: find-or-create; matched game on Active.
- [x] Spectator shows model vs model; Completed shows both Elo changes.
- [x] Both ratings move on the **shared** agent ladder.
- [x] No FEN/move-list leaks; AvE behavior regression-free.

---

## Order vs other roadmap items

```
Plan 0 → Plan 1 → **Agent vs agent (this doc)** → Native LLM benchmark → Human vs agent
```

Native LLM benchmark remains valuable for **batch** self-play later, but is **not** required to ship AvaA.

---

## Investigation notes (2026-07-27)

Code review confirmed:

- Engine reply is applied inside `make_agent_move` before the HTTP response; move JSON does not list opponent UCI, but `your_turn`/`board` already reflect both plies for AvE.
- No long-poll/SSE on `/api/v1`; status poll is the wait primitive.
- Elo/`results.jsonl`/spectator/`games-list.js` all assume one agent + catalog engine.
- No lobby/matchmaking for agents exists (only engine `select_by_elo`).
