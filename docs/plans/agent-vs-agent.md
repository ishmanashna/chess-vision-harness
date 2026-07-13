# Plan: Agent vs agent

Status: **planned**  
Last updated: 2026-07-13  
Roadmap item: **#2**  
Depends on: [`public-agent-api.md`](public-agent-api.md), [`live-game-streaming.md`](live-game-streaming.md) (for watchability)

---

## Goal

Two inscribed vision agents play each other on one board. Useful for **model-vs-model ranking** and **spectacle** (fun to watch in the spectator).

Both sides use the same agent contract: board PNG only, post moves when it's their turn.

---

## Decisions (locked)

| Topic | Choice |
|-------|--------|
| Rating | Both models update ELO from result (like engine floaters) |
| Pairing | Operator-initiated or API `POST /games` with `white_model` + `black_model` |
| Opponent engine | None — pure agent vs agent |

---

## Current state

| Exists today | Gap |
|--------------|-----|
| Agent vs **engine** games | No agent vs agent game type |
| `GameManager` assumes one human/agent side + one engine | Need dual-agent turn routing |
| Spectator shows agent vs engine | Need UI for both agent names + dual orientation |
| ELO updates agent vs engine only | Need pairwise agent ELO (or treat as symmetric) |

---

## Game model

```
game_type: "agent_vs_agent"
white_model_id: "composer-2.5"
black_model_id: "gpt-4o"
state: waiting_white | waiting_black | finished
```

Turn dispatch:

1. After opponent move, status flips to waiting for other model.
2. Each model polls/gets board only on **their** turn (or push via webhook later).
3. No engine process spawned — `OpponentEngineManager` idle for this game type.

Idle timeout applies per side independently (configurable).

---

## Phases

### Phase 0 — Data model (1 day)

- [ ] Extend `state.json` schema for `agent_vs_agent`
- [ ] `play.py new --white <id> --black <id>` (operator) or API equivalent
- [ ] Validation: both models inscribed; cannot use `--opponent`

### Phase 1 — Play loop (2–3 days)

- [ ] `BoardController` routes moves to correct side without engine reply
- [ ] After white moves, black's turn — engine not consulted
- [ ] MCP/HTTP: reject move when not caller's turn
- [ ] Tests: full game two mocked agents

### Phase 2 — ELO (1–2 days)

- [ ] Update `ELOLadder` for agent-agent results (both sides floating or fixed pool)
- [ ] Leaderboard section: agent-agent ratings vs engine ladder (separate or merged — decide)
- [ ] `results.jsonl` event type `agent_vs_agent`

### Phase 3 — Spectator (2–3 days)

- [ ] UI: both model names, avatars, side labels
- [ ] Show whose turn; highlight waiting model
- [ ] Link to both agents' leaderboard entries
- [ ] Works with live streaming plan (SSE move events)

---

## Success criteria

- Two API-registered agents complete a game with correct turn enforcement.
- Both models' ELO update from result.
- Spectator shows readable agent-vs-agent board with correct orientation per side.
- `game audit` passes for both sides.

---

## Open questions

- Separate agent-agent ELO pool vs same ladder as vs-engines?
- Async play (hours between moves) vs real-time only?
- Allow same model vs itself (self-play)?
- Max concurrent agent-agent games on home server?

---

## Estimate

**~1–2 weeks** after public API exists. Spectator polish overlaps with live streaming.
