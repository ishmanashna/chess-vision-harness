# Agent-created games, agent puzzles, board identification, and spectator viewing

## Goal

Add four focused agent capabilities while preserving the harness's existing game pathways and vision contract:

1. Let an agent create another normal game after finishing a game, receive a new brief, and continue — **but only after an explicit approval signal from the person or parent runtime. Agents must never autonomously start follow-up games or chain games on their own.**
2. Let a parent agent create games for subagents, including parent-vs-subagent and subagent-vs-subagent AvA, with every participant receiving the correct role brief and all play continuing through the normal web API.
3. Add an unlimited Lichess-style puzzle area for agents with a separate puzzle rating, puzzle difficulty rating, dedicated leaderboard, and public watching/replay.
4. Add an image-first board-identification mode in which an agent receives a board PNG and submits where every piece is located, with no moves, plus a separate identification leaderboard and public watching/replay.

These systems remain separate from game Elo, game Play rating, human browser credentials, and each other.

## Shared product decisions

- Existing game endpoints and `GameService` remain authoritative for all games.
- Agents remain primarily game players. A normal game brief must not silently authorize or trigger a new game.
- Follow-up games and parent orchestration require an explicit approval action from the person or parent runtime. Approval may be a deliberate UI/API action or a parent-issued task instruction, but it must be represented as an explicit opt-in rather than inferred from game completion.
- The harness creates games and task envelopes; it does not launch models or subagents itself. The parent runtime is responsible for actually prompting or running subagents.
- Parent-created child tasks use game-scoped credentials, not reusable parent API keys embedded in every child brief.
- Participants receive only their own role brief by default. Parents receive orchestration status without unnecessary child secrets.
- Puzzle attempts are unlimited. Puzzle matchmaking is out of scope for the first release.
- Board-identification attempts are unlimited. They are not games, do not create PGNs, do not affect game Elo, and do not use puzzle or game ratings.
- All agent-facing image modes are image-first. The existing sanctioned text board fallback may be used only when the PNG cannot be fetched or read.
- Agents solving puzzles or identifying positions are publicly watchable while they are active, and replayable after completion. Observers never see hidden solutions or answer keys before the attempt is complete.

**Order:** 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10, one implementation phase per subagent, run sequentially. Leaderboard loading is a separate plan.

## Phase 1 — Approved agent follow-up game creation

1. Add an explicit approval-gated follow-up creation path accepting the existing engine-game options and an optional previous-game reference for history only.
2. Completion of a game may expose a "request another game" capability, but it must not create anything until the person or parent runtime approves it.
3. Create the new engine game through `GameService.new_game()` and normal `BoardController` rules.
4. Return the normal sanitized creation payload plus `render_agent_brief()`.
5. Permit approved calls only after a finished game and enforce the existing rate, concurrency, model, opponent, and no-custom-FEN rules.
6. Keep normal game briefs focused on playing; add follow-up instructions only as an explicit, approval-dependent option, not as an automatic loop.
7. The approval gate applies to this new follow-up endpoint; the existing `POST /api/v1/games` path stays approval-free by design.

**Done when:** an agent can finish a game, receive explicit approval, request another game, get a new ID and brief, and continue through the normal board/status/move/PGN flow; without approval no new game is created.

## Phase 2 — Parent orchestration: approval core and scoped credentials

1. Add a parent orchestration creation path supporting: parent/self vs engine; child vs engine; parent vs child AvA; child vs child AvA.
2. Require an explicit parent approval/launch action before each orchestrated game is created. Drafting a task or preparing briefs must not start a game by itself.
3. Reuse the direct-AvA building blocks: side assignment, key binding, `GameService`, and the existing brief generators (`render_agent_brief_avaa` inputs match the task envelope). The parent authorization rule itself is new — a parent is not a participant, so the direct-AvA `auth.model_id in (white_id, black_id)` check cannot be reused; add an explicit parent-approval check without duplicating game mutation logic.
4. Track a lightweight orchestration record with parent, game, task IDs, participants, colors, mode, approval state, task status, timestamps, and result reference.
5. Add a side-scoped child credential store (separate from the permanent, model-scoped `ApiKeyStore`): each credential binds `game_id`, side, `model_id`, expiries at game end (with operator TTL cap), and grants an enumerated subscope — `status | board | board.txt | move | resign | pgn`. Route-level enforcement lives in a new participant-auth module that asserts the action is inside `game_id` and the credential's scopes before any `GameService` call. Keys are minted *before* the game is created because side keys are bound at game creation.
6. Compose the new machinery (scoped credentials, orchestration record, participant auth, brief assembly) into separate modules respecting ARCHITECTURE's per-file line limit.

**Done when:** an explicitly approved parent can start an orchestrated game through the new path, side creds are minted before creation, and any non-scoped call is rejected.

## Phase 3 — Parent orchestration: envelopes, lobby, and MCP

1. Return a structured task envelope containing role, game ID, API base, scoped credential, opponent label, and the existing mode-specific prompt.
2. Add parent status reporting approval, task creation, brief availability, joining, turn/game state, finish, and failure without exposing child secrets. Reuse `white_joined`/`black_joined` for the joining state.
3. Bind every participant call through the existing participant authorization and `GameService` pathways.
4. Keep lobby matchmaking out of parent orchestration for the first release: orchestrated AvA is always an explicit two-sided game with side-bound credentials, not a lobby join. (This avoids competing with lobby ownership guarantees.)
5. Fix the lobby race as an atomic claim: seize the lobby under the store lock *before* game creation, and delete the game left behind if the claim loses a concurrent race. Today the loser's orphan is permanent — awaiting-join AvA games are exempt from idle pruning and hold a concurrency slot indefinitely.
6. No MCP parity in the first release; parent-agent operation is HTTP-only until the path is stable.

**Done when:** an approved parent can hand one task envelope per side, both sides play (AvA or vs the parent) through the normal API, each side gets the correct brief and cannot use the other side's credential, and no game begins from a passive completion event.

## Phase 4 — Puzzle content import and storage

1. Add a puzzle content store separate from live games and finished-game history.
2. Import the official Lichess standard puzzle CSV fields: `PuzzleId`, `FEN`, `Moves`, `Rating`, `RatingDeviation`, `Popularity`, `NbPlays`, `Themes`, `GameUrl`, `OpeningTags`, `DailyDate`.
3. Preserve the Lichess convention: stored FEN is before the opponent setup move; display the position after applying the first move; the solution starts with the second move.
4. Validate legal lines, IDs, ratings, duplicates, and standard-chess positions before publication.
5. Store at runtime under `$CHESS_HARNESS_DIR/puzzles/` (outside git), as an indexed subset or small indexed dataset; never commit puzzle rows to the repository — only the content manifest is committed.
6. Store dataset version, source URL, import timestamp, row count, and CC0 license in a content manifest.
7. Provide idempotent, repeatable import/update without rewriting attempt history.
8. Split import, validation, and store access into separate modules respecting the per-file line limit; the puzzle store stays distinct from live games and finished-game history.

**Done when:** the same puzzle ID produces the same valid hidden-solution position after restart or re-import.

## Phase 5 — Agent puzzle solving flow

1. Add a dedicated authenticated puzzle API under `/api/v1/puzzles/*` (already proxied): select/start, board PNG, text-fallback, submit move, abandon, review. No unauth puzzle API paths in this phase.
2. Do not expose FEN, solution moves, legal-move lists, or hidden puzzle metadata before completion.
3. Apply the imported puzzle line as the authoritative opponent continuation. Failure behavior is fixed: an illegal or wrong move ends the attempt immediately as failed (a Glicko loss for the attempt); no retry within one attempt; the same puzzle is excluded from immediate re-selection in the same session.
4. Return a puzzle brief explaining selection, board retrieval, fallback use, move submission, hidden solutions, unlimited attempts, and the separate puzzle rating.
5. Support only these filters: a random eligible puzzle; optional importing rating band; optional theme; avoid recently attempted puzzles.
6. Unlock review data only after completion: outcome, rating change, themes, source link, solution line.
7. Puzzle attempts are not games: exclude them from per-key game and move caps (or use dedicated operator-tunable attempt caps). "Unlimited" means no rating cap, not unbounded concurrency or an Elo-farm vector.

**Done when:** agents solve unlimited puzzles through the image-first HTTP contract and can review solutions only after the attempt ends.

## Phase 6 — Public puzzle watching and replay

1. Give every attempt a public watch ID and a read-only spectator cover page (e.g. `/p/`), separate from authenticated agent endpoints.
2. Observer-safe live state exposes only attempt ID, agent display name, imported difficulty and safe themes, the current visible board, submitted-move count and progress, and the outcome state (thinking, correct continuation, failed, finished).
3. Never expose the solution, hidden FEN, unrevealed continuation, or correctness details that would help an observer solve the active attempt.
4. After the attempt ends, unlock a replay/review containing the puzzle setup and solution line, the agent's submitted line, first wrong move, final result, rating changes, source-link, and themes.
5. Reuse spectator conventions for the page shell, read-only polling, board PNG rendering, and completed-history listing. Do not reuse the game move replay: puzzles have no PGN, and the move-detail renderer leaks the solution by construction — the rejection is precisely the existing finished-game PGN 403 gate, extended to live puzzle secrecy. The live observer board must come from a restricted answer-safe path without move detail; this is new observer behavior.
6. Add a public section with active attempts, completed replays, minimal filtering for replay discovery only, and the puzzle leaderboard (referenced from Phase 9). Keep it observer-scoped; a full browse product is out of scope.
7. Keep observer page events without an agent API key, but never let observer endpoints mutate attempts or reveal hidden active answers.
8. Route the surface explicitly: add `/p/` watch prefix, puzzle browse/replay paths, and the live leaderboard route to `shouldProxyPath` in `public-site/functions/_proxy.js`; extend the nav map in `public-site/js/common.js`.

**Done when:** a visitor can watch an agent solve live (plate, board, progress only) and later replay it with the solution revealed only after completion.

## Phase 7 — Board-identification mode

1. Add a dedicated authenticated API under `/api/v1/identify/` (covered by the proxy): start/select, board PNG, text fallback, submit, score, finish/review. Authenticated, separate from games and puzzles.
2. Images follow the game agent surface exactly: absolute coordinate with white at the bottom, no flip by identity.
3. Do not provide the FEN, board text, legal moves, history, or answer-bearing metadata before submission. The text fallback is only the same recovery path as web board images; it must not mount a machine-readable answer beyond the visible board.
4. Answer format is fixed and deterministic: a compact mapping with only occupied pieces:
   `{"pieces": {"a1": "wR", "e8": "bK", ...}}`
   Keys are absolute squares; values are `w`/`b` + piece letter (`K Q R B N P`). Any other square absence is significant. Validate the schema exactly (legal square, legal piece code, no duplicates).
5. Score by exact placement: total correct pieces; per-piece correct square/color/type; missing, extra, misidentified; an overall full-position-accuracy flag.
6. Independent from game and puzzle ratings: expose mean placement accuracy and completed-attempt stats on a dedicated leaderboard; defer an Elo-like identification rating until enough data exists.
7. Support unlimited attempts from a controlled corpus (validated puzzle positions or sampled game positions). Position provenance and difficulty are operator-visible only and hidden until submission; attempts live in their own store and never count as puzzle solves.
8. Provide a brief stating the task (identify only), the answer schema above, PNG-first, and a hard "no moves" rule.
9. Public watch/replay parallels the puzzle pattern, under a proxied prefix (e.g. `/i/`): live observer sees the board, name, progress, and score state but not the true placement; replay reveals the submitted vs correct placement and per-piece errors.

**Done when:** an agent can get unlimited identification positions, read each image through the normal web flow, submit a placement answer without moves, score by placement, and it's independently watchable/replayable.

## Phase 8 — Puzzle ratings: Glicko-2 and attempt persistence

1. Keep puzzle ratings out of the single `elo` field. Store per-agent puzzle rating in its own store (e.g. `$CHESS_HARNESS_DIR/puzzle_ratings.json`, keyed by agent id); `inscribe`/`reset_all_elo` never touch it.
2. Store puzzle difficulty in the puzzle store itself, initialized from imported `Rating`/`deviation`.
3. Attempt → rating outcome: correct-and-finished = agent win; wrong answer = puzzle win; abandon/technical failure = no rating unless the failure mode previously said answer-failure.
4. Implement a Glicko-2-style system (greenfield; no existing code) matching Lichess's documented approach, retaining rating deviation and uncertainty. Split math and persistence into separate ≤300-line files; both stay out of the Elo ladder.
5. Update both agent and puzzle ratings from attempts; imported values are only starting estimates.
6. Persist each attempt with agent, puzzle, submitted moves, outcome, ratings/deviation before/after, timing it available, content version, timestamps.

**Done when:** puzzle ratings and puzzle difficulty change reproducibly from attempts, and are readable/replayable, with no regress to game ratings.

## Phase 9 — Puzzle and identification leaderboard views

1. Add Puzzle and Board-identification tabs/views in the main leaderboard area, visibly distinct from game Elo/Play/Accuracy columns. The `/leaderboard/` page has no tab state and its renderer hardcodes the Elo/Accuracy/Play/Games columns — the new tables need their own render, sort keys, and payload fields, not reuse of the helpers.
2. The Puzzle tab shows puzzle rating, attempts, solves, solve rate, and deviation.
3. The Board-identification tab shows mean placement accuracy, attempts, full-position rate; later confidence/deviation once an identification rating exists.
4. Puzzle content views (difficulty, solve rate, themes, popularity, source) visible in the Puzzle tab in a replay/observer scope.
5. No puzzle matchmaking; a requested rating band is a selection filter only.
6. Give both new snapshots the same refresh + publish path as `leaderboard.json` (origin background refresh and committed file), as part of this phase.

**Done when:** each tab is visibly separate, correct, refreshable, and independent from game standings.

## Phase 10 — Verification and rollout

- Games: verify approval-gate behavior, parent-vs-child and child-vs-child AvA, scoped-credential rejection on every unconfigured route, brief correctness, reconnect/status, atomic lobby claim (no orphan), unchanged Elo/results accounting.
- Puzzles: verify import legality, manifest, hidden solutions, correct/wrong continuation per this plan, unlimited attempts, attempt persistence (never in `results.jsonl`), Glicko replay outputs reproducibility, puzzle difficulty updates, public watch answer-safe board, completed replay, observer secrecy, dedicated Puzzle leaderboard, and routing for `/p/` and the live route.
- Identification: PNG first, fallback, schema validation, exact scoring, no move route, unlimited attempts, provenance privacy, watch/replay, dedicated identify leaderboard, routing for `/i/`.
- Non-regression: no passive finish event creates a follow-up; game Elo/Play untouched; full unit suite + frontend types/lint + smoke, online and offline Pages.
- Run tests on both timeouts (need smoke runs).

## Out of scope

- No daily challenge, streak campaign, puzzle races, social challenges, authoring, voting, or puzzle matchmaking.
- No automatic model/subagent launching by the harness.
- No custom agent-authored puzzle positions in the first release.
- No variants other than standard chess.
- No changes to game Elo, game Play rating, or the existing human browser flow.
- Leaderboard loading performance is covered by a separate plan.

## External source basis

The puzzle import follows the official Lichess open database documentation. The standard puzzle CSV is CC0 and includes `PuzzleId,FEN,Moves,Rating,RatingDeviation,Popularity,NbPlays,Themes,GameUrl,OpeningTags,DailyDate`. Lichess documents the setup-move convention and that puzzle attempts are rated as Glicko-2 games between the player and the puzzle.

Sources:

- [Lichess open database](https://database.lichess.org/)
- [Lichess: New Puzzles are here!](https://lichess.org/@/lichess/blog/new-puzzles-are-here/X-S6gRUA)

## Estimated duration

- Phase 1 — Approved follow-up creation: 1–2 agent-hours
- Phase 2 — Scoped-credential core: 3–5 agent-hours
- Phase 3 — Envelopes, lobby fix: 2–4 agent-hours
- Phase 4 — Puzzle import + store: 2–4 agent-hours
- Phase 5 — Agent puzzle flow: 3–5 agent-hours
- Phase 6 — Public puzzle watching: 3–5 agent-hours
- Phase 7 — Board-identification mode: 3–5 agent-hours
- Phase 8 — Glicko-2 ratings: 3–5 agent-hours
- Phase 9 — Puzzle/board leaderboards: 2–4 agent-hours
- Phase 10 — Verification + rolling: 2–3 agent-hours