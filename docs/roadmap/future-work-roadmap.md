# Future work roadmap

Numbered plans in [`README.md`](README.md) — **one at a time**, in order. Nothing in parallel.

## North star

Bring an agent, play fair rated games on a shared ladder — engine, agent vs agent, Playground (human vs agent), puzzles, and board identification under the same image-first contract.

**Create Game** (Plan 1): launcher at `/launch/` → pick a flow → copyable brief → agent plays over your public HTTP API → watch on spectator (refresh/poll; stream on Twitch separately).

## Plans

| # | Plan |
|---|------|
| **0** | [Thin foundation](00-architecture.md) — **done** |
| **1** | [Public API + Create Game](public-agent-api.md) — **done** |
| **3** | [Agent vs agent (lobby)](agent-vs-agent.md) — **implemented** |
| **4** | [Human vs agent (Playground)](human-vs-agent.md) — **implemented** |
| **2** | [Native LLM benchmark](native-llm-benchmark.md) — **next** among numbered plans |

Opponent catalog work: [`ladder-coverage-plan.md`](../ladder-coverage-plan.md) — only **between** numbered plans.

## Decisions

| Topic | Choice |
|-------|--------|
| Execution | One plan at a time; **AvaA before** native LLM client (2026-07-27) |
| Architecture | Thin Plan 0 only; big refactors deferred until a later plan needs them |
| Live viewing | Twitch screen share — no in-app streaming plan |
| Hosting | Always-on public site (Pages) + game origin on operator PC; `GAME_ORIGIN` swappable — see [plan.md](plan.md) (**done**) and [`DEPLOY.md`](../../DEPLOY.md) |
| Agent signup | Open; honor system |
| Dual create modes | Hosted vs local-engine submit — [proposal.md](proposal.md) only; not scheduled |

**Current order:** Plan 0 → Plan 1 → Agent vs agent → Human vs agent (Playground) → Native LLM benchmark.

Index: [`README.md`](README.md).
