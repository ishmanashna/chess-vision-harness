# Product roadmap

North star: [`future-work-roadmap.md`](future-work-roadmap.md).

**Rules**

- Plans are done **one at a time**, in order. Never two numbered plans at once.
- Non-roadmap maintainer work ([`ladder-coverage-plan.md`](../ladder-coverage-plan.md)) runs only **between** numbered plans — pause product work first; do not interleave.

| # | Plan | Status | Estimate |
|---|------|--------|----------|
| **0** | [Thin foundation](00-architecture.md) | **done** | ~1 week |
| **1** | [Public agent API + Create Game](public-agent-api.md) | **done** | ~3–4 weeks |
| **2** | [Native LLM benchmark](native-llm-benchmark.md) | planned | ~2 weeks |
| **3** | [Agent vs agent](agent-vs-agent.md) | planned | ~1–2 weeks |
| **4** | [Human vs agent (browser)](human-vs-agent.md) | planned | ~2 weeks |

**Not in roadmap:** in-app live streaming (Twitch screen share).

**Archived:** [home-server-ops](archive/home-server-ops.md) (merged into Plan 1).

**Deploy follow-on (before Plan 2):** [plan.md](plan.md) — public always-on site + home-PC game server (one URL).  
**Proposal (not scheduled):** [proposal.md](proposal.md) — hosted vs local-engine create-game modes.

---

## Order (strict)

```
Plan 0 → Plan 1 → Plan 2 → Plan 3 → Plan 4
```

**Plan 0** is a thin precursor (paths, engine lifecycle, `GameService`, `/health`) — not a multi-week rewrite.

**Plan 1** is the north-star product: public HTTP play + Create Game + deploy.

**Plan 2** uses that HTTP API as a harness-owned LLM client.

**Plans 3–4** add game types on the same API; do them after Plan 2 unless the north star changes.
