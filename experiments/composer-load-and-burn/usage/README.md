# Usage exports (Lane B)

## Export workflow

1. After sealed chess runs, export that day's Cursor usage CSV from the dashboard (timestamps, model, token/usage columns).
2. Save the file here as `usage/exports/YYYY-MM-DD.csv`.
3. Tell Dun-Dun which run folder(s) to attribute: `lane-a/runs/<stamp>/` or `lane-b/runs/<stamp>/`.

## Attribution

- **Pool:** subscription **included** only; on-demand is N/A unless a row appears anyway.
- **Window:** filter CSV rows to the manifest `[start, end]` local time (Europe/Madrid) recorded in `runs/<stamp>/manifest.md`.
- **Script:** `usage/attribute.ps1` reads the manifest + CSV and writes `attributed.md` next to the manifest.

## IDE arm caveat

If the CSV cannot split lead vs player rows, report **pool burn for the window** and per-game estimate = `window_total / 6` as a **labeled estimate**.

## Extra attribution rules (locked 2026-09-10)

- CSV may **not** label IDE vs CLI. Split by Madrid time windows in `usage/ATTRIBUTION-WINDOWS.md` and each run `manifest.md`.
- **Exclude Grok Bot / chat-assistant rows** from experiment Composer burn — launcher/host chatter, not seat model calls.
- Fill IDE start/end in `ATTRIBUTION-WINDOWS.md` when that arm runs.

## Game-length prior (for extrapolating full-game burn)

Do **not** use a generic 40-50 move chess average, and do **not** use only this experiment's finishers (Composer often fails to convert and leaves long grinders).

Use the harness on-disk archive (`.chess_harness/games/*/state.json`, `status=finished` / real results) as the length prior:

- Prefer **ply percentiles** stratified by model family (e.g. `composer-*` vs stronger) and opponent when n allows.
- Snapshot from 2026-09-10: **109** finished games; **composer-2.5** n=35, median **74** ply, p75 **180**, avg **~113**, max **420** (long tail). Whole archive median **50** ply.
- Lane B report: measured **usage per agent move** from the CSV window; extrapolated full-game = per-move x {p25, median, p75} from that prior, labeled as estimate. Completed games in the run are a check, not the sole length prior.
