# Prompt packs F / G — legal moves + text imagine

Local prompt-test add-on. Same AvE overlay machine as A–D. Two new packs after E (committee stays frozen / out of this plan). CLI Composer seats implement phase by phase. Orchestrator launches seats; does not play the games.

Parent contract: `docs/PROMPT_TEST_PLAN.md`. Do not reopen A–E product locks. Do not touch public Create Game, Pages, Elo, or published snapshots.

## Goal

Measure whether (1) a legal-move list handout and (2) a text-only what-if board (`imagine`) change AvE results versus baseline **A**, on the same inscribed model and opponent.

## Packs

| Id | Title | Kind | Extra |
|----|--------|------|--------|
| F | Legal | overlay | A turn loop + allowed `legal` command |
| G | Imagine | overlay | A turn loop + allowed text `imagine` |

Both are **overlay** (one seat). Not committee.

## Scope

- AvE only, localhost, tagged unrated packed games (same off-ladder path as A–D).
- New pack files + index rows `f`, `g`.
- Separate rules files so A–E keep “no legal / no imagine.”
- CLI + MCP for `legal` and text `imagine`, gated to the matching pack (or an explicit capability flag on the game derived from the pack).
- Ops A/B already rows-by-pack-id — F/G must appear when they have games. No Ops start button work.
- Update `experiments/prompt-packs/README.md` and a short delta section in `PROMPT_TEST_PLAN.md` (do not rewrite the whole parent).

## Out of scope

- Unfreezing or changing pack **E** (committee).
- Public HTTP agent briefs / Create Game paste prompts.
- Imagine as PNG (old `BOARD_IMAGINE_PLAYGROUND_PLAN.md` Phase 4). This plan’s imagine is **text grid only** via `format_board_text` (same shape as live `board.txt`).
- Engines, FEN in briefs, `state.json`, `pgn`, `game audit`.
- Illegal-attempt metrics (optional later; not required to ship F/G).
- Changing default opponent / color locks for the paused A–D run.
- Full pytest suite each phase (temp-dir / targeted tests only, same as parent).

## Product decisions (locked)

1. **F and G are A plus one tool.** Pack body = A’s two-step turn loop, then the exact command for that tool. Do not paste B/C/D verification essays into F/G.

2. **Rules are pack-family files.** Keep `config/prompt_packs/_rules.txt` for A–D (still bans legal + imagine). Add `_rules_f.txt` and `_rules_g.txt`. Brief renderer: if index entry has `"rules": "_rules_f.txt"` (etc.), use that file; else `_rules.txt`. Hash stays `{id}.txt` body only (unchanged parent rule).

3. **Capabilities from pack id, not free-form agent claims.** On create, store something the gate can read (prefer `prompt_pack` already on state; gate checks pack id ∈ {f} / {g}, or a derived `prompt_pack_caps` list like `["legal"]` / `["imagine"]` if that keeps the gate clearer — pick one and use it everywhere). Untagged games and packs a–e: both tools hard-reject.

4. **`legal`.** Read-only. From the **live** game position, return legal moves for the side to move (UCI list; SAN optional duplicate is fine if cheap). No engine. Does not reset idle? **Touch activity** like a successful board read is OK so listing legals does not starve the 30-minute clock — same spirit as committee `say`. Document that choice in the phase Done when.

5. **`imagine` (text).** Read-only what-if. Input: one move or a short line (UCI preferred; SAN if unambiguous, same parser as `move`). Clone live board → push moves → return `format_board_text(..., bottom_color="white")` plus `side_to_move` / `in_check` already in that helper. **No PNG path, no image bytes.** Cap line length (~12 plies). Illegal mid-line → clear error with ply index; live game untouched. Never overwrite `board.png`, never append moves. Soft reject for wrong pack.

6. **Still image-first for the real move.** F/G still read `board.png` before `move`. Legal/imagine are extras, not a replacement for the PNG on the committed ply. G’s imagine text is hypothetical; live PNG (and live board.txt if they already use CLI board helpers) remains ground truth before `move`.

7. **Forbidden cross-tools.** F may not call imagine. G may not call legal. Both still ban engines, `state.json`, spectator `/api/games/*`, `pgn`, `game audit`, operator commands.

8. **Letters are not special-cased in code beyond the capability map.** Loader stays “any id in index.” Adding H later must not require editing `if pack == "f"` sprinkled everywhere — centralize allow checks.

## Pack texts (copy into files)

Copy these bodies into `config/prompt_packs/`. Do not paraphrase.

### `_rules_f.txt`

```
You are playing an engine game on this machine. Image-first: the position is the board PNG. Do not cheat.

Game id: {game_id}
Model id: {model_id}
Board PNG: {board_path}
White is at the bottom. Square names are absolute. a1 is the bottom-left square of the image even when you play Black.

Your color and whether it is your turn come from chess-harness status {game_id}. That command is metadata only (your_turn, result, in_check). It is not the piece placement. chess-harness board {game_id} reprints the PNG path.

How you choose a move is in the instructions after this block. Follow those before you send a move.

You may list legal moves for the live position:
  chess-harness legal {game_id}
(or MCP chess_legal_moves). Use that list only as a handout of what the rules allow. Still read the PNG before you move. Prefer UCI (e2e4, g1f3, e7e8q). SAN is fine if it is unambiguous.
If a move is rejected, look at the PNG again and try another. The game continues.
If it is not your turn, wait. Do not move for the engine.

When status says game_over, start a new game with this exact command, then use the new game_id and board_path from the JSON:
  chess-harness new --model {model_id} --prompt-pack {prompt_pack}
Keep going until you are told to stop. Do not reuse the finished game id.

Never read state.json, game.pgn, results.jsonl, or FEN. Never call spectator /api/games/*. Never run an engine or a script to pick moves. Never chess-harness imagine or MCP chess_imagine_board. Never chess-harness pgn or chess-harness game audit. Never operator commands (serve, harness reset, models uninscribe, calibration).

If you go 30 minutes without a move that the harness accepts, the game dies with no result. Do not resign to skip a hard position.
```

### `f.txt`

```
Each turn, until the game is over:

1. Read the board PNG at {board_path}. Do not skip this. Do not reuse an old image.
2. Optional: chess-harness legal {game_id} if you want the legal-move list for this live position.
3. Send one move: chess-harness move {game_id} <move>
```

### `_rules_g.txt`

```
You are playing an engine game on this machine. Image-first: the position is the board PNG. Do not cheat.

Game id: {game_id}
Model id: {model_id}
Board PNG: {board_path}
White is at the bottom. Square names are absolute. a1 is the bottom-left square of the image even when you play Black.

Your color and whether it is your turn come from chess-harness status {game_id}. That command is metadata only (your_turn, result, in_check). It is not the piece placement. chess-harness board {game_id} reprints the PNG path.

How you choose a move is in the instructions after this block. Follow those before you send a move.

You may explore lines without changing the real game:
  chess-harness imagine {game_id} <move> [<move> ...]
(or MCP chess_imagine_board with the same moves). The reply is a compact text board only (same grid style as board.txt: white at bottom, files a–h). It is hypothetical. It is not a new PNG. Before you send a real move, read the live board PNG again. Prefer UCI. SAN is fine if it is unambiguous.
If a move is rejected, look at the PNG again and try another. The game continues.
If it is not your turn, wait. Do not move for the engine.

When status says game_over, start a new game with this exact command, then use the new game_id and board_path from the JSON:
  chess-harness new --model {model_id} --prompt-pack {prompt_pack}
Keep going until you are told to stop. Do not reuse the finished game id.

Never read state.json, game.pgn, results.jsonl, or FEN. Never call spectator /api/games/*. Never run an engine or a script to pick moves or list legal moves. Never chess-harness legal. Never chess-harness pgn or chess-harness game audit. Never operator commands (serve, harness reset, models uninscribe, calibration).

If you go 30 minutes without a move that the harness accepts, the game dies with no result. Do not resign to skip a hard position.
```

### `g.txt`

```
Each turn, until the game is over:

1. Read the board PNG at {board_path}. Do not skip this. Do not reuse an old image.
2. Optional: chess-harness imagine {game_id} <move> [<move> ...] to see a text-only board after that line. Hypothetical only.
3. Send one move: chess-harness move {game_id} <move>
```

### `index.json` rows to add

```json
"f": { "title": "F Legal", "kind": "overlay", "rules": "_rules_f.txt" },
"g": { "title": "G Imagine", "kind": "overlay", "rules": "_rules_g.txt" }
```

(Merge into existing `packs` object; keep a–e unchanged.)

## Files to touch (orientation)

- `config/prompt_packs/` — `f.txt`, `g.txt`, `_rules_f.txt`, `_rules_g.txt`, `index.json`
- Brief renderer / pack loader (wherever `_rules.txt` is chosen today) — honor optional `rules` field
- New small module or commands helpers for `legal` + text `imagine` (keep files ≤300 lines; split if needed)
- `commands.py` / `__main__.py` / MCP tools registration
- Gate helper used by CLI + MCP
- Tests next to existing prompt-test / CLI tests
- `docs/PROMPT_TEST_PLAN.md` — short “Packs F/G” delta pointing here
- `experiments/prompt-packs/README.md` — roster + pause note

Reuse: `board_text.format_board_text`, existing move parse path used by `move`. Do not implement PNG imagine.

## Phase 1 — Registry + rules selection + pack texts

**Goal:** F/G exist as overlay packs. Briefs pull the right rules file. Create tags `prompt_pack` f/g like a–d.

**Work**

- Write pack texts from this plan into `config/prompt_packs/`.
- Extend loader/index for optional `rules` (default `_rules.txt`).
- Brief renderer uses that rules file + `{id}.txt`.
- `new --prompt-pack f` / `g` and `prompt-test start --packs f` / `g` / `a,f,g` work for overlay create (tools may still 501/reject until Phase 2–3 — briefs may mention commands that land in later phases; prefer landing Phase 2–3 before telling seats to play F/G).

**Done when:** Temp harness: `prompt-test start --packs a,f,g` creates three games; f brief contains legal command and not imagine; g brief contains imagine and not legal; a brief still bans both. Unknown pack still fails. Hash of `f.txt` / `g.txt` only.

**Verify:** Loader + brief tests. Do not run the full suite.

## Phase 2 — `legal` command (CLI + MCP), gated

**Goal:** Pack F seats can list live legal moves. Everyone else cannot.

**Work**

- `chess-harness legal {game_id}` → JSON or plain list of UCI (document one shape; keep it stable).
- MCP `chess_legal_moves` same.
- Gate: only when game’s pack allows legal (f). Reject a–e, g, untagged.
- Activity touch policy as locked above.
- Unit/CLI tests: starting position has expected count; wrong pack rejected; does not change FEN/move list on disk.

**Done when:** Temp-dir f-game: `legal` returns non-empty UCI list; after a real `move`, list updates; a-game `legal` errors; game state files unchanged by `legal` alone.

**Verify:** Targeted tests only.

## Phase 3 — text `imagine` (CLI + MCP), gated

**Goal:** Pack G seats get hypothetical text boards. No PNG. Live game untouched.

**Work**

- `chess-harness imagine {game_id} <moves…>` → stdout text from `format_board_text` (white bottom).
- MCP `chess_imagine_board` — **text payload**, not image (if an old PNG stub exists, replace or add a distinct tool name and point G’s rules at the text one; do not ship PNG for this experiment).
- Cap length; illegal ply → error with index; gate to pack g only.
- No activity requirement beyond optional touch (same as legal — pick one consistent policy and document).

**Done when:** Temp-dir g-game: `imagine e2e4 e7e5` returns a text grid with side_to_move white (after those two plies); `board.png` bytes/mtime unchanged; move list unchanged; f-game and a-game `imagine` reject; illegal mid-line errors.

**Verify:** Targeted tests only.

## Phase 4 — Docs + experiment folder + smoke

**Goal:** Humans and orchestrators know how to run F/G without rereading this whole file.

**Work**

- Short delta in `PROMPT_TEST_PLAN.md` (roster includes f/g; forbidden-extras carve-out; link here).
- Update `experiments/prompt-packs/README.md`: table rows F/G; note A–D pause still stands; E frozen; how to `start --packs a,f,g` or `f,g` alone.
- Smoke from `python/`: start f and g, run `legal` / `imagine` once each, resign or one-move smoke — no need for a full wave.

**Done when:** README + parent plan mention F/G; smoke commands documented and run once on this PC.

**Verify:** Manual smoke checklist in the PR/summary. Do not run the full suite.

## Orchestrator notes (CLI seats)

- One Composer seat per phase (or per Work bullet if a phase is fat). Hard concurrency cap as usual.
- Seat prompt: open this file + `PROMPT_TEST_PLAN.md` product locks; implement only the named phase; stop at Done when; report verify commands + output.
- Do not launch F/G player seats for a scored wave until Phases 1–3 are green.
- Wave policy for comparison (orchestrator / Jordi, not coding seats): either separate F/G waves vs A baseline, or mixed waves that always include A — pick before burning tokens; default suggestion: waves of `a,f,g` so Ops rows stay comparable.

## Estimated duration

- Phase 1: 1.5–3 agent-hours
- Phase 2: 2–4 agent-hours
- Phase 3: 2.5–4.5 agent-hours
- Phase 4: 1–2 agent-hours
