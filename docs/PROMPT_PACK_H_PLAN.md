# Prompt pack H — non-vision (text-only board)

## Goal
Add pack **H** so we can A/B F / G / H in one CLI wave. H is baseline turn loop with **no board PNG**: position comes only from authenticated `board.txt` (CLI: whatever command reprints the text grid / path — prefer the existing harness board.txt channel). Answers OPENQUESTIONS #5.

## Locks
- Overlay pack `h`, title `H Text` (or `H Non-vision`).
- Same opponent default as F/G: `inverse-sf:exclude-top1-d8` unless overridden.
- Off Elo / public ladder / git sqlite (same as other prompt-test packs).
- **No** `legal`, **no** `imagine`. Same bans as A for engines/state.json/FEN/spectator.
- F and G stay image-first (unchanged).
- Do **not** git commit or push.
- Keep files under ~300 lines; surgical edits.

## Work

### 1. Pack files
- `config/prompt_packs/index.json`: add `"h": { "title": "H Text", "kind": "overlay", "rules": "_rules_h.txt" }` (or embed observation in meta if you add a field — see below).
- `config/prompt_packs/_rules_h.txt`: text-first rules. Position source is board.txt only. Ban fetching/reading the PNG. Ban legal/imagine/engines/state/FEN. Keep continue-until-done + idle 30m language like `_rules.txt`.
- `config/prompt_packs/h.txt`: turn loop:
  1. Read board.txt for this game (not PNG; not a cached copy).
  2. `chess-harness move {game_id} <move>`
- Placeholders `{game_id}`, `{board_path}`, `{model_id}`, `{prompt_pack}` as other packs.

### 2. Game observation = text for pack H
Prompt-test games currently inherit observation from the inscribed model (usually vision). For H, the **game state** must snapshot `observation: "text"` so Ops/results mark `[text]` and API briefs stay consistent.

Thread an optional `observation` (or derive from pack id `h`) through:
- `cmd_prompt_test_start` → `cmd_new` → `game_service.new_game` → `board_controller.new_game`
so pack `h` creates with `observation="text"` **without** requiring a separate inscribed model id.

Prefer: pack meta `"observation": "text"` in index.json, read in `load_pack` / start path. Default vision for a–g.

### 3. Overlay brief for H
`render_overlay_brief` for H must not tell the seat to read the PNG. Using `_rules_h.txt` + `h.txt` is enough if rules/body never mention PNG. If `{board_path}` still points at PNG, either:
- also pass `{board_txt_path}` / instruct `chess-harness board` / document the board.txt path next to the game, **or**
- change the H brief to use the authenticated board.txt URL / CLI that returns the text grid.

Inspect existing text brief helpers (`agent_brief_text.py`, `agent_board_text.py`) and reuse patterns. Do not break vision packs.

### 4. Docs
- Update `experiments/prompt-packs/README.md`: row H; how to `start --packs f,g,h`; note A–D still paused; wave policy: CLI seats, prefer wave size 3 (one of each), stack waves rather than 9-wide by default.
- Short delta in `docs/PROMPT_TEST_PLAN.md` if it lists packs.
- Optional: `docs/PROMPT_PACK_H_PLAN.md` can stay as the ticket; mark Done when when finished.

### 5. Smoke (required)
From `python/` with harness up:
```
python -m chess_harness prompt-test start --model <inscribed-id> --packs f,g,h --opponent inverse-sf:exclude-top1-d8
```
Then:
- `legal` on F game → ok
- `imagine …` on G → ok  
- `legal` / `imagine` on H → reject
- Confirm H game state (or results foreshadow) has observation text; brief text forbids PNG
- Resign all three smoke games

Use a real inscribed model id already on this machine (composer-2.5 or whatever `models list` shows).

### 6. Wave launcher (prep, do not start scored wave)
Add `experiments/prompt-packs/run-fgh-cli-wave.ps1` (or similar) that:
- starts `prompt-test start --packs f,g,h`
- writes each brief to a run folder
- launches 3 Cursor CLI `agent -p --trust` seats (one per game) with `--worktree` isolation (same lesson as load-and-burn: not `--workspace` on live repo)
- continue-until-game-over language in the outer prompt
- default Seats=3 (one triad); optional `-Waves N` to stack sequential triads (not 9 concurrent unless `-ParallelTriads` explicitly set)
- Do **not** auto-start a scored wave in this task — script ready only.

## Done when
- `f,g,h` start works; H is text-only; F/G unchanged
- Smoke commands run once on this PC; output pasted in the seat report
- README updated; launcher script present; **no git commit**

**Status: Done** (2026-09-12)

## Out of scope
- Running the full 9-game scored experiment
- Changing A–E
- Cloud agents / GitHub PR
