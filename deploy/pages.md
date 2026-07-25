# Cloudflare Pages — one-time setup

This deploys the static site in `public-site/` to the Cloudflare Pages project **chessvisionharness** (e.g. `https://chessvisionharness.pages.dev`). After setup, every push to `main`/`master` that touches `public-site/` triggers an automatic deploy via GitHub Actions — no manual drag-and-drop.

## 1. Cloudflare API token

1. Open [API Tokens](https://dash.cloudflare.com/profile/api-tokens) → **Create Token**.
2. Click **Create Custom Token** (do not use a read-only token).
3. Name it e.g. `pages-deploy`.
4. Permissions (exact):
   - **Account** → **Cloudflare Pages** → **Edit**
   - **Account** → **Account Settings** → **Read** (optional but helps Wrangler)
5. Under **Account Resources**, include **Jvalladaresgay@gmail.com's Account** (your account).
6. Create token → copy it once.

If deploy fails with `Authentication error [code: 10000]`, the token is missing **Cloudflare Pages → Edit**. Delete the old GitHub secret and paste a new token.

## 2. Account ID

In the Cloudflare dashboard, open any site or Workers & Pages overview. The **Account ID** is in the right-hand sidebar (or URL). Copy it.

## 3. GitHub repository secrets

In this repo on GitHub: **Settings → Secrets and variables → Actions → New repository secret**.

| Secret name | Value |
|-------------|--------|
| `CLOUDFLARE_API_TOKEN` | Token from step 1 |
| `CLOUDFLARE_ACCOUNT_ID` | Account ID from step 2 |

You only paste these once. The workflow does not print them in logs.

## 4. First deploy

1. Push a commit that includes `public-site/` and `.github/workflows/deploy-pages.yml` to `main` or `master`.
2. Open **Actions → Deploy public site** and confirm the job succeeds.
3. Visit `https://chessvisionharness.pages.dev` (or the URL shown in the Cloudflare Pages project).

If the Pages project does not exist yet, Wrangler creates it on the first successful deploy.

## 5. Local preview (optional)

From the repo root:

```bash
npx --yes serve public-site
```

Then open `http://localhost:3000` (or the port `serve` prints). All routes (`/leaderboard/`, `/create/`, etc.) work when served from `public-site` as the web root.

Opening `index.html` directly in a browser (`file://`) will not load `/data/leaderboard.json` or `/api/edge-health` — use a local static server instead.

## Leaderboard snapshot (Phase 2)

The site reads a committed JSON snapshot at `public-site/data/leaderboard.json`. Refresh it on the game PC after rated games finish:

```bash
chess-harness snapshot-leaderboard
```

Default output is `public-site/data/leaderboard.json` (repo root). Override with `--output path/to/leaderboard.json`.

Typical flow: run the exporter locally, commit and push — CI deploys whatever is in the repo. Optional: schedule the command (Windows Task Scheduler or cron) on the PC that runs games, then push when you want the public ladder updated.

## What deploys

- Static HTML, CSS, JS, and `data/leaderboard.json` (refresh via `chess-harness snapshot-leaderboard` on the game PC)
- Pages Functions: `/api/edge-health` (probes the game origin), middleware proxy for live play when `GAME_ORIGIN` is set
- No game server or tunnel in this workflow — the PC origin is configured separately: **[`home-pc.md`](home-pc.md)** (Phase 4 runbook)

## Phase 3 — Live game origin (`GAME_ORIGIN`)

The public site stays online even when your home PC is off. When the PC is running `chess-harness serve`, Cloudflare Pages can proxy live API and spectator routes to it.

### Cloudflare Pages environment variable

In the Cloudflare dashboard: **Workers & Pages → chessvisionharness → Settings → Environment variables**.

Add a **plain-text** variable (Production and Preview if you use preview deploys):

| Variable | Example value | Notes |
|----------|---------------|--------|
| `GAME_ORIGIN` | `https://your-tunnel-or-host.example` | **No trailing slash.** Base URL where `chess-harness serve` is reachable (Cloudflare Tunnel, Quick Tunnel, or any HTTPS/HTTP origin). |

You can set it either:

1. **Cloudflare dashboard** (Production env var), then redeploy, or  
2. **GitHub secret** `GAME_ORIGIN` — the deploy workflow syncs it onto the Pages project after each deploy (handy for Quick Tunnel URL updates: `gh secret set GAME_ORIGIN -b "https://….trycloudflare.com"` then re-run the workflow).

After you change `GAME_ORIGIN`, redeploy the site (push to `main`/`master` or **Retry deployment** in Actions). You do **not** edit HTML when the origin URL changes — only this variable.

**What it does when set:**

- `GET /api/edge-health` on Pages probes `{GAME_ORIGIN}/health` (3s timeout). The status chip shows **Online** when the probe succeeds.
- These paths are proxied to the origin: `/api/v1/*`, `/api/games/*`, `/g/*`.
- `/calibration*` is blocked at the edge (404) — calibration stays operator-only on the PC.

**When unset or the PC is down:** static pages and the leaderboard snapshot still work; Create Game and Active/Completed show the sleeping/offline UX.

### Game PC environment variable

On the machine running `chess-harness serve`, set:

```text
CHESS_HARNESS_PUBLIC_URL=https://chessvisionharness.pages.dev
```

(no trailing slash)

Agent briefs returned by `POST /api/v1/games` use this URL for board/move/PGN endpoints so agents hit the public hostname (proxied to your PC), not `127.0.0.1`.

Windows (current session): `set CHESS_HARNESS_PUBLIC_URL=https://chessvisionharness.pages.dev` before starting the server. For a permanent setup, see **[`home-pc.md`](home-pc.md)** (NSSM, Task Scheduler, tunnel, on/off checklist).

### Local Functions preview (optional)

From the repo root, with a local harness on port 8765:

```bash
cd public-site
echo GAME_ORIGIN=http://127.0.0.1:8765 > .dev.vars
npx wrangler pages dev .
```

Then open the URL Wrangler prints. `.dev.vars` is for local dev only — do not commit it.

## Troubleshooting

- **Workflow fails with auth error** — re-check token permissions and that both secrets are set on the correct repo.
- **404 on subpaths locally** — ensure you serve `public-site` as the document root, not the repo root.
- **Status chip always Sleeping** — `GAME_ORIGIN` is unset, the tunnel/origin is down, or `/health` on the origin failed. Check the Pages env var and that `chess-harness serve` is running.
- **Create Game online but brief missing** — set `CHESS_HARNESS_PUBLIC_URL` on the game PC to your Pages URL and restart the server.
