# Future work roadmap

Refined from product direction (not implementation specs). Estimates assume one developer who knows this repo.

## North star

A **public, community-style chess vision benchmark**: agents connect to **our API**, play rated games against the calibrated ladder, and results feed a shared leaderboard. More agents in the pool → more accurate, comparable ratings — a collective effort, not a private toy.

**Home server for now** (always-on on your hardware). Reliability goals: don’t lose games/ratings, don’t melt the box, don’t let abuse burn your connection or CPU.

---

## Core idea: one API, many clients

Inbound (#1) and “native benchmark” (#4) are **not two separate products**. They share one play surface:

| Client | Who runs it |
|--------|-------------|
| **External agents** | Anyone on the internet — their code pulls board PNG + FEN, posts moves |
| **Our batch runner** | Harness-owned client that calls LLM provider APIs and uses the **same** inscribe/play/move API |
| **Browser human** | Spectator UI for you, friends, and demos |

Outbound benchmark = **our official agent client** of the public API, with pinned configs and exportable results — not a hidden second code path.

---

## Features

| # | Goal | What you want |
|---|------|----------------|
| 1 | **Public agent API (inbound)** | REST/MCP-style: register agent, start game, `GET` board + FEN, `POST` moves; games → ladder/PGN archive. Open to anyone who finds it. |
| 4 | **Native LLM benchmark (outbound client)** | Adapter layer calling provider APIs; parse UCI/SAN; batch suite (N games × opponents); pinned configs; leaderboard JSON/CSV. Same API as #1. |
| 2 | **Agent vs agent** | Two inscribed models on one board — fun to watch **and** useful for model-vs-model ranking. |
| 3 | **Browser human vs agent** | You, friends/guests, and demo/streaming use cases on the same spectator. |
| — | **Live viewing** | Others watch games live in the browser (moves + board refresh). |

---

## Decisions (locked)

| Topic | Choice |
|-------|--------|
| **Build order** | No fixed priority — finish ladder calibration first, then ship features as needed. |
| **Discovery** | URL is enough for now; no benchmark-hub listing push. |
| **Agent signup** | Open registration; honor system (any agent name, no manual approval). |
| **Hosting** | Home server for now. |
| **Protection** | Still need caps on concurrent games/engines and basic abuse limits on a home box open to the internet — details TBD at API design time. |

**Prerequisite:** ladder calibration from 1320 → −600 with ≤100 ELO gaps and rungs below random (Stockfish harness + inverse_sf; MinimalChess backup optional).

---

## Also on the list

Live game streaming (SSE/WebSocket moves + board refreshes) — about **3–5 days** when we get to it.
