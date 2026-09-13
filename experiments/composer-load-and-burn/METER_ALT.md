# Lane B meter (rewritten 2026-09-10)

## Rejected
- Manual Cursor dashboard typing (included + on-demand) — brittle; Jordi does **not** use on-demand.  
- Harness-side Composer token capture — harness never sees Cursor inference.  
- Local AppData "token counters" — probed; no reliable per-ask balance for CLI/Composer.

## Locked
**Primary meter = Cursor usage CSV export** (timestamps, model, token/usage fields — same family of export Jordi has used before).

Workflow:
1. Record run window in `lane-*/runs/<stamp>/manifest.md` (local Europe/Madrid start/end, arm, game_ids).  
2. After the day's runs, export usage CSV from Cursor → drop in `usage/exports/`.  
3. Attribute rows to runs by time (and model/conversation if present) using `usage/attribute.ps1` (script added in a later rebuild phase).  
4. Report tokens (or export-native usage units) per game / per move with caveats.

### Drop path

Save dashboard exports as `usage/exports/YYYY-MM-DD.csv`.

### Attribution script

`usage/attribute.ps1` — params `-Manifest` (path to `manifest.md`), `-Csv` (path to export CSV). Reads manifest start/end, maps timestamp and token columns from the CSV header (no guessing). On success writes `attributed.md` next to the manifest; on mapping failure prints the header and exits nonzero.

Subscription **included** pool only; on-demand is N/A unless a row appears anyway.
