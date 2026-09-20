# Jeff A/B (family `jeff`)

Separate from Composer packs `a`–`h`. Ops default view hides Jeff; use `?family=jeff`.

| Id | Role |
|----|------|
| ja | Baseline Choice |
| jb | Verify-spirit Choice |
| jc | Principles-spirit Choice |
| jd | Careful-spirit Choice |
| je | Silent council of 3 Jeffs (jb+jc+jd), majority vote, no chat |
| ji | Endgame mate technique |
| j2 | Baseline with board text sent twice |

## Opponent slate (Jeff ~387)

Same for every seat, fixed order:

1. `stockfish-handicap:noise38` (~420)
2. `stockfish-handicap:noise38`
3. `stockfish-handicap:noise38`
4. `stockfish-handicap:noise30` (~480; fallback `noise72`)
5. `stockfish-handicap:noise30`

Total: **7 × 5 = 35 games**. Tag in jsonl: `jeff-ab-compare`.

## Soft-restart harness (once after code land)

```powershell
cd "C:\Users\jordi\Desktop\coding stuff\chess-vision-harness"
.\experiments\prompt-packs-jeff\soft_restart_harness.ps1
```

## Smoke (not the wave)

```powershell
$env:PYTHONPATH = (Resolve-Path .\python\src).Path
python experiments\prompt-packs-jeff\smoke_jeff_ab.py
```

## Compare wave

Dry-run (prints plan, no API burn):

```powershell
python experiments\prompt-packs-jeff\compare_wave.py
```

Play (35 games, sequential; optional `--parallel 2`):

```powershell
python experiments\prompt-packs-jeff\compare_wave.py --go
```

## Report

```powershell
python experiments\prompt-packs-jeff\report_jeff_ab.py --compare-wave-only --write
```

Ops: `http://127.0.0.1:8765/api/ops/prompt-test?family=jeff`

## Runner (open-ended seats, not fixed slate)

```powershell
.\experiments\prompt-packs-jeff\launch.ps1
```
