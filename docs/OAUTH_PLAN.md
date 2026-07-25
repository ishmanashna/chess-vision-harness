# OAuth + operator audit for Create Game

Status: **planned**  
Last updated: 2026-07-25

Gate public **inscribe** and **create game** behind a real login. Keep the rest of the site readable without auth. Record who did what so the operator has an internal activity trail (not a second public product).

## Goal

Only signed-in people can `POST /api/v1/agents` and `POST /api/v1/games` (and the Create Game UI that calls them). Home, leaderboard snapshot, Active/Completed spectate, and Contact stay public. Every successful inscribe and create is attributable to a user identity and stored for the operator.

## How this is usually done

Typical stack for a small public app:

1. **Identity provider (IdP)** — user clicks “Sign in with GitHub / Google”, browser redirects to the IdP, IdP redirects back with an auth code.
2. **Your app exchanges the code** for tokens, creates a **session** (HTTP-only cookie) or short-lived JWT.
3. **Protected routes** check the session before mutating state.
4. **Audit log** writes `{ when, user_id, action, payload }` on each sensitive action (append-only file or small DB).
5. **Operator UI** (private) lists that log; often behind the same login plus an allowlist, or a separate admin secret.

Common hosted shortcuts (same idea, less code):

- **Cloudflare Access** in front of `/create` and mutate APIs — CF handles OAuth; you still need to forward identity to the game origin and write audits.
- **Clerk / Auth0 / Supabase Auth** — hosted user tables + SDKs; you still enforce auth on the harness API and write your own audit events.

For this repo (Pages edge + PC `GAME_ORIGIN`, agent builders, free ops), **GitHub OAuth** fits best: one provider, familiar to contributors, no paid IdP required.

Out of scope for “usually”: building your own password database, or putting OAuth only on the static UI while leaving `/api/v1` open.

## Product decisions (locked for this plan)

| Topic | Choice |
|-------|--------|
| Provider | GitHub OAuth App (primary). Optional Google later, same session shape. |
| What requires login | Create Game page actions: inscribe model, create rated game. Matching API: `POST /api/v1/agents`, `POST /api/v1/games`. |
| What stays public | Home, Leaderboard, Contact, Active/Completed lists, `/g/*` spectate, board/move/PGN for an already-issued agent API key. |
| Session | HTTP-only secure cookie on the Pages hostname after OAuth callback. |
| API from Create UI | Browser sends session cookie (same-site) or a short-lived bearer minted at login; game origin must verify it (shared secret / JWT). |
| Existing agent API keys | Still used for move loops after create. Creating the game itself requires a logged-in user. |
| Audit store | Append-only JSONL on the game host under `.chess_harness/audit/` (and optional mirror to operator-only Pages Function storage later). |
| Operator “internal platform” | Private `/operator/activity` (or similar) on the harness, blocked at public edge except for an allowlisted operator session — list recent inscribes/creates with GitHub user, model id, game id, time. |
| Anonymous abuse | Rate limits remain; auth is the main gate. |

## Scope

- GitHub OAuth login/logout on the public site.
- Session verification for create/inscribe from the edge through to the harness.
- Audit events for inscribe + create.
- Operator activity page (read-only).
- Docs: env vars (`GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, session secret, operator allowlist).

## Out of scope

- Per-model ownership enforcement beyond “this user created it” (can follow later).
- Charging / billing.
- Replacing agent API keys with OAuth for every move.
- Full admin CMS.
- Cloudflare Access as the only solution (documented as an alternative, not the default path).

## Phase 1 — Session + GitHub OAuth on Pages

Add login/logout UI (header). Pages Function handles `/auth/github`, `/auth/callback`, `/auth/logout`. Store encrypted session cookie with `github_id`, `login`, `avatar_url`. Unauthenticated Create Game shows “Sign in with GitHub” instead of the form.

**Done when:** User can sign in/out on the public site; cookie is HTTP-only; Create Game form is hidden until signed in.

## Phase 2 — Enforce auth on mutate APIs

Harness rejects `POST /api/v1/agents` and `POST /api/v1/games` without a valid user session assertion (signed JWT from Pages, or verified cookie forwarded via proxy). Move/resign/board/status with existing agent API keys unchanged. Proxy must not strip auth headers/cookies for those routes.

**Done when:** Curl without login cannot inscribe or create; signed-in Create Game still works end-to-end through Pages.

## Phase 3 — Audit log + operator activity

On each successful inscribe/create, append an audit record (timestamp, github login/id, action, model_id, game_id, request ip hash optional). Add `GET` operator activity endpoint + simple HTML table. Edge: deny `/operator*` for everyone except configured operator GitHub ids (or separate operator token).

**Done when:** Operator can open activity and see recent creates/inscribes tied to GitHub users; public visitors cannot.

## Phase 4 — Hardening

Rotate session secret docs; CSRF on OAuth state; short session TTL + refresh; rate-limit failed auth; document revoke (delete GitHub OAuth app grants). Smoke: logged-out create fails; logged-in create audits; spectate still public.

**Done when:** Deploy docs cover secrets and the smoke matrix above.

## Order

1 → 2 → 3 → 4. Do not open mutate APIs until Phase 2 verifies the session.

## Verify

- Signed out: Create Game prompts login; `POST /api/v1/games` → 401.
- Signed in: inscribe + create succeed; agent brief still works with issued API key.
- Audit line appears for both actions with GitHub login.
- `/operator/activity` visible only to allowlisted operator.
- Active/Completed/Home/Leaderboard remain usable logged out.

## Estimated duration

- Phase 1: 4–6 agent-hours
- Phase 2: 4–6 agent-hours
- Phase 3: 3–5 agent-hours
- Phase 4: 2–3 agent-hours
