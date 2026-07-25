# Public site + home-PC game origin

Status: **Phases 1–4 implemented in repo** (2026-07-25). Human one-time: GitHub Actions secrets + push; then set `GAME_ORIGIN` when the PC should serve live games (see `deploy/pages.md` + `deploy/home-pc.md`).

Self-contained implementation plan. Public hostname today: `https://chessvisionharness.pages.dev`. Tunnel name: `chess-harness-pc` (connector healthy; no public hostname route yet).

## Goal

Ship one public URL that always loads. Home explains the product and shows the leaderboard. Leaderboard works when the game PC is off (snapshot + provisional Elo `*`). Create Game shows sleeping/offline when the origin is down; when up, users can inscribe or select a model and start a rated game. Contact goes to GitHub Issues. Live play proxies to a swappable `GAME_ORIGIN` (PC via tunnel now, other host later). No manual Pages drag-and-drop after the first Git/CI connect — deploys on push.

## Scope

- Static/edge site under `public-site/` (Home, Contact, Leaderboard, Create Game shell, Active/Completed offline UX).
- Cloudflare Pages + optional Worker/Functions for health probe and live proxy.
- Auto-deploy via Wrangler + GitHub Action (secrets: Cloudflare account/API token).
- Snapshot `leaderboard.json` schema; Python exporter from harness models/Elo; provisional `*` when `games < 100`.
- Create Game: offline banner; online inscribe + select wired to origin (`POST /api/v1/agents` + create flow).
- Edge blocks `/calibration*`.
- Deploy docs for tunnel → `127.0.0.1:8765`, Windows services, `CHESS_HARNESS_PUBLIC_URL`, `GAME_ORIGIN`.

## Out of scope

- Paying for VPS or custom domain.
- Dual local-engine create mode.
- Changing numbered game-type product plans.
- Agents running git (human pushes).
- Full pytest suite in agent runs.

## Phase 1 — Site shell + auto-deploy

Build the always-on site and CI deploy so pushes update Pages without manual upload.

- Replace placeholder with Home (default), Contact, Leaderboard, Create Game, Active, Completed nav.
- Home: short product copy, status chip, leaderboard section.
- Contact: primary CTA to `https://github.com/ishmanashna/chess-vision-harness/issues/new`, secondary profile link.
- Create Game: if origin unhealthy, prominent sleeping/offline message; no fake success.
- Active/Completed: offline message when origin down.
- Leaderboard UI reads `/data/leaderboard.json` (commit a bootstrap empty/minimal snapshot).
- Provisional Elo: `games < 100` → display `elo*` + legend.
- Add `wrangler.toml` (or Pages config) rooted at `public-site`, plus `.github/workflows/deploy-pages.yml` using `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`.
- Document one-time secret setup in `deploy/pages.md` (human pastes tokens into GitHub once).

**Done when:** Site files are complete locally; workflow exists; bootstrap snapshot renders; Create Game offline path is visible without a live origin.

## Phase 2 — Snapshot export from harness

- Python script or module: export agents (id, name, elo, games, provisional) + `generated_at` to `public-site/data/leaderboard.json` (and/or a path the edge reads).
- Hook or documented Task Scheduler / post-game call so a running PC can refresh the snapshot.
- Align legend copy with `rating_math.k_factor` (stable K at 100 games).

**Done when:** Running the exporter against a real harness data dir produces a valid snapshot the site can show.

## Phase 3 — Edge health + live proxy + public inscribe

- Worker/Pages Function: `GET /api/edge-health` probes `GAME_ORIGIN/health`.
- Status chip uses edge health.
- When `GAME_ORIGIN` is set, proxy `/api/v1/*`, `/create` mutations, `/g/*`, `/api/games/*`, live tabs to origin; deny `/calibration*`.
- Create Game online: inscribe (model id + optional name) via origin, then create game; reuse existing API key/agent registration limits.
- `CHESS_HARNESS_PUBLIC_URL` must be the Pages URL in briefs.

**Done when:** With a local origin and `GAME_ORIGIN` pointed at it, create/inscribe works through the edge shape; without origin, offline UX still holds.

## Phase 4 — PC runbook (tunnel + services)

- Document: cloudflared already installed for `chess-harness-pc`; add published route or Private Network / Worker binding so edge can reach `http://127.0.0.1:8765` without buying a domain if possible; else temporary Quick Tunnel as `GAME_ORIGIN` for testing.
- NSSM (or Task Scheduler) for `chess-harness serve` and cloudflared.
- Env: `CHESS_HARNESS_PUBLIC_URL=https://chessvisionharness.pages.dev`.
- Snapshot publish cadence on the PC.
- How to move `GAME_ORIGIN` off the PC later.

**Done when:** An operator following `deploy/` can bring live games up on the PC and take them down without editing site code.

## Order

1 → 2 → 3 → 4. Phase 1 does not need the tunnel. Phase 3 can be verified against localhost before Phase 4.

## Verify

- Open built Home/Contact/Leaderboard/Create (offline) from `public-site` or Pages after deploy.
- Exporter output validates against the snapshot schema.
- Local origin + Worker/`GAME_ORIGIN`: health online, inscribe+create; stop origin → sleeping message.
- Do not run the full pytest suite in agents; targeted checks only if needed.

## Estimated duration

- Phase 1: 3–5 agent-hours
- Phase 2: 1–2 agent-hours
- Phase 3: 4–6 agent-hours
- Phase 4: 2–3 agent-hours
