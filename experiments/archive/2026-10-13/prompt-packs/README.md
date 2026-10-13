# Prompt packs A–H (overlay comparison)

Same model, extra prompt texts, AvE only. Compare packs on local Ops **A/B** (finished W–D–L, mean accuracy, mean play rating). Elo, public spectator, and git sqlite stay off.

**Status:** A–D wave **paused** mid-run (target was 20 waves). Do not launch another A–D wave unless Jordi says so. Pack **E (committee) is frozen.** Packs **F (legal)**, **G (text imagine)**, and **H (text-only board)** are ready for separate or mixed waves — see `docs/PROMPT_PACKS_F_G_PLAN.md` and `docs/PROMPT_PACK_H_PLAN.md`.

The product contract for packs lives in `docs/PROMPT_TEST_PLAN.md`. Live numbers are the Ops A/B tab at `http://127.0.0.1:8765/ops/`.

## Question

Do extra prompt texts change AvE results versus baseline, on the same inscribed model and the same opponent?

For F/G/H specifically: does a legal-move handout (F), a text-only what-if board (G), or a text-only position channel (H) change results vs **A**?

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
| H | Text | overlay | A loop + `chess-harness board-text {game_id}` only (no PNG) |

Pack files: `config/prompt_packs/{a..h}.txt`. Default rules: `_rules.txt` (A–D). F uses `_rules_f.txt`; G uses `_rules_g.txt`; H uses `_rules_h.txt` and snapshots `observation: text` on the game.

## Locked play rules

- Overlay seats read `board.png` before every real `move` (except **H**, which reads `board-text` only).
- A–E and untagged games: never FEN, `state.json`, legal lists, text imagine, pgn, or audit.
- F may call `legal` only; G may call text `imagine` only; H may call `board-text` only (no PNG, legal, or imagine). Cross-use is rejected.
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

**F/G/H only (smoke or a dedicated experiment):**

```
python -m chess_harness prompt-test start --model <id> --packs f,g,h --opponent inverse-sf:exclude-top1-d8
```

**Mixed baseline + F/G (suggested for Ops comparison):**

```
python -m chess_harness prompt-test start --model <id> --packs a,f,g --opponent inverse-sf:exclude-top1-d8
```

Then launch one overlay seat per printed brief.

**Wave policy:** prefer one triad (`f,g,h`) per wave — three CLI seats, one of each pack. Stack sequential triads with `-Waves N` in `run-fgh-cli-wave.ps1` rather than nine concurrent seats by default.

### Smoke checklist (F/G/H tools)

After `start --packs f,g,h`, once per game:

```
python -m chess_harness legal <f-game-id>
python -m chess_harness imagine <g-game-id> e2e4 e7e5
python -m chess_harness board-text <h-game-id>
python -m chess_harness legal <h-game-id>
python -m chess_harness imagine <h-game-id> e2e4
python -m chess_harness resign <f-game-id>
python -m chess_harness resign <g-game-id>
python -m chess_harness resign <h-game-id>
```

Expect: `legal` on F returns non-empty `legal_moves_uci`; `imagine` on G returns a text grid; `board-text` on H returns a text grid; `legal` / `imagine` on H reject; H state has `observation: text`.

## Models used

- **Composer-only A/B (canonical):** composer-2.5 only. cursor-auto seats were excluded from Ops packing on 2026-09-12 (states keep prompt_pack_original + prompt_test_excluded).
- Historical Auto A–D games remain on disk for forensics but do **not** count in Ops A/B.
- F/G/H waves: composer-2.5. New waves stopped 2026-09-12; in-progress F/G/H seats may finish.

## Pause snapshot (Composer-only finished ≠ *)

See also COMPOSER_ONLY_SNAPSHOT.md. Opponent: inverse-sf:exclude-top1-d8.

| Pack | Finished | W–D–L | Mean acc | Notes |
|------|----------|-------|----------|-------|
| A | 3 | 0–3–0 | ~61.5 | composer only |
| B | 3 | 1–2–0 | ~70.4 | composer only |
| C | 4 | 4–0–0 | ~63.7 | short mates common |
| D | 4 | 2–2–0 | ~62.1 | composer only |
| E | 0 | — | — | frozen |
| F | 8 | 3–3–2 | ~57.4 | legal; open seats may add |
| G | 8 | 5–1–2 | ~72.7 | imagine; open seats may add |
| H | 8 | 2–3–3 | ~45.4 | text-only; open seats may add |

Older mixed Auto+Composer tables are obsolete for comparison.


## Pause snapshot (finished ≠ `*`)

Taken when this folder was created. Ops A/B is the source of truth if the table has moved. F/G/H rows appear when those packs have games.

| Pack | Finished | W–D–L | Mean acc | Mean play rating |
|------|----------|-------|----------|------------------|
| A | 11 | 8–3–0 | 76.04 | ~994 |
| B | 12 | 10–2–0 | 84.81 | ~1368 |
| C | 11 | 11–0–0 | 77.91 | ~1095 |
| D | 11 | 9–2–0 | 77.17 | ~1054 |
| E | 0 | — | — | — |
| F | — | — | — | — |
| G | — | — | — | — |
| H | — | — | — | — |

`*` games do not increment Ops finished. Early Composer waves had long draws; Auto waves were mostly short wins. C often mates fast. B has the best mean accuracy and play rating.

Wave 14 (last launched A–D, in progress at pause):

- A `game-NGVqH0uL989u6VPqo8h2Aw`
- B `game-9NuuIqxYz32EAbWyxqIKFw` (finished 1-0)
- C `game-bhFnBEgKzkor09FhLKA5hg`
- D `game-ghR3u3sB46oLTR6AAYLUfA`
