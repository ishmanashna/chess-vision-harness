# Plan 2: Native LLM benchmark (outbound client)

Status: **planned**  
Last updated: 2026-07-14  
**Prerequisite:** [Plan 1](public-agent-api.md) complete  
**Next plan:** [Plan 3 — Agent vs agent](agent-vs-agent.md)

---

## Goal

Harness-owned client that calls LLM providers and plays games through the **same HTTP API as Plan 1** — batch suites, pinned configs, exportable results.

---

## Phases

### Phase 0 — Provider adapter (3–4 days)

- [ ] `LLMProvider` abstraction
- [ ] OpenAI-compatible + Anthropic vision adapters
- [ ] API keys via env; unit tests with mocks

### Phase 1 — Move loop (2–3 days)

- [ ] Prompt from `AGENTS.md` (versioned in suite YAML)
- [ ] Parse UCI/SAN from model output
- [ ] Illegal-move / idle timeout handling
- [ ] Audit log (operator-only, gitignored)

### Phase 2 — Suite runner (2–3 days)

- [ ] YAML: model, provider, opponents, N games, colors
- [ ] Parallel games via Plan 1 API (respect concurrency caps)
- [ ] `benchmark run --suite …` CLI
- [ ] Export summary JSON, CSV, PGNs

### Phase 3 — Pinning & CI (1–2 days)

- [ ] Prompt hash + model version in output
- [ ] Optional scheduled runs on home server

---

## Success criteria

- One command runs N games without human intervention
- Results comparable to a remote agent on Plan 1 API
- Pinned config reproduces runs
- Illegal-move rate and latency reported

---

## Estimate

**~2 weeks**
