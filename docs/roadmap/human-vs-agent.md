# Plan 4: Browser human vs agent

Status: **implemented** (Playground — `/launch/?flow=playground`, `/play/{id}`)  
Last updated: 2026-08-13  
**Prerequisite:** [Plan 3](agent-vs-agent.md) complete  
**Next plan:** — (native LLM benchmark is separate; see [README](README.md))

---

## Goal

Human plays in the browser against an inscribed vision agent. Agent still gets PNG only. Human games excluded from the agent ELO ladder.

Last product plan: depends on Plan 1’s public URL and on multi-principal / game-type patterns from Plan 3.

---

## Shipped (Playground)

All planned phases below shipped as **Playground** (`/launch/?flow=playground`, `/play/{id}`):

- [x] `game_type: "human_vs_agent"` — human moves via session cookie; agent turn via Plan 1 API
- [x] `/play/{id}` interactive board (click/drag, server + client legal validation, human at bottom)
- [x] Nickname guest play, per-IP rate limits, operator toggle for public human play
- [x] Agent polls after human move (same HTTP contract); idle timeout; spectator AvH labeling; human games excluded from agent Elo ladder
- [x] Chat, draw offers, resume from Spectator → My games

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
