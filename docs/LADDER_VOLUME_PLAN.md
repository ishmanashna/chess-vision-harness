# Ladder volume: ready for API models

Make the harness able to play ordinary `/api/v1` games from a small internal runner **as soon as we have model API access**. This cycle is the plumbing: observation mode, a durable agent client, idle/reconnect, a stub-backed runner, and a provider plug. It is not a hunt for free tokens, and it does not wait on a live farm.

The website stays the public surface: watch, label, leaderboard, and a way for other people to donate games with their own agents. When keys exist, the runner writes the same dataset those agents already write. Text-only models share the same ladder and are marked. No second protocol, no browser, no new results store.

## Scope

- Same AvE (and later puzzle/identify) games as Create Game: PNG and/or `board.txt`, POST move, ordinary `results.jsonl` + PGN, ordinary quality analysis and Elo.
- Inscribed models carry an observation mode (`vision` or `text`). Leaderboard shows it. Each finished game stores the mode used, so later analysis does not lie if a model is relabeled.
- A Python HTTP client that talks to `/api/v1` like a well-behaved agent (real User-Agent, retries, resume).
- An internal runner: config slots, crash resume, logs, a **stub provider** that proves the loop without any vendor key. Not a community product this cycle.
- A provider adapter so a real OpenAI-compatible (or similar) chat API is config + env when keys exist — not a rewrite.
- Idle and reconnect behavior that does not silently drop a long game or leave a zombie `in_progress` forever.
- Puzzle and identify on the same client so those ratings are ready when volume starts.

## Out of scope

- Getting free tokens, signing up at provider consoles, or proving Groq / Mistral / Cloudflare / NVIDIA / Gemini / OpenRouter this cycle.
- Paying for inference, credit-card “unlocks”, wrapping Cursor or Copilot as the farm.
- A live unattended farm as a done-when. Volume starts when we have keys; this plan ends when the system can take them.
- A new public API, WebSocket, or “turn package” that replaces board PNG / `board.txt` / move.
- Parent orchestration, follow-up approval, or scoped child keys as the farm path (those are operator pairing tools, not this).
- Agent-vs-agent or Playground farming (two sides / a human). Community AvA still uses today’s API.
- Google Analytics, Sentry, the operator panel, named tunnels.
- A new database. The dataset is `.chess_harness` games + `results.jsonl` + PGN + quality fields (plus the existing `data/finished_games.sqlite` archive).
- Anti-cheat or identity verification.
- Sending FEN or move lists to models. Text-only means **`board.txt`**, the same grid the website already serves.
- Unofficial gateways with unclear terms (random “free LLM” reverse proxies).
- Porting the live ladder into Eleuther `lm-eval` / HELM as a FEN or multiple-choice YAML task. That would break the vision-first contract.
- Lab / aggregator outreach, Arena, Artificial Analysis, academic credit grants. Those wait until there are games to show. Not blockers for this plumbing.

## Product decisions (locked)

1. **One ladder, one dataset.** API/runner games are ordinary harness games. They must not skip engines, ratings, quality, or spectator. Text-only is allowed on that ladder. If those models score lower, that is a result, not a bug.

2. **Observation mode.** Each inscribed model has `observation`: `"vision"` (default for existing models and for `POST /api/v1/agents` when omitted) or `"text"`. Vision clients read **PNG and `board.txt`** every ply (today’s contract). Text clients read **`board.txt` only** and must not be required to fetch the PNG. Neither may use FEN/JSON as the position. The leaderboard name cell shows a short mark (e.g. “text”) with a tooltip that they play from the text board, not the image.

3. **Copy mode onto the game.** At create time, snapshot `observation` onto game state and onto the `results.jsonl` row at finish. Analysis of the dataset uses the row, not “whatever the model is labeled today.”

4. **No new door.** Create: `POST /api/v1/games`. Position: `GET .../board` and/or `GET .../board.txt`. Move: `POST .../move/{uci}`. Status/PGN/resign unchanged. `GET .../moves` still does not exist. `_sanitize_agent_payload` still strips FEN/move lists. The runner is a client of this, same as Claude with a correct Pages URL.

5. **Idle is 30 minutes without a move — not one minute.** Default `CHESS_HARNESS_IDLE_TIMEOUT_SEC` stays **1800**. A game dies only after half an hour with no submitted move (then `*` / inactivity, not a loss). The serve loop that *looks for* idle games runs about every 60 seconds; that tick is not the timeout. GET status/board must still **prune** so a reconnecting client sees a just-expired game immediately instead of waiting for the next tick. GET status/board does **not** reset the idle clock (only a move — or AvA/AvH first join — does). Do not lower idle for the runner; the env floor of 60 seconds exists for tests, not for production. Provider 429 backoff must stay well inside 30 minutes (cap sleeps; then skip/resign that ply’s game rather than sit until the clock fires). When a slot has no budget left, **stop the slot** — do not leave a live game open overnight waiting for quota. AvE `agent_joined` (spectator) is set on first board or `board.txt`, not on status; a text runner must hit `board.txt` so watch pages know it started.

6. **Limits stay global.** Default 10 concurrent games, 20 creates/hour/key, 600 moves/hour/key. The runner uses the same caps. The operator may raise env limits on this PC when farming; do not add a secret “runner bypass” route.

7. **Keys and identity.** One inscribed id per model. One harness API key per id, stored only on the operator machine. Honor-based names, same as web inscribe. Provider keys live in env, never git. The runner never wraps Stockfish or feeds FEN. Empty env for a slot means skip that slot — the runner must still start and play stub slots.

8. **Where it runs.** Operator PC, against `http://127.0.0.1:8765` while serve is up (fast, no Pages hop). Optional `HARNESS_BASE_URL` pointing at Pages for a remote runner. Always send a normal User-Agent. `CHESS_HARNESS_PUBLIC_URL` still Pages for any brief a human might copy; the runner itself does not parse briefs.

9. **Keys are later; the plug is now.** This cycle does not mint vendor keys or pick a free-tier roster. Git holds an example slot config with empty secrets: `{inscribed_id, provider, base_url, provider_model, observation, env_key, rpm, rpd}`. A `runner probe` command exists so that when a key arrives, one chess-shaped call (text: `board.txt`; vision: a harness-rendered PNG) can prove the slot before games start. Probe failure or missing env disables the slot. A stub/`fake` provider needs no env and is what CI and “done when” use.

10. **Adapters are a plug, not a catalog.** One OpenAI-compatible chat adapter (base URL + model id + env key name) covers whoever we get later. An in-process stub adapter is first-class: it returns legal UCI from a tiny scripted policy (or a fixed legal move) so tests and dry runs do not call the internet. Vision slots send the PNG to the model (base64 data URL) and still read `board.txt` locally. If a provider rejects the full PNG (size / tokens), the runner may JPEG-compress or downscale **only the bytes it sends to that provider** — the harness `board.png` is unchanged. Text slots send `board.txt` only. Parse a single UCI/SAN; on garbage, POST it anyway (illegal move ends the game today). No engine fallback. Do not add a Gemini-only adapter until we actually have a Gemini key.

11. **Puzzles after AvE.** The AvE loop is the first proof the runner works. Puzzle and identify use the same client and observation rules so those axes are ready when volume starts.

12. **Outreach is not this plan.** Labs and aggregators playing *here* is still the right later ask. Do not block plumbing on Arena, Artificial Analysis, or academic grants. Do not invent a second eval API for them.

## Verified current system (do not re-invent)

- Play loop already in `python/src/chess_harness/api_v1.py`: `POST /agents`, `POST /games`, `GET .../board`, `GET .../board.txt`, `POST .../move/{move}`, `GET .../status`, `POST .../resign`, `GET .../pgn`. Auth: `Authorization: Bearer`. Create returns `agent_brief` for paste; a program ignores it.
- Position leak guard: `api_v1._sanitize_agent_payload` and `agent_surface.agent_safe_status` (no `fen` / `moves`).
- Idle: default 1800s (`limits.py`). `last_activity` on moves and AvA/AvH join, not on AvE `GET status`. Background `spectator._idle_watcher` every 60s calls `GameService.prune_idle_games` → `end_no_result` (`*` , no Elo). `_prune_idle` also runs on create/move/resign, **not** on GET status/board (so a just-expired game can still look live until the next watcher tick or a write). Puzzle/identify idle abandon uses the same 1800s.
- Finish path already `schedule_game_quality` into `results.jsonl` and dual-writes `finished_games.sqlite`. Live leaderboard: `snapshot_leaderboard.build_snapshot` from `models.json` + results + puzzle/identify stores. No `observation` field today. AvE `agent_joined` is first PNG or `board.txt` only.
- No `GET /api/v1/games` for the agent. Spectator `GET /api/games` is operator UI — agents must not use it.
- Orchestration (`orchestration_api.py`) is the wrong farm. Test helper `python/tests/harness_client.py` is TestClient only, not a play SDK.
- Pages may 403 empty/`Python-urllib` User-Agents. Serve binds `127.0.0.1:8765`. Board PNG is about 502×502 from the Pillow renderer.
- Roadmap `docs/roadmap/native-llm-benchmark.md` is the older “harness calls providers” sketch. This plan is the one to implement; that doc does not add a second client.

## Phase 1 — Observation mode on the shared ladder

**Goal:** Models can be vision or text; the table and the dataset say which. Play rules match Decision 2. Existing inscribed models stay `vision`.

**Work**

- `models.json` / `ModelRegistry.inscribe` and `POST /api/v1/agents`: optional `observation` (`vision`|`text`). Persist. Include on `GET /api/v1/agents` and snapshot agent rows.
- Copy onto new game state; write onto result rows at finish.
- Leaderboard name mark + tooltip (home, `/leaderboard/`, live and snapshot). Spectator tables may show the same mark when the agent column is a model name.
- `PRODUCT.md` and paste briefs: text-only agents use `board.txt` as the position; vision agents still use PNG + `board.txt`. Same ladder. If the inscribed model is `text`, the brief must not tell them the PNG is required (vision briefs unchanged).

**Done when**

- Inscribe a text model, play a localhost AvE using only `board.txt`, game scores, row has `observation: "text"`, leaderboard shows the mark. A vision model’s brief still requires both channels. Old models without the field behave as vision.

**Verify**

- One text and one vision fixture in API tests. Public snapshot JSON includes `observation`. UI mark visible on `/leaderboard/` localhost.

## Phase 2 — Headless client: same loop, durable

**Goal:** A program can play and resume without HTML, without leaking FEN, without fighting idle zombies.

**Work**

- Prune idle on `GET .../status` and `GET .../board` / `board.txt` (same `_prune_idle` as moves) so a reconnecting client does not wait for the 60s watcher.
- `GET /api/v1/games` authenticated: this key’s in-progress (and optionally recent finished) games — ids, `your_turn`, `observation`, not FEN, not a move list. Not the spectator route.
- Package `chess_harness.agent_http`: base URL, Bearer, User-Agent, retries on 502/429/network, create AvE, fetch observation channels per mode, POST UCI, persist `{game_id, model_id}` to a small queue file under `.chess_harness/runner/`, on start reconcile queue with `GET /api/v1/games`. Never parse `agent_brief`. Never read `state.json`.
- Document env `CHESS_HARNESS_MAX_GAMES_PER_HOUR_PER_KEY` (etc.) for farm days. Do not add a bypass. Do not document lowering idle below 1800 for farming.

**Done when**

- Kill the client mid-game, restart it: it continues the same `game_id` until mate/resign/idle-*. Idle game appears finished on the next status/board GET. 429 is retried with backoff. urllib default UA is not used.

**Verify**

- Integration test: create, one move, simulated restart from queue, second move. Test prune-on-GET with a short idle env in tests only.

## Phase 3 — Internal AvE runner (stub first)

**Goal:** Unattended rated AvE through the client, proven with a stub provider, with a plug ready for a real chat API when keys exist.

**Work**

- Slot config from git example (empty secrets). Skip slots with empty env or last probe failure. A `provider: stub` slot always runs in tests and dry runs.
- Adapters: in-process stub; OpenAI-compatible HTTP client (base URL + model + env key). Honor `Retry-After`; cap wait so a ply still finishes inside the 30-minute idle window; on configured rpd/rpm exhaustion, stop the slot and do not leave `in_progress` games hanging.
- `python -m chess_harness runner probe`: one chess-shaped call per configured non-stub slot (does not start a harness game). Missing keys → fail closed for that slot, runner continues. Stub probe is always ok.
- Scheduler: respect configured rpm/rpd **and** harness 429. Sequential or few parallel slots ≤ `max_concurrent_games`.
- Logging: one JSONL under `.chess_harness/runner/` (game_id, model, provider, error, quota). Operator can `tail`. Do not build the ops panel.
- Entry: `python -m chess_harness runner` (or `chess-harness runner`) from repo, Windows-schedulable. Talks to localhost by default.
- Opponent: omit `opponent` so the harness keeps matching Elo as Create Game does, unless config sets an explicit `opponent` id.
- Optional JPEG downscale path for the bytes sent to a vision adapter; unit-test it without a vendor.

**Done when**

- Dry run against the stub plays a short game through `agent_http` into a temp harness dir and a `results.jsonl` row appears with quality scheduled. Spectator `/g/{id}` works in that dry run (or equivalent test app). Leaderboard mark matches observation.
- Example config in git has empty secrets and a documented stub slot. `runner probe` with no vendor env does not crash and does not enable empty-key HTTP slots.
- OpenAI-compatible adapter is unit-tested against a fake HTTP chat endpoint (no live vendor). Wiring a real key later is filling env + slot fields, not new code — unless the vendor is not OpenAI-shaped.

**Verify**

- Disconnect mid-game (kill runner): restart continues. Spend a tiny fake rpd: slot stops with no live game left behind. Illegal model output: game ends, logged, next game can start. Unset keys → HTTP slots stay off.

## Phase 4 — Puzzle and identify volume

**Goal:** Same runner/client can grind puzzles and identify so those ratings are ready when API models exist.

**Work**

- Extend `agent_http` with the existing puzzle/identify HTTP loops (`POST /api/v1/puzzles/start`, board + board.txt, `POST .../move`, review; identify `.../answer`). Observation mode applies the same way. Continuous start after review, as the puzzle/identify paste briefs.
- Runner config: `kind: ave | puzzles | identify` per slot. Do not mix kinds in one in-flight attempt beyond today’s concurrency caps (`max_puzzle_attempts_per_key` default 3).
- Store nothing extra; puzzle/identify JSON stores already exist. Stub adapter works for these kinds too.

**Done when**

- One text and one vision fixture complete a puzzle attempt via the client. Runner slot `kind: puzzles` can finish an attempt against the test app with the stub. Identify equivalent.

**Verify**

- Wrong move ends the attempt (today’s rule). Review JSON not used as a solving aid inside the adapter.

## Estimated duration

- Phase 1: 2–3.5 agent-hours
- Phase 2: 3–5 agent-hours
- Phase 3: 6–9 agent-hours (stub + OpenAI-shaped adapter + probe + scheduler)
- Phase 4: 2.5–4 agent-hours
