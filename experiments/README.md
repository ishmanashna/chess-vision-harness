# Experiments

This directory contains the foundation for future experiments and an archive of old
runs. Experiment tooling is separate from the public product and rated ladder.

## Current status

- **Active experiments:** none found during the 2026-10-13 archive check. No matching
  experiment launcher/keepalive processes, scheduled experiment tasks, or in-progress
  harness games were found. This is a dated observation, not a live status display.
- **Historical experiments:** [2026-10-13 archive](archive/2026-10-13/README.md).
  The eight old folders were moved with their contents intact. Research questions may
  remain unanswered; archiving does not imply a successful or completed study.
- **Future work:** copy [template](template/README.md), reuse [run_record.py](run_record.py),
  and implement the actual provider interaction in the experiment's own launcher.

## Small shared contract

Each run produces `manifest.json`, `events.jsonl`, and `report.md` under an ignored
`runs/<run-id>/` directory. Metadata records the hypothesis, code revision, model and
provider settings, observation mode, prompt/config hashes, opponent slate, and outcome.
Events join a run to its seats/games and record progress and failure reasons.
See the [event contract](template/EVENTS.md) and [example manifest](template/manifest.example.json).

Keep provider-specific launchers small. There is no Cursor/OpenCode integration or
experiment executor in this foundation. Ops monitoring/filtering is a later batch.
The native runner's existing `ts`, `event`, `game_id`, `model`, and `provider` log keys
are retained in the shared event shape; do not build a second game database.

## Offline smoke

From the repo root:

```powershell
python experiments/template/run.py --run-id demo-001
```

This creates an explicitly synthetic run, without HTTP, engines, model calls, or
agent applications. Rerunning the same ID fails rather than overwriting evidence.
Use another ID or `--output-root <directory>` for a temporary smoke destination.

## Evidence and privacy

- Runtime output, raw prompts, credentials, and provider logs stay ignored. Never copy
  API keys or full environment dumps into metadata/events/reports.
- Commit reviewed summaries and non-sensitive reproduction settings deliberately.
  Configuration hashing does not make a credential safe to publish.
- Report exclusions, missing usage, and incomplete runs explicitly. A process exit or
  scored game alone does not prove an experiment's hypothesis.
- Archive by moving evidence with a path mapping and closure note. Do not remove the
  harness's game records, results, or finished-games SQLite to clean up experiments.
- Archived scripts are historical evidence, not supported launch commands. Their
  original absolute/relative paths are intentionally preserved inside the evidence.
