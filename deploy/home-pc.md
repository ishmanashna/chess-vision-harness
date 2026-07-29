# Home PC runbook — live games through Cloudflare Pages

This is the operator guide for running games on your Windows PC while the public site stays at **https://chessvisionharness.pages.dev**. You do not edit site code to turn live play on or off — you start/stop services on the PC and set Cloudflare environment variables.

Related docs

- Root operator entry: [`../DEPLOY.md`](../DEPLOY.md)
- One-time Pages + GitHub secrets: [`pages.md`](pages.md)
- General harness install, backup, monitoring: also in [`../DEPLOY.md`](../DEPLOY.md)

---

## Current status

| Item | State |
|------|--------|
| Public site | **https://chessvisionharness.pages.dev** (Pages project `chessvisionharness`) |
| Named tunnel | `chess-harness-pc` — connector **Healthy** in Cloudflare Zero Trust |
| Public route | **None yet** — tunnel has no published hostname, so Pages cannot reach the PC until you add a route or use a Quick Tunnel |
| Harness bind | `127.0.0.1:8765` (localhost only; tunnel or proxy reaches it) |

Until `GAME_ORIGIN` points at a URL that reaches your PC, Create Game and Spectator show the sleeping/offline state. The leaderboard still works from the committed snapshot.

---

## How the pieces fit together

```text
Visitor → chessvisionharness.pages.dev (always on)
              │
              ├─ Static pages + leaderboard snapshot (works when PC is off)
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
| `GAME_ORIGIN` | Cloudflare Pages (dashboard) | Where Pages proxies live traffic — your tunnel or host URL |
| `CHESS_HARNESS_PUBLIC_URL` | Game PC (harness service) | URL agents see in Create Game briefs — always the **Pages** URL |

Agents must never get the raw tunnel hostname in briefs. Set `CHESS_HARNESS_PUBLIC_URL=https://chessvisionharness.pages.dev` on the PC.

**Calibration** (`/calibration*`) is blocked at the Pages edge. Use **`http://127.0.0.1:8765/calibration`** on the PC (direct localhost, not via tunnel). Calibration POSTs require `CHESS_HARNESS_CALIBRATION_SECRET` or `CHESS_HARNESS_ALLOW_REMOTE_CALIBRATION=1` — client IP is not trusted behind Cloudflare Tunnel.

---

## One-time: Pages and GitHub secrets

Do this once before the public site auto-deploys. Full steps: **[`pages.md`](pages.md)**.

Summary:

1. Create a Cloudflare API token (Pages edit permission).
2. Copy your Cloudflare Account ID.
3. Add GitHub repository secrets: `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`.
4. Push to `main`/`master`; confirm the **Deploy public site** workflow succeeds.

Later, when live play is ready, add the Pages environment variable `GAME_ORIGIN` (see below). That is separate from the GitHub secrets.

---

## Reaching the PC without a custom domain

Pages needs an HTTPS (or HTTP) base URL for `GAME_ORIGIN` that forwards to `http://127.0.0.1:8765`. Options below, best first for a permanent setup.

### Option A — Quick Tunnel (good for testing; URL changes on restart)

No domain and no tunnel route configuration. Cloudflare gives you a random `*.trycloudflare.com` URL each time.

1. On the PC, start the harness (see [Start the harness](#start-the-harness-on-the-pc)).
2. In a second terminal:

   ```powershell
   cloudflared tunnel --url http://127.0.0.1:8765
   ```

3. Copy the `https://….trycloudflare.com` URL from the output.
4. In Cloudflare: **Workers & Pages → chessvisionharness → Settings → Environment variables** → set **Production** `GAME_ORIGIN` to that URL (no trailing slash).
5. Redeploy Pages (**Retry deployment** on the latest deploy, or push any commit).

Verify: open https://chessvisionharness.pages.dev — status chip should show **Online**; Create Game should work.

**Downside:** the URL changes every time you restart the Quick Tunnel. You must update `GAME_ORIGIN` and redeploy after each restart. Fine for smoke tests, not for leaving up for weeks.

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
5. Set Pages `GAME_ORIGIN=https://games.yourdomain.com` (no trailing slash) and redeploy.

The tunnel connector runs as a Windows service (below); the hostname stays stable across reboots.

### Option C — Do not use for this project

- **Zero Trust paid** features — not required for a single published tunnel route.
- **Binding the harness to `0.0.0.0`** — keep localhost-only; the tunnel connects outbound to your machine.

**Ranking:** use **Option A** to verify end-to-end today; move to **Option B** when you add a domain so `GAME_ORIGIN` stops changing.

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

Run **two** things at boot: the harness and cloudflared (named tunnel or Quick Tunnel — named tunnel + route is preferred long-term).

### Harness — NSSM (recommended)

[NSSM](https://nssm.cc/) keeps `chess-harness serve` running and restarts it on failure.

```powershell
# Run from an elevated PowerShell; adjust paths
nssm install ChessHarness "C:\path\to\chess-vision-harness\.venv\Scripts\chess-harness.exe" serve
nssm set ChessHarness AppDirectory "C:\path\to\chess-vision-harness"
nssm set ChessHarness AppEnvironmentExtra "CHESS_HARNESS_PUBLIC_URL=https://chessvisionharness.pages.dev"
nssm set ChessHarness AppStdout "C:\path\to\chess-vision-harness\.chess_harness\logs\harness.log"
nssm set ChessHarness AppStderr "C:\path\to\chess-vision-harness\.chess_harness\logs\harness.err.log"
nssm set ChessHarness AppRotateFiles 1
nssm set ChessHarness AppRotateBytes 10485760
nssm start ChessHarness
```

`nssm stop ChessHarness` / `nssm restart ChessHarness` for maintenance.

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

### cloudflared — named tunnel (already installed)

If `cloudflared` was installed as a service for **`chess-harness-pc`**, ensure it is set to start automatically:

```powershell
Get-Service cloudflared
# If stopped:
Start-Service cloudflared
Set-Service cloudflared -StartupType Automatic
```

After you add a **public hostname** on the tunnel (Option B), this service keeps the route up without a manual Quick Tunnel window.

### cloudflared — Quick Tunnel only (testing)

Quick Tunnel is a foreground command, not ideal as a service. For a one-off test, run it in a console. For “always on” without a domain, you would need a script that restarts Quick Tunnel and updates `GAME_ORIGIN` each time — that is why Option B is better for production.

---

## Turn live games **on**

Checklist:

1. **Harness running** — service or manual; `curl http://127.0.0.1:8765/health` OK.
2. **Tunnel reachable from the internet**
   - Quick Tunnel: `cloudflared tunnel --url http://127.0.0.1:8765` → note HTTPS URL.
   - Named tunnel: public hostname route → `http://127.0.0.1:8765`; `curl https://your-games-host/health` OK.
3. **Pages `GAME_ORIGIN`** set to that tunnel/host URL (no trailing slash); redeploy if you changed it.
4. **`CHESS_HARNESS_PUBLIC_URL=https://chessvisionharness.pages.dev`** on the harness; restart harness after changing.

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

- Remove or clear `GAME_ORIGIN` in Pages settings and redeploy. Static site and leaderboard snapshot still work.

Leaderboard on the public site always comes from the last pushed `public-site/data/leaderboard.json`, not from the live PC.

---

## Leaderboard snapshot

The public leaderboard does not call your PC. Refresh it after rated games finish.

```powershell
cd C:\path\to\chess-vision-harness
.\.venv\Scripts\Activate.ps1
chess-harness snapshot-leaderboard
```

Default output: `public-site\data\leaderboard.json`. Override with `--output path\to\leaderboard.json`.

**Publish:** commit and push that file (human step — agents do not run git). GitHub Actions deploys the updated snapshot to Pages.

**Optional schedule** (e.g. daily after games):

```powershell
schtasks /Create /TN "ChessHarnessSnapshot" /TR "\"C:\path\to\chess-vision-harness\.venv\Scripts\chess-harness.exe\" snapshot-leaderboard" /SC DAILY /ST 04:00 /RU YOUR_USER /RL HIGHEST
```

You still push when you want the public site updated; the scheduled task only refreshes the local JSON file.

---

## Move `GAME_ORIGIN` off this PC later

The public URL **https://chessvisionharness.pages.dev** stays the same. Agents keep using `CHESS_HARNESS_PUBLIC_URL` pointing at Pages.

1. Stand up `chess-harness serve` on the new host (VPS, another machine) behind TLS or a tunnel.
2. In Cloudflare Pages, change **`GAME_ORIGIN`** to the new origin URL. Redeploy.
3. On the **new** host, set `CHESS_HARNESS_PUBLIC_URL=https://chessvisionharness.pages.dev`.
4. Run `chess-harness snapshot-leaderboard` on whichever machine owns ladder data; push `leaderboard.json` as today.
5. Stop harness and cloudflared on the old PC.

No HTML or Worker code changes — only origin env and where the harness runs.

---

## Troubleshooting

| Symptom | What to check |
|---------|----------------|
| Status always **Sleeping** | `GAME_ORIGIN` unset/wrong; harness stopped; tunnel down; `/health` fails on origin URL |
| Create Game works but brief shows `127.0.0.1` | Set `CHESS_HARNESS_PUBLIC_URL` on PC and restart harness |
| Quick Tunnel worked yesterday | URL changed — update `GAME_ORIGIN` and redeploy |
| Tunnel healthy but no public URL | Add a **public hostname** route on `chess-harness-pc`, or use Quick Tunnel |
| Calibration 404 on Pages | Expected — calibration is not exposed on the public site |

More Pages/tunnel detail: [`pages.md`](pages.md) (Phase 3 — `GAME_ORIGIN`, edge health).
