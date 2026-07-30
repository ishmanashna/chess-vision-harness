# Spectator polish, AvA same-model, contact inbox — plan

Playtest/UI pass: spectator list cleanup, Create Game tab leak, leaderboard/home chrome, spectator/play controls, allow AvA mirror matches, and a simple contact inbox.

Do not implement until this plan is accepted.

## Goals

1. Clean up idle-timeout / no-result games from the harness and metrics.
2. Shorten long engine names in spectator **lists** (game pages can keep full labels).
3. Compact date+time in spectator lists.
4. List result text: **Timeout** instead of “No result (idle timeout)”.
5. Mode badges (AvE / AvA / AvH) visually distinct (color-coded, standardized).
6. Acc. / Est. Elo cells: stop looking “half broken” when only one side has quality (thin / one-sided games).
7. Create Game: **Find match / Direct** (and AvA pairing chrome) only on Agent vs Agent — not on Agent vs Engine.
8. Home about copy: **same text color** for all paragraphs; user edits copy in `public-site/index.html`.
9. Leaderboard: Engines heading same visual size as Agents; explanatory copy on the **left**, tables on the **right**.
10. `/g/` spectator: remove “Spectating {id}” and the redundant outer “Game” title (info already in Game info).
11. Playground play: move **Cancel premoves** out of the Resign/draw row.
12. AvH spectator: move Show chat / Show game so toggling does not thrash layout.
13. AvA: **allow the same model vs itself** (two instances / two keys) — remove “must differ”; fix auth so sides are not collapsed to white.
14. Contact: public form (sender + message) writes to a project inbox folder; on **localhost**, Contact shows received messages.

## Architectural decisions (locked)

- **Timeout cleanup:** Run/extend `chess-harness prune-no-result` for finished `*` / `inactivity` games. Add **rebuild-elo** when pruned games had ladder deltas (or always rebuild after prune for safety). Also scrub orphan `results.jsonl` rows with no game dir.
- **List abbreviations:** List-only transform (JS and/or list API fields). Do not shorten `opponents.json` `display_name` used on game pages.
- **Half quality cells:** Prefer side-aware display: if only one of white/black has accuracy (or est Elo), show a single value (optionally with W/B hint), not `93% / —`. Do not invent black accuracy when black never moved.
- **Create pairing tabs leak:** Root cause is CSS `.mode-tabs { display: inline-flex }` overriding HTML `hidden`. Fix with `[hidden] { display: none !important }` (site-wide) and keep pairing UI gated to AvA only.
- **AvA same model:** Removing the reject alone is **not** enough. Today participant color is derived from `model_id` (white checked first), so two keys for the same model both resolve as white. Lock: bind each API key (or a side token) to **white or black** for that game; `participant_color` / join / move / brief use that binding. Lobby Find-match may still skip self-host by model id (open matchmaking); Direct explicitly allows same id with two keys.
- **Contact inbox:** Store under `.chess_harness/inbox/` (jsonl or one file per message). `POST` only on origin. Localhost Contact page shows inbox; Pages Contact shows the form (proxied to origin when Online, soft-fail when Sleeping). No email sending required.
- **Home copy file for humans:** Edit paragraphs in `public-site/index.html` inside `<section class="about-copy">`. Color fix is CSS only (`.lead` / `.about-copy .lead` → same as body secondary, or drop the override).

## Out of scope

- Changing idle timeout duration.
- Re-analysing every thin historical game for missing black accuracy.
- Email/SMTP delivery of contact messages.
- Renaming `/human/` URL.

---

## Phase 1 — Timeout purge + list result label

### Scope

- Operator: prune idle/no-result games (`prune-no-result`); harden to rebuild Elo after prune; handle orphan results rows.
- Spectator list: map inactivity / long no-result label → **Timeout**.

### Done when

Timeout games gone from Completed (and results/Elo consistent); list shows Timeout.

---

## Phase 2 — Spectator list density (names, dates, modes, quality cells)

### Scope

- Abbreviate long Stockfish/engine list names (e.g. strip redundant “Stockfish 17.1 ” prefix or use short noise/depth tags).
- Compact `formatWhen` (e.g. `16 Jul 17:31` / locale short without year if current year — pick one consistent compact form).
- Mode badges: distinct colors for AvE / AvA / AvH; keep accessible contrast in light/dark.
- Acc. / Est. Elo: single-sided display when the other side is null (no `x / —`).

### Done when

Completed/Active tables are readable; half-quality rows no longer look like a bug; modes are easy to tell apart.

---

## Phase 3 — Create Game AvA-only pairing chrome

### Scope

- Fix `hidden` vs `.mode-tabs` display so Find match / Direct only show for Agent vs Agent.
- Agent vs Engine heading stays “Rated game vs engine” without pairing tabs beside it.
- Smoke both modes (and offline banner still sane).

### Done when

Engine mode never shows Find match / Direct; AvA still has both paths.

---

## Phase 4 — Home color + Leaderboard layout

### Scope

- Home: unify about paragraph colors (opening lead same color as siblings). Copy stays in `public-site/index.html`.
- Leaderboard: Engines summary matches Agents `h2` size.
- Leaderboard layout: left column = Agents intro + How ratings work (and any short copy); right column = Agents table + Engines details/table. Responsive: stack on narrow screens.

### Done when

Home text is one tone; Leaderboard headings match; copy left / tables right on desktop.

---

## Phase 5 — Spectator `/g/` chrome + play/spectator controls

### Scope

- Remove `Spectating {gid}` line; remove or rename redundant outer “Game” so only Game info / Game state remain.
- Play: relocate Cancel premoves (e.g. under board or beside moves — not in Resign/draw row).
- AvH `/g/`: Show chat / Show game control placed so toggling does not change column height (reserve min-height or overlay chat; keep board/moves stable).

### Done when

`/g/` header is clean; cancel premove and chat toggle no longer fight the layout.

---

## Phase 6 — AvA same model vs itself

### Scope

- Remove “must differ” checks in API, core, and Create Direct UI; update tests that expected 400.
- Implement per-game **side binding** for keys (white key / black key), including when `white_model_id == black_model_id`.
- Dual briefs, joins, moves, and Elo finish still attribute the correct side.
- Direct UI allows picking the same model twice (two inscribed uses / two keys).
- Lobby Find-match: keep “don’t join your own waiting lobby” by host identity; Direct is the mirror path.

### Done when

Two agents with the same model id can play each other as white and black with correct turns, briefs, and results.

---

## Phase 7 — Contact form + localhost inbox

### Scope

- Contact form: sender (name or email) + message text; `POST` to origin; append under `.chess_harness/inbox/`.
- Rate-limit / basic validation; no secrets required.
- Localhost Contact (or a clear inbox section when Host is loopback): list messages so far.
- Pages: form UI; submit via proxy when Online; when Sleeping, show that messages need the game PC online (or keep GitHub Issues as fallback).
- Nav already has Contact; no new public tab required beyond localhost inbox behavior.

### Done when

A visitor can leave a message on the live site when the origin is up; you can read messages from the inbox folder / localhost Contact UI.

---

## Suggested order

1. Phase 1 — purge + Timeout label  
2. Phase 2 — list density / badges / quality cells  
3. Phase 3 — Create tab leak (small, high visibility)  
4. Phase 4 — home + leaderboard layout  
5. Phase 5 — `/g/` + play/chat controls  
6. Phase 6 — AvA same-model (largest; auth redesign)  
7. Phase 7 — contact inbox  

Phases 2–5 are mostly independent after Phase 1; Phase 6 should not overlap AvA auth files with Phase 3 Create UI in the same wave without care (Create UI touches both — sequence 3 then 6, or one agent owns create.js for both).

## Verify

- After prune, Completed has no idle Timeout pile (or only new ones); Elo/Games sane.  
- Long Stockfish labels shortened in list; dates compact; result says Timeout; modes colored.  
- One-sided quality shows one number, not `x / —`.  
- Create Engine mode: no Find match / Direct.  
- Home paragraphs same color; edit copy in `public-site/index.html`.  
- Leaderboard: Engines ≈ Agents heading size; copy left, tables right.  
- `/g/`: no Spectating line / duplicate Game title; chat toggle stable; Cancel premoves relocated.  
- AvA Direct: same model twice works end-to-end.  
- Contact message appears under `.chess_harness/inbox/` and on localhost Contact.

## Estimated duration

- Phase 1: 0.5–1.5 agent-hours  
- Phase 2: 1.5–2.5 agent-hours  
- Phase 3: 0.5–1 agent-hour  
- Phase 4: 1.5–2.5 agent-hours  
- Phase 5: 1–2 agent-hours  
- Phase 6: 3–5 agent-hours (side-bound auth)  
- Phase 7: 1.5–2.5 agent-hours  
