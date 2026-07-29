# AvH play polish, chat, and spectator density

Third-pass playtest: remove hub clutter, fix draw-after-move, make chat feel like a real chat (and make agents actually use it), restore AvH spectator eval, and tighten play + `/g/` layouts so blank space and awkward export chrome stop dominating.

Grounded in the live codebase after the AvH UX hub work. Prior “no eval for AvH” decision is **reversed** here for spectators only (games stays unranked).

## Product decisions (locked)

1. **Remove Your games from `/human/`** — Hub is create + waiting room + aside only. Resume stays on Spectator → **My games** (same `localStorage` registry). Delete the Your games card from `public-site/human/index.html` and stop mounting hub registry UI there; keep Spectator My games wiring. Update `PRODUCT.md` / `test_create_game.py` (hub test currently asserts “Your games”). Optional one-line aside: “Resume saved games in Spectator → My games.”

2. **Strip the long play disclaimer** — Remove the play-page footer wall (“30 minutes without a move… Illegal… Cheating…”). Keep a short idle / illegal-move note in the **Play vs Agent aside** and in the **agent brief** only. Do not paste that paragraph onto `/g/{id}`.

3. **Draw offer after you move** — Today `can_offer_draw` requires `your_turn`, so humans cannot offer after moving. Change to: `in_progress && !pending` (either side may offer anytime there is no pending offer). Accept/decline unchanged (only the other side). Offering on your own turn before moving stays allowed. Update AvH agent brief wording. Moving still clears a pending offer (already true).

4. **Bolder agent chat contract** — Rewrite AvH brief so chat is not “optional curiosity”:
   - On every status iteration: if `chat_seq` advanced, fetch and read new messages **before** deciding draw/move.
   - When `your_turn`: read chat (if any new), then board, then move; after a successful move, check status/chat again before sleeping.
   - While waiting for the human: you may send short chat (banter / “thinking”) whenever you want; still never treat chat as position info.
   - When `game_over`: **send one short chat message** acknowledging the result, then `GET` PGN.
   Keep status-first discovery (`chat_seq`); do not require blind chat polling every N seconds without seq advance.

5. **Minimal chat UI** — Replace boxed message chips with a normal minimal transcript: plain message rows (name + text), tall scroll area, compact composer. **Enter sends**; Shift+Enter inserts a newline if the control stays multiline, otherwise use a single-line input + Send. More vertical space for the log; less panel chrome / uppercase “CHAT” weight. Spellcheck stays off.

6. **Premoves must work** — Premoves already exist (`canPremove` when not your turn; fire on turn edge). Audit the input coordinator + premove path end-to-end and fix whatever still blocks queuing/firing (human can set a premove while waiting; it auto-submits when their turn arrives if still legal). Agent remains unaware of premoves.

7. **Download / export chrome** — On `/g/{id}`, remove the fat **Export** card. Put **Download board PNG** and **Copy PGN** as compact text links (e.g. under Game info or a thin actions row). On the interactive play page, keep Download in `.play-actions` with Resign/Draw (already there; visible when the game is over only).

8. **Play header → one line** — Collapse “Play board” / matchup / result-status into a **single** status line (matchup + Elo + your color + live result/turn). No stacked triplicate.

9. **AvH spectator eval restored** — Prior suppression was intentional (unranked); this plan **reverses it for spectators**. Flip `show_eval_for_state` and remove `/g/` JS hardcodes that hide eval (and the Evaluation row) when `game_type === 'human_vs_agent'`. Keep Elo-change empty/`—` (still unranked). Result / Termination stay. Update `test_spectator_human.py` which currently asserts `show_eval: False`.

10. **Tighter `/g/{id}` layout (all modes)** — Root cause: center track is `auto` while the board is capped (~600px) and centered, so leftover viewport width becomes empty gutters inside the middle column (all modes; layout lives in `spectator_game_page.py` inline CSS). Fix: center column `max-content` / `fit-content`, smaller `gap`, optionally center the whole `.layout` band; revisit `#board` `calc(100vw - 640px)` if side tracks change. Mobile stack unchanged in spirit.

## Scope

In scope: decisions above; hub cleanup; draw-after-move; brief chat rewrite; chat UI + Enter; premove fix; play header; play disclaimer; spectator export demotion; AvH eval on; `/g/` density for all modes.

Out of scope: WebSockets; LLM-backed auto-replies; human Elo; clocks; changing rated AvE vision redaction; removing Spectator My games.

## Architecture (imprinted)

**Draw flags:**

```text
can_offer_draw = in_progress && !draw_offer_pending
can_respond_draw = in_progress && pending && offered_by != you
```

**Chat brief priority (AvH):** status → draw → chat if seq advanced → if your_turn board/move → if waiting optional chat send → on game_over chat once then PGN.

**Eval:** `show_eval_for_state(state) → True` for all types including AvH; `/g/` JS trusts `show_eval` from API (no AvH special-case hide).

**Resume:** only Spectator My games mounts `human-games-ui` list; `/human/` does not.

## Phases

### Phase 1 — Hub + play chrome cleanup

Remove Your games from `/human/`. Strip long play-meta disclaimer. Collapse play header to one line. Confirm Download stays in play `.play-actions` (over-only).

**Done when:** `/human/` has no Your games card; play page shows one header line and a short meta line without the 30-minute essay; Spectator My games still resumes.

**Verify:** Open `/human/` and `/play/{id}` locally; Spectator My games still lists registry games.

### Phase 2 — Draw after move

Change `draw_offer_payload` / offer endpoint rules; enable Offer draw in the play UI whenever `can_offer_draw` is true off-turn; update AvH brief draw sentence; focused draw tests.

**Done when:** Human can move, then offer draw while waiting; agent can do the same per flags; accept/decline still work; move still clears pending offers.

**Verify:** Focused `test_human_vs_agent_draw` (+ any new off-turn case); manual one offer after a human move.

### Phase 3 — Chat UI + Enter-to-send

Restyle play chat to a minimal transcript + composer; Enter sends (Shift+Enter newline if multiline); more log height; less box chrome.

**Done when:** Chat looks like a normal minimal chat; Enter sends; spellcheck still off.

**Verify:** Visual `/play/{id}`; keyboard send; no regressions to polling.

### Phase 4 — Agent brief chat boldness + end-game message

Rewrite AvH `render_agent_brief_human` per decision 4 (before/after move, waiting banter, mandatory end-game chat). Align examples. Update `test_agent_brief` expectations.

**Done when:** New briefs contain the stronger chat duties and end-game chat; AvE/AvaA briefs unchanged.

**Verify:** Focused `test_agent_brief`.

### Phase 5 — Premoves actually work

Trace `syncInputState` → premove handler → `tryFirePremove` → POST move. Fix coordinator/premove bugs so a queued premove fires on turn edge without reload; clear quietly if illegal.

**Done when:** Human can queue a premove while waiting and it submits (or clears) when their turn arrives; no `moveInput already enabled` spam.

**Verify:** Manual white and black premove once each after an agent reply.

### Phase 6 — Spectator density + export demotion (all modes)

Tighten `/g/{id}` CSS grid/board sizing; demote Export card to compact links; keep Copy PGN working.

**Done when:** Desktop `/g/` no longer shows large empty gutters between columns; Download/Copy are compact; mobile still stacks.

**Verify:** Eyeball AvE and AvH `/g/{id}` at ~1280px and ~720px width.

### Phase 7 — AvH spectator eval + game state parity

Enable eval for AvH in `show_eval_for_state` and remove `/g/` JS hardcodes that hide eval for AvH. Confirm Result/Termination (and Elo change `—`) still render. Snapshot eval continues on AvH moves (already called in human move paths).

**Done when:** Finished and in-progress AvH `/g/{id}` show eval bar + Evaluation row like AvE; still unranked.

**Verify:** Focused spectator/human tests; open a finished AvH game on `/g/{id}`.

### Phase 8 — Hardening

Focused regression across hub, draw-off-turn, chat Enter, brief strings, premove smoke notes, `/g/` layout, AvH eval. Line-limit pass on touched files. Tiny PRODUCT one-liner if hub/resume wording needs it.

**Done when:** Smoke `/human/` → play (premove, chat Enter, draw after move) → `/g/` AvH with eval; Spectator My games resume; Create unchanged.

**Verify:** Focused pytest set; one manual local pass (Pages after deploy).

## Order

1 → 2 → 3 → 4 → 5 → 6 → 7 → 8  

Phases 3 and 4 may run as a wave after Phase 2 if needed; otherwise sequential. One implementation subagent per phase.

## Estimated duration

- Phase 1 — Hub + play chrome cleanup: 1–2 agent-hours
- Phase 2 — Draw after move: 1–2 agent-hours
- Phase 3 — Chat UI + Enter: 2–3 agent-hours
- Phase 4 — Agent brief chat boldness: 1–2 agent-hours
- Phase 5 — Premoves fix: 2–4 agent-hours
- Phase 6 — Spectator density + export: 2–3 agent-hours
- Phase 7 — AvH spectator eval: 1–2 agent-hours
- Phase 8 — Hardening: 1–2 agent-hours
