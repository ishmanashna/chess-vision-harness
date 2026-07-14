# Plan: Home server operations

> **Archived (2026-07-14).** Merged into **[Plan 1 — public-agent-api.md](../public-agent-api.md)** (Phases 2–4: deploy, limits, backup). Do not execute this as a separate plan.

Status: **superseded**  
Last updated: 2026-07-13  
Cross-cutting: supports all public-facing roadmap items  
Depends on: nothing to **start** Phases 0–1; Phase 2 **blocks** [`public-agent-api.md`](public-agent-api.md) Phase 2 (internet exposure)

---

## Goal

Run the harness **24/7 on home hardware** without losing games/ratings, melting the CPU, or letting open-internet abuse burn bandwidth or spawn unlimited engines.

---

## Decisions (locked)

| Topic | Choice |
|-------|--------|
| Hosting | Home server for now (not cloud VPS) |
| Protection | Data integrity + machine health + abuse prevention — **equal priority** |
| Discovery | Raw URL; no hub listing |

---

## Threats

| Risk | Mitigation |
|------|------------|
| Orphan Stockfish / pool workers | `engine_cleanup.py`, `serve stop`, `max_tasks_per_child=1` (done) |
| Disk fill from PGN/PNG/logs | Rotation, quotas, `harness prune` CLI |
| CPU/RAM from unlimited games | Global concurrency cap; queue or 503 |
| API abuse (spam games/moves) | Per-key + per-IP rate limits |
| Data loss on crash | Atomic writes (existing); optional nightly backup |
| TLS / exposure | Reverse proxy; only 443 public |

---

## Current state

| Exists today | Gap |
|--------------|-----|
| `engine_cleanup.py`, kill script | No scheduled janitor on server |
| Local `.chess_harness/` data dir | No backup automation |
| `play.py serve` | Binds localhost; not production-hardened |
| Windows dev machine | Production target OS/process manager TBD |

---

## Phases

### Phase 0 — Process supervision (1–2 days)

- [ ] Document production start: `play.py serve` + reverse proxy
- [ ] systemd unit (Linux) or NSSM (Windows) — auto-restart on crash
- [ ] Run cleanup on startup and shutdown (already partial)
- [ ] Health: `GET /health` → 200 if process up, engine count OK

### Phase 1 — Reverse proxy + TLS (1 day)

- [ ] Caddy or nginx config template in `deploy/`
- [ ] Let's Encrypt for home domain (or Cloudflare tunnel alternative)
- [ ] Bind harness to `127.0.0.1` only; proxy handles public

### Phase 2 — Limits (2–3 days)

- [ ] Config file: `max_concurrent_games`, `max_engine_processes`, `max_games_per_hour_per_key`
- [ ] Enforce in API middleware + `GameManager`
- [ ] Graceful 429/503 with `Retry-After`
- [ ] Log abuse patterns (IP, key id)

### Phase 3 — Backup & recovery (1–2 days)

- [ ] Nightly tarball: `models.json`, `results.jsonl`, `elo_calibration/results/merged_ratings.json`, recent games
- [ ] Restore procedure doc
- [ ] Optional: sync to off-site (S3, Backblaze) — user-provided credentials

### Phase 4 — Monitoring (1–2 days)

- [ ] Simple metrics endpoint: active games, engine count, disk free, uptime
- [ ] Optional: Uptime Kuma / healthchecks.io ping
- [ ] Alert on engine count > threshold (leak detector)

---

## Success criteria

- Server survives 24h with 5 concurrent agent games — no orphan engines, disk stable.
- Restart loses zero in-progress game state (or clean forfeits with audit).
- Obvious abuse (100 games/min from one IP) blocked without manual intervention.
- Operator can restore from backup in <30 minutes.

---

## Open questions

- Linux vs Windows for always-on host?
- Cloudflare Tunnel vs port-forward + Let's Encrypt?
- Max concurrent games budget for your hardware?
- Keep calibration running 24/7 or agent-games only?

---

## Estimate

**~1 week** spread across other features; Phase 0–1 can be done before public API launch.
