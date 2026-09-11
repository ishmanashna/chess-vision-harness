# Prompt packs A–G (overlay comparison)

Same model, extra prompt texts, AvE only. Compare packs on local Ops **A/B** (finished W–D–L, mean accuracy, mean play rating). Elo, public spectator, and git sqlite stay off.

**Status:** A–D wave **paused** mid-run (target was 20 waves). Do not launch another A–D wave unless Jordi says so. Pack **E (committee) is frozen.** Packs **F (legal)** and **G (text imagine)** are ready for separate or mixed waves vs baseline A — see `docs/PROMPT_PACKS_F_G_PLAN.md`.

The product contract for packs lives in `docs/PROMPT_TEST_PLAN.md`. Live numbers are the Ops A/B tab at `http://127.0.0.1:8765/ops/`.

## Question

Do extra prompt texts change AvE results versus baseline, on the same inscribed model and the same opponent?

For F/G specifically: does a legal-move handout (F) or a text-only what-if board (G) change results vs **A**?

## Packs

| Id | Title | Kind | Extra text |
|----|--------|------|------------|
| A | Baseline | overlay | Read PNG, send move |
| B | Verify | overlay | 11-step PNG verification list |
| C | Principles | overlay | Chess principles |
| D | Slow | overlay | Sit with the position; no slogans |
| E | Committee | committee (`seat_packs`: b,c,d) | Frozen — not in this run |
| F | Legal | overlay | A loop + optional `chess-harness legal {game_id}` (live UCI list) |
| G | Imagine | overlay | A loop + optional text `chess-harness imagine {game_id} <moves…>` |

Pack files: `config/prompt_packs/{a..g}.txt`. Default rules: `_rules.txt` (A–D). F uses `_rules_f.txt`; G uses `_rules_g.txt`.

## Locked play rules

- Overlay seats read `board.png` before every real `move`.
- A–E and untagged games: never FEN, `state.json`, legal lists, text imagine, pgn, or audit.
- F may call `legal` only; G may call text `imagine` only (no PNG imagine). Cross-use is rejected.
- Idle 30 minutes without an accepted move → `*` (does not count as finished). `legal` / text `imagine` touch activity like a board read.
- Same opponent default as A–D unless overridden: `inverse-sf:exclude-top1-d8`.
- All White (unless you change it at create).
- Packed games stay off Elo, the public ladder, and git sqlite.

## How to start a wave

From `python/`:

**A–D (paused — do not relaunch without OK):**

```
python -m chess_harness prompt-test start --model <id> --packs a,b,c,d --opponent inverse-sf:exclude-top1-d8
```

**F/G only (smoke or a dedicated experiment):**

```
python -m chess_harness prompt-test start --model <id> --packs f,g --opponent inverse-sf:exclude-top1-d8
```

**Mixed baseline + F/G (suggested for Ops comparison):**

```
python -m chess_harness prompt-test start --model <id> --packs a,f,g --opponent inverse-sf:exclude-top1-d8
```

Then launch one overlay seat per printed brief.

### Smoke checklist (F/G tools)

After `start --packs f,g`, once per game:

```
python -m chess_harness legal <f-game-id>
python -m chess_harness imagine <g-game-id> e2e4 e7e5
python -m chess_harness resign <f-game-id>
python -m chess_harness resign <g-game-id>
```

Expect: `legal` returns non-empty `legal_moves_uci`; `imagine` returns a text grid with `side_to_move` white after those two plies; live game files unchanged by imagine alone.

## Models used

- Waves 1–5: Composer 2.5 (`composer-2.5`)
- From wave 6: Auto seats (`inherit`) with harness tag `cursor-auto` (`auto` is not a valid model id)

## Pause snapshot (finished ≠ `*`)

Taken when this folder was created. Ops A/B is the source of truth if the table has moved. F/G rows appear when those packs have games.

| Pack | Finished | W–D–L | Mean acc | Mean play rating |
|------|----------|-------|----------|------------------|
| A | 11 | 8–3–0 | 76.04 | ~994 |
| B | 12 | 10–2–0 | 84.81 | ~1368 |
| C | 11 | 11–0–0 | 77.91 | ~1095 |
| D | 11 | 9–2–0 | 77.17 | ~1054 |
| E | 0 | — | — | — |
| F | — | — | — | — |
| G | — | — | — | — |

`*` games do not increment Ops finished. Early Composer waves had long draws; Auto waves were mostly short wins. C often mates fast. B has the best mean accuracy and play rating.

Wave 14 (last launched A–D, in progress at pause):

- A `game-NGVqH0uL989u6VPqo8h2Aw`
- B `game-9NuuIqxYz32EAbWyxqIKFw` (finished 1-0)
- C `game-bhFnBEgKzkor09FhLKA5hg`
- D `game-ghR3u3sB46oLTR6AAYLUfA`
