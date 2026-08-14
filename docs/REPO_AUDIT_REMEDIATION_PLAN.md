# Repo audit remediation plan

Make this a durable public agent-chess harness on the operator’s home PC: honest Online recovery without a paid domain, quiet git, truthful docs, fast tests, responsive serve, safe calibration, correct watch/play UI, and a gradual clean split between the game API and the public web shell. Product identity is **whatever an agent needs to play chess fairly**—not a vision-only demo brand—while the fair-play contract stays image-first with authenticated text fallback only when the image cannot be read.

## Operator decisions (locked)

- Game server stays on this PC; no paid domain for now (Quick Tunnel is the public path).
- Public metric label is **Performance** everywhere user-facing.
- Stop tracking volatile runtime data going forward; do **not** rewrite git history.
- Implementation order is flexible except hard dependencies below.
- Full remediation arc is wanted; Phase 9c–9d are a later track, not a blocker for the core path.

## Scope

- Home-PC Online: supervised harness + Quick Tunnel ops loop, verify-online, clear Sleeping recovery (not zero-touch stable hostname).
- Quiet git + real backups + truth matrix for runtime vs publish artifacts.
- Product/docs reframing under the existing **Chess Vision Harness** name (prose/tagline, not rename).
- Copy, briefs, edge honesty (Performance canon, idle timeout, Pages API/health hygiene).
- Test trim and CI tiers.
- Serve hot-path performance and calibration guardrails.
- Watch/play UI proportions and table bugs.
- Origin/web hygiene now (client IP, stop accidental `public-site/` writes); full static-shell / out-of-process calibration later.

## Out of scope

- Paying for a domain; automated zero-touch Online that never needs a `GAME_ORIGIN` refresh (needs a stable DNS hostname).
- Moving the game server off this PC.
- Full product rename (display name, package, GitHub repo, Pages URL)—reframe prose under the legacy brand unless the operator opens a separate rename decision.
- Multi-region / remote game database; Stockfish replacement; full ladder recalibration.
- Changing fair-play rules (no FEN shortcuts, no engines for agents, illegal moves rejected). Image-first + authenticated `board.txt` fallback remains.
- Git history rewrite for old blobs.
- Cosmetic tone tweaks unrelated to identity or factual claims (contact page banter, etc.). Phase 0 **may** change home/README/PRODUCT where they still sell “vision-only product.”

## Ordering

Core path: **1 → 2 → (0 ∥ early) → 3 → 4 → 5 → 6 → 7 → 8 → 9a → 9b**; later track **9c → 9d**. Phase 0 may run parallel with 1–2. Phase 6 before Phase 7. Phase 5 before 9a; re-check CI after 9c. Phase 8 may parallel Phase 4 after Performance naming lands in Phase 4.

---

## Phase 0 — Product identity (prose only)

Reframe PRODUCT, README lede, home meta/lead, AGENTS preamble (not Ground truth / Forbidden / play loops), and launcher asides/cards that still say “vision-only” or “vision agent” as the product category. Keep display name **Chess Vision Harness** and `chessvisionharness.pages.dev`; add/adjust tagline toward “fair agent chess benchmark.” Vision remains the default position channel and anti-cheat mechanism, not the product thesis. Preserve the home fairness argument (why PNG beats move-list leakage) as supporting copy under the new lead. No behavioral API break.

**Explicitly out of Phase 0:** `/api/v1` routes/auth; MCP/CLI behavior; generated brief templates (Phase 4); UI-wide Performance relabel (Phase 4); package/repo/domain rename; any weakening of AGENTS Ground truth or Forbidden.

**Done when:** A stranger reading PRODUCT + README + home understands “bring an agent, play fair rated chess on a shared ladder” with image-first as the rule—not “vision model leaderboard only.” AGENTS preamble matches; Ground truth and Forbidden unchanged. No primary “vision-only product/benchmark” label (mode-specific “board PNG” for puzzles/identify is fine).

**Verify:** Diff PRODUCT/README/home/AGENTS preamble; confirm Forbidden section untouched.

---

## Phase 1 — Home-PC Online durability and detection

Ship Windows harness NSSM (or equivalent) install helper: `.chess_harness/logs`, `CHESS_HARNESS_PUBLIC_URL`, restart-on-failure. Document Quick Tunnel as the current public path with two separate success criteria:

1. **Harness:** After reboot, serve is back; localhost `/health` green within a few minutes.
2. **Public Online:** Documented recovery (start/supervise Quick Tunnel → copy URL → `GAME_ORIGIN` secret → Deploy public site, redeploy again if secret raced) completes in under ~15 minutes with the operator present. Optional helper may log URL and drive secret+deploy; it is not required for phase done.

Ship `deploy/verify-online.ps1` (localhost `/health`, `{GAME_ORIGIN}/health`, Pages `/api/edge-health`) with clear exit codes; schedule it when the PC is expected Online. Sleeping runbook card lists only those three URLs. Clarify that a named `cloudflared` service without a public hostname does not make Pages Online. Non-goal: Quick Tunnel providing a stable `GAME_ORIGIN` across reboots without refresh.

**Done when:** Harness survives reboot; verify script distinguishes healthy vs Sleeping; operator can recover Online from stale origin using the runbook; dual-tunnel confusion is gone from docs.

**Verify:** Reboot harness path; force stale `GAME_ORIGIN` → verify fails → runbook recovery → edge-health online.

---

## Phase 2 — Quiet git, backups, and truth matrix

Untrack volatile runtime data going forward (`elo_calibration/results/continuous/games.jsonl`, `play_rating_samples.jsonl`, `data/finished_games.sqlite`, etc.). Fix inverted allow-lists in `elo_calibration/results/.gitignore` (remove force-track `!` rules for churn files). Leave historical blobs alone. Expand `backup_harness.py` before claiming restore: play-rating samples, `accuracy_elo_map.json`, play-rating map, puzzle/identify stores, audit. Task Scheduler template for nightly backup on this PC. Document truth matrix: live game dirs, finished SQLite, calibration JSONL, publish snapshots. Keep `public-site/data/*.json` tracked as deliberate Sleeping fallbacks—commit only for intentional offline publish; prefer serve refresh writing a runtime copy so daily Elo ticks do not dirty git (mini-item here if cheap; otherwise Phase 9b). Update DEPLOY restore matrix to match the backup manifest. Guard: pytest must not mutate `public-site/data/` or `elo_calibration/results/` (`test_data_files_untouched` pattern). Bound calibration JSONL growth on disk (rotate or cap).

**Done when:** Calibration/scored finish does not force multi‑MB diffs; backup tarball contains the expanded paths; restore drill works; truth matrix is one short DEPLOY section; data-untouched test green.

**Verify:** `git status` after calibration; inspect backup manifest; restore into throwaway dir; run data-untouched test.

---

## Phase 3 — Root docs match shipped product

Finish PRODUCT/ARCHITECTURE/README/AGENTS against shipped modes (engine, AvA, Playground, puzzles, identify; operator-only orchestration labeled). Live vs snapshot leaderboards; localhost-only calibration; `public-site/` as real UI / `frontend/` as lint scaffold. Fix roadmap AvH/AvA shipped status. Reconcile line-limit language (aspirational with waivers or enforce later)—no hard ≤300 claim while giants remain unwaved. Phase 0 identity already applied; this phase is accuracy and completeness.

**Done when:** PRODUCT+ARCHITECTURE+AGENTS suffice for every public mode without contradictions; README entry is `/launch/`.

**Verify:** Second-agent pass against live nav/routes; `check_clean_root.py` passes.

---

## Phase 4 — User-facing copy, briefs, and edge contract

Briefs match AGENTS (idle timeout on all game briefs; Imagine on engine/AvA; drop engine “rare” off-turn wording). Canonize **Performance** across home, leaderboard, spectator, tooltips, README, calibration UI (replace remaining “Play rating”). Fix AvA Games tooltip, accuracy→Elo prose, `/create?mode=human` → Playground, duplicate `ladder-heading`. Pages: unknown `/api/*` → JSON 404; public liveness is `/api/edge-health` not `/health`; block `/api/calibration/*` like `/calibration*`. Identify Sleeping snapshot parity or stop advertising the static path; `/identify` → launcher. Watch metrics join by agent id. Strip `board_path` host paths from public state. Idle/abandon stuck identify attempts. No contract/API behavior changes beyond messaging and redaction.

**Done when:** Briefs mention idle timeout; `/api/models` is 404 JSON on Pages; identify paths consistent; puzzle watch shows Performance when ratings exist; no user-facing “Play rating” where Performance is canon.

**Verify:** Brief diff vs AGENTS; curl Pages health/edge-health/api/models/identify paths; puzzle watch with known ratings.

---

## Phase 5 — Test suite trim and CI tiers

Shared Stockfish/session fixtures and mocks; merge duplicate `test_basic`/`test_moves`; shared spectator client and API helpers; `slow`/`integration` markers. PR: `pytest -m "not slow"`; nightly/full with Stockfish. Demote redundant calibration/catalog clones; wire or delete orphan Node smokes.

**Done when:** PR job much faster; markers used; leak/security tests still somewhere in CI.

**Verify:** Collect-only; PR timing before/after; spot-check leak tests.

---

## Phase 6 — Serve hot-path performance

Offload blocking move/imagine/eval/list work via bounded `to_thread`. Stop per-move full engine-pool release; reuse pools up to `CHESS_HARNESS_MAX_ENGINE_PROCESSES`. Cheap games-list projections (no per-row Stockfish; no full JSONL Elo replay on list). Cap spectator eval and quality-finish concurrency. PNG thread pool; skip re-render when fresh. Watch client: no double `/state`+`/eval`; skip in-progress PGN fetch.

**Done when:** Scripted parallel status/board/moves while `/api/games` is hammered keeps `/health` responsive; list endpoints without per-row Stockfish; engine PID count bounded by config.

**Verify:** Load script with latency + max engine PID count before/after.

---

## Phase 7 — Calibration safety and operator UX

Confirms and hard caps for Start all / high parallel; lightweight live status vs heavy table; surface POST errors; confirm+progress for rebuild map; warn/lock pairing changes while running; UI/DEPLOY naming aligned to Performance / accuracy→Elo. No calibration secret in HTML on non-loopback Host.

**Done when:** Cannot silently no-op Start; cannot unboundedly melt the PC without confirm; status feels responsive when idle.

**Verify:** Localhost start/stop with caps; bad secret shows error; status poll timing.

---

## Phase 8 — Watch and play UI proportions

Fix board shrink (`100vw - 848px`); earlier single-column; shared watch CSS (may live in `public-site/css/watch.css` linked from Python templates before any static-shell migration). Playground coordinates + player rails. Puzzle attempts column mismatch; table overflow wrappers; hide empty Active quality cols; poll error banners; height sync; identify answer overlay in review flow on narrow viewports. Tier: ship layout/bug fixes first; CSS consolidation second.

**Done when:** At 1024–1280px the board dominates on `/g/`, `/p/`, `/i/`, `/play/`; columns align; errors visible.

**Verify:** Browser pass at 1024 / 1280 / 1440 / mobile on game, puzzle, identify, Playground.

---

## Phase 9a — Proxy client IP and rate limits (now)

Stop Pages proxy from stripping client identity; forward `CF-Connecting-IP` (or equivalent); document `CHESS_HARNESS_TRUSTED_PROXIES` for the tunnel hop. Shared proxy route contract tests so allowlists cannot silently drift.

**Done when:** Two API keys behind Pages hit independent rate-limit buckets in a scripted test.

**Verify:** Scripted dual-key flood via public host; metrics/limits show separate buckets.

---

## Phase 9b — Stop serve writing the deploy tree (now)

Redirect snapshot export away from mutating the git `public-site/data/` tree during serve (runtime publish dir and/or CLI-only publish). Define who publishes Sleeping snapshots after this change (operator CLI before long offline, or CI artifact)—must not break Sleeping freshness or reintroduce git churn.

**Done when:** Rated finish and calibration tick do not modify tracked files under `public-site/`; Sleeping path still has a defined publish step.

**Verify:** File-watch `public-site/` during finish/calibration; Sleeping fallback still loads after deliberate publish.

---

## Phase 9c — Static watch/play shells (later track)

Replace Python-rendered `/g/`, `/p/`, `/i/`, `/play/` with Pages static shells that hydrate from APIs. Origin drops hub/watch HTML serving for those routes. Re-stabilize CI after the cut.

**Done when:** Watch/play HTML is served as static from Pages; origin no longer owns those page bodies.

**Verify:** Curl watch HTML from Pages with origin API-only; spot spectator/API tests green.

---

## Phase 9d — Calibration out of process (later track)

Move continuous calibration off the uvicorn process so heavy cal work cannot starve live play. Prefer after Phase 7 caps prove insufficient or after 9b/9c land.

**Done when:** Heavy calibration POST/load does not block `/health` or agent moves under a defined load test.

**Verify:** Start capped cal load; agent move + `/health` stay within budget.

---

## Estimated duration

- Phase 0 — Product identity: 3–6 agent-hours
- Phase 1 — Home-PC Online durability and detection: 8–16 agent-hours (includes verify + optional origin helper)
- Phase 2 — Quiet git, backups, truth matrix: 8–14 agent-hours
- Phase 3 — Root docs match shipped product: 6–10 agent-hours
- Phase 4 — Copy, briefs, and edge contract: 8–12 agent-hours
- Phase 5 — Test suite trim and CI tiers: 10–16 agent-hours
- Phase 6 — Serve hot-path performance: 12–20 agent-hours
- Phase 7 — Calibration safety and operator UX: 8–12 agent-hours
- Phase 8 — Watch and play UI proportions: 10–16 agent-hours
- Phase 9a — Proxy client IP: 4–8 agent-hours
- Phase 9b — Stop deploy-tree writes: 6–10 agent-hours
- Phase 9c — Static watch/play shells (later): 16–24 agent-hours
- Phase 9d — Calibration out of process (later): 10–16 agent-hours

Core path (0–8 + 9a–9b): roughly 85–140 agent-hours. Later track 9c–9d adds roughly 25–40.
