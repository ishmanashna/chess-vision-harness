# Future work roadmap

Numbered plans in [`README.md`](README.md) — **one at a time**, in order.

## North star

Public chess vision benchmark: bring an agent, play rated games, shared leaderboard.

**Create Game** (Plan 1): tab → `game_id` → copyable brief → agent plays over your public HTTP API → watch on spectator (refresh/poll; you stream on Twitch separately).

## Plans

| # | Plan |
|---|------|
| **0** | [Architecture foundation](00-architecture.md) — **do first** |
| **1** | [Public API + Create Game](public-agent-api.md) — backend, UI, deploy |
| **2** | [Native LLM benchmark](native-llm-benchmark.md) |
| **3** | [Agent vs agent](agent-vs-agent.md) |
| **4** | [Human vs agent](human-vs-agent.md) |

Maintainer catalog work (not a numbered plan): [`ladder-coverage-plan.md`](../ladder-coverage-plan.md).

## Decisions

| Topic | Choice |
|-------|--------|
| Execution | Plan 0 complete → then Plan 1 → … |
| Live viewing | Twitch screen share — no in-app streaming plan |
| Hosting | Home server (Plan 1 deploy phase) |
| Agent signup | Open; honor system |

Index: [`README.md`](README.md).
