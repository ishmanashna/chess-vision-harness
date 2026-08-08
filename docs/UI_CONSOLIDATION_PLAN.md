# Plan: Consolidate the UI around one launcher and one leaderboard

## Problem summary

Feedback from a single manual pass. The navigation still exposes Playground and Puzzles as separate tabs even though the launcher now covers them; the launcher itself uses five tabs instead of two clear steps (pick mode, pick model); inscribing a model still requires two fields and the new model is not auto-selected; Home and the Leaderboard page aren't formatted correctly: columns should be split in the middle; the Leaderboard uses different modes instead of a unified table; the anchored engines are absent from the accuracy-based Performance calibration; and the copy is styled with bold text that should be plain and justified.

This plan consolidates everything into one launcher and one leaderboard and cleans up the copy. It is implementation, not a design study.

## Product decisions (locked)

1. **One launcher entry.** "Create Game" is the only launcher nav item, pointing at `/launch/`. Playground and Puzzles disappear as nav tabs; the legacy `/create/`, `/human/`, and `/puzzles/` launcher pages are decommissioned (301 → `/launch/?flow=...`) rather than kept as stacked duplicates.
2. **Two-step launcher.** The five inline flow tabs inside the launcher card become a single mode dropdown; the page then always asks exactly two questions: pick a mode, pick your model.
3. **One-field inscribe.** Inscribing needs a single field (display name); the model id is generated client-side (slug of the name + short random suffix), and the newly inscribed model is auto-selected in the model select.
4. **Middle split.** Home and Leaderboard body grids become equal columns (`1fr 1fr`) so the page splits in the middle; responsive collapse is unchanged.
5. **Unified Leaderboard.** The Agents / Puzzles / Board-identification tab modes are removed. One agents table carries game Elo/Accuracy/Play/Games plus the per-agent puzzle and identification stats (empty domains show `—`). The engines section and the puzzle-content table stay on the page. Puzzle + identification stats are merged server-side into the agent payload so Home and Leaderboard share one source of truth; the standalone identify snapshot + live endpoint are removed.
6. **Anchored engines in calibration.** The /calibration rating table (Elo, Games, Accuracy, Play rating) includes the Stockfish anchors again (fixed catalog Elo); they are read-only (no start/stop control), exactly like the rest of the ladder tables.
7. **Plain, justified copy.** Bold styling is removed from prose; descriptive copy is justified.

Out of scope: puzzle/identify data models, ratings math, API contracts (v1), engine pairing, calibration math, spectators, `/p/`/`/i/` watch pages, and the Home top-10 layout aside from the column split.

---

## Phase A — One launcher entry in the nav; decommission the three legacy launcher pages

**What:** The merged launcher already replaces `/create/`, `/human/`, and `/puzzles/`, but the header still lists Playground and Puzzles as separate tabs. Make "Create Game" the single launcher entry and remove the now-redundant legacy launcher pages entirely (replace, don't stack).

**Scope:**
1. Remove `<a id="nav-human">Playground</a>` and `<a id="nav-puzzles">Puzzles</a>` from every site header: the five surviving static pages (`public-site/{index,launch,spectator,leaderboard,contact}/index.html`) and `PUBLIC_SITE_HEADER` in `python/src/chess_harness/ladder_display.py` (covers `/g/`, `/p/`, `/i/`, `/play/`, `/calibration`). Keep exactly one launcher entry: `id="nav-create"` → `/launch/`.
2. `common.js`: drop the `"/human": "nav-human"` mapping from `setActiveNav()`; map `/play/` → `nav-create` (it currently lights `nav-human`). `/p/` + `/i/` keep pointing at `nav-spectator`.
3. **Origin redirects** (`spectator.py`): change the `create_game_get`, `local_human`, and `puzzles_page` routes to 301 redirects: `/create[/]` → `/launch/?flow=engine` (any `?mode=` variant included), `/human[/]` → `/launch/?flow=playground`, `/puzzles[/]` → `/launch/?flow=puzzles`. `POST /create` stays absent (405). Delete the `_public_site_html` calls for the three removed directories; the `/launch` route stays.
4. **Pages redirects** (`public-site/functions/_middleware.js`): replace `humanCreateRedirect` with a launcher redirect covering `/create[/]` (all modes), `/human[/]`, `/puzzles[/]` → the same 301 targets as the origin.
5. **Delete the legacy pages and their page-only scripts:** `public-site/create/index.html`, `public-site/human/index.html`, `public-site/puzzles/index.html`, and `public-site/js/create.js`, `public-site/js/create-human.js`, `public-site/js/puzzle-launcher.js`. Keep the shared helpers the launcher reuses (`create-result.js`, `create-match.js`, `create-human-wait.js`, `human-games-registry.js`, `common.js`, `launcher.js`).
6. **Repoint remaining links/copy:** Home about-copy links `/create/` and `/human/` → `/launch/?flow=engine` / `/launch/?flow=playground` (reword so Playground is described as a launcher flow, not a separate destination); `auth/callback.js` post-login location `"/create/"` → `"/launch/"`; `play_page.py` footer "Create another Playground game" href → `/launch/?flow=playground`.
7. **Docs accuracy** (small edits, kept to URLs/labels only): `README.md` route table, `DEPLOY.md` "origin serves" paragraph, `AGENTS.md` operator-flow line (`/create`), `PRODUCT.md` Playground line. No behavioral text changes.

**Tests:** `test_create_game.py` (and `test_puzzle_leaderboards.py`'s `data-lb-*` tab assertions) are rewritten: `/create`, `/human`, `/puzzles` assert 301 locations; deleted page files asserted absent.

**Done when:** no header anywhere shows Playground or Puzzles as a separate tab; "Create Game" is the only launcher entry and highlights on `/launch/`; `/create|/human|/puzzles` redirect to the matching launcher flow on both origin and Pages; the three legacy pages and their page scripts are gone with no dangling references; Home and play-page copy link to `/launch/...` only.

---

## Phase B — Launcher: mode dropdown + "Select your model" (two steps)

**What:** Replace the five inline mode tabs inside the launcher card with a dropdown so the user always takes exactly two steps: pick a game mode, then pick a model.

**Scope:**
1. In `public-site/launch/index.html`: replace the outer `.mode-tabs` five-button group with a `<select data-launch-mode>` listing Agent vs Engine, Agent vs Agent, Playground, Puzzles, Board identification. Keep the per-flow option blocks (AvA pairing tabs + Direct selects; Playground nickname) and the per-flow aside, shown/hidden by the selection.
2. In `public-site/js/launcher.js`: drive the flow from the select change event (instead of tab clicks) while keeping `setFlowId`, heading/card/submit-text/aside updates, the `?flow=` deep-link, validation, and all five submit handlers.
3. Rename the model field label from "Inscribed model" to "Select your model" (placeholder text too).
4. Update the launcher aside links that point at `/leaderboard/?tab=puzzles|identify` → `/leaderboard/` (tabs disappear in Phase D).

**Done when:** the launcher card offers exactly two steps: a mode dropdown, then "Select your model"; all five flows start correctly; `?flow=` deep-links still open the right mode; redirects from Phase A land on the correct flow.

---

## Phase C — One-field inscribe with auto-generated id and auto-select

**What:** Inscribing a model takes a single field (display name); the id is generated programmatically and the new model is automatically selected after inscribing.

**Scope:**
1. In the launcher's inscribe panel keep only the "Display name" field; remove the "New model id" input.
2. Client-side id generation in `launcher.js` `registerAgent`: slugify the display name (lowercase, spaces→hyphens, strip to `[a-z0-9_-]`, fallback `model` when empty) plus a short random suffix (6 lowercase/digit chars), guaranteed unique against the current inscribed list (re-roll on collision).
3. On success: reload agents and auto-select the newly inscribed model in "Select your model"; show the generated id in the success message so the operator can still reference it.
4. This is the only reachable inscribe UI after Phase A decommissions the legacy pages; backend `/api/v1/agents` is unchanged.
5. If the display name is empty, inscribe is rejected with a friendly message ("Enter a display name").

**Done when:** inscribing takes exactly one field; the generated id is always valid and unique; the new model is auto-selected and ready to submit; the flow works for every launcher mode.

**Verify:** browser smoke on `/launch/` for every flow; `node --check` on `launcher.js`.

---

## Phase D — One unified Leaderboard table

**What:** remove the Agents / Puzzles / Board-identification tab modes and show one unified agents table (game + puzzle + identification stats per agent), with the engines section and the puzzle-content table below. Merge the puzzle/identification data server-side so Home and Leaderboard share one payload.

**Scope:**
1. **Backend merge** (`snapshot_leaderboard.py` + `puzzle_leaderboard.py`): `build_snapshot` and `load_live_leaderboard` attach per-agent puzzle fields (`puzzle_rating`, `puzzle_deviation`, `puzzle_attempts`, `puzzle_solves`, `puzzle_solve_rate`) and identification fields (`identify_attempts`, `identify_mean_accuracy`, `identify_full_position_rate`) to each agent row, by merging `build_puzzle_leaderboard(...).agents` and `build_identify_leaderboard(...).agents` on model id (nulls when no activity). Add optional store params to `build_snapshot` so tests inject fixtures.
2. **Remove the standalone identification surface:** delete `/api/leaderboard/identify/live` + the `identify` cache kind and `/data/identify_leaderboard.json` route in `spectator.py`, `default_identify_leaderboard_path` + the identify member of `export_public_snapshots` in `snapshot_leaderboard.py`, and the committed `public-site/data/identify_leaderboard.json` file. The puzzle payload `/api/leaderboard/puzzles/live` + `/data/puzzles_leaderboard.json` stay — they feed the puzzle-content table.
3. **Leaderboard page** (`public-site/leaderboard/index.html`): delete the tab bar and `data-lb-panel` wrappers; render one agents table with columns `# Agent Elo Accuracy Play rating Games Puzzle rating Solve rate % pieces % boards` (tooltips explain each); the "How ratings work" copy explains that puzzles (Glicko-2) and identification (percentage metrics) are separate, ungame-related surfaces shown in the same table. The engines `<details class="engines-section" data-engines-leaderboard>` stays on the page. The puzzle-content table (`[data-puzzle-content-leaderboard]`) stays on the page (it is per-puzzle, not per-agent, data).
4. **Renderer** (`common.js` `renderLeaderboardRows` + `mountLeaderboardTable`): extend the unified columns for the leaderboard via a `showUnifiedStats` flag/attribute; declare the new sortable keys in `AGENT_NUMERIC_KEYS`; `—` when a stat is missing. Home keeps its current columns (only game stats, no model id) — one renderer, two column sets.
5. **`puzzle-leaderboards.js`**: delete the tab logic (`setTab`/`initialTab`/`data-launch-tab` wiring), the puzzle per-agent table mount, and the identify table mount; keep only the puzzle-content mount (same payload shape).
6. **Cross-links:** all `?tab=puzzles|identify` references (launcher aside, leaderboard copy) → plain `/leaderboard/`.
7. **Tests** (`test_puzzle_leaderboards.py`, `test_leaderboard*`): update assertions to the merged shape (agent rows carry `puzzle_*` / `identify_*`); replace the identify-endpoint assertions; keep puzzle-content assertions.

**Done when:** `/leaderboard/` shows one agents table with all per-agent numbers and no tabs; engines and puzzle content are on the same page; the unified payload serves both `/data/leaderboard.json` (snapshot) and `/api/leaderboard/live`; identify snapshot/endpoint removed with nothing left reading them; Home renders from the same payload; all tests pass.

---

## Phase E — Stockfish anchors in the calibration table

**What:** the anchored engines are missing from the accuracy/performance calibration table: `get_calibration_status` filters them out before enrichment.

**Scope:**
1. In `calibration_view.py::get_calibration_status`, stop stripping anchors from the rating table: `rating_table = mgr.enrich_rating_rows([r for r in rating_table if not r.get("anchor")])` → enrich the full rating table. `enrich_rating_rows` already tags anchor rows (`activity="anchor"`, `continuous=False`, `can_calibrate=False`), so the JS renders fixed Elo, `—` accuracy/play when unsampled, and no controls.
2. `ladder_display.py` calibration page JS: no functional change needed (it renders whatever rows arrive); add nothing for anchors; keep the "Play rating" tooltip text.
3. Tests (`test_calibration_view.py`): a status call now includes at least one `anchor: True` row with `activity == "anchor"`, `continuous is False`, `can_calibrate is False`.

**Done when:** opening /calibration shows Stockfish anchors in the "Calibrated ratings" table with their fixed Elo and, once games vs anchors are analysed, real Accuracy and Play-rating values.

---

## Phase F — Copy is plain and justified

**Goal:** remove bold emphasis from prose and justify explanatory copy.

**Scope:**
1. Strip `<strong>`/`<b>` from prose copy, keeping the text content identical: leaderboard intro + "How ratings work" + engine-section blurb (`leaderboard/index.html`), launcher aside/info blocks and heading summary (`launch/index.html`), Home about-copy if any remain, `ladder_display.py` calibration lead/legend, and the `puzzles=`-era copy kept via Phase D. Keep bold only where it's a UI element, not prose: buttons, table headers, `.empty-state`, status chips, banner titles, headline markers.
2. CSS (`public-site/css/site.css` + calibration `<style>` in `ladder_display.py`): `text-align: justify` for `.about-copy p`, `.leaderboard-copy p`, `.rating-explain p`, `.info-block p`, `.engines-section > p`, and the calibration `.cal-lead`/`.cal-legend`.
3. Home copy that uses *emphasis* on `sound` is kept as italics (it's not bold).

**Done when:** no prose paragraph anywhere uses bold; descriptive copy renders justified; buttons/table labels remain bold.

---

## Verification (all phases)

- Gates: full `pytest` suite, `scripts/check_line_limits.py` (no new files over 300), `node --check` on any touched/edited JS, `npm run lint`, `npm run typecheck`.
- Manual smoke: `/` (two equal columns), `/launch/` (mode select → model select, each of the 5 flows, inscribe + auto-select), `/leaderboard/` (no tabs; unified table; engines + puzzle content; `?tab=` links no longer referenced), `/calibration` (anchors present), `/create` `/human` `/puzzles` redirect, watch pages `/p/` and `/i/` render with the new header.
- Snapshot refresh: run `snapshot-leaderboard` so the unified snapshot (and deleted identify file) land in `public-site/data/`.
- Then commit + push (auto-deploy Pages) and redeploy the harness service, per DEPLOY.md.

## Out of scope

- No changes to the `/api/v1` contract, puzzle/identify stores, ratings math, or engine calibration math.
- No `?tab=` compatibility shims: the old deep links (e.g. `/leaderboard/?tab=puzzles`) land on the unified page.
- No changes to `/play/` gameplay, `/g/`, `/p/`, or `/i/` pages beyond the shared header.
- No new tabs in the launcher: the five flows remain, in a dropdown.

## Estimated duration

- Phase A — Nav + decommission legacy launcher pages + redirects + link repoints: 2–3 agent-hours
- Phase B — Launcher two-step (dropdown + label): 1–2 agent-hours
- Phase C — One-field inscribe + generated id + auto-select: 2–3 agent-hours
- Phase D — Merged leaderboard payload + unified table + endpoint removal: 4–6 agent-hours
- Phase E — Anchors in the calibration table: 1–2 agent-hours
- Phase F — Plain and justified copy: 1–2 agent-hours
- Verify + snapshot + deploy: 1–2 agent-hours