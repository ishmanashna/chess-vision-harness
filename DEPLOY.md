# Deploy — Chess Vision Harness

How the public benchmark is hosted today, and how to run the game server on your machine (or move it later).

**Live site:** [https://chessvisionharness.pages.dev](https://chessvisionharness.pages.dev)

---

## Architecture (current)

```text
Visitors / agents
        │
        ▼
https://chessvisionharness.pages.dev     ← Cloudflare Pages (always on)
   public-site/  +  Pages Functions
        │
        ├─ static Home / Leaderboard / Contact
        │     Online → live ladder via /api/leaderboard/live (proxied)
        │     Sleeping → public-site/data/leaderboard.json (offline fallback)
        │
        └─ live paths (/api/v1/*, /api/games/*, /g/*, Create when online)
              proxy via GAME_ORIGIN
                    │
                    ▼
         Cloudflare Tunnel → http://127.0.0.1:8765
                    │
                    ▼
         chess-harness serve   (your PC, localhost only)
```

| Variable | Where | Purpose |
|----------|--------|---------|
| `GAME_ORIGIN` | Pages deploy (GitHub secret `GAME_ORIGIN`, injected into Functions) | Upstream harness URL — tunnel or host. **No trailing slash.** |
| `CHESS_HARNESS_PUBLIC_URL` | Game PC / harness service | URL in agent briefs — always the **Pages** URL, never the raw tunnel hostname |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `AUTH_SESSION_SECRET` | Pages deploy (GitHub Actions secrets, injected like `GAME_ORIGIN`) | Cosmetic Google sign-in on the public site — does **not** gate create/inscribe. Setup: [`deploy/pages.md`](deploy/pages.md). |
| `CHESS_HARNESS_AUDIT_SALT` | Game PC / harness service | Salt for hashing client IPs in `.chess_harness/audit/activity.jsonl` (create/inscribe log). |
| `CHESS_HARNESS_TRUSTED_PROXIES` | Game PC / harness service | Comma-separated CIDRs for the **immediate** proxy hop (typically `127.0.0.0/8` when `cloudflared` connects to localhost). **Required for Online** — Pages forwards each visitor via `X-Forwarded-For`; without this, all traffic looks like `127.0.0.1` for per-IP limits. The harness logs a one-time warning on the first loopback request that carries forwarded identity headers when unset. |

Calibration (`/calibration*`) is blocked at the Pages edge. Run it only on the game PC at **`http://127.0.0.1:8765/calibration`** (direct localhost — not via tunnel/Pages). On loopback hostnames (`127.0.0.1`, `localhost`), the shared site nav inserts **Calibration** after Leaderboard with no status probe; on the deployed Pages host the tab never appears. Direct loopback Host (`127.0.0.1` / `localhost`) may POST without a secret. Via tunnel or any non-loopback Host, calibration **POST** endpoints require `CHESS_HARNESS_CALIBRATION_SECRET` (header `CHESS_HARNESS_CALIBRATION_SECRET` or query `calibration_secret`) or set `CHESS_HARNESS_ALLOW_REMOTE_CALIBRATION=1`. Do not rely on client IP behind Cloudflare Tunnel.

**Calibration data layers:** **A** engine Elo from `elo_calibration/results/*/ratings.json`; **B** quality samples from `continuous/play_rating_samples.jsonl`; **C** accuracy→Elo map in `accuracy_elo_map.json`; **D** agent ladder in `$CHESS_HARNESS_DIR` (unchanged). Serve reads **A–C from disk** for `/api/calibration/status` even when the worker is stopped; live activity overlays from `.chess_harness/calibration_worker/status.json`. `merged_ratings.json` is **publish-only** (not runtime SSOT). Continuous start/stop POSTs still require the worker.

### Local serve vs Pages (intentional diffs)

When you run `chess-harness serve`, the origin serves the same `public-site/` HTML/CSS/JS as Pages for `/`, `/launch/`, `/spectator/`, `/leaderboard/`, and `/contact/` (legacy `/create/`, `/human/`, `/puzzles/` 301 to their `/launch/?flow=` equivalents). Shared static assets (`/css`, `/js`, `/data`, favicons) are mounted on the origin too.

| Behavior | Pages (public) | Local origin (`chess-harness serve`) |
|----------|----------------|--------------------------------------|
| Home / nav chrome | `public-site/` static | Same static shell; **Calibration** nav on loopback hostnames only |
| Leaderboard | **Online:** live `/api/leaderboard/live` (proxied). **Sleeping:** `public-site/data/leaderboard.json` | Same live vs snapshot logic; origin also serves live data at `/api/leaderboard/live` and `/data/leaderboard.json` when up |
| Google sign-in | OAuth via Pages Functions | Not available (cosmetic only; does not gate create) |
| Agent brief base URL | `CHESS_HARNESS_PUBLIC_URL` (Pages hostname) | Defaults to `http://127.0.0.1:8765` unless you set `CHESS_HARNESS_PUBLIC_URL` |
| Calibration UI | 404 (blocked at edge) | `/calibration` on localhost; toolbar has **Rebuild accuracy map** only (no snapshot/publish buttons) |
| Create Game | Static shell + `/api/v1/*` proxy when online | Same static shell; APIs served directly (no proxy hop) |

Legacy Python card-grid home (`/?tab=active|done`) and form `POST /create` are removed — use `/spectator/` and `/api/v1` instead.

---

## Operator quick path (this repo’s public setup)

1. **Pages always-on site** — auto-deploys from `public-site/` via GitHub Actions. One-time secrets: [`deploy/pages.md`](deploy/pages.md).
2. **Game PC** — `chess-harness serve` on `127.0.0.1:8765` with  
   `CHESS_HARNESS_PUBLIC_URL=https://chessvisionharness.pages.dev`. Production: [`deploy/install-harness-nssm.ps1`](deploy/install-harness-nssm.ps1) (survives reboot).
3. **Reach the PC** — **Quick Tunnel** is the current public path (URL changes on restart). Named `cloudflared` without a public hostname does **not** make Pages Online. Full steps: [`deploy/home-pc.md`](deploy/home-pc.md).
4. **Wire live play** — set GitHub secret `GAME_ORIGIN` to the tunnel/host URL, then redeploy Pages (`gh workflow run "Deploy public site"`). Verify: [`deploy/verify-online.ps1`](deploy/verify-online.ps1).

**Leaderboard (live vs offline)**

- **Online** (status chip / edge-health): Home and `/leaderboard/` load the ladder from the **live** API (`/api/leaderboard/live` on Pages via proxy; same numbers as the game PC). Calibration Elo and agent ladder updates appear without git.
- **Sleeping** (game server down): the site falls back to the committed files `public-site/data/*.json` — last intentional offline snapshot. The edge health field `origin: true` only means `GAME_ORIGIN` is configured; clients must use `status: "online"` or `online: true` to treat the origin as reachable. If a live leaderboard request fails, the browser also falls back to the snapshot.
- While `chess-harness serve` runs, debounced snapshot refresh writes to `$CHESS_HARNESS_DIR/publish/` (runtime only — does not touch git). Online visitors load live APIs; no git step.
- **Sleeping publish (operator):** before a long offline period or when you want Pages to show fresher fallback data, run `chess-harness snapshot-leaderboard`, commit `public-site/data/*.json`, and push (or let the deploy workflow run). That is **not** how you publish live Elos when Online.

**Detailed runbooks**

| Doc | Use when |
|-----|----------|
| [`deploy/home-pc.md`](deploy/home-pc.md) | Windows PC + tunnel, services, on/off, moving origin later |
| [`deploy/pages.md`](deploy/pages.md) | Cloudflare Pages secrets, `GAME_ORIGIN` inject, local Functions preview |

Templates and helpers live under [`deploy/`](deploy/) (Caddyfile, systemd unit, nginx example, disk-usage script). This file is the root entry point; [`deploy/README.md`](deploy/README.md) only points here.

---

## 1. Install (game host)

On the machine that will run engines (Linux or Windows):

```bash
git clone <your-repo-url> /opt/chess-vision-harness
cd /opt/chess-vision-harness
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e "python/[dev]"
python scripts/fetch_opponents.py
chess-harness opponents verify
```

Set `STOCKFISH_PATH` if the binary is not at `bin/stockfish*`. Optional: `CHESS_HARNESS_DIR` for a custom data directory (default `.chess_harness/` under the repo).

---

## 2. Environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `CHESS_HARNESS_PUBLIC_URL` | **Yes (public deploy)** | HTTPS URL agents use in Create Game briefs (Pages: `https://chessvisionharness.pages.dev`). No trailing slash. |
| `STOCKFISH_PATH` | If not default | Path to Stockfish binary |
| `CHESS_HARNESS_DIR` | No | Runtime data (games, models, API keys) |
| `CHESS_HARNESS_IDLE_TIMEOUT_SEC` | No | End game with no result after N seconds idle (default `1800` = 30 min) |
| `CHESS_HARNESS_MAX_CONCURRENT_GAMES` | No | Global in-progress cap (default `10`) |
| `CHESS_HARNESS_MAX_ENGINE_PROCESSES` | No | In-flight engine cap (default `12`) |
| `CHESS_HARNESS_MAX_GAMES_PER_HOUR_PER_KEY` | No | Per API key (default `20`) |
| `CHESS_HARNESS_MAX_MOVES_PER_HOUR_PER_KEY` | No | Per API key (default `600`) |
| `CHESS_HARNESS_MAX_AGENT_REGISTRATIONS_PER_IP_PER_HOUR` | No | Unauthenticated `POST /api/v1/agents` (default `10`) |

**Volume / runner:** the headless `chess_harness.agent_http` client and a future internal runner use the **same** caps above — there is no bypass route. To farm more games on your operator PC, raise `CHESS_HARNESS_MAX_CONCURRENT_GAMES`, `CHESS_HARNESS_MAX_GAMES_PER_HOUR_PER_KEY`, and `CHESS_HARNESS_MAX_MOVES_PER_HOUR_PER_KEY` in the serve environment. Keep `CHESS_HARNESS_IDLE_TIMEOUT_SEC` at the default **1800** (30 minutes); do not lower idle to stretch volume.

| `CHESS_HARNESS_AUDIT_SALT` | No | Salt for hashing client IPs in `.chess_harness/audit/activity.jsonl`. Read with `chess-harness audit tail`. |
| `CHESS_HARNESS_TRUSTED_PROXIES` | No | Comma-separated CIDRs for the immediate proxy hop (`127.0.0.0/8` for local `cloudflared` → `127.0.0.1:8765`). Pages sets `X-Forwarded-For` from the visitor's `CF-Connecting-IP`; the harness trusts that header only when the peer is in this list. Leave unset only for direct localhost access with no tunnel. |
| `CHESS_HARNESS_INBOX_SECRET` | No | Optional secret for inbox list/read/delete from a trusted non-loopback operator path; loopback access remains available. |
| `CHESS_HARNESS_CALIBRATION_SECRET` | For calibration UI POSTs | Shared secret for `/api/calibration/*` mutations when the harness is reachable via tunnel. On loopback Host only, the `/calibration` page may embed it in a meta tag for same-origin POSTs; non-loopback hosts never receive the secret in HTML — paste it in the on-page field or send the header yourself. |
| `CHESS_HARNESS_ALLOW_REMOTE_CALIBRATION` | No | Set to `1` to allow calibration POSTs without the secret (explicit override; not recommended on exposed hosts). |
| `CHESS_HARNESS_UMAMI_TOKEN` | No | Umami Cloud API key for the operator panel **Site visitors** block (`GET /api/ops/audience`). **Game PC only** — never commit or deploy to Pages. |
| `CHESS_HARNESS_UMAMI_WEBSITE_ID` | No | Umami Cloud website id for `chessvisionharness.pages.dev`. Required with the token above for audience data. |
| `CHESS_HARNESS_UMAMI_API_HOST` | No | Umami Cloud API base URL (default `https://api.umami.is/v1`). Override only for region paths or self-hosted Umami (not used on Pages). |

Create Game briefs read `CHESS_HARNESS_PUBLIC_URL`. Without it, briefs default to `http://127.0.0.1:8765` (local only).

**Umami (operator panel):** paste the website id into `UMAMI_WEBSITE_ID` in `public-site/js/common.js` so the public Pages site loads the Umami tracker. Keep `CHESS_HARNESS_UMAMI_TOKEN` on the game PC serve environment only — the Traffic tab reads audience stats via localhost `/api/ops/audience`.

**Do not** pass `--host 0.0.0.0` to `chess-harness serve`. Default bind is `127.0.0.1`. Only a reverse proxy or tunnel should expose the process.

---

## 3. Start the harness (manual smoke test)

```bash
cd /opt/chess-vision-harness
source .venv/bin/activate
export CHESS_HARNESS_PUBLIC_URL=https://chessvisionharness.pages.dev
chess-harness serve
```

```bash
curl -s http://127.0.0.1:8765/health
```

Stop with Ctrl+C. Production uses systemd (Linux) or NSSM (Windows) below — see also [`deploy/home-pc.md`](deploy/home-pc.md).

---

## 4. TLS / reaching the harness

### Preferred for this project: Cloudflare Tunnel → Pages `GAME_ORIGIN`

No open inbound ports. Tunnel to `127.0.0.1:8765`; set `GAME_ORIGIN` on Pages; keep `CHESS_HARNESS_PUBLIC_URL` as the Pages URL. On the game PC set `CHESS_HARNESS_TRUSTED_PROXIES=127.0.0.0/8` so rate limits and audit hashes see each visitor IP that Pages forwards (not the tunnel peer). See [`deploy/home-pc.md`](deploy/home-pc.md).

### Online vs Sleeping (localhost up, public site Sleeping)

These are **three separate probes** (same order as [`deploy/home-pc.md`](deploy/home-pc.md#sleeping-runbook-card-three-urls-only)):

| # | Check | What it proves |
|---|-------|----------------|
| 1 | `http://127.0.0.1:8765/health` | Harness process is up **on this PC only** |
| 2 | `{GAME_ORIGIN}/health` | Tunnel/origin URL that Pages is configured to use |
| 3 | `https://chessvisionharness.pages.dev/api/edge-health` | Public **Online** (`online: true`) |

Automated: `.\deploy\verify-online.ps1 -GameOrigin "https://your-current.trycloudflare.com"` (exit codes in script header).

Edge-health fields:

- `origin: false` — `GAME_ORIGIN` is not configured on Pages.
- `origin: true`, `online: false` — `GAME_ORIGIN` is set, but Cloudflare cannot reach that URL (stale Quick Tunnel hostname, named tunnel with no public route, tunnel process down, or wrong host/port).
- `online: true` — live play/proxy path is usable.

**Typical failure:** Quick Tunnel was restarted (or its edge registration died) while GitHub secret `GAME_ORIGIN` still held the old `*.trycloudflare.com` URL. Localhost stays healthy; the public chip shows Sleeping. The named tunnel Windows service can be “Healthy” and still not help until it has a **public hostname** route to `http://127.0.0.1:8765`.

**Recovery (Quick Tunnel):** start a fresh `cloudflared tunnel --url http://127.0.0.1:8765`, set `GAME_ORIGIN` to the new HTTPS URL (no trailing slash), redeploy Pages, wait for the workflow, then re-check `/api/edge-health`. If you update the secret and redeploy in the same second, run deploy **once more** after the secret has settled — the first run can still inject the previous value.

**Lasting setup:** prefer named tunnel `chess-harness-pc` + a stable public hostname on a domain you control, then point `GAME_ORIGIN` at that hostname once. Quick Tunnel is fine for smoke tests; it is not a stable production origin.

### Alternative: Caddy on a VPS (classic reverse proxy)

1. Install [Caddy](https://caddyserver.com/docs/install).
2. Copy and edit [`deploy/Caddyfile`](deploy/Caddyfile); point DNS at the host.
3. Open firewall **443** (and **80** for ACME if needed).

```bash
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl enable --now caddy
```

### Alternative: nginx

See [`deploy/nginx.conf.example`](deploy/nginx.conf.example).

**Contact administration:** Pages proxies public contact submission only. Inbox list/read/delete remains local-origin-only at `http://127.0.0.1:8765/contact/`; it is not exposed through the public Pages site.

If the public site stays on Pages, still set `CHESS_HARNESS_PUBLIC_URL` to the Pages hostname and `GAME_ORIGIN` to this host’s HTTPS URL.

---

## 5. systemd (Linux)

1. Edit [`deploy/chess-harness.service`](deploy/chess-harness.service) (`User`, `WorkingDirectory`, `ExecStart`, `CHESS_HARNESS_PUBLIC_URL`).
2. Install:

```bash
sudo cp deploy/chess-harness.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now chess-harness
```

Logs: `journalctl -u chess-harness -f`. On SIGTERM, lifespan releases engines (`TimeoutStopSec=30`).

---

## 6. Windows (NSSM)

Use the install helper (creates `.chess_harness\logs`, sets `CHESS_HARNESS_PUBLIC_URL` and `CHESS_HARNESS_TRUSTED_PROXIES`, merges existing `AppEnvironmentExtra`, restart-on-failure):

```powershell
# Elevated PowerShell, from repo root
.\deploy\install-harness-nssm.ps1
```

Manual equivalent:

```powershell
nssm install ChessHarness "C:\path\to\chess-vision-harness\.venv\Scripts\chess-harness.exe" serve
nssm set ChessHarness AppDirectory "C:\path\to\chess-vision-harness"
nssm set ChessHarness AppEnvironmentExtra "CHESS_HARNESS_PUBLIC_URL=https://chessvisionharness.pages.dev" "CHESS_HARNESS_TRUSTED_PROXIES=127.0.0.0/8"
nssm set ChessHarness AppStdout "C:\path\to\chess-vision-harness\.chess_harness\logs\harness.log"
nssm set ChessHarness AppStderr "C:\path\to\chess-vision-harness\.chess_harness\logs\harness.err.log"
nssm set ChessHarness AppRotateFiles 1
nssm set ChessHarness AppRotateBytes 10485760
nssm set ChessHarness AppExit Default Restart
nssm start ChessHarness
```

After reboot, the harness should answer `http://127.0.0.1:8765/health` within a few minutes. **Public Online** is separate — Quick Tunnel URLs change on restart; see [`deploy/home-pc.md`](deploy/home-pc.md).

Put Cloudflare Tunnel (or another proxy) in front of `127.0.0.1:8765`. Do not bind the harness to `0.0.0.0`.

---

## 7. Log rotation

| Component | Approach |
|-----------|----------|
| **chess-harness** (systemd) | `journald` |
| **chess-harness** (NSSM) | `AppRotateFiles` / `AppRotateBytes` |
| **Caddy / nginx** | Distro defaults or Caddyfile `log` block |

---

## 8. Disk usage

Game data: `$CHESS_HARNESS_DIR/games/` (default `.chess_harness/games/`).

```bash
./deploy/games_disk_usage.sh
```

PowerShell: measure `.chess_harness\games`. Monitor `GET /api/v1/metrics` (`disk_free_bytes`). Prune old completed games after backup — `prune-no-result` / `remove-game` clear live dirs only; scored history stays in `data/finished_games.sqlite`. Restore a deleted live game with `chess-harness finished-db restore <game_id>` (see ARCHITECTURE runtime paths).

---

## 9. Verify end-to-end (Pages + PC)

1. https://chessvisionharness.pages.dev — status chip **Online**
2. **Create Game** — inscribe or select model; brief URLs use `chessvisionharness.pages.dev`
3. Agent play loop works through the public hostname
4. Spectator → Active lists the game

Classic single-host check: `curl https://your-host/health` and Create Game briefs matching that host.

---

## 10. Backup (nightly)

[`scripts/backup_harness.py`](scripts/backup_harness.py) archives runtime data:

| Archive path | Source |
|--------------|--------|
| `harness/models.json`, `api_keys.json`, `results.jsonl` | `$CHESS_HARNESS_DIR` (default `.chess_harness/`) |
| `harness/games/<game_id>/` | Recent live game dirs (age/count filters) |
| `harness/puzzle_attempts.json`, `identify_attempts.json`, `puzzle_ratings.json` | Puzzle / identify runtime stores |
| `harness/puzzles/` | Imported puzzle dataset (`puzzles.json`, manifest) |
| `harness/audit/activity.jsonl` | Create/inscribe audit log |
| `data/finished_games.sqlite` | Permanent scored-game archive |
| `calibration/merged_ratings.json`, `accuracy_elo_map.json` | Operator publish snapshots (`merged_ratings.json` is not runtime SSOT — serve merges `*/ratings.json`) |
| `calibration/continuous/*` | Live calibration (`ratings.json`, `games.jsonl`, `play_rating_samples.jsonl`) |
| `calibration/<suite>/` | Batch suite outputs (`ratings.json`, `games.jsonl`) when present |

```bash
python scripts/backup_harness.py
python scripts/backup_harness.py --output /var/backups/chess-harness --game-days 0 --keep 14
```

**Windows Task Scheduler (this PC):** edit paths in [`deploy/backup-nightly.ps1`](deploy/backup-nightly.ps1), then register [`deploy/backup-task-scheduler.xml`](deploy/backup-task-scheduler.xml):

```powershell
schtasks /Create /TN "ChessHarnessNightlyBackup" /XML "deploy\backup-task-scheduler.xml" /F
```

Copy archives off-host. Calibration JSONL logs are capped on disk (`CHESS_HARNESS_MAX_CALIBRATION_JSONL_LINES`, default `100000` newest lines per log).

---

## 10a. Truth matrix (runtime vs git)

| Data | Canonical location | In git? | Sleeping / public fallback |
|------|-------------------|---------|----------------------------|
| Live in-progress games | `$CHESS_HARNESS_DIR/games/<id>/` | No | N/A — requires Online origin |
| Scored game history | `data/finished_games.sqlite` | **No** (backup only) | N/A |
| Agent registry + ladder Elo | `$CHESS_HARNESS_DIR/models.json`, `results.jsonl` | No | Live API when Online |
| Calibration JSONL + continuous ratings | `elo_calibration/results/continuous/` | **No** | N/A (localhost calibration UI) |
| Operator calibration snapshots | `merged_ratings.json`, `accuracy_elo_map.json` | Yes — intentional commits | N/A |
| Public ladder / puzzle snapshots | `public-site/data/*.json` | Yes — deliberate Sleeping fallbacks | Pages static `/data/*.json` when Sleeping |
| Runtime snapshot cache (serve) | `$CHESS_HARNESS_DIR/publish/*.json` | No | N/A — live APIs when Online; copy via CLI for Sleeping publish |
| Puzzle / identify attempts | `$CHESS_HARNESS_DIR/puzzle_*.json`, `identify_attempts.json` | No | Live API when Online |

**Git quiet going forward:** volatile paths above marked **No** should be untracked (see operator commands below). Historical blobs stay in old commits — no history rewrite.

**Sleeping publish (operator or CI):** `chess-harness snapshot-leaderboard` writes `public-site/data/leaderboard.json`, `puzzles_leaderboard.json`, and `identify_leaderboard.json`, and injects inline snapshot into home/leaderboard HTML. Commit and push so Pages deploy picks up the fallback. Run before extended offline, or periodically if you care about Sleeping freshness. While Online, live ladder APIs need no commit.

Serve-time debounced refresh (rated finish, calibration tick, startup watcher) writes only to `$CHESS_HARNESS_DIR/publish/` — never `public-site/`.

**Operator — untrack volatile files (run once after pulling Phase 2):**

```bash
git rm --cached data/finished_games.sqlite
git rm --cached elo_calibration/results/continuous/ratings.json
git rm --cached elo_calibration/results/continuous/games.jsonl
git rm --cached elo_calibration/results/continuous/play_rating_samples.jsonl
git rm --cached elo_calibration/results/continuous/play_rating_map.json
git add data/.gitignore elo_calibration/results/.gitignore
git commit -m "Stop tracking volatile runtime data (Phase 2 quiet git)"
```

---

## 11. Restore

1. Stop the harness (`systemctl stop` / `nssm stop`).
2. Optional safety copy of `$CHESS_HARNESS_DIR`, `data/finished_games.sqlite`, and `elo_calibration/results/`.
3. Extract the backup archive to a throwaway directory; read `manifest.json` for the path list.
4. Restore in order:
   - `data/finished_games.sqlite` → repo `data/finished_games.sqlite`
   - `harness/models.json`, `api_keys.json`, `results.jsonl` → `$CHESS_HARNESS_DIR/`
   - `harness/games/*` → `$CHESS_HARNESS_DIR/games/`
   - `harness/puzzle_attempts.json`, `identify_attempts.json`, `puzzle_ratings.json`, `harness/puzzles/`, `harness/audit/` → matching paths under `$CHESS_HARNESS_DIR/`
   - `calibration/*` → `elo_calibration/results/`
5. Verify `chess-harness finished-db list`; use `chess-harness finished-db restore <game_id>` for deleted live games, then run `chess-harness rebuild-elo` if needed.
6. Start harness; `curl http://127.0.0.1:8765/health`; confirm public site Online if `GAME_ORIGIN` is set.

**Restore drill:** extract a recent archive into `%TEMP%\cvh-restore-test`, copy one file back, confirm `manifest.json` paths match section 10, then discard the temp dir.

---

## 12. Monitoring

| Check | URL |
|-------|-----|
| Edge health (Pages) | `GET https://chessvisionharness.pages.dev/api/edge-health` |
| Harness liveness | `GET http://127.0.0.1:8765/health` (or via tunnel/proxy) |
| Load | `GET …/api/v1/metrics` |

**Windows — all three probes in one script** (exit codes in script header):

```powershell
$env:GAME_ORIGIN = "https://your-current.trycloudflare.com"   # or -GameOrigin
.\deploy\verify-online.ps1
```

Schedule `verify-online.ps1` via Task Scheduler when the PC is expected Online; non-zero exit → follow [`deploy/home-pc.md`](deploy/home-pc.md) recovery.

Alert on stuck `engine_count` with `active_games == 0`, and low `disk_free_bytes`.

---

## 13. Moving the game origin off this PC

Public URL stays **https://chessvisionharness.pages.dev**. Change **`GAME_ORIGIN`**, run `chess-harness serve` on the new host with the same `CHESS_HARNESS_PUBLIC_URL`, redeploy Pages. Steps: [`deploy/home-pc.md`](deploy/home-pc.md#move-game_origin-off-this-pc-later).

---

## Security checklist

- [ ] Harness on `127.0.0.1:8765` only (no `--host 0.0.0.0`)
- [ ] Public agents/humans use Pages (or your HTTPS front door), not raw tunnel in briefs
- [ ] `CHESS_HARNESS_PUBLIC_URL` matches that public HTTPS URL
- [ ] `GAME_ORIGIN` points at the reachable harness origin
- [ ] Port **8765** not exposed on the public internet
- [ ] Service runs as unprivileged user
- [ ] API keys treated as secrets (shown once at registration)
