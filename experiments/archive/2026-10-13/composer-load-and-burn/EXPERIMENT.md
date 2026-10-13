# Composer load and burn â€” intent

**Folder:** `experiments/composer-load-and-burn/`  
**Stack:** Cursor Composer, subversions / non-fast. Real **agent vs engine** chess on this harness â€” not toy worker prompts.

Evolves: intent â†’ plan â†’ rebuild scripts/prompts â†’ baseline â†’ run.

---

## Locks (do not reopen in the rebuild)

- **Model:** `composer-2.5` (inscribed). Subversions / non-fast.
- **Opponent:** `random` for this rebuild, dry runs, and default hot runs. A stronger engine is a later operator flag, not this build.
- **Color:** agent White.
- **Idle:** 30 minutes without an accepted move ends the game with no result.
- **Harness wrapper:** `experiments/composer-load-and-burn/bin/ch.ps1` (already works). Do not put `chess-harness` on PATH.
- **Sampler:** WMI/Cim `Win32_Processor.LoadPercentage` (Spanish Windows). Not English `Get-Counter`.
- **OS CSV:** one `os.csv` per run with a `phase` column (`baseline` then `hot`). Baseline length **90 seconds** unless overridden.
- **Lane A players:** 6 simultaneous agent-vs-engine games. IDE also has **one lead** (7 Composer seats).
- **IDE arm:** one pasted lead prompt; the lead spawns 6 subagents. Not six manual tabs.
- **CLI arm:** 6 `agent` processes. Prefer Cursor IDE **closed**. Scripts must not kill Cursor; they record whether `Cursor` processes are present.
- **CLI isolation:** do **not** pass `--workspace` pointing at the live repo (that pulled leftover `prompt_test` committee briefs). Use `--worktree` only. Games live on the harness / live `.chess_harness`; player briefs use **absolute** `board_path` and the full `chess-harness.exe` path.
- **Lane B meter:** Cursor **usage CSV export**, attributed by run manifest time window. Subscription included pool. No manual on-demand typing. Harness never sees Composer tokens.

---

## Lane A â€” PC load (IDE lead+subs vs CLI, real chess)

### Question
Can this machine sustain a **6-wide agent-vs-engine** chess swarm, and how does OS stress differ when:

1. **IDE arm:** Cursor open; **one lead** gets a pasted prompt and **spawns 6 subagents** (â‰ˆ **7** Composer seats: 1 lead + 6 players).
2. **CLI arm:** **6** `agent` CLI workers playing games â€” **prefer Cursor IDE closed** so we learn whether CLI-native swarms free the machine.

Same game shape both arms: White `composer-2.5` vs `random`. Width under test for **players** is **6**; IDE adds the lead on top.

### Baseline (required before every hot run)

Take a short OS sample **before** spawning players so â€œhotâ€ CSV is comparable.

| Arm | Machine state during baseline |
| --- | --- |
| **IDE** | Only **Grok Bot** + **Cursor** open (nothing else heavy). Then start sampler â†’ paste lead prompt â†’ lead spawns 6. |
| **CLI** | Prefer **Cursor fully closed**; Grok Bot OK if needed for ops. Sampler â†’ launch 6 CLI players. If CLI *requires* some Cursor process, document that as a finding (still a result). |

### What success looks like

- OS evidence (CPU/RAM/disk/stability, process working set) for baseline vs hot, IDE vs CLI.
- Whether CLI works with Cursor closed.
- Whether 6 simultaneous agentâ€“engine games stay alive.

### What this lane is not

- Not token economics (Lane B).
- Not six manual IDE tabs.
- Not scratch-file busywork.

### Shared chess-stack cost (read this before generalizing)

Hot OS samples are **agents + harness + Stockfish** (and tunnel if up), not agents alone. CLI vs IDE stays fair when both arms use the same chess stack. Do **not** later read "this machine fits X agents" onto a non-chess job from Lane A peaks — that X was carrying engine/harness load too. Right now even with opponent `random`, Stockfish processes are still alive on the box (calibration / analysis); a stronger engine would weigh more.

### Process tree (CLI launched from Grok Bot)

Task Manager may nest CLI `agent` seats under **Grok Bot.exe** when this chat starts the run — that is Windows parentage (Shell host → `run-cli-6.ps1` → `agent.cmd` → `node`), not the seats running inside the IDE. The binaries are still Cursor **CLI** (`agent -p`), and Cursor IDE process count can stay 0. Extra cost vs a double-clicked terminal: Grok Bot's own processes sit in the tree. For CLI↔IDE, compare agent/node load and keep that launcher caveat labeled; do not read "under Grok Bot" as "this was an IDE Composer run."

### Concurrency tapers

Six-wide is a **peak at the start**, not a guarantee for the whole wall-clock. Seats finish (or die) at different times, so machine load falls as games complete. Read `os.csv` `proc_count_agentish` / node counts over time and seat exit times in `summary.md`; report minutes-at-N-concurrent (or a simple timeline), not only the opening peak. Same taper applies to the IDE arm.

---

## Lane B â€” tokens / burn per chess game

### Question
For Composer playing harness chess (agent vs engine), what is a usable ballpark of **tokens (and related usage)** per move / per game from **real Cursor usage export data**.

### Meter

- **Primary:** After sealed runs, Jordi exports the Cursor usage CSV and drops it in `usage/exports/`. Attribute rows using time windows + model + `runs/<stamp>/manifest.md`.
- **Not:** Manual dashboard fields. Jordi does **not** use on-demand.
- **Not:** Pretending the harness sees Composer tokens.
- Optional later: local/CLI usage surfaces if they appear. CSV is enough to proceed.

### Run shape
Same real games as Lane A (or a smaller sealed set). Record `run_id`, `game_id`s, start/end local timestamps (Europe/Madrid) in `manifest.md`.

### What success looks like
Attributed token (or export-native usage) totals per game / per move band â€” labeled as export-derived, with caveats (other Cursor activity in-window, lead vs sub rows on IDE arm). If the CSV cannot split lead vs players, report **pool burn for the window** and per-game = window_total / 6 as a labeled estimate.

---

### CLI migration / continue-until-done (locked 2026-09-11)

If we migrate long jobs (chess swarms, DDP seats) to **CLI `agent -p`** with Cursor closed for performance: do **not** assume the same visible player brief behaves like IDE Composer. Harden prompts so agents **must continue until the task/game is fully done** — ban mid-run wrap-ups like "say if you want to continue." Same user file is not enough if CLI/IDE inject different hidden context; for chess CLI especially, hammer play-through-to-`game_over` (and consider an outer continue loop as backup).

## Relationship

Lane A is PC survivability (OS sampler + baseline). Lane B is usage/tokens per game (CSV export). Same chess shape. Separate meters. Separate writeups.

---

## Status

Rebuild landed 2026-09-10. Tree matches locked design (lead+6 IDE, CLI Cursor-closed preferred, real chess, CSV Lane B). Sampler/ch/
ew smoke OK. Next: CLI `-Seats 1` with a real agent (costs Composer), then full 6 when ready.
