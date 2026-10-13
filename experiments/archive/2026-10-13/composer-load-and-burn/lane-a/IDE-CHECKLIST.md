# Lane A IDE arm - operator checklist

Manual steps for the **IDE** load arm: **one** Composer lead spawns 6 subagents (7 Composer seats total). Not six manual tabs.

All paths are under `experiments/composer-load-and-burn/`. Run commands from **repo root**.

---

## Before you start

1. Close everything heavy except **Grok Bot** + **Cursor**.
2. Choose a run stamp (e.g. `20260910-220000`) or let the clock pick one when you create the folder.
3. Create the run directory:
   ```
   experiments\composer-load-and-burn\lane-a\runs\<stamp>\
   ```

---

## 1. Baseline sampler

From repo root, in a dedicated terminal (wait until it finishes):

```powershell
.\experiments\composer-load-and-burn\lane-a\sample-os.ps1 -OutDir experiments\composer-load-and-burn\lane-a\runs\<stamp> -IntervalSec 5 -Phase baseline -DurationSec 90
```

---

## 2. Hot sampler

In another terminal, start the hot sampler and **leave it running**:

```powershell
.\experiments\composer-load-and-burn\lane-a\sample-os.ps1 -OutDir experiments\composer-load-and-burn\lane-a\runs\<stamp> -IntervalSec 5 -Phase hot
```

Note the sampler process PID (Task Manager or `Get-Process`).

---

## 3. Paste the lead prompt

Open **one** new Composer chat in this repo. Do **not** continue a chess or prompt-test thread.

Paste **all** of:

`experiments/composer-load-and-burn/prompts/lane-a-lead.txt`

The lead will check harness health, create 6 games, spawn 6 Composer 2.5 subagents, and report results. You do **not** open six tabs or paste player prompts yourself.

---

## 4. Wait

Wait until the lead reports all six games finished or failed.

---

## 5. Stop hot sampler

Stop the hot sampler terminal with **Ctrl+C**, or kill the sampler PID from step 2.

---

## 6. Write manifest

Create `experiments/composer-load-and-burn/lane-a/runs/<stamp>/manifest.md` with:

- **arm:** IDE
- **start / end:** Europe/Madrid local times (baseline start through lead finish)
- **seats:** 7 (1 lead + 6 players)
- **game_ids:** from the lead's report table
- **board_paths:** if the lead reported them
- Note: one lead paste, not six tabs

Glance at `os.csv` in the same directory (baseline rows then hot rows).

---

## Compare arms later

| Arm | How started |
| --- | --- |
| **CLI** | `.\experiments\composer-load-and-burn\lane-a\run-cli-6.ps1` |
| **IDE** | This checklist |

Same game shape (White `composer-2.5` vs `random`), same sampler script - compare `os.csv` and stability.

## 7. Summarize OS samples

From repo root:

```powershell
.\experiments\composer-load-and-burn\lane-a\summarize-os.ps1 -RunDir experiments\composer-load-and-burn\lane-a\runs\<stamp>
```

Writes `os-summary.md` (baseline vs hot means/max + deltas). Use that when comparing IDE vs CLI.
