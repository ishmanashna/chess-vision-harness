# Leaderboard labels, engine columns, live Estimated Elo, spectator polish

Fix localhost leaderboard/engine display bugs, rename Estimated Elo for visitors, keep Estimated Elo in sync with the accuracy→Elo table, show mid-game quality while spectating, and fix unfinished-game formatting.

## Product decisions (locked)

1. **Label: “Estimated Elo”** — Replace user-visible “Est. Elo (play)” everywhere (leaderboard, home, calibration, spectator). Hover/title explains briefly: estimated strength from move accuracy via the calibration accuracy→Elo table; not ladder Elo.

2. **Visitor copy** — Leaderboard “How ratings work” must not tell visitors to rebuild tables on Calibration. Operator-only mechanics stay on `/calibration`.

3. **Home mini-ladder** — Agents table includes Accuracy and Estimated Elo (same meanings as full leaderboard). Short note comparing ladder scale to typical human/club Elo (about 1400–1600 for an average club player; beginners lower, masters much higher). Online platform ratings differ — keep the note honest and short.

4. **Engine table columns** — Fix misaligned Kind/Accuracy (Kind text must not appear under Accuracy). Floaters with samples show Accuracy + Estimated Elo; anchors show Kind=Anchor and — until sampled. Keep Engines collapsed by default; floaters first.

5. **Estimated Elo follows the current map** — Leaderboard agent Estimated Elo is derived from stored **accuracy** through the **current** `accuracy_elo_map.json` at snapshot/live build time — not a frozen average of old `play_rating` fields. Rebuilding the map changes Estimated Elo without re-analysing every game.

6. **Spectator mid-game quality** — While spectating an in-progress game, Accuracy and Estimated Elo update as moves are played (best-effort async analysis of the game so far), not only after the game ends. Finished games keep end-of-game values. Agent `/api/v1` may continue to omit mid-game quality if that would leak eval; spectator UI is the requirement.

7. **Unfinished / inconclusive spectator formatting** — Long termination / Elo-change strings must wrap normally as words, never stack one character per line.

8. **Deleted draw test game** — Ensure `game-6048-2093` is fully gone from results, game dir, and any public lists. AvH games do not count toward ladder Games/Elo; if the user still sees an unchanged Games count, that is expected for AvH — confirm and clean any leftover listing.

## Scope

In scope: public-site leaderboard/home/engines JS+HTML+CSS; results aggregation Estimated Elo from live map; spectator page CSS + mid-game quality scheduling; rename strings; focused tests; ship (commit/push/deploy/restart).

Out of scope: Changing ladder Elo math; bringing Calibration to Pages; forcing a full continuous sample rebuild in CI.

## Phases

### Phase 1 — Engine column bug + Estimated Elo rename (UI)

Root-cause fix for Kind appearing under Accuracy (stale/4-column render vs 6-column headers; cache-bust `engines.js`; avoid double-mount races). Rename to Estimated Elo with title tooltips. Rewrite leaderboard visitor blurb; engines blurb without operator rebuild instructions. Home mini-ladder: add Accuracy + Estimated Elo columns and human Elo note.

**Done when:** Localhost Engines expanded shows floaters with numeric Accuracy and Estimated Elo in the correct columns; Kind only in Kind; agents/home use “Estimated Elo”.

**Verify:** Eyeball `/leaderboard/` and `/`; focused string/HTML asserts.

### Phase 2 — Live map for agent Estimated Elo

In `aggregate_quality_by_model` / snapshot build, set `mean_play_rating` from mean (or per-row) accuracy via `est_elo_from_accuracy` using the current map. Stored `play_rating` on results rows may remain for history but must not freeze the ladder display.

**Done when:** Rebuilding the accuracy→Elo map changes agent Estimated Elo on the next live leaderboard load without `--force` re-analyse.

**Verify:** Unit test with mocked map + accuracy-only rows.

### Phase 3 — Spectator mid-game quality + unfinished formatting

Schedule lightweight quality analysis as moves accrue (reuse analyse path; debounced / async so serve stays responsive). Spectator shows quality rows during in-progress games when provisional metrics exist. Fix `.meta-grid dd` wrapping so “No result (idle timeout)” and “No ELO change recorded yet” display as normal wrapped sentences.

**Done when:** Spectating an in-progress game updates Accuracy/Estimated Elo after moves; old inconclusive games no longer show vertical letter salad.

**Verify:** CSS/HTML assert on word-break; focused JS/HTML checks for quality rows not limited to `game_over` only.

### Phase 4 — Draw-game leftovers audit

Confirm `game-6048-2093` absent from results and game storage; remove from any list APIs if still present. Document in done-when that AvH does not affect Games/Elo columns.

**Done when:** No traces of that game id in harness results/games listing.

## Estimated duration

- Phase 1 — Engine columns + rename + home/copy: 1.5–3 agent-hours
- Phase 2 — Live map Estimated Elo for agents: 1–2 agent-hours
- Phase 3 — Mid-game spectator quality + formatting: 2–4 agent-hours
- Phase 4 — Draw leftover audit: 0.5–1 agent-hours
