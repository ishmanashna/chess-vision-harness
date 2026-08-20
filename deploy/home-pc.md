# Home PC runbook — live games through Cloudflare Pages

This is the operator guide for running games on your Windows PC while the public site stays at **https://chessvisionharness.pages.dev**. You do not edit site code to turn live play on or off — you start/stop services on the PC and refresh GitHub secret `GAME_ORIGIN` when the tunnel URL changes.

Related docs

- Root operator entry: [`../DEPLOY.md`](../DEPLOY.md)
- One-time Pages + GitHub secrets: [`pages.md`](pages.md)
- General install, backup, restore, and monitoring: also in [`../DEPLOY.md`](../DEPLOY.md)

---

## Current status

| Item | State |
|------|--------|
| Public site | **https://chessvisionharness.pages.dev** (Pages project `chessvisionharness`) |
| Named tunnel | `chess-harness-pc` — connector may show **Healthy** in Cloudflare Zero Trust |
| Public route (named) | **None** — no published hostname on the named tunnel |
| Live path today | **Quick Tunnel** → `GAME_ORIGIN` GitHub secret + Pages redeploy (URL changes whenever Quick Tunnel restarts) |
| Harness bind | `127.0.0.1:8765` (localhost only; tunnel or proxy reaches it) |

**Do not confuse the two tunnels**

| What | Makes localhost `/health` OK? | Makes Pages **Online**? |
|------|------------------------------|-------------------------|
| NSSM `ChessHarness` (`chess-harness serve`) | Yes | No |
| Named `cloudflared` service (`chess-harness-pc`) with **no public hostname** | No (connector only) | **No** |
| **Quick Tunnel** (`cloudflared tunnel --url …`) with URL in `GAME_ORIGIN` | No (harness still required) | **Yes** (when harness + tunnel + secret + deploy align) |

A named tunnel connector can be Healthy while Pages stays **Sleeping** — there is no public URL for Pages to probe until you add a **public hostname** route (needs a domain) or point `GAME_ORIGIN` at a live Quick Tunnel URL.

`GAME_ORIGIN` must be a URL that currently reaches this PC. A stale Quick Tunnel hostname (or a named tunnel with no public hostname) makes the site show Sleeping even when localhost `/health` is fine. Leaderboard uses the live API when Online and the offline snapshot when Sleeping.

### Two success criteria (separate)

1. **Harness (reboot durability)** — After reboot / logon, `chess-harness serve` comes back; `http://127.0.0.1:8765/health` is green within a few minutes.
   - **Preferred (admin):** [`install-harness-nssm.ps1`](install-harness-nssm.ps1) with [`tools/nssm.exe`](tools/nssm.exe).
   - **No admin (this PC):** [`install-harness-logon-task.ps1`](install-harness-logon-task.ps1) — Startup folder + HKCU Run.
2. **Public Online (operator present)** — Run **one script** after you want the public site live:

```powershell
.\deploy\go-online.ps1
```

Or double-click **`deploy\Start-Online.bat`** (same script; the window stays open if something fails — missing `gh`, `cloudflared`, etc.).

**Install a Desktop shortcut (once, no admin):**

```powershell
.\deploy\go-online.ps1 -InstallShortcut
```

Creates **`Chess Vision Harness Go Online.lnk`** on your Desktop pointing at `deploy\Start-Online.bat`. The shortcut does **not** install or start the NSSM service (that can need admin).

**Prerequisites before Go Online**

| Tool | Why |
|------|-----|
| **`cloudflared`** on PATH or default install path | Quick Tunnel to `127.0.0.1:8765` |
| **`gh auth login`** with repo access | Set `GAME_ORIGIN` secret and trigger Pages deploy |
| **`chess-harness`** on your **Desktop user PATH** | Background `serve --force` when no NSSM service and `/health` is down |

**Localhost-only surfaces** — **Calibration** (`/calibration*`) and **Puzzle set** (`/puzzle-set`) stay on **`http://127.0.0.1:8765`** (direct loopback, not via the tunnel). Public Pages proxies live play/watch/create only.

**Durability — pick one harness auto-start path:** NSSM (`install-harness-nssm.ps1`, admin) **or** logon task (`install-harness-logon-task.ps1`, no admin). **Do not run both** — they can fight over port 8765.

**What `go-online` does to the harness (`Ensure-Harness`)**

- If `http://127.0.0.1:8765/health` is already OK (NSSM service, logon task, or manual `serve`): **no restart**, no `--force`.
- If the **ChessHarness** NSSM service exists but is stopped: starts the service and waits for `/health`.
- If there is **no** NSSM service and `/health` is down: starts `chess-harness serve --force` in the background (logon task uses `--force` the same way). **`--force`** kills a stuck listener on `:8765` only in that no-service path.

**Quick Tunnel + deploy**

- Each run starts a fresh Quick Tunnel; the URL changes → updates GitHub secret `GAME_ORIGIN` and may trigger **Deploy public site** **twice** (secret/deploy race — see verify step in the script).
- Target **under ~15 minutes**. **Not** zero-touch across reboots — run Go Online again after reboot or when Pages shows Sleeping.

That starts/reuses a Quick Tunnel, sets GitHub `GAME_ORIGIN`, redeploys Pages, and runs [`verify-online.ps1`](verify-online.ps1).

---

## How the pieces fit together

```text
Visitor → chessvisionharness.pages.dev (always on)
              │
              ├─ Static pages; leaderboard Online → live API, Sleeping → snapshot
              │
              └─ Live paths (/api/v1/*, /create, /g/*, …)
                     proxy via GAME_ORIGIN
                           │
                           ▼
              cloudflared tunnel → http://127.0.0.1:8765
                           │
                           ▼
              chess-harness serve (your PC)
```

**Two URLs, two jobs**

| Variable | Where | Purpose |
|----------|--------|---------|
| `GAME_ORIGIN` | GitHub secret `GAME_ORIGIN` (deploy workflow injects into Pages Functions) | Where Pages proxies live traffic — your tunnel or host URL |
| `CHESS_HARNESS_PUBLIC_URL` | Game PC (harness service) | URL agents see in Create Game briefs — always the **Pages** URL |

Agents must never get the raw tunnel hostname in briefs. Set `CHESS_HARNESS_PUBLIC_URL=https://chessvisionharness.pages.dev` on the PC.

**Client IP through Pages:** Cloudflare Pages Functions copy each visitor's `CF-Connecting-IP` into `X-Forwarded-For` when proxying to `GAME_ORIGIN`. On the harness, set:

```text
CHESS_HARNESS_TRUSTED_PROXIES=127.0.0.0/8
```

so `cloudflared` (the immediate peer on localhost) is trusted to supply that header. Without it, every public agent appears to share one IP and per-IP rate limits collapse. Per-key limits still bucket by API key, but registration and `by_key` scan limits need the real visitor IP. The harness logs a one-time warning on the first proxied request if this variable is missing while loopback peers send `X-Forwarded-For` / `CF-Connecting-IP`.

**Calibration** (`/calibration*`) is blocked at the Pages edge. Use **`http://127.0.0.1:8765/calibration`** on the PC (direct localhost, not via tunnel). On loopback hostnames the site nav shows Calibration after Leaderboard (no status probe). Loopback Host may POST without a secret; non-loopback / tunnel POSTs require `CHESS_HARNESS_CALIBRATION_SECRET` or `CHESS_HARNESS_ALLOW_REMOTE_CALIBRATION=1` — client IP is not trusted behind Cloudflare Tunnel. Map control: **Rebuild accuracy map** only (no snapshot/publish buttons).

**Calibration worker (Phase 9d):** Continuous engine calibration runs in a **separate child process** so heavy cal work cannot starve live play. `chess-harness serve` spawns and supervises the worker on **`127.0.0.1:8766`** by default (control plane stays on port 8765; same calibration UI and `/api/calibration/*` routes). The worker writes live activity to `.chess_harness/calibration_worker/status.json`; serve overlays that on GET status while **ratings, quality samples, and the accuracy map are read from disk** (full status works with the worker stopped). Operator override: run `chess-harness calibration-worker` manually (e.g. debugging) — serve reuses a healthy worker if one is already listening. Set `CHESS_HARNESS_CALIBRATION_IN_PROCESS=1` only for tests or emergency fallback (calibration back inside serve). Verify responsiveness: `python scripts/calibration_load_check.py` while capped cal is running.

---

## One-time: Pages and GitHub secrets

Do this once before the public site auto-deploys. Full steps: **[`pages.md`](pages.md)**.

Summary:

1. Create a Cloudflare API token (Pages edit permission).
2. Copy your Cloudflare Account ID.
3. Add GitHub repository secrets: `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`.
4. Push to `main`/`master`; confirm the **Deploy public site** workflow succeeds.

Later, when live play is ready, set GitHub secret `GAME_ORIGIN` and redeploy (see below). That is separate from the Cloudflare API token secrets.

---

## Reaching the PC without a custom domain

Pages needs an HTTPS (or HTTP) base URL for `GAME_ORIGIN` that forwards to `http://127.0.0.1:8765`. Options below, best first for a permanent setup.

### Option A — Quick Tunnel (current public path; URL changes on restart)

No domain and no tunnel route configuration. Cloudflare gives you a random `*.trycloudflare.com` URL each time. This is the supported path without a paid domain.

1. On the PC, start the harness (see [Start the harness](#start-the-harness-on-the-pc)).
2. In a second terminal:

   ```powershell
   cloudflared tunnel --url http://127.0.0.1:8765
   ```

3. Copy the `https://….trycloudflare.com` URL from the output (no trailing slash).
4. Update the deploy secret and redeploy Pages:

   ```powershell
   gh secret set GAME_ORIGIN -b "https://….trycloudflare.com"
   gh workflow run "Deploy public site"
   ```

   Wait for the workflow to finish. If the status chip stays **Sleeping**, run deploy **once more** (secret update and workflow start can race).

   Optional: you can also set **Production** `GAME_ORIGIN` in **Workers & Pages → chessvisionharness → Settings → Environment variables**, but the GitHub secret is what the deploy pipeline uses — keep the secret current.

5. Verify:

   ```powershell
   .\deploy\verify-online.ps1 -GameOrigin "https://….trycloudflare.com"
   ```

   Or open https://chessvisionharness.pages.dev — status chip should show **Online**; Create Game should work.

**Downside:** the URL changes every time you restart the Quick Tunnel. You must update `GAME_ORIGIN` and redeploy after each restart. There is no zero-touch Online across reboots without refreshing the secret.

### Option B — Named tunnel + hostname (recommended when you have a domain)

You already have a named tunnel: **`chess-harness-pc`** (connector healthy). Add a **public hostname** in Cloudflare that routes to the harness.

**Requires:** a domain on your Cloudflare account (can be a cheap registrar domain; free Cloudflare DNS is enough). You do **not** need Zero Trust paid plans for a standard published tunnel route.

1. Ensure `chess-harness serve` is running on `127.0.0.1:8765`.
2. Cloudflare Zero Trust (or **Networks → Tunnels**): open tunnel **`chess-harness-pc`**.
3. **Public Hostname** → Add a route, for example:
   - Subdomain: `games` (or `harness`)
   - Domain: your domain
   - Service: `http://127.0.0.1:8765`
4. Confirm from another device: `curl https://games.yourdomain.com/health` returns OK.
5. Set GitHub secret `GAME_ORIGIN` to `https://games.yourdomain.com` (no trailing slash) and redeploy:

   ```powershell
   gh secret set GAME_ORIGIN -b "https://games.yourdomain.com"
   gh workflow run "Deploy public site"
   ```

The tunnel connector runs as a Windows service (below); the hostname stays stable across reboots.

### Option C — Do not use for this project

- **Zero Trust paid** features — not required for a single published tunnel route.
- **Binding the harness to `0.0.0.0`** — keep localhost-only; the tunnel connects outbound to your machine.

**Ranking:** **Option A** is the current no-domain public path (operator refreshes `GAME_ORIGIN` after Quick Tunnel restarts). **Option B** when you add a domain so `GAME_ORIGIN` stays stable across reboots.

---

## Install on the PC (once)

From an elevated or normal PowerShell, in the repo directory:

```powershell
cd C:\path\to\chess-vision-harness
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e "python/[dev]"
python scripts/fetch_opponents.py
chess-harness opponents verify
```

Set `STOCKFISH_PATH` if Stockfish is not under `bin\`. Optional: `CHESS_HARNESS_DIR` for data outside the repo.

---

## Start the harness on the PC

Manual smoke test:

```powershell
cd C:\path\to\chess-vision-harness
.\.venv\Scripts\Activate.ps1
$env:CHESS_HARNESS_PUBLIC_URL = "https://chessvisionharness.pages.dev"
chess-harness serve
```

Another terminal:

```powershell
curl http://127.0.0.1:8765/health
```

Stop with Ctrl+C. Production uses a Windows service (next section).

---

## Windows always-on services

### Harness — NSSM (recommended)

[`install-harness-nssm.ps1`](install-harness-nssm.ps1) installs or updates the **ChessHarness** service: creates `.chess_harness\logs`, sets `CHESS_HARNESS_PUBLIC_URL` and `CHESS_HARNESS_TRUSTED_PROXIES`, log rotation, and restart-on-failure.

```powershell
# Elevated PowerShell, repo root
.\deploy\install-harness-nssm.ps1
```

Manual steps and Task Scheduler alternative remain below if you prefer not to use the helper.

`nssm stop ChessHarness` / `nssm restart ChessHarness` for maintenance.

**After reboot:** wait a few minutes, then `curl http://127.0.0.1:8765/health`. That confirms harness durability only — not Public Online.

### Harness — logon auto-start (no admin)

If NSSM / service install is blocked (`Acceso denegado`), use:

```powershell
.\deploy\install-harness-logon-task.ps1
```

Registers HKCU Run + a Startup folder `.cmd` that runs `python -m chess_harness serve --force` with `TRUSTED_PROXIES` set. Starts after **user logon** (not before login screen).

### Public Online — one script or Desktop shortcut

```powershell
.\deploy\go-online.ps1
```

Or double-click **`deploy\Start-Online.bat`**. Install a Desktop icon once:

```powershell
.\deploy\go-online.ps1 -InstallShortcut
```

Use after reboot (or whenever Pages shows Sleeping) once the harness is healthy. Needs **`cloudflared`**, **`gh auth login`** (repo write for secrets/workflows), and **`chess-harness`** on your user PATH. The shortcut does not start NSSM. See [Two success criteria](#two-success-criteria-separate) for `--force`, NSSM vs logon-task, and localhost-only Calibration / Puzzle set.

### Harness — manual NSSM (reference)

[NSSM](https://nssm.cc/) keeps `chess-harness serve` running and restarts it on failure.

```powershell
# Run from an elevated PowerShell; adjust paths — or use install-harness-nssm.ps1
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

### Harness — Task Scheduler (alternative)

If you prefer not to use NSSM:

1. **Task Scheduler → Create Task**
2. **Triggers:** At startup (or At log on)
3. **Actions:** Start program  
   - Program: `C:\path\to\chess-vision-harness\.venv\Scripts\chess-harness.exe`  
   - Arguments: `serve`  
   - Start in: `C:\path\to\chess-vision-harness`
4. Add environment variable in the action or a wrapper batch file:

   ```bat
   set CHESS_HARNESS_PUBLIC_URL=https://chessvisionharness.pages.dev
   C:\path\to\chess-vision-harness\.venv\Scripts\chess-harness.exe serve
   ```

5. **Settings:** restart on failure if desired.

### cloudflared — named tunnel (connector only today)

If `cloudflared` was installed as a service for **`chess-harness-pc`**, it keeps the **connector** registered with Cloudflare. That is **not** the same as a public URL:

```powershell
Get-Service cloudflared
# If stopped:
Start-Service cloudflared
Set-Service cloudflared -StartupType Automatic
```

Until you add a **public hostname** on the tunnel (Option B, requires a domain), this service does **not** satisfy `GAME_ORIGIN` and does **not** make Pages Online. For the current no-domain setup, use Quick Tunnel for the public path.

### cloudflared — Quick Tunnel (current public path)

Quick Tunnel is a foreground command. It is the supported way to expose the harness without a paid domain. The URL changes whenever Quick Tunnel restarts — plan on refreshing `GAME_ORIGIN` each time (see [Recover Public Online](#recover-public-online-from-stale-game_origin-15-min)).

---

## Sleeping runbook card (three URLs only)

When the public chip shows **Sleeping**, check these in order:

| # | URL | What it proves |
|---|-----|----------------|
| 1 | `http://127.0.0.1:8765/health` | Harness on this PC |
| 2 | `{GAME_ORIGIN}/health` | Tunnel/origin Pages is configured to use |
| 3 | `https://chessvisionharness.pages.dev/api/edge-health` | Public **Online** (`online: true`) |

Automated check (exit codes documented in the script):

```powershell
$env:GAME_ORIGIN = "https://your-current.trycloudflare.com"
.\deploy\verify-online.ps1
```

| Exit | Meaning |
|------|---------|
| 0 | Public Online |
| 1 | Harness down — fix NSSM / `ChessHarness` |
| 2 | Harness OK; `GAME_ORIGIN` dead — refresh Quick Tunnel + secret |
| 3 | Tunnel OK from PC; Pages not Online — redeploy (twice if secret raced) |
| 4 | Pass `-GameOrigin` or set `$env:GAME_ORIGIN` |

**Schedule when Online:** Task Scheduler → daily or at log-on → run `verify-online.ps1` with `GAME_ORIGIN` set; alert on non-zero exit.

---

## Recover Public Online from stale `GAME_ORIGIN` (~15 min)

Use when probe 1 passes and probe 2 or 3 fails (typical after reboot or Quick Tunnel restart).

1. Confirm harness: `curl http://127.0.0.1:8765/health`
2. Stop any old Quick Tunnel window/process.
3. Start fresh: `cloudflared tunnel --url http://127.0.0.1:8765` → copy `https://….trycloudflare.com` (no trailing slash).
4. `gh secret set GAME_ORIGIN -b "https://….trycloudflare.com"`
5. `gh workflow run "Deploy public site"` — wait for the workflow to finish.
6. `.\deploy\verify-online.ps1 -GameOrigin "https://….trycloudflare.com"`
7. If exit **3**, run deploy **once more** (secret update and workflow start can race), then re-verify.

Optional later: a helper script may log the Quick Tunnel URL and drive secret+deploy; operator steps above are sufficient for phase done.

---

## Turn live games **on**

Checklist:

1. **Harness running** — service or manual; `curl http://127.0.0.1:8765/health` OK.
2. **Tunnel reachable from the internet**
   - Quick Tunnel: `cloudflared tunnel --url http://127.0.0.1:8765` → note HTTPS URL.
   - Named tunnel: public hostname route → `http://127.0.0.1:8765`; `curl https://your-games-host/health` OK.
3. **GitHub secret `GAME_ORIGIN`** set to that tunnel/host URL (no trailing slash); `gh workflow run "Deploy public site"` if you changed it.
4. **`CHESS_HARNESS_PUBLIC_URL=https://chessvisionharness.pages.dev`** and **`CHESS_HARNESS_TRUSTED_PROXIES=127.0.0.0/8`** on the harness (`install-harness-nssm.ps1` sets both); restart harness after changing.

Verify:

- https://chessvisionharness.pages.dev — status **Online**
- **Create Game** — inscribe or select model, start game; brief URLs use `chessvisionharness.pages.dev`
- **Active** tab shows the game

---

## Turn live games **off**

You do not need to change site code or redeploy static HTML.

**Sleeping site, PC off (typical):**

1. Stop the harness: `nssm stop ChessHarness` (or end the manual process).
2. Stop cloudflared if you want zero tunnel traffic: `Stop-Service cloudflared` (optional).
3. Leave `GAME_ORIGIN` as-is or clear it in Pages — if the origin is unreachable, the edge shows offline/sleeping anyway.

**Fully disable proxy (optional):**

- Remove or clear `GAME_ORIGIN` in Pages settings and redeploy. Static site still works; leaderboard uses the offline snapshot when Sleeping.

When **Online**, public leaderboards load from the live proxied APIs (same numbers as your PC). When **Sleeping**, the site falls back to `public-site/data/*.json`.

---

## Leaderboard (live vs offline)

- **Online:** Home and `/leaderboard/` fetch `/api/leaderboard/live` through Pages (no git step).
- **Sleeping:** the site falls back to `public-site/data/*.json`.
- Serve refreshes runtime snapshots in `$CHESS_HARNESS_DIR/publish/` only — not the git tree.

**Sleeping publish** (before extended offline or when you want fresher fallback data):

```powershell
cd C:\path\to\chess-vision-harness
.\.venv\Scripts\Activate.ps1
chess-harness snapshot-leaderboard
git add public-site/data/*.json public-site/index.html public-site/leaderboard/index.html
git commit -m "Update Sleeping leaderboard snapshots"
git push
```

Writes `public-site\data\leaderboard.json`, `puzzles_leaderboard.json`, and `identify_leaderboard.json` (plus inline snapshot in home/leaderboard HTML). Commit and push only if you want fresher Sleeping fallbacks on Pages when the PC is off — **not** the normal path to publish live Elos while Online.

You still push when you want the public site updated; the scheduled task only refreshes the local JSON file.

---

## Move `GAME_ORIGIN` off this PC later

The public URL **https://chessvisionharness.pages.dev** stays the same. Agents keep using `CHESS_HARNESS_PUBLIC_URL` pointing at Pages.

1. Stand up `chess-harness serve` on the new host (VPS, another machine) behind TLS or a tunnel.
2. `gh secret set GAME_ORIGIN -b "https://new-origin.example"` then `gh workflow run "Deploy public site"`.
3. On the **new** host, set `CHESS_HARNESS_PUBLIC_URL=https://chessvisionharness.pages.dev`.
4. Run `chess-harness snapshot-leaderboard` on whichever machine owns ladder data; push `leaderboard.json` as today.
5. Stop harness and cloudflared on the old PC.

No HTML or Worker code changes — only origin env and where the harness runs.

---

## Troubleshooting

| Symptom | What to check |
|---------|----------------|
| Localhost `/health` OK, public chip **Sleeping** | Stale or unreachable `GAME_ORIGIN`. Probe `{GAME_ORIGIN}/health` (not only `127.0.0.1`). Edge-health `origin: true` + `online: false` means the configured URL is dead from Cloudflare’s edge. |
| Status always **Sleeping** | `GAME_ORIGIN` unset/wrong; harness stopped; tunnel down; `/health` fails on origin URL |
| Create Game works but brief shows `127.0.0.1` | Set `CHESS_HARNESS_PUBLIC_URL` on PC and restart harness |
| Quick Tunnel worked yesterday | URL changed or registration died — restart Quick Tunnel, update `GAME_ORIGIN`, redeploy Pages (`gh workflow run "Deploy public site"`). Redeploy again if the first run raced the secret update. |
| Named `cloudflared` service Running / Healthy, still Sleeping | Connector ≠ public URL. Add a **public hostname** on `chess-harness-pc` to `http://127.0.0.1:8765`, or use a live Quick Tunnel URL in `GAME_ORIGIN`. |
| Tunnel healthy but no public URL | Add a **public hostname** route on `chess-harness-pc`, or use Quick Tunnel |
| Calibration 404 on Pages | Expected — calibration is not exposed on the public site |

### Diagnose Online vs Sleeping

See [Sleeping runbook card](#sleeping-runbook-card-three-urls-only) or run:

```powershell
.\deploy\verify-online.ps1 -GameOrigin "https://YOUR-GAME-ORIGIN"
```

Only `{GAME_ORIGIN}/health` (probe 2) is what Pages uses for edge-health. If it fails, the site stays Sleeping no matter how healthy localhost looks. A named `cloudflared` service without a public hostname does not replace probe 2.

For step-by-step recovery, see [Recover Public Online](#recover-public-online-from-stale-game_origin-15-min). For a stable origin across reboots (when you have a domain), use **Option B** (named tunnel + public hostname).

More Pages/tunnel detail: [`pages.md`](pages.md) (`GAME_ORIGIN`, edge health).
