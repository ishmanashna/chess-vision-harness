# Plan: Live game streaming

Status: **planned**  
Last updated: 2026-07-13  
Roadmap item: **live viewing** (also supports #2, #3)  
Depends on: [`architecture-maturity.md`](architecture-maturity.md) (EventBus), existing `spectator.py`

---

## Goal

Anyone with the spectator URL watches games **live** — board updates and move list refresh without manual page reload. Foundation for agent-vs-agent spectacle and human-vs-agent demos.

---

## Decisions (locked)

| Topic | Choice |
|-------|--------|
| Transport | SSE first (simpler); WebSocket if bidirectional needed later |
| Scope | All active game types (agent vs engine, agent vs agent, human vs agent) |
| Public | Read-only stream; no move injection via stream |

---

## Current state

| Exists today | Gap |
|--------------|-----|
| Spectator polls or partial refresh | No push updates; stale UI during fast games |
| `GET /api/games/{id}/state` | Full fetch each time |
| Static board PNG per turn | Client must re-fetch image on change |
| FastAPI app | No SSE/WebSocket routes |

---

## Event model

Server emits on game state change:

```json
{
  "type": "move",
  "game_id": "abc123",
  "ply": 14,
  "san": "Nf3",
  "turn": "black",
  "board_url": "/api/games/abc123/board.png?v=14",
  "result": null
}
```

Terminal events: `game_over`, `resign`, `timeout`.

Channels:

- `GET /api/stream/games` — all active games (spectator home)
- `GET /api/stream/games/{id}` — single game focus

---

## Phases

### Phase 0 — SSE backbone (2 days)

- [ ] `GameManager` hook: broadcast on move/result (in-process asyncio queue)
- [ ] `GET /api/stream/games/{id}` — `text/event-stream`
- [ ] Heartbeat every 30s; reconnect-friendly `Last-Event-ID`
- [ ] Tests: mock game, assert event sequence

### Phase 1 — Spectator UI (2 days)

- [ ] Replace polling with `EventSource` on active game page
- [ ] Update board image + move list on `move` events
- [ ] Connection status indicator (live / reconnecting)
- [ ] Fallback to poll if SSE unsupported

### Phase 2 — Multi-game dashboard (1 day)

- [ ] Home tab subscribes to global stream
- [ ] Thumbnail or mini-board updates for parallel games
- [ ] Calibration tab: optional rating-update events (lower priority)

### Phase 3 — WebSocket (optional, 1–2 days)

- [ ] Only if human-vs-agent needs low-latency bidirectional
- [ ] Same event schema as SSE

---

## Success criteria

- Spectator shows new move within **<2s** of harness accepting it (local network).
- 10 concurrent viewers on one game without extra engine load.
- Reconnect after tab sleep recovers current position.
- No agent-only data (FEN, legal moves) on public stream endpoints.

---

## Open questions

- Cache-bust board PNG via query param vs separate move-only payload?
- Auth on streams (public read vs token)?
- Compress event batching for calibration flood?

---

## Estimate

**~3–5 days** per roadmap. Can ship Phase 0–1 before public API; benefits local spectator immediately.
