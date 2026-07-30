# Spectator lists, AvA matchmaking, cleanup — plan

Investigation findings and ordered work. Do not implement until this plan is accepted.

## Goals

1. Spectator Active/Completed lists show **per-game** Accuracy and Estimated Elo (not model averages).
2. Home mini-ladder has **no** explanatory note under the table.
3. Leaderboard tab has **one** place for rating explanations (no double body).
4. Human create: clear “creating” vs “created” messaging.
5. Idle / no-result (`*`) games: clean up old ones; stop counting them in Games / averages; show as “No result” in lists.
6. Fix AvA find-or-create: remove max-2 lobby cap; reattach instead of spawning orphan lobbies; clear sticky status; auto-open spectator on match.
7. Confirm AvA spectator quality matches AvE/AvH (mostly already shared UI — fix gaps that make it look incomplete).

---

## Phase 1 — Copy cleanup (small, no API)

### 1a. Home

In `public-site/index.html`, remove the entire `.home-ladder-note` paragraph (“Scale check… Hover column headers…”). Leaderboard section = heading + table + snapshot meta only. Keep column `title` tooltips if useful; no body text under Home Leaderboard.

Update `tests/test_leaderboard_polish_phase1.py` accordingly (drop assertions on 1500 / club player / scale note).

### 1b. Leaderboard tab — single explanation

Today: Agents intro paragraph **and** “How ratings work” both define Elo / Accuracy / Estimated Elo.

- Agents intro → one short line (e.g. inscribed vision agents; hover headers for column meanings; `*` = provisional).
- Keep **How ratings work** as the only full explanation (K-factor, anchors, Estimated Elo vs ladder Elo, Games = rated only).
- Optionally add the ~1500 club / chess.com scale sentence **once** inside How ratings work (not on Home).

### 1c. Human create dual messages

`human-hub.js` sets `"Creating game…"` on `[data-human-message]` and never clears it on success; `create-human.js` then shows `"Game created…"` in `[data-create-result]`.

- On success (before/after `showHumanResult`): clear `[data-human-message]`.
- Mirror for Create Game AvE/AvA: clear `[data-create-message]` when `showBriefResult` / match succeeds (fixes sticky `"Finding match…"` too).

**Done when:** Home has no ladder blurb; Leaderboard has one explanation body; create UIs show either pending or success, never both.

---

## Phase 2 — Spectator list: modern columns + per-game quality

### Column model (AvE / AvA / AvH)

Today’s table is AvE-shaped: **Agent / Elo / Opponent** with opponent Elo stuffed into the name (`"MiMo V2.5 Black (418)"`). That breaks AvA/AvH readability.

**Replace with side-based columns** (same for Active and Completed):

| Column | Content |
|--------|---------|
| Game | id link |
| Mode | AvE / AvA / AvH |
| White | display name (no Elo in the string) |
| White Elo | ladder Elo for white side (— if none, e.g. human) |
| Black | display name (no Elo in the string) |
| Black Elo | ladder Elo for black side |
| Acc. | per-game accuracy (see below) |
| Est. Elo | per-game Estimated Elo (see below) |
| Turn / result | turn label or result / “No result” |
| Updated | timestamp |

Drop standalone Agent / Opponent / single Elo columns.

**Accuracy / Estimated Elo cells**

| Mode | Acc. / Est. Elo |
|------|----------------|
| AvE / AvH | Agent side only (`agent_accuracy` / `agent_play_rating`), or White/Black pair if both analysed |
| AvA | Compact `W / B` using `white_*` / `black_*` |

Prefer showing **both sides** whenever `white_accuracy` / `black_accuracy` exist (covers all modes after quality). Fallback to agent-only fields mapped by `agent_color` for older AvE rows.

Strip Elo from opponent label strings in list enrichment / `normalizeGame` (names only in White/Black).

### Backend

`GET /api/games` `_enrich_list_game`:

- Include `white_display_name`, `black_display_name`, `white_elo`, `black_elo` for **all** modes (not only AvA).
- AvE: map agent/opponent onto white/black by `agent_color`.
- AvH: already has display names; human Elo stays null.
- `row.update(quality_fields_from_state(state, include_provisional=True))`.

### Frontend

`spectator/index.html` + `games-list.js` + CSS: new thead/colspan; `normalizeGame` maps white/black; no `(elo)` suffix in names.

**Done when:** Active/Completed show White/Black + separate Elo cols for all modes; Acc./Est. Elo per game; no Elo-in-name; tests cover enrichment + render shape.


---

## Phase 3 — No-result (`*`) games: display, counts, cleanup

### Meaning

`result: "*"` + `status: finished` + usually `end_reason: inactivity` = idle timeout / abandoned. Correctly appears under Completed today; UI shows raw `*`.

### Fixes

1. **Display:** List API / `games-list.js` — show `"No result"` or `end_reason_label` (e.g. idle timeout), never bare `*`.
2. **Games count:** `ResultsManager.count_by_model` currently counts `*` rows (skips AvH only). Skip `result == "*"` so Games matches “Elo-rated only” copy. Elo and accuracy aggregates already skip `*`.
3. **Cleanup CLI** (operator): e.g. `chess-harness prune-no-result` (or analyse-quality sibling):
   - Find finished games with `result == "*"` (and/or `end_reason == inactivity`).
   - `delete_game` + `ResultsManager.remove_game_results(game_id)`.
   - Re-export leaderboard snapshot.
4. Optional later: Completed filter “Hide no-result” or separate Abandoned view — not required for first pass.

**Done when:** Old `*` games removable in one command; Games counts exclude them; Spectator shows “No result”; regression tests for count filter.

---

## Phase 4 — AvA matchmaking (create flow)

### Root causes

| Symptom | Cause |
|---------|--------|
| Same model, second tab → max 2 / no join | Same model **cannot** join own lobby (`find_matchable` skips `host_model_id`). Second Find match **creates another waiting lobby**. Cap `MAX_LOBBIES_PER_MODEL = 2` (`lobby.py`, docs `agent-vs-agent.md`) then errors. |
| Host stuck waiting; joiner matched | Host can click Find match again while polling → orphan lobby L2; joiner matches oldest L1; host polls L2 forever. Submit re-enabled while waiting. |
| “Finding match…” after match | Status message never cleared on `showResult`. |
| No auto-redirect | AvA only links to `/g/{id}`; AvH auto-redirects to play — AvA never redirected. |

Direct `POST /games/agent-vs-agent` is API-only; Create Game uses `POST /api/v1/lobbies` only.

### Changes

1. **Remove `MAX_LOBBIES_PER_MODEL`** (user request). Rely on reattach + cancel + concurrent-game limits.
2. **Reattach:** `POST /lobbies` if this model already has a waiting lobby → return that lobby (`status: waiting`) instead of creating another.
3. **UI:** While waiting, keep Find match disabled (or Cancel lobby explicit); cancel previous lobby before creating a new one if user insists.
4. **On match:** Clear status message; **`location.assign('/g/' + gameId)`** (or strong primary “Open spectator” that auto-navigates). Still show brief for the agent that needs it — prefer redirect after brief is on screen, or open spectator in same tab with brief copyable above (product choice: redirect joiner+host to `/g/` once matched; brief remains on Create result until they leave, or brief on a one-shot toast — default: clear messages + auto-redirect to spectator like a finished match page, keep brief on Create result if they use Back).
   - Practical default: on match, clear sticky text, show result panel with brief + **immediately** `location.assign('/g/'+id)` after a short beat **or** redirect with `?brief=1` — simplest: redirect both sides to `/g/{id}` and keep agent brief available via Create result only if they don’t redirect. Prefer: **auto-redirect to spectator**; agent brief stays copyable on the Create result page if we **don’t** redirect the tab that still needs to paste the brief.
   - **Decision:** Host waiting for opponent still needs their brief when matched (they already got it at create). Joiner gets brief at match. Auto-redirect **both** to `/g/{id}` after match; brief was already shown/copied from the result panel — if redirect is instant, show result 1–2s or open spectator and leave brief in sessionStorage. **Simplest accepted approach:** clear “Finding/Waiting…”, show Matched + brief + spectate, and **auto-redirect to `/g/{id}` after ~1.5s** (cancellable by clicking the link early).
5. Poll: retry transient errors; file lock on `LobbyStore` read-modify-write.
6. Docs: update `docs/roadmap/agent-vs-agent.md` — drop max-2 rule; document reattach.

**Done when:** Two different models match; both leave waiting/finding chrome; both land on spectator; same model second tab reattaches instead of erroring; no max-2 string left in code.

---

## Phase 5 — AvA spectator quality parity

Shared `/g/` UI already groups white/black Accuracy + Estimated Elo for all modes. AvA writes `white_*` / `black_*` via `quality_finish` (no `agent_*`).

Gaps that look like “AvA spectator outdated”:

1. List columns (Phase 2) currently hide quality entirely — do Phase 2.
2. Idle `*` AvA never gets quality (by design) — Phase 3 labeling.
3. Cold accuracy→Elo map → accuracy shown, Est. Elo `—`.
4. Poll stops before `quality_at` → keep polling or show “Analysing…”.
5. Backfill: `chess-harness analyse-quality` for finished AvA missing `quality_at`.

No separate AvA spectator page — harden shared path + list enrichment.

**Done when:** Finished scored AvA games show the same Game state quality block as AvE; list columns populated when state has metrics.

---

## Out of scope

- Allowing same model to play itself (engine rule forbids; keep).
- Changing idle timeout length.
- Full `harness reset`.
- Changing how model-average Accuracy/Est. Elo are computed on the leaderboard (except excluding `*` from Games count).

---

## Suggested order

1. Phase 1 (copy + create message) — quick UX wins  
2. Phase 4 (AvA matchmaking) — broken product path  
3. Phase 3 (no-result cleanup + Games count) — data integrity  
4. Phase 2 (modern White/Black columns + Acc./Est. Elo) — Spectator table  
5. Phase 5 (AvA quality polish / Analysing…) — residual

## Verify

- Home: no ladder note; Leaderboard: one explanation section.  
- Human create: only “Game created…” after success.  
- AvA: model A waits → model B finds → both redirect to `/g/`; same model reattach; no max-2.  
- Spectator lists: White / White Elo / Black / Black Elo / Acc. / Est. Elo; `*` → No result; Games on leaderboard ignore `*`.  
- Prune CLI removes sample idle games and snapshot Games drop accordingly.  
- Finished AvA `/g/` shows white/black accuracy + est Elo after analysis.

## Estimated duration

- Phase 1: 0.5–1 agent-hour (copy + clear pending messages)
- Phase 4: 1.5–2.5 agent-hours (lobby reattach, remove max-2, poll/redirect UX)
- Phase 3: 1–1.5 agent-hours (display, Games count, prune CLI)
- Phase 2: 1.5–2.5 agent-hours (list API enrichment + modern columns + Acc./Est. Elo)
- Phase 5: 0.5–1 agent-hour (Analysing… / poll polish on shared `/g/`)
