# Product roadmap

North star: [`future-work-roadmap.md`](future-work-roadmap.md).

**Rules:** Plans done **one at a time**, in order. Each plan is self-contained.

| # | Plan | Status | Estimate |
|---|------|--------|----------|
| **0** | [Architecture foundation](00-architecture.md) | **not started** | ~5–6 weeks |
| **1** | [Public agent API + Create Game](public-agent-api.md) | planned | ~3–4 weeks |
| **2** | [Native LLM benchmark](native-llm-benchmark.md) | planned | ~2 weeks |
| **3** | [Agent vs agent](agent-vs-agent.md) | planned | ~1–2 weeks |
| **4** | [Human vs agent (browser)](human-vs-agent.md) | planned | ~2 weeks |

**Not in roadmap:** in-app live streaming (you use Twitch screen share).

**Separate maintainer work:** [`ladder-coverage-plan.md`](../ladder-coverage-plan.md) (opponent catalog — can run during Plan 0).

**Archived:** [home-server-ops](archive/home-server-ops.md) (merged into Plan 1).

---

## Order (strict)

```
Plan 0 → Plan 1 → Plan 2 → Plan 3 → Plan 4
```

**Plan 0 is mandatory.** It puts `GameService`, spectator templates, and `/api/v1/` seams in place so Plans 1–4 add features without rewriting `board_controller.py`.

Plan 1 includes backend, Create Game, deploy, and production hardening (no separate ops plan).
