> **Rebuild note (2026-09-10):** This experiment now targets real agent-vs-engine chess plus CSV usage export (`usage/exports/`). First-build artifacts (`lane-a-worker.txt`, dashboard `record-usage.ps1`, `usage-log.md`) are obsolete. Evidence below is kept for history.

# Lane B smoke — 2026-09-10 (Europe/Madrid)

> **Location:** `experiments/composer-load-and-burn/`  
> Restored 2026-09-10 from Dun-Dun session copy after a folder move truncated the disk file.

Machine: DESKTOP-7TGORRG (`5a735b1a-f55d-4bc1-8cb4-ddadb75ae5e1`)  
Repo: `C:\Users\jordi\Desktop\coding stuff\chess-vision-harness`  
Default story: Composer plays via brief + HTTP/CLI/MCP — harness does not call LLMs.

## 1) Harness path smoke

### Server
- **Already up** — did not start a new one.
- PID **13480**: `python.exe -m chess_harness serve --force`
- Health: `GET http://127.0.0.1:8765/health` → `{"ok":true,"status":"up",...}`
- Docs: `http://127.0.0.1:8765/docs`, OpenAPI: `http://127.0.0.1:8765/openapi.json`
- `chess-harness` not on PATH; working binary:  
  `%APPDATA%\Python\Python313\Scripts\chess-harness.exe`  
  (also `python -m chess_harness.__main__ …`)

### Commands used
```text
chess-harness.exe new --model composer-2.5 --opponent random --agent-color white
chess-harness.exe status <game_id>
chess-harness.exe board <game_id>
chess-harness.exe move <game_id> e2e4
```

### Results — **PASS**
| Step | Result | Detail |
|------|--------|--------|
| Create | PASS | `game_id=game-cpwdE8xwL7Xm5p2wJWoqjw`, WHITE vs `random`, `your_turn=true` |
| Observe | PASS | CLI `board_path`; local `board.png`; public `GET /g/{id}/board.png` (200, 46881 bytes). Authenticated `GET /api/v1/games/{id}/board.txt` needs Bearer model key (401/missing without it). No local `board.txt` file on disk. |
| Move | PASS | `chess-harness move … e2e4` → ok; status `move_count` 0→**2** (agent + random reply); PGN `1. e4 Nh6 *` |

### URLs / paths
- Game (spectator): `http://127.0.0.1:8765/g/game-cpwdE8xwL7Xm5p2wJWoqjw`
- Public board PNG: `http://127.0.0.1:8765/g/game-cpwdE8xwL7Xm5p2wJWoqjw/board.png`
- Local game dir: `.chess_harness\games\game-cpwdE8xwL7Xm5p2wJWoqjw\` (`board.png`, `game.pgn`, `state.json`)
- Earlier black-side create (unused for e2e4): `game-rrIYHQGVxznHBe0MtjeHqw`

### Note
OpenAPI `CreateGameBody` has no `model` field — model identity is via minted API key / CLI `--model` (Authorization Bearer on agent HTTP).

## 2) Composer burn visibility smoke (read-only)

### CLI
- `agent` present: `%LOCALAPPDATA%\cursor-agent\agent.cmd`
- `agent about` → Pro+, model Composer 2.5, email present; **no token/usage numbers**
- `agent status` → logged in only
- **No** `usage` / `billing` / `tokens` subcommand in `agent --help`

### Local artifacts (paths only; no secrets dumped)
| Path | Parseable for metering? |
|------|-------------------------|
| `%APPDATA%\Cursor\logs\**\cursor.requestTraces.log` | Span/timing traces (`agent.request`, Composer spans). **No** `token`/`usage`/`billing`/`promptTokens` hits in latest sample. Good for latency/request counts, not token $ |
| `%USERPROFILE%\.cursor\ai-tracking\ai-code-tracking.db` | SQLite: code attribution (`ai_code_hashes`, `scored_commits`, …). **Not** LLM token/billing |
| `%APPDATA%\Cursor\User\globalStorage\state.vscdb` | Keys exist: `cursorAuth/stripeSubscriptionStatus=active`, billing-banner dismissals, `cursor.slashUsage.v1` (slash-command usage, not LLM). Auth tokens present (redacted). **No** clear included/on-demand remaining balance field found by name probe |
| `https://cursor.com/dashboard` / `…/dashboard/usage` | Exists (settings→308→dashboard); unauthenticated fetch **403** — needs signed-in browser for coarse $ meter |

### Conclusions
- Fine-grained per-seat tokens: **NO** (not exposed via CLI or obvious local parseable token logs)
- Coarse before/after money meter: **UNKNOWN → likely YES via dashboard UI only** (Pro+ / stripe `active`; no local machine-readable remaining balance found in this probe)
- What to try next (one real Composer move later):
  1. Screenshot / note Cursor dashboard usage (included + on-demand) **before** and **after** one brief+move Composer turn
  2. Diff newest `cursor.requestTraces.log` around that turn for any new usage fields
  3. Optional: `agent --mode ask` one-liner (cheap) only after confirming dashboard baseline

## 3) Optional CLI agent ask
**SKIPPED** in first harness smoke (keep cheap). Later `METER_PROBE` ask (~18s) confirmed no local usage delta — see `METER_ALT.md`.

## Lane A smokes (same day)

| Check | Result | Notes |
|-------|--------|--------|
| OS WMI sampler | **PASS** | ~13 GB RAM free; English `Get-Counter` fails on ES locale — use WMI/`LoadPercentage` |
| CLI `agent -p --trust --mode ask "Reply with exactly: SMOKE_OK"` | **PASS** | ~32s; exit 0; no auth block. Binary: `%LOCALAPPDATA%\cursor-agent\agent.cmd` |

## Alternatives locked

See `METER_ALT.md`. Summary:
1. Primary burn meter = dashboard included + on-demand before/after → `usage-log.md`
2. Secondary = requestTraces request-count / latency only (not $)
3. PATH = full `chess-harness.exe` or `python -m chess_harness`
4. Observe = CLI board/status + public `/g/{id}/board.png`; Bearer only if agent uses HTTP API

## Blockers for a later full Composer game meter
1. No CLI/API for per-request or per-seat token counts → metering must be **dashboard before/after**
2. Agent HTTP observe (`board.txt` / PNG under `/api/v1/…`) needs harness **Bearer API key**; CLI + public PNG do not
3. `chess-harness` not on PATH — use full Scripts path or `python -m chess_harness`
4. Do **not** play a full game in smoke; full meter run needs explicit budget + dashboard baseline

## Verdict
- Harness create/observe/move: **PASS**
- Server: **already up** (`serve --force`, port 8765)
- OS + CLI ask: **PASS**
- Usage probe: coarse UI locked; fine-grained tokens **NO** from Shell
