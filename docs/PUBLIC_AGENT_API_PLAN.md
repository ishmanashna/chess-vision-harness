# Public agent API + Create Game

Anyone with the harness URL can register an agent, create a rated vision game, and play it over HTTP. Localhost first; public deploy and hardening follow.

**Plan 1 status: complete (2026-07-19).** Phases 0–4 done; see [`docs/roadmap/public-agent-api.md`](roadmap/public-agent-api.md).

## Scope

In scope: `/api/v1` play API, API keys tied to inscribed models, Create Game tab + copyable agent brief, deploy templates, abuse limits, backup/monitoring.

Out of scope: automated LLM runner, agent-vs-agent, human browser moves, SSE/WebSocket, ladder catalog work.

## Locked design

### Auth

- Header: `Authorization: Bearer <api_key>`.
- Store: `.chess_harness/api_keys.json` under `resolve_base_dir()` (gitignored runtime data).
- Persist `model_id`, `key_hash` (SHA-256 of raw key), `key_prefix` (first 8 chars), `created`.
- Raw key returned **once** on `POST /api/v1/agents`. Never stored in plaintext.
- Every `/api/v1/games*` mutation/read for a game requires a key whose `model_id` matches that game’s model.
- `GET /api/v1/agents` and `GET /api/v1/leaderboard` are unauthenticated (public list/ratings).
- `GET /health` stays unauthenticated.

### HTTP contract (`/api/v1`)

Mount on the existing FastAPI spectator app. New module `python/src/chess_harness/api_v1.py` — do not grow `spectator.py`. All game mutations/reads go through `GameService` only. Responses for agents go through `agent_surface` (no FEN, no move lists, no internal paths that leak position).

| Method | Path | Auth | Behavior |
|--------|------|------|----------|
| POST | `/api/v1/agents` | no | Body `{id, name?}`. Inscribe model if needed + create key. Return `{model_id, name, api_key}` once. |
| GET | `/api/v1/agents` | no | List inscribed agents `{id, name, elo}` (no keys). |
| POST | `/api/v1/games` | yes | Body `{opponent?, agent_color?}`. Start game as key’s model. Return agent-safe start payload + `game_id`. |
| GET | `/api/v1/games/{id}/status` | yes | Agent-safe status (turn metadata). |
| GET | `/api/v1/games/{id}/board` | yes | `image/png` bytes only (`GameService.get_board_bytes`). |
| POST | `/api/v1/games/{id}/move/{uci_or_san}` | yes | Move in path; no body (preferred). Legacy JSON `POST .../move` still accepted. |
| POST | `/api/v1/games/{id}/resign` | yes | Resign. |
| GET | `/api/v1/games/{id}/pgn` | yes | Finished games only. |
| GET | `/api/v1/leaderboard` | no | Agent ratings JSON. |
| GET | `/api/v1/metrics` | no | Operator load: active games, engine count, disk free, configured limits (no secrets). |

Errors: JSON `{ok: false, error: "..."}` with 4xx/5xx. Rate limits return 429/503 with `Retry-After`. Illegal move → 400. Wrong key / unknown game → 401/404. Never include FEN in agent error bodies.

Legacy `GET /api/games/*` stays for spectator UI only. Agents must not use it.

### Agent brief

Template function returns plain text: public/base URL, `game_id`, `Authorization` header line, curl loop (status → board PNG → move), vision rules (board image only; no FEN shortcuts). Create Game copy button uses this. Dev default base `http://127.0.0.1:8765`. Env `CHESS_HARNESS_PUBLIC_URL` overrides for deploy.

### Abuse numbers (enforce in hardening phase)

- `max_concurrent_games`: 10
- `max_engine_processes`: 12
- `max_games_per_hour_per_key`: 20
- `max_moves_per_hour_per_key`: 600
- Idle timeout: 5 minutes without a move → game ends with **no result** (`*`, no ELO). Not a draw or resign.

### Deploy layout (deploy phase)

- Harness binds `127.0.0.1:8765` only.
- Caddy (preferred) or nginx terminates TLS and proxies `/`.
- systemd (Linux) / NSSM (Windows) restarts `chess-harness serve`.
- Briefs use `CHESS_HARNESS_PUBLIC_URL`.
- Log rotation + games disk quota noted in deploy README.

## Phases

### Phase 0 — Design

Done when this document’s locked design is accepted and roadmap Plan 1 is marked in progress. No code.

### Phase 1a — HTTP API + keys

Add `ApiKeyStore`, auth dependency, `api_v1` router wired from spectator app lifespan/shared `GameService`. Implement all `/api/v1` endpoints above. Integration test: register → create game → play moves via HTTP → resign or finish; assert PNG content-type; assert no `fen`/`board_fen`/`moves` keys on agent JSON. Keep files ≤300 lines; split helpers if needed.

**Done (2026-07-19):** `api_keys.py`, `api_v1.py`, spectator router mount, `tests/test_api_v1.py` + `tests/test_api_keys.py`.

Done when: endpoints work on localhost; integration test green; spectator legacy routes unchanged.

### Phase 1b — Create Game UI + docs

Create Game tab on spectator: **model picker only** — no opponent, color, or API key fields. On submit: `ApiKeyStore.create(model_id)` mints auth invisibly; `GameService.new_game` with random color and default ELO-weighted opponent (`opponent_id` omitted). Show `game_id` + copyable **agent prompt** (paste-ready brief with embedded `Authorization` header, play loop, vision rules). New games appear on Active (existing poll/refresh). `AGENTS.md` centers Create Game → paste prompt; `POST /api/v1/agents` remains for API-only clients. Prefer new HTML helper module over bloating `spectator.py`.

**Done (2026-07-19):** `agent_brief.py`, `create_game_page.py`, `/create` routes, spectator tab, `AGENTS.md` + README remote section, `tests/test_agent_brief.py`, `tests/test_create_game.py`.

Done when: operator can create a game in the browser, copy brief, and an HTTP client can finish the loop; docs mention remote play.

### Phase 2 — Deploy

`deploy/` with Caddyfile template, systemd unit, Windows NSSM notes, bind localhost, graceful shutdown already via lifespan. Document `CHESS_HARNESS_PUBLIC_URL`, TLS, log rotation, disk quota.

**Done (2026-07-19):** `deploy/README.md`, `deploy/Caddyfile`, `deploy/nginx.conf.example`, `deploy/chess-harness.service`, `deploy/games_disk_usage.sh`. Harness default bind `127.0.0.1:8765` confirmed (`commands.cmd_serve`, `__main__.py`); lifespan in `spectator._lifespan` releases engines on stop.

Done when: an operator can follow `deploy/README.md` and expose the harness behind TLS with briefs using the public URL.

### Phase 3 — Production hardening

Config module for abuse numbers; middleware + game-layer enforcement; 429/503 + `Retry-After`; optional IP rate limit; basic metrics endpoint or log gauges (active games, engine count, disk free).

**Done (2026-07-19):** `limits.py`, `api_limits.py`, `/api/v1/metrics`, env-configurable caps + idle timeout; `tests/test_api_limits.py`.

Done when: over-limit requests are rejected automatically; metrics visible to operator.

### Phase 4 — Backup & monitoring

Nightly backup script (models, results, ratings, recent games); restore steps in deploy/README; optional healthchecks.io note for `/health`; alert guidance if engine count exceeds threshold.

**Done (2026-07-19):** `scripts/backup_harness.py`, restore + monitoring sections in `deploy/README.md`, `tests/test_backup_harness.py`.

Done when: backup/restore is documented and scripted; monitoring hooks are documented.

## How to verify

- Phase 1a: targeted pytest for `api_v1` + key store only.
- Phase 1b: manual Create Game + curl from brief; game on Active tab.
- Phase 2: dry-run config files; process binds localhost.
- Phase 3: unit tests for limit math; overflow returns 429.
- Phase 4: script creates tarball from a temp harness dir.

Do not run the full pytest suite inside a phase agent.

## Estimated duration

- Phase 0: 0.5–1 agent-hour (design already locked here)
- Phase 1a: 4–8 agent-hours
- Phase 1b: 3–6 agent-hours
- Phase 2: 2–4 agent-hours
- Phase 3: 4–8 agent-hours
- Phase 4: 2–4 agent-hours
