# Plan: Native LLM benchmark (outbound client)

Status: **planned**  
Last updated: 2026-07-13  
Roadmap item: **#4**  
Depends on: [`public-agent-api.md`](public-agent-api.md) (same play surface)

---

## Goal

An **official harness-owned client** that calls LLM provider APIs, plays games through the **same API as external agents**, and runs batch suites with pinned configs and exportable results.

Not a second hidden code path — this is how *we* dogfood the public benchmark.

---

## Decisions (locked)

| Topic | Choice |
|-------|--------|
| API target | Same REST API as inbound agents (#1) |
| Config | Pinned model IDs, prompts, opponents, N games — reproducible runs |
| Output | Leaderboard JSON/CSV + per-game PGN/audit trail |

---

## Current state

| Exists today | Gap |
|--------------|-----|
| Manual subagent runs via `AGENTS.md` + MCP/CLI | No automated provider integration |
| `models.json` inscription | Local only until API exists |
| `results.jsonl`, `leaderboard` CLI | No batch orchestration or export format |
| Operator docs in `scripts/run_agent_game.md` | Human-driven, not scripted |

---

## Architecture

```
benchmark_runner/
  providers/     # openai, anthropic, cursor, ollama, …
  vision.py      # board PNG → provider message
  parser.py      # model text → UCI/SAN (reuse move validation)
  suite.py       # YAML: model × opponents × N × colors
  reporter.py    # JSON/CSV/MD summary
```

Runner calls **public API** (`POST /games`, `GET /board`, `POST /move`) — not `BoardController` directly — so results are comparable to community agents.

Local dev mode: runner may call in-process API or `localhost` without TLS.

---

## Phases

### Phase 0 — Provider adapter (3–4 days)

- [ ] Abstract `LLMProvider` — `complete(messages, image_bytes) → str`
- [ ] OpenAI-compatible adapter (covers many providers)
- [ ] Anthropic vision adapter
- [ ] Config: API keys via env, never committed
- [ ] Unit tests with mocked responses

### Phase 1 — Move loop (2–3 days)

- [ ] Prompt template from `AGENTS.md` (versioned in suite YAML)
- [ ] Parse UCI/SAN from model output (regex + fallback retry prompt)
- [ ] Idle timeout handling; resign on repeated illegal moves
- [ ] Log full prompt/response for audit (operator-only, gitignored)

### Phase 2 — Suite runner (2–3 days)

- [ ] YAML suite format: `model`, `provider`, `opponents[]`, `games_per_pair`, `colors`
- [ ] Parallel games with distinct `game_id`s (respect API concurrency caps)
- [ ] `benchmark run --suite nightly.yaml` CLI
- [ ] Export: `results/benchmarks/<run_id>/summary.json`, `games.csv`, PGNs

### Phase 3 — Pinning & CI (1–2 days)

- [ ] Lock prompt hash + model version in output metadata
- [ ] Optional GitHub Action (self-hosted runner on home server) for scheduled suites
- [ ] Compare runs over time (ELO drift, illegal-move rate)

---

## Success criteria

- One command runs N games against M opponents for a configured model without human intervention.
- Results export matches what a remote agent would produce on the same API.
- Pinned config reproduces comparable runs (same prompt hash, same opponent IDs).
- Illegal-move rate and latency reported per model.

---

## Open questions

- Which providers for v1? (OpenAI + Anthropic minimum?)
- Retry policy on provider 429/5xx?
- Store raw model responses publicly or operator-only?
- Cost budget caps per suite run?

---

## Estimate

**~2 weeks** after public API Phase 1 lands. Can prototype move-loop locally against CLI before API ships.
