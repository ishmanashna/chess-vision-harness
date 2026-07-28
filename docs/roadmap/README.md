# Product roadmap

North star: [`future-work-roadmap.md`](future-work-roadmap.md).

**Rules**

- Plans are done **one at a time**. Never two numbered plans at once.
- Non-roadmap maintainer work ([`ladder-coverage-plan.md`](../ladder-coverage-plan.md)) runs only **between** numbered plans — pause product work first; do not interleave.

| # | Plan | Status | Estimate |
|---|------|--------|----------|
| **0** | [Thin foundation](00-architecture.md) | **done** | ~1 week |
| **1** | [Public agent API + Create Game](public-agent-api.md) | **done** | ~3–4 weeks |
| **3** | [Agent vs agent (lobby)](agent-vs-agent.md) | **implemented** | ~3–4 weeks |
| **2** | [Native LLM benchmark](native-llm-benchmark.md) | planned (after AvaA) | ~2 weeks |
| **4** | [Human vs agent (browser)](human-vs-agent.md) | planned | ~2 weeks |

**Order note:** Agent vs agent does **not** require the native LLM client. AvaA uses copy-paste HTTP briefs like Create Game. Plan 2 is optional automation on the same API and comes after AvaA unless priorities change again.

**Not in roadmap:** in-app live streaming (Twitch screen share).

**Archived:** [home-server-ops](archive/home-server-ops.md) (merged into Plan 1).

**Deploy (done):** [plan.md](plan.md) — public always-on site + home-PC game server. Operator entry: [`../../DEPLOY.md`](../../DEPLOY.md).  
**Proposal (not scheduled):** [proposal.md](proposal.md) — hosted vs local-engine create-game modes.

---

## Order (current)

```
Plan 0 → Plan 1 → Agent vs agent → Native LLM benchmark → Human vs agent
```

**Plan 0** — thin precursor (paths, lifecycle, `GameService`, `/health`).

**Plan 1** — public HTTP play + Create Game + deploy (**done**).

**Agent vs agent** — lobby tab, dual-principal `/api/v1`, poll/wait loop, shared ladder Elo (**next**).

**Native LLM benchmark** — harness-owned provider client for batch suites (after AvaA).

**Human vs agent** — browser play on the same API.
