# Deploy — Chess Vision Harness (public agent API)

Expose the spectator + `/api/v1` agent API behind TLS. The harness process binds **localhost only**; a reverse proxy terminates HTTPS and forwards to `127.0.0.1:8765`.

**Prerequisites:** Phase 1 complete (HTTP API + Create Game). See [`docs/PUBLIC_AGENT_API_PLAN.md`](../docs/PUBLIC_AGENT_API_PLAN.md).

---

## 1. Install

On the server (Linux or Windows):

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
| `CHESS_HARNESS_PUBLIC_URL` | **Yes (public deploy)** | HTTPS URL agents use in Create Game briefs (e.g. `https://chess.example.com`). No trailing slash. |
| `STOCKFISH_PATH` | If not default | Path to Stockfish binary |
| `CHESS_HARNESS_DIR` | No | Runtime data (games, models, API keys) |
| `CHESS_HARNESS_IDLE_TIMEOUT_SEC` | No | End game with no result after N seconds idle (default `300`) |
| `CHESS_HARNESS_MAX_CONCURRENT_GAMES` | No | Global in-progress cap (default `10`) |
| `CHESS_HARNESS_MAX_ENGINE_PROCESSES` | No | In-flight engine cap (default `12`; see metrics note) |
| `CHESS_HARNESS_MAX_GAMES_PER_HOUR_PER_KEY` | No | Per API key (default `20`) |
| `CHESS_HARNESS_MAX_MOVES_PER_HOUR_PER_KEY` | No | Per API key (default `600`) |
| `CHESS_HARNESS_MAX_AGENT_REGISTRATIONS_PER_IP_PER_HOUR` | No | Unauthenticated `POST /api/v1/agents` (default `10`) |

Create Game briefs and `agent_brief.public_base_url()` read `CHESS_HARNESS_PUBLIC_URL`. Without it, briefs default to `http://127.0.0.1:8765` (fine for local dev only).

**Do not** pass `--host 0.0.0.0` to `chess-harness serve`. The default bind is `127.0.0.1` (see `commands.cmd_serve` and `__main__.py`). Only the reverse proxy should listen on the public interface.

---

## 3. Start the harness (manual smoke test)

```bash
cd /opt/chess-vision-harness
source .venv/bin/activate
export CHESS_HARNESS_PUBLIC_URL=https://chess.example.com
chess-harness serve
```

Verify locally:

```bash
curl -s http://127.0.0.1:8765/health
```

Stop with Ctrl+C. Production uses systemd (Linux) or NSSM (Windows) below.

---

## 4. TLS reverse proxy (Caddy — preferred)

1. Install [Caddy](https://caddyserver.com/docs/install).
2. Copy and edit [`Caddyfile`](Caddyfile): replace `chess.example.com` with your hostname; ensure DNS A/AAAA points to this machine.
3. Open firewall **443** (and **80** for ACME HTTP-01 if used).
4. Run Caddy with the site block (example):

```bash
sudo cp deploy/Caddyfile /etc/caddy/Caddyfile
# edit hostname, then:
sudo systemctl enable --now caddy
```

Caddy obtains and renews **Let's Encrypt** certificates automatically when the site block uses a real public hostname and ports 80/443 reach this host.

Proxy health check: `curl -s https://chess.example.com/health`

### Alternative: nginx

See [`nginx.conf.example`](nginx.conf.example). Use certbot or your CA for TLS; proxy all paths to `http://127.0.0.1:8765`.

### Alternative: Cloudflare Tunnel (no open ports)

If you cannot expose 443 on the host:

1. Install `cloudflared` and create a tunnel to your Cloudflare account.
2. Route `chess.example.com` → `http://127.0.0.1:8765`.
3. Set `CHESS_HARNESS_PUBLIC_URL=https://chess.example.com` on the harness service.
4. TLS is handled by Cloudflare; the tunnel connects outbound — no inbound firewall rules required.

---

## 5. systemd (Linux)

1. Edit [`chess-harness.service`](chess-harness.service):
   - `User` / `Group` — unprivileged account that owns the repo and `.chess_harness/`
   - `WorkingDirectory` — repo root (e.g. `/opt/chess-vision-harness`)
   - `ExecStart` — path to venv `chess-harness` (template uses `/opt/chess-vision-harness/.venv/bin/chess-harness`)
   - `Environment=CHESS_HARNESS_PUBLIC_URL=https://chess.example.com`
2. Install and start:

```bash
sudo cp deploy/chess-harness.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now chess-harness
sudo systemctl status chess-harness
```

Logs: `journalctl -u chess-harness -f`

### Graceful shutdown

`chess-harness serve` runs Uvicorn with a FastAPI **lifespan** handler (`spectator._lifespan`). On **SIGTERM** (systemd stop/restart) or **Ctrl+C**:

- Idle-game watcher task is cancelled
- Continuous calibration stops
- Opponent engine pool is released (`opponent_mgr.release()`)
- Spectator meta file is removed

Allow ~30s for stop: the unit file sets `TimeoutStopSec=30`. Avoid `KillMode=process` overrides that skip Uvicorn shutdown.

---

## 6. Windows (NSSM)

Use [NSSM](https://nssm.cc/) to run the harness as a Windows service with auto-restart.

1. Install the package in a venv under the repo (same as §1).
2. Download `nssm.exe` and run (elevated PowerShell):

```powershell
nssm install ChessHarness "C:\path\to\chess-vision-harness\.venv\Scripts\chess-harness.exe" serve
nssm set ChessHarness AppDirectory "C:\path\to\chess-vision-harness"
nssm set ChessHarness AppEnvironmentExtra "CHESS_HARNESS_PUBLIC_URL=https://chess.example.com"
nssm set ChessHarness AppStdout "C:\path\to\chess-vision-harness\.chess_harness\logs\harness.log"
nssm set ChessHarness AppStderr "C:\path\to\chess-vision-harness\.chess_harness\logs\harness.err.log"
nssm set ChessHarness AppRotateFiles 1
nssm set ChessHarness AppRotateBytes 10485760
nssm start ChessHarness
```

Put a reverse proxy (Caddy, IIS ARR, or Cloudflare Tunnel) in front of `127.0.0.1:8765` the same way as Linux. Do not bind the harness to `0.0.0.0`.

Stop/restart: `nssm stop ChessHarness` / `nssm restart ChessHarness`

---

## 7. Log rotation

| Component | Approach |
|-----------|----------|
| **chess-harness** (systemd) | `journald` — configure `/etc/systemd/journald.conf` (`SystemMaxUse=`, `MaxRetentionSec=`) or forward to your log stack |
| **chess-harness** (NSSM) | `AppRotateFiles` / `AppRotateBytes` (see §6) |
| **Caddy** | Default access logs to stdout/journal; use `log { output file ... }` in Caddyfile with Caddy's built-in rotation, or log to journald |
| **nginx** | `logrotate` on `/var/log/nginx/*` (distro default) |

Uvicorn logs requests at `info` level. There is no separate harness log file on Linux unless you redirect journald.

---

## 8. Disk usage (games directory)

Game data lives under `$CHESS_HARNESS_DIR/games/` (default `.chess_harness/games/`). Each game stores `state.json`, `board.png`, `game.pgn`, and related files. Long-running public instances should monitor disk.

**Quick check (Linux/macOS):**

```bash
./deploy/games_disk_usage.sh
# or with custom data dir:
CHESS_HARNESS_DIR=/var/lib/chess-harness ./deploy/games_disk_usage.sh
```

**PowerShell:**

```powershell
$dir = "C:\path\to\chess-vision-harness\.chess_harness\games"
"{0:N2} MB  ({1} game dirs)" -f ((Get-ChildItem $dir -Recurse | Measure-Object Length -Sum).Sum / 1MB), (Get-ChildItem $dir -Directory).Count
```

**Practical limits:** Phase 3 enforces concurrent games and per-key hourly caps on `/api/v1` (429/503 + `Retry-After`). Monitor load via `GET /api/v1/metrics` (active games, engine count, disk free). Operators should:

- Cron a weekly check; alert if usage exceeds a threshold (e.g. 80% of disk or 50 GB under `games/`)
- Prune old completed game directories after backup (see §11)
- Keep completed games you need for ladder audit; delete test games manually

---

## 9. Verify end-to-end

1. `curl https://chess.example.com/health` → OK
2. Open `https://chess.example.com/create` — create a game, copy brief
3. Confirm brief shows `https://chess.example.com` (not `127.0.0.1`)
4. From another machine, run the brief's curl loop through game end
5. Game appears on Active tab

---

## 10. Backup (nightly)

Cross-platform script: [`scripts/backup_harness.py`](../scripts/backup_harness.py). Uses `resolve_base_dir()` / `CHESS_HARNESS_DIR` — not a hardcoded repo path.

**Includes:** `models.json`, `api_keys.json` (hashed keys — still treat as secret), `results.jsonl`, recent game dirs under `games/`, and calibration files under `elo_calibration/results/` (`merged_ratings.json`, suite `ratings.json`, continuous `games.jsonl` when present).

```bash
cd /opt/chess-vision-harness
source .venv/bin/activate
python scripts/backup_harness.py
# custom output dir, all games, keep 14 archives:
python scripts/backup_harness.py --output /var/backups/chess-harness --game-days 0 --keep 14
```

| Flag | Default | Purpose |
|------|---------|---------|
| `--output` | `<harness>/backups` | Where archives are written |
| `--game-days` | `30` | Games modified in last N days (`0` = all) |
| `--max-games` | none | Cap to N most recent game dirs |
| `--keep` | `7` | Delete older archives in `--output` |

Archives: `chess-harness-backup-YYYYMMDD-HHMMSS.tar.gz` (Linux/macOS) or `.zip` (Windows). Each archive has a `manifest.json` listing copied paths.

**Schedule (Linux cron — daily 03:00):**

```cron
0 3 * * * cd /opt/chess-vision-harness && .venv/bin/python scripts/backup_harness.py >> /var/log/chess-harness-backup.log 2>&1
```

**systemd timer** (drop-in `/etc/systemd/system/chess-harness-backup.timer`):

```ini
[Unit]
Description=Daily Chess Vision Harness backup

[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

Service unit `chess-harness-backup.service`: `Type=oneshot`, `User=` harness user, `WorkingDirectory=/opt/chess-vision-harness`, `ExecStart=/opt/chess-vision-harness/.venv/bin/python scripts/backup_harness.py`, same `Environment=` as `chess-harness.service`. Enable with `systemctl enable --now chess-harness-backup.timer`.

**Windows Task Scheduler (daily 03:00):**

```powershell
schtasks /Create /TN "ChessHarnessBackup" /TR "\"C:\path\to\chess-vision-harness\.venv\Scripts\python.exe\" \"C:\path\to\chess-vision-harness\scripts\backup_harness.py\"" /SC DAILY /ST 03:00 /RU SYSTEM
```

Copy archives off-host (rsync, S3, restic) — `api_keys.json` hashes are still credential material.

---

## 11. Restore

1. **Stop the harness** so files are not mid-write:
   - Linux: `sudo systemctl stop chess-harness`
   - Windows: `nssm stop ChessHarness`
2. **Optional safety copy** of the current `$CHESS_HARNESS_DIR` and `elo_calibration/results/`.
3. **Extract** the latest archive to a temp dir:
   - `.tar.gz`: `tar -xzf chess-harness-backup-*.tar.gz -C /tmp/restore`
   - `.zip`: `Expand-Archive` (PowerShell) or unzip
4. **Restore files** (adjust paths to your install):
   ```bash
   export CHESS_HARNESS_DIR=/opt/chess-vision-harness/.chess_harness   # or your custom dir
   cp -a /tmp/restore/harness/* "$CHESS_HARNESS_DIR/"
   cp -a /tmp/restore/calibration/* /opt/chess-vision-harness/elo_calibration/results/
   ```
   Ensure the service user owns the restored files.
5. **Smoke test** (harness still stopped): inspect `manifest.json` game count; optional `chess-harness leaderboard`.
6. **Start** and verify health:
   ```bash
   sudo systemctl start chess-harness
   curl -s http://127.0.0.1:8765/health
   curl -s https://chess.example.com/health
   ```
7. Confirm Active tab and `/api/v1/leaderboard` look sane before resuming public traffic.

---

## 12. Monitoring & alerts

**Uptime (external):** Point [Uptime Kuma](https://github.com/louislam/uptime-kuma) or [healthchecks.io](https://healthchecks.io/) at:

| Check | URL | Expect |
|-------|-----|--------|
| Liveness | `GET https://chess.example.com/health` | HTTP 200, body OK |
| Load (optional) | `GET https://chess.example.com/api/v1/metrics` | HTTP 200, JSON `ok: true` |

Restrict `/api/v1/metrics` at the proxy if you do not want it public; localhost polling via cron is fine:

```bash
curl -sf http://127.0.0.1:8765/api/v1/metrics | jq .
```

**Metrics fields** (from Phase 3 — no secrets):

| Field | Alert guidance |
|-------|----------------|
| `active_games` | Baseline for load; sudden drop with proxy up may mean process crash |
| `engine_count` | Should track in-flight work. **Leak:** `engine_count` stays near `limits.max_engine_processes` while `active_games` is low or zero for several minutes — restart service after checking logs; engines should release after each move (`engine_count_note` in JSON) |
| `disk_free_bytes` | Alert if below your threshold (e.g. &lt; 5 GB or &lt; 10% free on the volume holding `CHESS_HARNESS_DIR`) |
| `limits` | Reference caps (`max_concurrent_games`, `max_engine_processes`, …) when interpreting saturation |

Example leak check (cron every 5 min, alert if engines stuck high with no active games):

```bash
metrics=$(curl -sf http://127.0.0.1:8765/api/v1/metrics) || exit 1
active=$(echo "$metrics" | jq '.active_games')
engines=$(echo "$metrics" | jq '.engine_count')
max=$(echo "$metrics" | jq '.limits.max_engine_processes')
if [ "$active" -eq 0 ] && [ "$engines" -gt 2 ]; then echo "possible engine leak: engines=$engines"; fi
```

Pair with §8 disk checks and §10 backups.

---

## Security checklist

- [ ] Harness listens on `127.0.0.1:8765` only (default; no `--host 0.0.0.0`)
- [ ] TLS on the public hostname (Caddy, nginx+certbot, or Cloudflare)
- [ ] `CHESS_HARNESS_PUBLIC_URL` matches the public HTTPS URL
- [ ] Firewall: 443 (and 80 if needed) to proxy only; **not** 8765 publicly
- [ ] Service runs as unprivileged user
- [ ] API keys treated as secrets (shown once at registration)
