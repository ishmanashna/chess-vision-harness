# Run record contract (version 1)

`manifest.json` identifies one immutable run configuration: experiment/run IDs,
hypothesis, code revision and dirty state, provider/model/effort, observation mode,
opponents/colors/seed, prompt/config SHA-256 hashes, synthetic flag, timestamps,
status, reason, last progress, and relative artifact locations.

Status transitions: `running` to `completed`, `failed`, or `abandoned`. Completion
requires a reason and operational summary. The run directory cannot be reused.

`events.jsonl` is UTF-8 JSON, one append-only object per line. Every event contains:

| Field | Meaning |
|---|---|
| `schema_version` | `1` |
| `ts` | UTC ISO-8601 timestamp |
| `event` | Transition name, such as `run_started`, `seat_started`, `heartbeat`, `run_finished` |
| `experiment_id`, `run_id` | Join keys matching the manifest |
| `model`, `provider` | Declared execution identity |
| `seat_id`, `game_id` | Optional IDs linking progress to existing harness records |
| `phase` | Optional short execution stage |
| `reason` | Optional non-sensitive completion/failure/retry description |
| `retry_count`, `rate_limited` | Optional retry/rate-limit evidence, when observed |
| `usage` | Optional provider-reported usage; omit when unavailable |

Each written event updates `last_progress_at` in the manifest. A future monitor may
combine this with the experiment's declared heartbeat interval to detect stalls;
the helper itself does not run a background heartbeat or classify live processes.

Default manifest usage is `{ "tokens": null, "cost_usd": null, "source": "unavailable" }`.
Never infer zero tokens from missing measurements. Later telemetry work can add
durations and measured usage without replacing this event stream.

Only pass public-safe diagnostics into `reason` or `usage`. No request headers,
provider keys, raw prompt dumps, session tokens, or automatic environment capture.
The logger uses the native runner's existing event key names, but does not modify
or ingest its historical logs in this batch.
