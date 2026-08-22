# Operator panel

A localhost ops desk for the person running the game PC: traffic that hit this machine, errors, disk, contact inbox, live activity, and one-click public Online. Replaces the static prototype in `deploy/operator-panel.html`.

## Scope

- Open a real panel on this PC while serve is up.
- Same visual structure as the prototype (Overview, Traffic, Errors, Machine, Inbox, Activity).
- Origin numbers (errors, latency, API hits) come from this process. **People** (referrers, countries, public pageviews) come from Umami Cloud, which keeps counting while the PC is Sleeping.
- Double-click Go Online opens the panel in the browser once localhost is up (the daily gesture). The panel can also send Go Online / Sleep while serve is already running.
- A Sleep public button that drops the tunnel so Pages goes Sleeping, without killing localhost serve (the panel must stay open).
- Public Pages cannot see or run any of this.

## Out of scope

- Hosting the panel on chessvisionharness.pages.dev.
- Sentry, Datadog, Google Analytics, Cloudflare Web Analytics. One Umami Cloud site only.
- Self-hosting Umami on this PC (it would go dark whenever games are Sleeping).
- Killing or recycling `chess-harness serve` from the panel (that would kill the page that launched Go Online).
- Replacing Calibration or Puzzle set. The existing Desktop Go Online shortcut stays; it also opens the panel. No second “Ops” desktop icon.
- Linux/macOS Go Online (the script is Windows).
- Auth beyond loopback. This is an operator surface on 127.0.0.1.

## Product decisions (locked)

1. **Where it lives.** `http://127.0.0.1:8765/ops/` — same class as Calibration and Puzzle set. Loopback host nav grows an **Ops** link after Puzzle set. Pages middleware returns 404 for `/ops` and `/api/ops`. Add those prefixes to the Pages proxy contract so they cannot leak through `GAME_ORIGIN`. Daily access is the existing **Go Online** Desktop shortcut: after localhost `/health` is OK, the script opens the default browser to `/ops/` (so you watch the rest of tunnel + deploy from the desk). Scripted runs may pass `-NoPanel`. Do not add a second Desktop icon only for the panel.

2. **Two traffic stories, labeled as such.** **Origin requests** = HTTP that reached this PC (live API, watch, localhost). **Site visitors** = Umami pageviews on the public Pages host (humans in a browser). Do not mix them into one “views” number. Agent board-fetch storms belong in origin requests, not Umami.

3. **Errors and latency.** In-process ring: status class (2xx/4xx/5xx), route family, duration. Illegal moves stay 4xx and are not painted as outages. Panel Errors tab lists recent 5xx and unexpected 4xx. No Sentry project.

4. **Inbox.** Reuse the existing localhost contact inbox APIs. Overview shows unread; Inbox tab is the full list (read / delete already exist).

5. **Activity.** Tail the existing activity audit log plus in-progress games / puzzle / identify attempts already exposed to Spectator. Do not invent a second event store.

6. **Machine.** `shutil.disk_usage` for the system drive and `.chess_harness` size; process flags for serve (always true if the panel loaded), tracked Quick Tunnel pid, calibration worker port. Local `/health` is this process. Tunnel and Pages probes are the same three URLs Go Online already verifies — from the PC, with timeouts, without blocking the page.

7. **Two directions, one script.** Desktop / `Start-Online.bat` is how you wake the PC: start serve if needed, open `/ops/`, then tunnel + Pages. The panel button is for when serve is already up (refresh tunnel, or Sleep). `POST /api/ops/go-online` is loopback-only. It starts `deploy/go-online.ps1` **without recycling serve** and **without opening another browser tab** (you are already on the panel). The HTTP call returns a job id immediately. The panel polls `GET /api/ops/go-online` for phase text and log tail until verify succeeds or fails. One job at a time; a second click is rejected while running.

8. **Sleep public.** `POST /api/ops/sleep-public` stops the tracked Quick Tunnel process only. Serve stays up. Pages will show Sleeping on the next edge-health probe. Panel stays usable.

9. **Prototype file.** `deploy/operator-panel.html` is the visual reference. Implementation is a real origin page + JS. Delete the prototype once `/ops/` ships so there are not two panels.

10. **Umami Cloud for audience.** Operator creates a free Umami Cloud website for `chessvisionharness.pages.dev`. Public pages load the Umami tracker **only on that host** (never on `127.0.0.1` / localhost). The website id in the snippet is not a secret. The API token never ships to Pages; it lives on the game PC (`CHESS_HARNESS_UMAMI_TOKEN`, plus website id and optional API host). `GET /api/ops/audience` (loopback) fetches last-24h pageviews, referrers, top pages, and countries and the Traffic tab renders them. If the token is missing, that block says to set the env vars — no fake referrers. The Umami web dashboard remains a fallback when this PC is off.

## Phase 1 — Page, lock, live leftovers

**Goal:** Operator opens `/ops/` on localhost and sees a real desk with health, disk, inbox, activity, and live games. Charts may be empty zeros until Phase 2.

**Work**

- Serve `public-site/ops/index.html` (and JS) from origin at `/ops` and `/ops/`. Loopback-only HTML (404 off loopback, same idea as Puzzle set).
- Loopback nav: **Ops**.
- Pages: 404 `/ops*` and `/api/ops*`; contract lists those paths as origin-only, not proxied.
- `GET /api/ops/snapshot` (loopback): disk, harness dir size, `/health`, optional tunnel pid + last known tunnel URL file, inbox unread count + latest messages, activity tail, in-progress games/attempts. No go-online side effects.
- Wire Overview / Machine / Inbox / Activity to that snapshot. Poll ~10s.
- `go-online.ps1`: after harness healthy, `Start-Process` `http://127.0.0.1:8765/ops/` unless `-NoPanel`. `Start-Online.bat` does not pass `-NoPanel`.

**Done when**

- Loopback: panel loads, nav shows Ops, snapshot matches inbox on `/contact/` and disk in Explorer within rounding.
- Off loopback and on Pages: `/ops` is 404 JSON/HTML not the desk.
- Desktop Go Online (serve already installable) opens `/ops/` in the browser once localhost is healthy, even while tunnel/deploy still runs.
- Panel Go Online button is visible but inert or hidden until Phase 3 (do not ship a fake click).

**Verify**

- Browser on `127.0.0.1:8765/ops/`. Curl Pages `/ops` → 404. Leave a contact message, see it on Inbox.

## Phase 2 — Request metrics

**Goal:** KPIs and charts are real for traffic that hit this process.

**Work**

- ASGI/Starlette middleware: count requests, bytes optional, status, ms, coarse route (static, `/api/v1`, watch, other). In-memory ring (e.g. last 24h in 1-minute buckets + last N error events). Survives only as long as this serve process — say so on the charts.
- Snapshot adds: origin request counts (24h), error rate, p95, per-route table, error event list. Do not label these “visitors.”
- Traffic / Errors / Overview charts read those buckets. 4xx from illegal moves / 422 schema are counted separately from 5xx.

**Done when**

- Load Home on localhost, create or watch something: request series moves. Force a 5xx or unplug tunnel briefly: Errors tab shows it. Restart serve: charts reset (documented).

**Verify**

- Two browsers hitting `/ops/` and `/launch/` while Online; numbers increase. Illegal move does not look like an outage.

## Phase 3 — Go Online and Sleep public

**Goal:** The panel brings the public site Online and can put it to sleep, without restarting serve.

**Work**

- `go-online.ps1`: if localhost `/health` is already OK, do not stop/start serve. Still set `CHESS_HARNESS_PUBLIC_URL` in the *script* environment only for a newly spawned serve; a healthy existing process keeps whatever env it was started with (Go Online from Desktop still recycles when health is down).
- Job runner in serve: spawn the script, capture stdout/stderr to a log under `.chess_harness/logs/`, expose status `idle|running|ok|fail`.
- Panel: Go Online runs the job and streams status into Overview (phase line + last log lines). Sleep public kills tracked `cloudflared` pid.
- After job ok: Pages chip Online without requiring the operator to leave `/ops/`. After sleep: Pages Sleeping; localhost panel still works.

**Done when**

- From `/ops/` with serve already up: Go Online refreshes tunnel + secret + deploy; public chip Online; serve pid unchanged; agent briefs still the Pages URL if this process was started by Go Online with that env.
- Sleep public: tunnel gone, Pages Sleeping, `/ops/` still loads.
- Second Go Online click while running: rejected, first job continues.

**Verify**

- Pages tab left open (Sleeping), press Go Online on the panel, wait: chip Online; no extra browser window. Then Sleep public: chip Sleeping. Localhost Calibration still opens.
- Cold start from the Desktop shortcut: serve comes up, panel opens, public becomes Online.

## Phase 4 — Site visitors (Umami)

**Goal:** Traffic tab shows where public-site people came from, including visits while the game PC was Sleeping.

**Work**

- Operator-only env on the PC (not git, not Pages): Umami API token, website id, optional API host (default Umami Cloud).
- Public HTML/JS: Umami tracker on the Pages hostname only. One snippet path so Home, Create, Spectator, watch shells cannot drift (shared `common.js` or one include).
- Loopback `GET /api/ops/audience`: last 24 hours pageviews, unique visitors, referrers, top pages, countries. Token used only in serve. Cache ~60s.
- Traffic tab: **Site visitors** (Umami) beside **Origin requests** (Phase 2). Empty state if env unset.
- Do not send localhost operator clicks to Umami.

**Done when**

- Open the public site from a phone or a second browser: Umami (and then `/ops/` Traffic) shows a pageview and a referrer or “direct.” Localhost `/ops/` itself does not increment Umami. Pages HTML never contains the API token.

**Verify**

- Pages while origin Sleeping: visit Home, then later open `/ops/` with serve up — that visit is in Site visitors. A Create Game session Online increments both origin requests and a Create pageview, counted separately.

## Estimated duration

- Phase 1: 2.5–4 agent-hours
- Phase 2: 2–3.5 agent-hours
- Phase 3: 3–5 agent-hours
- Phase 4: 2–3.5 agent-hours
