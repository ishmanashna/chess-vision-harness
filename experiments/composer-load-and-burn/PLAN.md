# PLAN — rebuild composer-load-and-burn

**Audience:** Composer 2.5 implementer (orchestrator dispatches one agent per phase).  
**Repo root:** `C:\Users\jordi\Desktop\coding stuff\chess-vision-harness`  
**Experiment root (`$Exp`):** `experiments/composer-load-and-burn/`  
**Scope:** files **only under** `$Exp`. Do not change `python/src/chess_harness/**`, product APIs, spectator, or `runner/`. Do not run git. Do not run the product pytest suite. ASCII hyphens only in `.ps1` (PowerShell 5.1 on this Spanish box). Handle spaces in `coding stuff`.

**Stack:** Cursor Composer, subversions / non-fast. Real agent-vs-engine games.

**Keep as-is:** `bin/ch.ps1` (already resolves `chess-harness.exe` then `python -m chess_harness` from `python/`). `SMOKE.md` (add one rebuild note at the top only).

**Delete when replaced:** `prompts/lane-a-worker.txt`, `lane-b/record-usage.ps1`, `usage-log.md`.

**Read before coding:** this file, `EXPERIMENT.md`, `SMOKE.md`, `scripts/run_agent_game.md`, existing `bin/ch.ps1`, existing `lane-a/sample-os.ps1`.

**Locks (verbatim):** model `composer-2.5`; opponent `random`; agent White; idle 30 minutes; CLI must **not** pass `--workspace` at the live repo; sampler WMI not Get-Counter; Lane B meter is usage CSV drop, not dashboard Read-Host.

All operator commands below are from **repo root**.

---

## Done shape

| Arm | Operator does |
| --- | --- |
| **A CLI** | Close Cursor if possible. `.\experiments\composer-load-and-burn\lane-a\run-cli-6.ps1` (default 6 seats). Wait. Read `lane-a/runs/<stamp>/` (`os.csv`, `manifest.md`, `summary.md`). |
| **A IDE** | Only Grok Bot + Cursor. Follow `lane-a/IDE-CHECKLIST.md`: baseline sampler, paste `prompts/lane-a-lead.txt` into **one** Composer lead, wait for 6 games, stop sampler, copy game ids into the run manifest. |
| **B** | `.\experiments\composer-load-and-burn\lane-b\run-game.ps1` creates a sealed game + paste + manifest. After the day, drop Cursor usage CSV in `usage/exports/`. |

Real 6-wide / full-game burns are operator runs. This rebuild stops after dry `-Seats 1`.

---

## Tree after rebuild

```
experiments/composer-load-and-burn/
  EXPERIMENT.md
  PLAN.md
  SMOKE.md
  METER_ALT.md
  bin/ch.ps1
  prompts/
    lane-a-lead.txt
    lane-a-player.txt
    lane-b-player.txt          (same body as lane-a-player.txt)
  lane-a/
    sample-os.ps1
    run-cli-6.ps1
    IDE-CHECKLIST.md
    runs/
  lane-b/
    run-game.ps1
    runs/
  usage/
    README.md
    exports/
    attribute.ps1
```

No `record-usage.ps1`. No `lane-a-worker.txt`. No `usage-log.md`.

---

## Spec per file

### `prompts/lane-a-player.txt` (canonical player)

Paste-ready. Placeholders the scripts/lead must substitute:

- `{{GAME_ID}}`
- `{{BOARD_PATH}}` — absolute `board_path` from `new` JSON
- `{{SPECTATOR_URL}}` — `http://127.0.0.1:8765/g/{{GAME_ID}}`
- `{{BOARD_PNG_URL}}` — `http://127.0.0.1:8765/g/{{GAME_ID}}/board.png`
- `{{MODEL_ID}}` — `composer-2.5`
- `{{AGENT_COLOR}}` — `white`

Behavior:

- You play **one** White vs `random` harness game `{{GAME_ID}}` to `game_over`.
- Each turn: look at the PNG at `{{BOARD_PATH}}` (or `chess-harness board` / MCP `chess_get_board`). Do not read `state.json`. Default: no authenticated `/api/v1`.
- Move: `chess-harness move {{GAME_ID}} <uci>` or MCP `chess_make_move`. After a move, poll status until `your_turn` or `game_over`.
- Idle 30 minutes without an accepted move kills the game with no result. Keep moving. No resign unless truly stuck. No editing `python/src/**`.
- CLI seats often have **no** chess MCP: include the full exe invocation:

```
& "$env:APPDATA\Python\Python313\Scripts\chess-harness.exe" status {{GAME_ID}}
& "$env:APPDATA\Python\Python313\Scripts\chess-harness.exe" board {{GAME_ID}}
& "$env:APPDATA\Python\Python313\Scripts\chess-harness.exe" move {{GAME_ID}} <uci>
```

- Play **this** `game_id` only. Do not open `.chess_harness/prompt_test/`, do not start committee/pack E games, do not create extra games.

`prompts/lane-b-player.txt` must be the **same bytes** as `lane-a-player.txt` (copy).

### `prompts/lane-a-lead.txt` (IDE only, not substituted by scripts)

Complete prompt the operator pastes into **one** Composer lead in this repo. No `PLACEHOLDER` lines.

Must say:

- You are the Lane A IDE lead. Composer subversions / non-fast.
- Spawn **exactly 6** Composer 2.5 subagents via the Task tool (`subagent_type` generalPurpose, `model` composer-2.5). Do not play the six games yourself.
- First ensure the harness is up (`GET http://127.0.0.1:8765/health`). If not, from repo root: `.\experiments\composer-load-and-burn\bin\ch.ps1 serve --force`.
- Create exactly 6 games, one per sub, each:

```
.\experiments\composer-load-and-burn\bin\ch.ps1 new --model composer-2.5 --opponent random --agent-color white
```

- Parse JSON (`ok`, `game_id`, `board_path`). Abort a seat if `ok` is false.
- For each game, give that subagent the **full substituted** `lane-a-player.txt` body (read `experiments/composer-load-and-burn/prompts/lane-a-player.txt` and replace placeholders). Tell them to play to the end.
- Wait until all six finish or fail. Report a table: seat, game_id, result or error.
- Do not change product code. Do not run git.

### `lane-a/sample-os.ps1`

Keep WMI CPU and existing metric columns. Add:

- `-Phase` (mandatory when not using a default): `baseline` or `hot`. Default `hot` if omitted is wrong — **require** `-Phase baseline|hot`.
- CSV header exactly:

```
timestamp_iso_local,phase,cpu_load_pct,ram_total_gb,ram_free_gb,commit_used_gb,commit_limit_gb,disk_c_free_gb,proc_count_node,proc_ws_mb_node_sum,proc_count_agentish,proc_ws_mb_cursor_sum
```

- `-OutDir`, `-IntervalSec` default 5, `-Once`, `-DurationSec` optional.
- Append to `os.csv` if it exists (same header); write header only on create.
- InvariantCulture decimals.
- Agentish: any process whose Name or Path contains `agent` or `cursor-agent`. Missing → 0.

### `lane-a/run-cli-6.ps1`

From repo root: `.\experiments\composer-load-and-burn\lane-a\run-cli-6.ps1`

Params: `-Seats` default **6** (allow 1–6), `-TimeoutSec` default 900, `-BaselineSec` default 90.

Behavior:

1. Create `lane-a/runs/<yyyyMMdd-HHmmss>/`.
2. Print: close Cursor IDE for this arm if possible. Record `Cursor` process count to `summary.md` (do not kill Cursor).
3. Baseline: start `sample-os.ps1 -OutDir $RunDir -IntervalSec 5 -Phase baseline -DurationSec $BaselineSec` and **wait until it exits**.
4. Health: `GET http://127.0.0.1:8765/health`. If not ok, `ch.ps1 serve --force` and wait up to 45s.
5. Create `$Seats` games via `ch.ps1 new --model composer-2.5 --opponent random --agent-color white`. Parse JSON. Abort the run if any `ok` is false.
6. Write `manifest.md`: stamp, arm `CLI`, Europe/Madrid start local time, seats, each `game_id` + `board_path`, Cursor process count at launch.
7. Hot: start `sample-os.ps1 -OutDir $RunDir -IntervalSec 5 -Phase hot` in background; record PID.
8. For seats 1..N: substitute `prompts/lane-a-player.txt`; spawn:

```
agent -p --trust --force --worktree lane-a-seat-<n> <prompt>
```

Agent binary: `%LOCALAPPDATA%\cursor-agent\agent.cmd`. Omit `--mode ask`. Omit `--workspace`. Omit `--model` unless `agent --list-models` confirms an id (then document it in `summary.md`). Pass the prompt as **one** string via PowerShell splatting (do not split on newlines). Working directory = repo root.

9. Wait with timeout; `seat-<n>.log` with exit code + stdout/stderr tails. Stop sampler. Append end time to `manifest.md`. Write `summary.md`.

### `lane-a/IDE-CHECKLIST.md`

Short operator doc (not six tabs):

1. Close everything heavy except Grok Bot + Cursor.
2. Create `lane-a/runs/<stamp>/`.
3. Baseline: `.\experiments\composer-load-and-burn\lane-a\sample-os.ps1 -OutDir experiments\composer-load-and-burn\lane-a\runs\<stamp> -IntervalSec 5 -Phase baseline -DurationSec 90`
4. Start hot sampler in another terminal (`-Phase hot`, leave running).
5. Paste **all** of `prompts/lane-a-lead.txt` into **one** new Composer chat (do not continue a chess/prompt-test thread).
6. Wait until the lead reports 6 finished or failed games.
7. Stop hot sampler. Write `manifest.md` in that stamp dir: arm `IDE`, start/end Europe/Madrid, game_ids from the lead, note “7 seats (1 lead + 6 players)”.

### `lane-b/run-game.ps1`

Sealed **one** game (param `-Count` later is out of scope). No Read-Host usage meter.

1. Create `lane-b/runs/<stamp>/`.
2. Health / `ch.ps1 serve --force` same as CLI.
3. `ch.ps1 new --model composer-2.5 --opponent random --agent-color white`.
4. Substitute `lane-b-player.txt` → `PASTE.txt` + print `----- PASTE INTO COMPOSER -----`.
5. Write `manifest.md`: arm `B`, start time, `game_id`, `board_path`. Print: when the game ends, edit manifest end time. Print spectator URLs.
6. Do not launch Composer. Do not scrape dashboards.

### `usage/README.md`

How Jordi exports Cursor usage CSV (dashboard export for that day). Save as `usage/exports/YYYY-MM-DD.csv`. Point Dun-Dun at matching `lane-a/runs/<stamp>/` or `lane-b/runs/<stamp>/`. Included pool only; on-demand N/A. Attribution = filter CSV rows to manifest `[start,end]`. If CSV cannot split lead vs players, window total / 6 is a labeled estimate.

### `usage/attribute.ps1`

Params: `-Manifest` path, `-Csv` path. Read manifest start/end. Read CSV header. Map a timestamp column (try names containing `time`, `date`, `timestamp`) and token-like columns (try names containing `token`, `input`, `output`, `cache`). If mapping fails, print the header row and exit nonzero — do not guess. If it works, write `attributed.md` next to the manifest: row count in window, sum of mapped token columns, per-game estimate = total/game_count if game_ids listed.

### `METER_ALT.md`

Keep the rewrite already there (CSV primary, dashboard typing rejected). Add the drop path `usage/exports/` and `attribute.ps1`.

### `SMOKE.md`

Prepend a short note: 2026-09-10 rebuild = real chess + CSV meter; first-build `lane-a-worker` / dashboard meter are obsolete. Do not delete the 2026-09-10 smoke evidence.

---

## Out of scope (reject if suggested)

- Changing product code or inscribing new models
- Default opponent other than `random`
- Six manual IDE tabs
- `--workspace` live repo on CLI seats
- Killing Cursor
- Dashboard Read-Host / on-demand typing
- Parsing Composer tokens from local DBs
- Full 6-wide or full-game burns as part of this rebuild
- Git commands

---

## Phases (one Composer 2.5 implementer each, sequential)

### Phase 1 — prompts + usage docs + delete obsolete

Write `lane-a-player.txt`, copy to `lane-b-player.txt`, write complete `lane-a-lead.txt`, refresh `usage/README.md`, `usage/exports/.gitkeep`, rewrite `METER_ALT.md` drop path, SMOKE note, delete `lane-a-worker.txt`, `record-usage.ps1`, `usage-log.md`.

Done when: player prompt has all placeholders; lead prompt has exact `ch.ps1 new` command and Task spawn rules; those three deletes are gone.

### Phase 2 — sampler + CLI runner + IDE checklist

Rewrite `sample-os.ps1` (phase column), `run-cli-6.ps1` (baseline then 6 games then 6 agents), `IDE-CHECKLIST.md`.

Done when: `sample-os.ps1 -OutDir $env:TEMP\os-phase -Phase baseline -Once` writes header + one row with `phase=baseline` and a numeric `cpu_load_pct`.

### Phase 3 — Lane B runner + attribute.ps1

Rewrite `run-game.ps1`; add `usage/attribute.ps1`.

Done when: `echo.` piped if needed, `run-game.ps1` creates a game, writes `PASTE.txt` with a real `game_id` and existing `board_path`, writes `manifest.md`, does not prompt for dashboard numbers.

### Phase 4 — CLI dry width 1

From repo root: `.\experiments\composer-load-and-burn\lane-a\run-cli-6.ps1` (default 6 seats, no kill timeout). Optional plumbing check: `-Seats 1` only if you want a single-seat script smoke.

Done when: run dir has `os.csv` with both `baseline` and `hot` rows, `manifest.md` with one `game_id`, `seat-1.log` with an exit code (success or fail is OK). Default `-Seats` remains 6. Do not run width 6.

If the CLI seat starts leftover committee/prompt_test chess instead of the new `game_id`, that is a **fail** — fix isolation (no live `--workspace`, prompt forbids prompt_test) and re-dry once.

---

## Acceptance (orchestrator checks after phase 4)

1. Sampler CSV includes `phase`.
2. Dry CLI `-Seats 1` created a real game and launched one agent.
3. IDE checklist is lead → 6 subs, not six tabs.
4. No dashboard Read-Host meter.
5. `usage/README.md` describes CSV drop.
6. No files outside `$Exp` except `$env:TEMP` sampler smokes.

---

## Estimated duration

- Phase 1 prompts/docs/deletes: 0.5–1 agent-hour
- Phase 2 sampler + CLI + checklist: 1–2 agent-hours
- Phase 3 Lane B + attribute: 0.5–1 agent-hour
- Phase 4 dry `-Seats 1`: 0.5–1 agent-hour (wall clock includes one short chess seat)
- Orchestrator review between phases: 0.25 hour each
