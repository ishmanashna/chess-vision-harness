# Jeff seats J1–J5

| Id | Role | Kind |
|----|------|------|
| j1 | Baseline single Choice | overlay |
| j2 | Careful (old jd style) | overlay |
| j3 | Code classifies opening/middle/end × ahead/even/behind, injects spirit, then Choice | jeff_phase |
| j4 | Checklist of Jeff yes/no questions → final Choice | jeff_checklist |
| j5 | **Jeff** proposes → we render imagined board text → Jeff better/worse → keep or ban+retry (max 5) | jeff_imagine |

Legacy packs `ja`–`je` / `ji` / `j2_double` stay in the index for old runs. Old double-board seat is `j2_double` (not `j2`).

## Cost note
- j1/j2: 1 System One call per ply
- j3: 1 call per ply (phase is local)
- j4: ~6 calls per ply (5 checklist + 1 move)
- j5: up to ~10 calls per ply (propose + compare, retries)

## Launch (when you say go)

Soft-restart first so the harness picks up new adapters:

```powershell
cd "C:\Users\jordi\Desktop\coding stuff\chess-vision-harness"
.\experiments\prompt-packs-jeff\soft_restart_harness.ps1
```

Then:

```powershell
$env:PYTHONPATH = (Resolve-Path .\python\src).Path
python experiments\prompt-packs-jeff\compare_wave.py --packs j1,j2,j3,j4,j5
python experiments\prompt-packs-jeff\compare_wave.py --go --packs j1,j2,j3,j4,j5 --parallel 1
```

Runner config: `config\runner_slots_jeff_j1j5.json`
