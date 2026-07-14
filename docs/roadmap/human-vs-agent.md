# Plan 4: Browser human vs agent

Status: **planned**  
Last updated: 2026-07-14  
**Prerequisite:** [Plan 1](public-agent-api.md) complete  
**Next plan:** — (last in current roadmap)

---

## Goal

Human plays in the browser against an inscribed vision agent. Agent still gets PNG only. Human games excluded from agent ELO ladder.

Uses Plan 0 session-auth hook on operator routes.

---

## Phases

### Phase 0 — Game type (1–2 days)

- [ ] `game_type: "human_vs_agent"`
- [ ] Human moves via session cookie
- [ ] Agent turn via Plan 1 API

### Phase 1 — Interactive board (3–4 days)

- [ ] `/play/<game_id>` with click/drag moves
- [ ] Server + client legal move validation
- [ ] Human always at bottom

### Phase 2 — Guest access (1–2 days)

- [ ] Nickname-only guest play
- [ ] Rate limit per IP
- [ ] Operator toggle public human play

### Phase 3 — Agent integration (2–3 days)

- [ ] Notify agent on human move
- [ ] Timeout if agent idle
- [ ] Spectator tab for human vs agent games

---

## Success criteria

- Guest completes game from browser without CLI
- Agent contract unchanged (PNG only)
- Human games do not pollute agent ELO
- Works on Plan 1 public URL with TLS

---

## Estimate

**~2 weeks**
