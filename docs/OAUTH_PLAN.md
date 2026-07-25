# OAuth (cosmetic) + light activity audit

Status: **planned**  
Last updated: 2026-07-25

Add GitHub login to the public site **without** gating Create Game or inscribe. Add a durable, no-auth activity log for creates/inscribes so the operator can see what happened (IP-ish metadata only). Prove OAuth works with a tiny signed-in-only UI affordance.

## Goal

1. **Audit (no auth):** every successful public `POST /api/v1/agents` and `POST /api/v1/games` appends a line the operator can read later.
2. **OAuth (fun / proof):** users can Sign in with GitHub, see their name, Sign out. Create/inscribe stay open to everyone (logged in or not).
3. **Smoke signal:** one trivial UI difference only when logged in (so we know the session works).

## Product decisions

| Topic | Choice |
|-------|--------|
| Create / inscribe | **Open to everyone** (unchanged access) |
| OAuth purpose | Cosmetic + future-ready; **no** API enforcement in this plan |
| Provider | GitHub OAuth App |
| Session | HTTP-only cookie on the Pages hostname |
| Login UI | Header control next to Dark mode / status: **Sign in with GitHub** when logged out; **avatar/login + Sign out** when logged in |
| Signed-in-only toy | e.g. a small “Signed in as @{login}” chip under the header on Create Game, or a soft highlight on the Create heading — pick one in implementation; must be obvious and harmless |
| Audit store | Append-only JSONL on the game host: `.chess_harness/audit/activity.jsonl` |
| Audit fields | `ts`, `action` (`inscribe` \| `create_game`), `model_id`, `game_id` (creates), `ip_hash` (hash of client IP + server salt), `user_agent` truncated — **no** GitHub identity until a later plan |
| Operator read path | CLI or local file read for v1 (`chess-harness audit tail` or documented `Get-Content`); optional tiny localhost-only HTML later — not a public page |

## Scope

- Pages Functions: `/auth/github`, `/auth/callback`, `/auth/logout`, `/auth/me`.
- Public-site header: login / user / logout.
- One trivial logged-in-only visual on Create Game (or global header subtitle).
- Harness: write activity JSONL on successful register + create; env `CHESS_HARNESS_AUDIT_SALT` for IP hashing.
- Docs: GitHub OAuth app setup, Pages secrets, audit file location.

## Out of scope

- Requiring login for create/inscribe.
- Attaching GitHub user to audit lines (can follow later).
- Public operator dashboard.
- Cloudflare Access.
- Changing agent API key / move-loop auth.

## Phase 1 — Light activity audit (no OAuth)

On successful `POST /api/v1/agents` and `POST /api/v1/games`, append one JSON line to `.chess_harness/audit/activity.jsonl`. Hash IP with a server salt. Document how to read the file on the PC. Keep rate limits as they are.

**Done when:** Creating a game or inscribing locally appends a parseable line; failures do not write success lines.

## Phase 2 — GitHub OAuth on Pages (no gates)

GitHub OAuth App → callback Function sets session cookie (`github_id`, `login`, `avatar_url`). Header shows Sign in / signed-in identity / Sign out. `/auth/me` returns the session JSON for the client. Create and inscribe APIs remain open.

**Done when:** User can complete login/logout on chessvisionharness.pages.dev; cookie is HTTP-only; logged-out users still create games.

## Phase 3 — Trivial logged-in-only UI

If `/auth/me` says signed in, show a small non-blocking cue (recommended: header shows `@login`; Create Game aside or form card gets a one-line “Playing as GitHub @{login} — login is optional.”). No API changes.

**Done when:** The cue appears only when logged in and disappears on logout; create still works logged out.

## Phase 4 — Docs + verify

Document secrets (`GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, session secret, `CHESS_HARNESS_AUDIT_SALT`). Smoke: audit lines after anonymous create; login shows name; logout clears cue; create still works both ways.

**Done when:** `DEPLOY.md` or `deploy/pages.md` lists the secrets and the smoke checks above.

## Order

1 → 2 → 3 → 4.

## Verify

- Anonymous create/inscribe still succeed.
- Each success adds an `activity.jsonl` line with hashed IP (not raw IP in the clear if salt is set).
- Login → header shows GitHub login; logout clears it.
- Logged-in-only cue toggles with session; no 401 on create either way.

## Estimated duration

- Phase 1: 1–2 agent-hours
- Phase 2: 3–5 agent-hours
- Phase 3: 1 agent-hour
- Phase 4: 1 agent-hour
