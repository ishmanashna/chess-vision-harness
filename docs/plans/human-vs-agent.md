# Plan: Browser human vs agent

Status: **planned**  
Last updated: 2026-07-13  
Roadmap item: **#3**  
Depends on: [`public-agent-api.md`](public-agent-api.md) (CORS + session auth), [`live-game-streaming.md`](live-game-streaming.md) (optional polish)

---

## Goal

You, friends, and demo viewers play chess in the **browser** against an inscribed vision agent — same spectator app, new interactive mode.

Use cases: demos, streaming, casual human baseline vs agents, teaching.

---

## Decisions (locked)

| Topic | Choice |
|-------|--------|
| Agent side | Existing inscribed model; human does not need API key |
| Human auth | Guest or simple nickname for v1; no account system |
| Rating | Human games **excluded** from agent ELO ladder (or informal "guest" bucket) |

---

## Current state

| Exists today | Gap |
|--------------|-----|
| Spectator — read-only game watch | No human move input |
| `play.py move` — CLI only | No browser move UI |
| Board PNG generation | Need interactive board (click or drag-drop) |
| Agent plays vs engine | Human replaces engine **or** human replaces agent — pick one |

**Recommended model:** Human plays **White**, agent plays **Black** (agent keeps vision contract). Human sees full board (legal moves OK); agent still gets PNG only.

---

## UX flow

1. Operator or public page: "Play vs `<model>`" → creates `human_vs_agent` game.
2. Human gets interactive board in browser (chess.js or similar).
3. Human submits move → harness updates state → agent's turn triggered (webhook poll or harness calls agent API if agent is remote).
4. Agent move applied → board refreshes for human.
5. Game ends → optional PGN download; no ELO change for guest human.

---

## Phases

### Phase 0 — Game type (1–2 days)

- [ ] `game_type: "human_vs_agent"` in state
- [ ] Human moves via authenticated session cookie (not agent API key)
- [ ] Agent turn: invoke registered agent's move endpoint or local runner

### Phase 1 — Interactive board (3–4 days)

- [ ] Spectator page `/play/<game_id>` with move input
- [ ] Legal move validation client-side + server-side
- [ ] Orientation: human always at bottom
- [ ] Mobile-friendly layout (stretch goal)

### Phase 2 — Guest access (1–2 days)

- [ ] "Play as guest" — nickname only, no signup
- [ ] Rate limit guest games per IP
- [ ] Operator toggle: enable/disable public human play

### Phase 3 — Agent integration (2–3 days)

- [ ] When human moves, notify agent (poll `status` or server-push to agent's webhook)
- [ ] Timeout if agent doesn't move — human wins on time or draw policy
- [ ] Spectator tab shows human vs agent games alongside agent vs engine

---

## Success criteria

- Guest completes a game vs agent from browser without CLI.
- Agent still receives only board PNG on its turns (agent contract unchanged).
- Human games do not pollute agent ELO ladder.
- Works on home server behind TLS with reasonable latency.

---

## Open questions

- Human as White only, or choose color?
- Human ELO tracking for registered humans later?
- Stream-friendly layout (OBS browser source)?
- Block bots pretending to be human?

---

## Estimate

**~2 weeks** after public API + CORS. Board UI is the bulk of the work.
