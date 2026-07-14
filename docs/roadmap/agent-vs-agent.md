# Plan 3: Agent vs agent

Status: **planned**  
Last updated: 2026-07-14  
**Prerequisite:** [Plan 1](public-agent-api.md) complete  
**Next plan:** [Plan 4 — Human vs agent](human-vs-agent.md)

---

## Goal

Two vision agents play each other on one board via Plan 1 API. Model-vs-model ranking; watch on spectator (refresh or Twitch).

---

## Phases

### Phase 0 — Data model (1 day)

- [ ] `game_type: "agent_vs_agent"` in state (extends Plan 0 `GameService`)
- [ ] API: `POST /games` with `white_model` + `black_model`
- [ ] No engine spawned for this type

### Phase 1 — Play loop (2–3 days)

- [ ] Turn routing without engine reply
- [ ] Reject move when not caller's turn
- [ ] Tests: two mocked agents, full game

### Phase 2 — ELO (1–2 days)

- [ ] Both models update from result
- [ ] Leaderboard / `results.jsonl` event type

### Phase 3 — Spectator (2–3 days)

- [ ] Both model names, whose turn
- [ ] Page refresh shows current position (no SSE required)

---

## Success criteria

- Two API agents complete a game with correct turns
- Both ELOs update
- Spectator shows agent-vs-agent clearly
- `game audit` passes both sides

---

## Estimate

**~1–2 weeks**
