# Cloudflare Pages — one-time setup

This deploys the static site in `public-site/` to the Cloudflare Pages project **chessvisionharness** (e.g. `https://chessvisionharness.pages.dev`). After setup, every push to `main`/`master` that touches `public-site/` triggers an automatic deploy via GitHub Actions — no manual drag-and-drop.

**Start here for operators:** [`../DEPLOY.md`](../DEPLOY.md). Home-PC live path: [`home-pc.md`](home-pc.md).


## 1. Cloudflare API token

1. Open [API Tokens](https://dash.cloudflare.com/profile/api-tokens) → **Create Token**.
2. Click **Create Custom Token** (do not use a read-only token).
3. Name it e.g. `pages-deploy`.
4. Permissions (exact):
   - **Account** → **Cloudflare Pages** → **Edit**
   - **Account** → **Account Settings** → **Read** (optional but helps Wrangler)
5. Under **Account Resources**, include **your Cloudflare account** (the account that owns the Pages project).
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
| `GAME_ORIGIN` | (optional until live play) Tunnel/host URL, no trailing slash — see [Live game origin](#live-game-origin-game_origin) |
| `GOOGLE_CLIENT_ID` | (optional until OAuth) Google OAuth Web client id — see Google sign-in below |
| `GOOGLE_CLIENT_SECRET` | (optional until OAuth) Google OAuth Web client secret |
| `AUTH_SESSION_SECRET` | (optional until OAuth) Long random string used to sign the session cookie |

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

Then open `http://localhost:3000` (or the port `serve` prints). `public-site/serve.json` rewrites `/g/{id}`, `/p/{id}`, `/i/{id}`, and `/play/{id}` to the static watch/play shells; APIs and board PNGs still need the game server (see below).

**Watch/play with live data locally:** run `chess-harness serve` on the PC (default `http://127.0.0.1:8765`). It serves the same static shells from `public-site/{g,p,i,play}/index.html` and proxies board images plus `/api/*` from the origin. Pages production uses the same shells; only asset subpaths (`/g/{id}/board.png`, etc.) hit `GAME_ORIGIN`.

**Pages watch shells:** middleware must return the shell HTML at `/g/{id}` (etc.) with status 200. Cloudflare maps `/g/index.html` → 308 `/g/`; if that redirect is forwarded to the browser, the id is stripped and the page stays empty (no moves/pieces). `fetchWatchShellHtml` in `functions/_watch_shell.js` follows that redirect server-side.

Opening `index.html` directly in a browser (`file://`) will not load `/data/leaderboard.json` or `/api/edge-health` — use a local static server instead.

## Leaderboard (live vs offline)

When the game server is **Online**, the site loads the ladder from `/api/leaderboard/live` (proxied via `GAME_ORIGIN`). When **Sleeping**, it uses the committed files `public-site/data/*.json`.

Serve writes debounced snapshots to `$CHESS_HARNESS_DIR/publish/` only (runtime — does not touch git). **Sleeping publish** before extended offline:

```bash
chess-harness snapshot-leaderboard
git add public-site/data/*.json public-site/index.html public-site/leaderboard/index.html
git commit -m "Update Sleeping leaderboard snapshots"
git push
```

Default CLI output is `public-site/data/leaderboard.json` (+ puzzles and identify siblings). Commit/push only for offline fallback — not how you publish live Elos when Online.

## What deploys

- Static HTML, CSS, JS, and `data/leaderboard.json` (offline fallback; live ladder when Online)
- Pages Functions: `/api/edge-health` (probes the game origin), middleware proxy for live play when `GAME_ORIGIN` is set
- No game server or tunnel in this workflow — the PC origin is configured separately: **[`home-pc.md`](home-pc.md)**

## Live game origin (`GAME_ORIGIN`)

The public site stays online even when your home PC is off. When the PC is running `chess-harness serve`, Cloudflare Pages can proxy live API and spectator routes to it.

### GitHub secret (primary)

Set repository secret **`GAME_ORIGIN`** to the tunnel/host URL (**no trailing slash**). The deploy workflow appends it to `public-site/wrangler.toml` `[vars]` before upload (required so Direct Upload Functions actually bind it) and syncs the Pages project setting via `deploy/sync-game-origin.py`.

| Variable | Example value | Notes |
|----------|---------------|--------|
| `GAME_ORIGIN` | `https://your-tunnel-or-host.example` | Base URL where `chess-harness serve` is reachable (Cloudflare Tunnel, Quick Tunnel, or any HTTPS/HTTP origin). |

Update when the Quick Tunnel URL changes:

```bash
gh secret set GAME_ORIGIN -b "https://….trycloudflare.com"
gh workflow run "Deploy public site"
```

Optional: you can also set **Production** `GAME_ORIGIN` in **Workers & Pages → chessvisionharness → Settings → Environment variables**, but the GitHub secret is what the deploy pipeline uses — keep the secret current.

After a successful deploy with that secret, `/api/edge-health` reports online when the tunnel and harness are up. You do **not** edit HTML when the origin URL changes — only the secret/dashboard value. After changing `GAME_ORIGIN`, always redeploy; if the chip stays Sleeping, redeploy once more (secret update and workflow start can race).

**Named tunnel vs Quick Tunnel:** a Windows `cloudflared` service for a named tunnel (e.g. `chess-harness-pc`) with **no public hostname** does **not** make Pages Online. Only a URL in `GAME_ORIGIN` that currently reaches `{origin}/health` counts — typically a live Quick Tunnel `*.trycloudflare.com` hostname until you add a domain route. Verify from the game PC: [`verify-online.ps1`](verify-online.ps1).

**Scripted API clients:** Cloudflare may return **403** for empty or `Python-urllib/*` User-Agents on the Pages host. Use curl/browsers (normal UA) or set e.g. `User-Agent: ChessVisionHarness-Agent/1.0`. Local `http://127.0.0.1:8765` is unaffected.

**What it does when set:**

- `GET /api/edge-health` on Pages probes `{GAME_ORIGIN}/health` (~10s timeout). The status chip shows **Online** when the probe succeeds.
- `origin: true` only means the variable is configured; `online: true` / `status: "online"` means the origin answered healthy. Localhost `/health` does not imply public Online.
- These paths are proxied to the origin (see `public-site/functions/proxy-routes.contract.json`): `/api/v1/*`, `/api/games/*`, `/api/play/*`, watch **asset** subpaths (`/g/{id}/board.png`, `/p/{id}/board.txt`, `/i/{id}/answer.png`, …), live leaderboard routes, and `/api/contact`. Watch/play **HTML** (`/g/{id}`, `/p/{id}`, `/i/{id}`, `/play/{id}`) is static on Pages and hydrates via those APIs.
- `/calibration*` is blocked at the edge (404) — calibration stays operator-only on the PC.

**When unset or the PC / tunnel origin is unreachable:** static pages and the leaderboard snapshot still work; Create Game and Spectator show the sleeping/offline UX. A common cause is a stale Quick Tunnel `*.trycloudflare.com` in `GAME_ORIGIN` while the harness is still fine on `127.0.0.1:8765` — see [`home-pc.md`](home-pc.md) troubleshooting.

### Game PC environment variable

On the machine running `chess-harness serve`, set:

```text
CHESS_HARNESS_PUBLIC_URL=https://chessvisionharness.pages.dev
CHESS_HARNESS_TRUSTED_PROXIES=127.0.0.0/8
```

(no trailing slash on the public URL)

`CHESS_HARNESS_PUBLIC_URL` is what agent briefs use for board/move/PGN endpoints (public hostname, proxied to your PC). `CHESS_HARNESS_TRUSTED_PROXIES` tells the harness to trust `X-Forwarded-For` from the local tunnel hop — Pages sets that header from each visitor's `CF-Connecting-IP` when proxying live routes.

Windows (current session): `set CHESS_HARNESS_PUBLIC_URL=https://chessvisionharness.pages.dev` before starting the server. For a permanent setup, see **[`home-pc.md`](home-pc.md)** (NSSM, Task Scheduler, tunnel, on/off checklist).

### Local Functions preview (optional)

From the repo root, with a local harness on port 8765:

```bash
cd public-site
echo GAME_ORIGIN=http://127.0.0.1:8765 > .dev.vars
npx wrangler pages dev .
```

Then open the URL Wrangler prints. `.dev.vars` is for local dev only — do not commit it. For Google sign-in locally, also put `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `AUTH_SESSION_SECRET` in `.dev.vars`, and add `http://localhost:8788/auth/callback` (or whatever port Wrangler prints) as an Authorized redirect URI on the Google OAuth client.

## Google sign-in (cosmetic — Create stays open)

Login is optional. Create Game and inscribe work for anonymous visitors. Sign-in only shows identity in the header and a one-line cue on Create.

1. Open [Google Cloud Console](https://console.cloud.google.com/) → create or pick a project.
2. **APIs & Services → OAuth consent screen** → External → app name e.g. `Chess Vision Harness` → your email as support/contact → Save. For testing, add yourself under **Test users** until you publish the app.
3. **APIs & Services → Credentials → Create credentials → OAuth client ID** → Application type **Web application**.
4. Name: `Chess Vision Harness Pages`.
5. Authorized JavaScript origins: `https://chessvisionharness.pages.dev`
6. Authorized redirect URIs: `https://chessvisionharness.pages.dev/auth/callback`
7. Create → copy **Client ID** and **Client secret**.
8. Create a long random session secret (PowerShell: `-join ((1..32) | ForEach-Object { '{0:x2}' -f (Get-Random -Max 256) })`).
9. Set GitHub Actions secrets on this repo:
   - `GOOGLE_CLIENT_ID`
   - `GOOGLE_CLIENT_SECRET`
   - `AUTH_SESSION_SECRET`
10. Redeploy: `gh workflow run "Deploy public site"` (or push a `public-site/` change). The deploy workflow injects these into `wrangler.toml` `[vars]` for Direct Upload, same pattern as `GAME_ORIGIN`.

Smoke: visit the site → **Sign in with Google** → header shows your name → Create shows “Signed in as … — login is optional.” → **Sign out** clears both → create a game while logged out still works.

While the consent screen is in **Testing**, only listed test users can sign in. Click **Publish app** when you want anyone with a Google account.

## Troubleshooting

- **Workflow fails with auth error** — re-check token permissions and that Cloudflare secrets are set on the correct repo.
- **404 on subpaths locally** — ensure you serve `public-site` as the document root, not the repo root.
- **Status chip always Sleeping** — `GAME_ORIGIN` is unset, the tunnel/origin is down, or `/health` on the origin failed. A named `cloudflared` connector without a public hostname does not help. Run [`verify-online.ps1`](verify-online.ps1) on the game PC; recovery: [`home-pc.md`](home-pc.md).
- **Create Game online but brief missing** — set `CHESS_HARNESS_PUBLIC_URL` on the game PC to your Pages URL and restart the server.
- **No Sign in button** — OAuth secrets not injected yet (`/auth/me` reports `oauth_configured: false`).
- **redirect_uri_mismatch** — the Google client’s Authorized redirect URI must be exactly `https://chessvisionharness.pages.dev/auth/callback`.
- **Access blocked: app is in testing** — add your Google account under OAuth consent screen → Test users, or publish the app.
