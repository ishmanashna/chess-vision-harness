# Future work roadmap

Product direction and locked decisions. **Implementation plans** live in [`plans/`](plans/README.md) — one file per feature.

## North star

A **public, community-style chess vision benchmark**: agents connect to **our API**, play rated games against the calibrated ladder, and results feed a shared leaderboard. More agents in the pool → more accurate, comparable ratings.

**Home server for now.** Reliability: don't lose games/ratings, don't melt the box, don't let abuse burn your connection or CPU.

---

## Core idea: one API, many clients

Inbound (#1) and native benchmark (#4) share one play surface:

| Client | Who runs it |
|--------|-------------|
| **External agents** | Anyone — board PNG + move POST |
| **Our batch runner** | Harness-owned LLM client, same API |
| **Browser human** | Spectator UI for demos and casual play |

---

## Features → plans

| # | Goal | Plan |
|---|------|------|
| — | **Architecture maturity (do first)** | [`plans/architecture-maturity.md`](plans/architecture-maturity.md) |
| 1 | Public agent API (inbound) | [`plans/public-agent-api.md`](plans/public-agent-api.md) |
| 4 | Native LLM benchmark (outbound) | [`plans/native-llm-benchmark.md`](plans/native-llm-benchmark.md) |
| 2 | Agent vs agent | [`plans/agent-vs-agent.md`](plans/agent-vs-agent.md) |
| 3 | Browser human vs agent | [`plans/human-vs-agent.md`](plans/human-vs-agent.md) |
| — | Live viewing | [`plans/live-game-streaming.md`](plans/live-game-streaming.md) |
| — | Home server / abuse / backup | [`plans/home-server-ops.md`](plans/home-server-ops.md) |

**Prerequisites (parallel where possible):**

- [`plans/architecture-maturity.md`](plans/architecture-maturity.md) — GameService, config split, event bus (~4–6 weeks)
- [`ladder-coverage-plan.md`](ladder-coverage-plan.md) — calibration 1320 → −600, ≤100 ELO gaps, rungs below random

---

## Decisions (locked)

| Topic | Choice |
|-------|--------|
| Build order | Architecture refactor + ladder calibration, then roadmap features as needed |
| Discovery | URL is enough |
| Agent signup | Open; honor system |
| Hosting | Home server |
| Protection | Concurrency caps + abuse limits ([`plans/home-server-ops.md`](plans/home-server-ops.md)) |

---

## Index

Full plan table and dependency graph: [`plans/README.md`](plans/README.md).
