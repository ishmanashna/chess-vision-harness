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
        ├─ static Home / Leaderboard / Contact / offline UX
        │     (leaderboard from public-site/data/leaderboard.json)
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

Calibration (`/calibration*`) is blocked at the Pages edge. Run it only on the PC over localhost.

---

## Operator quick path (this repo’s public setup)

1. **Pages always-on site** — auto-deploys from `public-site/` via GitHub Actions. One-time secrets: [`deploy/pages.md`](deploy/pages.md).
2. **Game PC** — `chess-harness serve` on `127.0.0.1:8765` with  
   `CHESS_HARNESS_PUBLIC_URL=https://chessvisionharness.pages.dev`.
3. **Reach the PC** — Quick Tunnel (URL changes on restart) or named tunnel + domain (stable). Full steps: [`deploy/home-pc.md`](deploy/home-pc.md).
4. **Wire live play** — set GitHub secret `GAME_ORIGIN` to the tunnel/host URL, then redeploy Pages (`gh workflow run "Deploy public site"`).
5. **Refresh leaderboard snapshot** (when PC has new ratings):

```powershell
cd python
python -m chess_harness snapshot-leaderboard
# commit + push public-site/data/leaderboard.json when you want the public ladder updated
```

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
| `CHESS_HARNESS_AUDIT_SALT` | No | Salt for hashing client IPs in `.chess_harness/audit/activity.jsonl`. Read with `chess-harness audit tail`. |

Create Game briefs read `CHESS_HARNESS_PUBLIC_URL`. Without it, briefs default to `http://127.0.0.1:8765` (local only).

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

No open inbound ports. Tunnel to `127.0.0.1:8765`; set `GAME_ORIGIN` on Pages; keep `CHESS_HARNESS_PUBLIC_URL` as the Pages URL. See [`deploy/home-pc.md`](deploy/home-pc.md).

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

```powershell
nssm install ChessHarness "C:\path\to\chess-vision-harness\.venv\Scripts\chess-harness.exe" serve
nssm set ChessHarness AppDirectory "C:\path\to\chess-vision-harness"
nssm set ChessHarness AppEnvironmentExtra "CHESS_HARNESS_PUBLIC_URL=https://chessvisionharness.pages.dev"
nssm set ChessHarness AppStdout "C:\path\to\chess-vision-harness\.chess_harness\logs\harness.log"
nssm set ChessHarness AppStderr "C:\path\to\chess-vision-harness\.chess_harness\logs\harness.err.log"
nssm set ChessHarness AppRotateFiles 1
nssm set ChessHarness AppRotateBytes 10485760
nssm start ChessHarness
```

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

PowerShell: measure `.chess_harness\games`. Monitor `GET /api/v1/metrics` (`disk_free_bytes`). Prune old completed games after backup.

---

## 9. Verify end-to-end (Pages + PC)

1. https://chessvisionharness.pages.dev — status chip **Online**
2. **Create Game** — inscribe or select model; brief URLs use `chessvisionharness.pages.dev`
3. Agent play loop works through the public hostname
4. Active tab lists the game

Classic single-host check: `curl https://your-host/health` and Create Game briefs matching that host.

---

## 10. Backup (nightly)

[`scripts/backup_harness.py`](scripts/backup_harness.py) — models, API key hashes, results, recent games, calibration files.

```bash
python scripts/backup_harness.py
python scripts/backup_harness.py --output /var/backups/chess-harness --game-days 0 --keep 14
```

Schedule via cron, systemd timer, or Windows Task Scheduler (examples historically lived in `deploy/`; same commands apply). Copy archives off-host.

---

## 11. Restore

1. Stop the harness (`systemctl stop` / `nssm stop`).
2. Optional safety copy of `$CHESS_HARNESS_DIR` and `elo_calibration/results/`.
3. Extract archive; copy `harness/*` into `$CHESS_HARNESS_DIR` and calibration files back under `elo_calibration/results/`.
4. Start harness; `curl http://127.0.0.1:8765/health`; confirm public site Online if `GAME_ORIGIN` is set.

---

## 12. Monitoring

| Check | URL |
|-------|-----|
| Edge health (Pages) | `GET https://chessvisionharness.pages.dev/api/edge-health` |
| Harness liveness | `GET http://127.0.0.1:8765/health` (or via tunnel/proxy) |
| Load | `GET …/api/v1/metrics` |

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
