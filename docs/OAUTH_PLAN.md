# OAuth (cosmetic) + light activity audit

Status: **done** (Google sign-in)  
Last updated: 2026-07-27

Add Google login to the public site **without** gating Create Game or inscribe. Add a durable, no-auth activity log for creates/inscribes so the operator can see what happened (IP-ish metadata only). Prove OAuth works with a tiny signed-in-only UI affordance.

## Goal

1. **Audit (no auth):** every successful public `POST /api/v1/agents` and `POST /api/v1/games` appends a line the operator can read later.
2. **OAuth (fun / proof):** users can Sign in with Google, see their name, Sign out. Create/inscribe stay open to everyone (logged in or not).
3. **Smoke signal:** one trivial UI difference only when logged in (so we know the session works).

## Product decisions

| Topic | Choice |
|-------|--------|
| Create / inscribe | **Open to everyone** (unchanged access) |
| OAuth purpose | Cosmetic + future-ready; **no** API enforcement in this plan |
| Provider | Google OAuth (Web application client) |
| Session | HTTP-only cookie on the Pages hostname |
| Login UI | Header: **Sign in with Google** when logged out; name/avatar + **Sign out** when logged in |
| Signed-in-only toy | Create Game shows “Signed in as … — login is optional.” when signed in |
| Audit store | Append-only JSONL on the game host: `.chess_harness/audit/activity.jsonl` |
| Audit fields | `ts`, `action` (`inscribe` \| `create_game`), `model_id`, `game_id` (creates), `ip_hash`, truncated `user_agent` — **no** Google identity in audit until a later plan |
| Operator read path | `chess-harness audit tail [n]` or read `.chess_harness/audit/activity.jsonl` on the PC |

## Implemented

- Harness: `activity_audit.py`; wired on successful register + create; `CHESS_HARNESS_AUDIT_SALT`; CLI `chess-harness audit tail`.
- Pages Functions: `/auth/google`, `/auth/callback`, `/auth/logout`, `/auth/me`.
- Public-site header auth UI via `js/auth.js`; Create cue via `[data-auth-cue]`.
- Deploy injects `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `AUTH_SESSION_SECRET` when GitHub Actions secrets are set.

## Operator setup

See [`deploy/pages.md`](../deploy/pages.md) (Google Cloud OAuth client + Pages secrets) and [`DEPLOY.md`](../DEPLOY.md) (audit salt on the game PC).

## Verify

- Anonymous create/inscribe still succeed.
- Each success adds an `activity.jsonl` line with hashed IP.
- Login → header shows Google name; logout clears it.
- Logged-in-only cue toggles with session; no 401 on create either way.
