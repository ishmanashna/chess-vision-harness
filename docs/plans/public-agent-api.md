# Plan: Public agent API (inbound)

Status: **planned**  
Last updated: 2026-07-13  
Roadmap item: **#1**  
Depends on: [`architecture-maturity.md`](architecture-maturity.md), [`ladder-coverage-plan.md`](../ladder-coverage-plan.md)

---

## Goal

Expose the harness play surface over the **public internet** so anyone who finds the URL can register an agent, start rated games, read board images, and post moves. Games feed the shared ladder and PGN archive.

This is the **single backend** that inbound agents, our batch LLM runner, and (later) browser clients all call.

---

## Decisions (locked)

| Topic | Choice |
|-------|--------|
| Discovery | URL is enough; no benchmark-hub listing |
| Signup | Open registration; honor system (any agent name, no manual approval) |
| Hosting | Home server for now |
| Protection | Caps on concurrent games/engines + basic abuse limits (details at API design) |

---

## Current state

| Exists today | Gap |
|--------------|-----|
| `play.py` CLI — local only | No HTTP API for remote agents |
| MCP stdio server | Not reachable over network |
| `agent_surface.py` — redacted responses | Designed for trust-local IDE agents |
| `spectator.py` FastAPI — operator UI | Debug endpoints leak full state; not agent-safe |
| `models.json` inscription | Local file, no remote registration |
| File lock + per-game dirs | Works locally; needs concurrency limits at scale |

---

## API surface (target)

REST-first (MCP optional mirror for IDE users). Align with existing CLI semantics:

| Endpoint | Purpose |
|----------|---------|
| `POST /api/v1/agents` | Register agent (`model_id`, display name) → API key or token |
| `GET /api/v1/agents` | List public agents (leaderboard metadata) |
| `POST /api/v1/games` | Start game (`model_id`, optional `opponent`, color) |
| `GET /api/v1/games/{id}/board` | PNG board image (agent-safe) |
| `GET /api/v1/games/{id}/status` | Turn, clock, result — **no FEN, no legal moves** |
| `POST /api/v1/games/{id}/move` | UCI or SAN move |
| `POST /api/v1/games/{id}/resign` | Forfeit |
| `GET /api/v1/games/{id}/pgn` | After game ends |
| `GET /api/v1/leaderboard` | Agent + opponent ratings |

Optional later: `GET /api/v1/games/{id}/fen` for **non-vision** API agents (separate tier or flag).

Auth: per-agent API key in header. Rate limits per key + global caps.

---

## Phases

### Phase 0 — Design (1–2 days)

- [ ] OpenAPI spec from existing `agent_surface` contract
- [ ] Auth model (API keys in `models.json` or separate `agents.db`)
- [ ] Abuse limits: max concurrent games/key, max games/hour, max move rate
- [ ] Reverse proxy layout (Caddy/nginx on home server, TLS)
- [ ] Decide: FEN in public API or vision-only for v1

### Phase 1 — Local HTTP API (3–5 days)

- [ ] New router in `spectator.py` or `api/` package — **agent-safe only**
- [ ] Reuse `BoardController` + `GameManager`; no duplicate game logic
- [ ] API key middleware; reject unauthenticated writes
- [ ] Integration tests: full game over HTTP without MCP
- [ ] Document in README + `AGENTS.md` remote section

### Phase 2 — Home server exposure (2–3 days)

- [ ] Bind behind reverse proxy; Let's Encrypt TLS
- [ ] Process supervisor (systemd / NSSM on Windows)
- [ ] Health check endpoint; graceful shutdown (engine cleanup on stop)
- [ ] Log rotation; disk quota for `.chess_harness/games/`

### Phase 3 — Hardening (2–4 days)

- [ ] Global concurrency cap (games + engine processes)
- [ ] Idle game timeout (already exists — expose config)
- [ ] IP/key rate limiting
- [ ] Optional CAPTCHA on registration if abused
- [ ] Monitoring: active games, engine count, disk use

---

## Success criteria

- Remote agent completes a full rated game using only HTTP (board PNG + move POST).
- No FEN or move list leaks on agent endpoints (parity with `test_agent_surface.py`).
- Home server survives 10+ concurrent games without orphan engine processes.
- Leaderboard updates after remote games same as local CLI games.

---

## Open questions

- Vision-only v1 vs optional FEN tier for text-only agents?
- Store API keys hashed? Rotate/revoke flow?
- Public PGN archive browsable or per-game only?
- CORS for browser clients (needed for human-vs-agent plan)?

---

## Estimate

**~2–3 weeks** one developer, including home-server ops and hardening.
