# Future work roadmap

Numbered plans in [`README.md`](README.md) — **one at a time**, in order. Nothing in parallel.

## North star

Public chess vision benchmark: bring an agent, play rated games, shared leaderboard.

**Create Game** (Plan 1): tab → `game_id` → copyable brief → agent plays over your public HTTP API → watch on spectator (refresh/poll; stream on Twitch separately).

## Plans

| # | Plan |
|---|------|
| **0** | [Thin foundation](00-architecture.md) — paths, lifecycle, `GameService`, `/health` |
| **1** | [Public API + Create Game](public-agent-api.md) — backend, UI, deploy |
| **2** | [Native LLM benchmark](native-llm-benchmark.md) |
| **3** | [Agent vs agent](agent-vs-agent.md) |
| **4** | [Human vs agent](human-vs-agent.md) |

Opponent catalog work: [`ladder-coverage-plan.md`](../ladder-coverage-plan.md) — only **between** numbered plans.

## Decisions

| Topic | Choice |
|-------|--------|
| Execution | Strict serial: 0 → 1 → 2 → 3 → 4 |
| Architecture | Thin Plan 0 only; big refactors deferred until a later plan needs them |
| Live viewing | Twitch screen share — no in-app streaming plan |
| Hosting | Always-on public site (edge) + game origin on operator PC for now; `GAME_ORIGIN` swappable later — see [plan.md](plan.md) |
| Agent signup | Open; honor system |
| Dual create modes | Hosted vs local-engine submit — [proposal.md](proposal.md) only; not scheduled |

Index: [`README.md`](README.md).
