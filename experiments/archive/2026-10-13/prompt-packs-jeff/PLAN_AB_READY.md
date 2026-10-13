# Jeff A/B — prepare (do not launch until Jordi says go)

## Seats (Jev / TypeSafe Choice)
| Pack | Adapter | Spirit |
|------|---------|--------|
| j1 | TypesafeAdapter | **empty** (= plain AvE baseline) |
| j2 | TypesafeAdapter | careful delta only |
| j3 | JeffPhaseAdapter | phase×material snippet only |
| j4 | JeffChecklistAdapter | checklist Qs then Choice |
| j5 | JeffImagineAdapter | propose → local board → keep/ban |

## Slate (CALIBRATED ladder Elo — never catalog)
Identical for every seat, fixed order, 5 games:
1–3. `stockfish-handicap:noise90` (~**409**)
4–5. `stockfish-handicap:noise94` (~**359**)

Why this band: Jeff inscribed ~402. Old comments saying noise38≈420 were **wrong** (ladder noise38≈760). Catalog depth4=200 is ladder **1431**.

Total Jeff wave: **25 games** (5 seats × 5).

## Launch Jeff (when greenlit)
```
cd "C:\Users\jordi\Desktop\coding stuff\chess-vision-harness"
$env:PYTHONPATH = (Resolve-Path .\python\src).Path
$env:TYPESAFE_API_KEY = (Get-Content "C:\Users\jordi\Desktop\coding stuff\keys\typesafe_api_key.txt" -Raw).Trim()
python experiments\prompt-packs-jeff\compare_wave.py --go --packs j1,j2,j3,j4,j5 --parallel 1 --opp-a stockfish-handicap:noise90 --opp-b stockfish-handicap:noise94
```

## MiMo (free OpenCode) — separate lane
- Inscribed: `mimo-v2.5` (~517 inscribed elo)
- Free CLI model: `opencode/mimo-v2.5-free`
- Runner Choice adapters are TypeSafe-only; MiMo plays via **agent HTTP / OpenCode**, not Jeff Choice.
- Prior overnight free-MiMo hit Zen rate-limit then hung — for A/B: short wave, **no retry-sleep loop**, abort on 429.
- Proposed MiMo slate (same calibrated band): 5× baseline AvE (no pack) vs noise90/noise94, then optional pack overlays if agent `prompt_pack` path is confirmed.
- Do **not** start MiMo until Jeff wave is greenlit or Jordi picks MiMo-first.

## Report
After wave: accuracy + play-rating from ops snapshot, **wave game ids only** (not mixed pack board means).
