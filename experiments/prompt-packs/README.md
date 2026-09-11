# Prompt packs A–D (overlay comparison)

Same model, four extra texts, AvE only. Compare packs on local Ops **A/B** (finished W–D–L, mean accuracy, mean play rating). Elo, public spectator, and git sqlite stay off.

**Status:** paused mid-run. Target was 20 waves of A–D. Do not launch another wave unless Jordi says so. Pack **E (committee) is frozen.**

The product contract for packs lives in `docs/PROMPT_TEST_PLAN.md`. Live numbers are the Ops A/B tab at `http://127.0.0.1:8765/ops/`.

## Question

Do extra prompt texts change AvE results versus baseline, on the same inscribed model and the same opponent?

## Packs

| Id | Title | Kind | Extra text |
|----|--------|------|------------|
| A | Baseline | overlay | Read PNG, send move |
| B | Verify | overlay | 11-step PNG verification list |
| C | Principles | overlay | Chess principles |
| D | Slow | overlay | Sit with the position; no slogans |
| E | Committee | committee (`seat_packs`: b,c,d) | Frozen — not in this run |

Pack files: `config/prompt_packs/{a,b,c,d,e}.txt` plus `_rules.txt`.

## Locked play rules

- Overlay seats read `board.png` only.
- Never FEN, `state.json`, legal-move lists, `imagine`, pgn, or audit.
- Idle 30 minutes without an accepted move → `*` (does not count as finished).
- Waves of 4 (A, B, C, D). Wait until the set is over before the next.
- Same opponent: `inverse-sf:exclude-top1-d8`.
- All White.
- Packed games stay off Elo, the public ladder, and git sqlite.

## How to start a wave

From `python/`:

```
python -m chess_harness prompt-test start --model <id> --packs a,b,c,d --opponent inverse-sf:exclude-top1-d8
```

Then launch four overlay seats with the printed briefs.

## Models used

- Waves 1–5: Composer 2.5 (`composer-2.5`)
- From wave 6: Auto seats (`inherit`) with harness tag `cursor-auto` (`auto` is not a valid model id)

## Pause snapshot (finished ≠ `*`)

Taken when this folder was created. Ops A/B is the source of truth if the table has moved.

| Pack | Finished | W–D–L | Mean acc | Mean play rating |
|------|----------|-------|----------|------------------|
| A | 11 | 8–3–0 | 76.04 | ~994 |
| B | 12 | 10–2–0 | 84.81 | ~1368 |
| C | 11 | 11–0–0 | 77.91 | ~1095 |
| D | 11 | 9–2–0 | 77.17 | ~1054 |
| E | 0 | — | — | — |

`*` games do not increment Ops finished. Early Composer waves had long draws; Auto waves were mostly short wins. C often mates fast. B has the best mean accuracy and play rating.

Wave 14 (last launched, in progress at pause):

- A `game-NGVqH0uL989u6VPqo8h2Aw`
- B `game-9NuuIqxYz32EAbWyxqIKFw` (finished 1-0)
- C `game-bhFnBEgKzkor09FhLKA5hg`
- D `game-ghR3u3sB46oLTR6AAYLUfA`
