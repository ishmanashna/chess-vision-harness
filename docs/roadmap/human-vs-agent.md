# Plan 4: Browser human vs agent

Status: **planned**  
Last updated: 2026-07-18  
**Prerequisite:** [Plan 3](agent-vs-agent.md) complete  
**Next plan:** — (last in current roadmap)

---

## Goal

Human plays in the browser against an inscribed vision agent. Agent still gets PNG only. Human games excluded from the agent ELO ladder.

Last product plan: depends on Plan 1’s public URL and on multi-principal / game-type patterns from Plan 3.

---

## Phases

### Phase 0 — Game type (1–2 days)

- [ ] `game_type: "human_vs_agent"`
- [ ] Human moves via session cookie (operator/public play routes)
- [ ] Agent turn via Plan 1 API

### Phase 1 — Interactive board (3–4 days)

- [ ] `/play/<game_id>` with click/drag moves
- [ ] Server + client legal move validation
- [ ] Human always at bottom
- [ ] Extract templates from spectator only if needed for this page

### Phase 2 — Guest access (1–2 days)

- [ ] Nickname-only guest play
- [ ] Rate limit per IP
- [ ] Operator toggle public human play

### Phase 3 — Agent integration (2–3 days)

- [ ] Agent notified / polled after human move (same HTTP contract)
- [ ] Timeout if agent idle
- [ ] Spectator shows human vs agent clearly
- [ ] Rating path excludes human games from agent ladder

---

## Success criteria

- Guest completes a game from the browser without CLI
- Agent contract unchanged (PNG only)
- Human games do not pollute agent ELO
- Works on Plan 1 public URL with TLS

---

## Estimate

**~2 weeks**

---

## Out of scope

- In-app live streaming → **not planned** (Twitch)
- New opponent rungs → [`ladder-coverage-plan.md`](../ladder-coverage-plan.md)
