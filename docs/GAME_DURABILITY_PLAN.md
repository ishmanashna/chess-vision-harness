# Game durability & recovery plan

Finished agent games (AvE / AvA / AvH) get a **permanent centralized SQLite database** at end of game. Live play stays on the filesystem (`games/<id>/state.json`, PNG, PGN). The DB is the forever record; delete/prune/remove of live files must not erase it.

Calibration games stay out of this DB (they remain under `elo_calibration/`).

## Problem

Live data is only under `.chess_harness/games/` + `results.jsonl`. Hard delete is permanent. Soft-delete/trash fails when a deleter never uses it. Durability must not depend on agent discipline.

## Solution

**SQLite database, dual-written at scored finish, tracked in git.**

| Layer | Role |
|-------|------|
| Live filesystem | In-progress + operator convenience (boards, locks, spectator) |
| `results.jsonl` + `models.json` | Current ladder / quality aggregates (unchanged for now) |
| **Finished-games SQLite** | Permanent store of finished-game facts (no PNGs) |

- Written automatically by the harness on scored finish — not an optional archive step.
- Official delete/prune/remove/reset of **live** data never `DELETE`s from this DB (no API for agents to wipe history).
- Path lives **outside** `.chess_harness/` so harness wipe and gitignore of runtime data do not drop it.
- **Git tracks the DB file** (do not ignore it). Operators commit periodically so GitHub holds history; expect binary diffs / occasional larger commits.

## Scope

- Schema + write path on scored finish (all agent modes).
- One-time (and repeatable) import of **current** live finished games into the DB.
- Git: DB path committed; `.gitignore` must not exclude it.
- Operator restore: rebuild live game dir + results row from a DB row when needed.
- Prune stays `result == "*"` only for live cleanup.

## Out of scope

- Soft-delete / trash as the durability mechanism.
- Storing board PNGs in the DB.
- Calibration / engine-vs-engine rows in this DB.
- Replacing `results.jsonl` as the live Elo source in this plan (DB is durability + recovery; ladder can keep reading JSONL until a later migration).
- Off-site cloud backup beyond GitHub’s copy of the committed DB.
- Stopping a process with full disk access from deleting the DB file on disk (git history still retains last pushed version).

## Location & git

- Default path: `data/finished_games.sqlite` (repo-relative; new `data/` dir is fine under ARCHITECTURE layout rules).
- Override: `CHESS_HARNESS_FINISHED_DB` for local experiments only; production/operator default is the tracked path.
- Ensure no `.gitignore` (root or subdirectory) ignores `data/finished_games.sqlite` or `data/*.sqlite`.
- Seed empty DB or create on first serve/finish; after import of current games, **commit the file**.

## What gets stored (no PNGs)

Per finished scored game (`result` not `*`):

- Identity: `game_id`, `game_type`, timestamps, end reason, result
- Players: model ids / display names, colors, human nickname when AvH, opponent id/elo when AvE
- Moves: UCI list (and/or full PGN text)
- Final FEN, plies, PGN headers JSON
- Quality: accuracies, estimated Elo / play ratings, quality meta when present
- Ladder deltas if present on state/results
- Raw `state.json` snapshot (JSON text) for lossless recovery of fields not yet columnar
- Optional: results.jsonl row(s) JSON for that game_id

Board PNGs stay filesystem-only.

## Phase 1 — Schema, dual-write, git path

- Add finished-games SQLite module (connect, migrate schema, upsert by `game_id`).
- Hook after successful scored finish (shared helper from finish / `append_result` choke point for AvE, AvA, AvH, resign, mate, draw).
- Skip `result == "*"`.
- Idempotent upsert on `game_id`.
- Create `data/` + ensure DB is not gitignored; document commit expectation.
- Done when: finishing a scored game upserts a row; live `delete_game` leaves the row; focused tests cover write + survive delete; `git check-ignore` does not match the DB path.

## Phase 2 — Import current games

- Operator/CLI: `chess-harness finished-db import-live` (name flexible) scans `.chess_harness/games/*/state.json` for finished scored games, upserts each, and merges matching `results.jsonl` rows.
- Run once on this machine against current games; commit the resulting `data/finished_games.sqlite`.
- Done when: every current finished scored game is in the DB; re-import is idempotent; focused test with a temp harness dir imports two fixtures.

## Phase 3 — Restore + operator note

- `chess-harness finished-db list` / `finished-db restore <game_id>`: recreate live `games/<id>/` from stored state + PGN text, merge results row if missing, rebuild-elo + leaderboard snapshot. Do not invent PNGs (re-render board from FEN on next view/serve if needed).
- Short operator note: DB path, git tracking, import, restore after accidental live delete; prune/remove do not touch the DB.
- Done when: delete live scored game → restore from DB → appears on Completed again; note exists; focused CLI tests pass.

## Order

1 → 2 → 3 (import before relying on restore in production use).

## Verify

- Finish game → delete live dir → row still in SQLite → restore → Completed + results.
- Import of current tree matches game_id set of finished scored live games.
- DB file is tracked (`git status` shows it; not ignored).
- Focused tests only.

## Estimated duration

- Phase 1 — Schema, dual-write, git path: 2–3.5 agent-hours
- Phase 2 — Import current games: 0.75–1.5 agent-hours
- Phase 3 — Restore + operator note: 1–2 agent-hours
