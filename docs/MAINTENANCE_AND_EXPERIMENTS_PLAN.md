# Maintenance, Ops, and future experiments

Status: Batches 1–2 complete locally (2026-10-13); Batches 3–7 planned. Not published.
Decisions: Jordi, 2026-10-13, following the repository audit and questionnaire.

## Outcome

Make the homepage reflect Performance, make Ops useful for monitoring and reviewing
runs, archive inactive experiments, and leave a small reusable foundation for future
experiments. Add engine annotations to spectator moves. Work in small, independently
reviewable batches, with a working site after each batch.

This document is the implementation plan for this maintenance pass. Existing product
roadmap items are reconciled during the documentation batch rather than implicitly
reopened by this plan.

## Accepted decisions

- Home: put Show all beside the Benchmark heading, right-aligned.
- Remove the game Elo column from Home. Performance becomes the main ranking metric.
- Keep game Elo on Leaderboards and in the underlying game/rating system.
- Use **Performance** consistently for the accuracy-derived strength estimate.
- Keep the current two-column Home on wide screens where it fits. On narrower screens,
  put explanatory text above a full-width benchmark. Jordi's desktop screenshot fits;
  do not treat that layout as broken or redesign it unnecessarily.
- Preserve Accuracy, Puzzles, Games, cost, and AA Index on Home. Removing those columns
  was not selected.
- Archive inactive experiments rather than finishing them. Create basic scaffolding
  for future experiments; no Cursor or OpenCode launch/keepalive integrations.
- Ops is for monitoring, filters, results, and log links. Experiment execution remains
  outside the panel. Existing Go Online/Sleep controls remain operational controls.
- Share run metadata and tracking while allowing provider-specific launchers.
- Spectator annotations: engine move labels and evaluation changes, without best-move
  alternatives or suggested lines.
- Maintain one active backlog; archive superseded plans while preserving history.
- Keep existing model/effort/observation identities for now.
- No priority preference between workstreams. The sequence below is a practical
  default; dependencies and independent review matter more than the order.

## Evidence and limits of the audit

- Ops rendered Overview, Traffic, Machine, and A/B during inspection. It is partially
  functional; individual failures and omissions need fixing rather than replacement.
- A/B pack totals default to Composer while the games list includes Jeff runs.
- The running server reports Umami audience configuration missing.
- Machine reports saved tunnel PID/URL files, without proving tunnel reachability.
- Desktop Go Online does not populate the Ops job state.
- Ops refresh fetches hidden-section data and waits on a combined request group.
- Local Home HTML, common.js, and site.css matched the checkout byte-for-byte.
  A general localhost version lag was not reproduced. Local and public Home have the
  same columns and expansion control; investigate specific differences if reproduced.
- Home overflow appeared at narrower audit viewports; Jordi supplied a wide desktop
  screenshot where the complete table fits.
- Root-layout validation fails on current root files, including .gitignore and
  OPENQUESTIONS.md. The line-limit validator reports 62 files over 300 lines.
- Native provider runners, static watch/play shells, calibration worker separation,
  backups, and finished-game recovery already have implementations. Old plans are not
  proof that these features still need building.
- The audit did not run the full test suite or establish backup scheduling/restore
  readiness. Those remain validation tasks, not confirmed outages.

## Batch 1 — Home and metric naming

Status: complete locally, 2026-10-13.

Work:

- Give Benchmark a heading/control row. Keep the 15-row preview and the dynamic total;
  Show all / Show first 15 stay in that row and expose expansion state accessibly.
- Remove only Home's game Elo column and provisional-Elo tooltip from its table.
- Default Home sorting to descending Performance (`mean_play_rating`). Migrate saved
  Home Elo sorting to Performance; preserve other valid user-selected sorts and keep
  Leaderboards sort preferences independent. Put missing Performance values last.
- Keep API field names and rating calculations intact. Update Home column counts,
  empty states, table labels, and explanatory copy to match the new presentation.
- Rename user-facing Strength / Play rating references to Performance where they mean
  the accuracy-derived metric; distinguish this from game Elo and puzzle ratings.
- Correct copy that confuses approximate convergence with the actual 100-rated-game
  provisional rule. Avoid claiming the Performance estimate is an official human rating.
- Switch to text-above/full-width-table layout at a content-tested breakpoint. Contain
  any remaining very-small-screen table scroll within the table, not the whole page.
- Fix confirmed text-encoding artifacts such as the footer's broken middle dot.

Done when:

- Home has no game Elo column, starts sorted by Performance, and has the chosen control
  placement; Leaderboards still shows Elo.
- Wide-screen proportions remain familiar. Check approximately 1768, 1440, 1280, 1024,
  768, and 390 CSS-pixel widths in light/dark themes, collapsed and expanded.
- Snapshot-first and live-upgrade paths render the same columns and sorting behavior;
  legacy saved sorts and missing metrics behave correctly.

Verification: 15 targeted Python tests and 22 JavaScript tests passed. Browser checks
at 1768, 1440, 1280, 1024, 768, and 390 CSS pixels covered light/dark themes and
expansion/collapse. No page-wide horizontal overflow; the table scrolls internally
when needed. The layout stacks at 1500px and below. Desktop and stacked preview
screenshots were saved with this chat's artifacts. Public deployment remains pending.

## Batch 2 — Archive inactive experiments and add basic scaffolding

Status: complete locally, 2026-10-13.

Work:

- Inventory the eight experiment directories, current processes/seats, durable game
  records, and tracked/ignored artifacts. Classify each run active or inactive from
  evidence; old timestamps alone do not establish inactivity.
- Archive inactive Composer load-and-burn, prompt-pack, Jeff, InferX, Muse, and MiMo
  material with original run IDs, scripts, reports, and a brief closure/status note.
  Unfinished runs may be archived as incomplete; do not spend tokens completing them.
- Keep running seats and their referenced paths intact until they finish or are
  separately stopped. Preserve uncommitted work and archive mappings so old links and
  report references can be understood. Keep secret-bearing runtime material ignored;
  moving it must not accidentally make it trackable.
- Retire Cursor/OpenCode launcher and keepalive code into the historical archive.
  The new active scaffold has no dependency on either tool.
- Create an experiments README/index and a small template with a brief, example
  manifest, event-format documentation, and report template. Reuse standard-library
  tooling and existing runner logging where practical; no new experiment framework.
- Shared metadata: schema version, experiment/run IDs, hypothesis, code revision,
  provider/model/effort, observation mode, prompt/config hashes, opponent slate,
  colors/seeds where relevant, start/end timestamps, status, and artifact locations.
- Shared events: run/seat/game IDs, timestamp, phase, last progress, completion/failure
  reason, and retry/rate-limit information. Tokens and costs are optional with an
  explicit unavailable state; never invent provider usage.
- Keep generated logs/results ignored by default. Preserve reviewed summaries and
  reproducibility metadata without credentials, private briefs, or raw tokens.

Done when:

- The active experiments index clearly separates running work, archived history, and
  the future template. Inactive runs no longer appear as unfinished active projects.
- One offline dummy run produces valid metadata, a short event stream, and a report
  through the template. No paid API calls or external agent applications are required.

Verification: no matching launcher/keepalive processes, scheduled experiment tasks,
or in-progress harness game states were found. All eight folders moved to
`experiments/archive/2026-10-13/`; all 1,575 original files passed SHA-256 checks.
The 41 previously tracked source/doc files remain trackable and 1,534 private/runtime
originals remain ignored. Machine-specific launch notes were separately preserved.
Twelve focused tests passed, covering metadata/hashes, progress, terminal states,
path isolation, duplicate IDs, and the offline example. The ignored demonstration
run produced manifest.json, events.jsonl, and report.md without provider calls.
The shared game store, results, ratings, and finished-games SQLite were not moved.

## Batch 3 — Ops experiment results and loading

Work:

- Make family filtering consistent across packs, games, and related chat/results.
  Expose Composer/Jeff selection so legacy results remain inspectable.
- Add run/model/pack/opponent/status filters as supported by the available metadata.
  Use explicit legacy/unassigned grouping for old data without run IDs; do not silently
  treat lifetime aggregates or the latest 40 games as a controlled experiment.
- Show finished, live, failed, abandoned, and excluded counts, sample sizes, data
  freshness, and a concise reason for missing metrics.
- Link runs to their reports and safe log views. Do not expose credentials or add
  experiment launch/pause/resume controls.
- Fetch A/B and audience data when their sections are visible. Give sections their
  own loading/error states, bounded requests, and protection against overlapping polls.
- Separate operator polling, health probes, static requests, and agent/product traffic.
  Keep the existing origin-versus-site-visitors distinction.
- Provide a clear Umami setup/diagnostic state. Reuse an existing setup if available;
  do not create accounts, guess credentials, or present missing data as zero visitors.

Done when:

- Summary totals and game rows agree for the selected family/run. Legacy Jeff runs are
  reachable from the UI. Filtering does not cross-contaminate experiments.
- A slow or failed audience/A/B endpoint does not prevent Overview from updating.
- Ops remains useful with Umami unset and when no runs are active.

## Batch 4 — Ops health and shared Go Online status

Work:

- Report actual local, tunnel, and Pages health checks with timestamps, timeouts, and
  stale/unknown states. Distinguish a tracked PID from a verified running tunnel.
- Have Desktop and Ops Go Online publish the same operation ID, phases, completion,
  failure reason, and log tail. Keep the GitHub retry fix from the earlier repair.
- Prevent simultaneous Desktop/panel operations from competing over the tunnel.
- Preserve localhost serve during public recovery and Sleep. Report relevant runtime
  paths/configuration without secrets so environment mismatches are diagnosable.

Done when:

- Desktop-started recovery appears in Ops; a failed GitHub step remains inspectable.
- Saved stale files cannot produce a healthy tunnel indicator.
- Validate failure handling with fakes/local fixtures; schedule any live Sleep/recovery
  smoke so it does not interrupt an active game or experiment.

## Batch 5 — Spectator move annotations

Work:

- Persist per-ply engine analysis sufficient for move-quality labels and evaluation
  changes. Record engine/version/settings and analysis status for reproducibility.
- Reuse current quality analysis where possible; avoid an engine run on every poll.
- Attach labels to moves in the spectator list and synchronize evaluation details with
  replay. Define thresholds centrally and use both text and color for clarity.
- Show pending/unavailable analysis honestly. Limit the first version to finished
  games; historical games can be analysed explicitly or in a bounded background queue.
- Do not show alternative moves, suggested lines, or AI prose. Existing right-click
  arrows stay separate from engine move annotations.
- Keep analysis on the spectator/operator surface; agent observations and active-game
  play contracts must not gain engine information.

Done when:

- A finished game shows reproducible move labels and evaluation changes while
  scrubbing; missing analysis is handled without blocking replay.
- Focused tests cover move-to-ply alignment, mate scores, both colors, and missing data.
- No alternative lines appear and agent API payloads remain unchanged.

## Batch 6 — Active backlog, parity, and useful validation

Work:

- Establish one active backlog with status, scope, acceptance criteria, dependencies,
  and links to evidence. Reconcile this plan with the numbered roadmap.
- Mark old plans shipped, partial, superseded, or parked after checking implementation.
  Archive superseded plans and update the documentation index and incoming links.
- Keep model identity and assistance-policy decisions parked; do not change them here.
- Add build/revision and start-time diagnostics for the local server/public deployment.
  Document intentional localhost-only differences and smoke-test shared page behavior.
- Reconcile root-layout checks with actual conventions. Preserve useful files such as
  OPENQUESTIONS.md; remove scratch clutter only after establishing what is disposable.
- Make lint/syntax/tests cover shipped public-site JS and Functions, not just the TS
  scaffold. Wire existing JS tests into CI and add a small shared-page smoke check.
- Resolve the line-limit policy explicitly. Refactor touched code by responsibility;
  track remaining hotspots rather than mechanically splitting 62 files at once.
- Move cost/AA mappings into dated metadata with provenance and assumptions, preserving
  current values during extraction. Refreshing external numbers is a separate task.

Done when:

- The index points to a trustworthy active backlog; shipped features are not scheduled
  for rebuilding. Current checks have clear, useful pass/fail meaning.
- Shared-page parity can be checked without guessing whether a process or asset is old.

## Batch 7 — Minimal telemetry and durability verification

Work:

- Add provider-call and total-turn durations, accepted-move timestamps, retries, rejected
  moves, and optional reported usage to shared run events. Separate harness latency
  from provider time; distinguish tool calls from complete agent turns.
- Show last progress, stalled seats, and basic timing summaries in Ops. Reuse this
  pass's metadata rather than creating a second telemetry system.
- Verify backup configuration, cadence, retention, off-PC coverage, and a restore into
  an isolated directory. Never overwrite live runtime data during the drill.
- Document Sleeping snapshot publication and expose snapshot age. Record unresolved
  operational setup in the active backlog rather than claiming it is already configured.

Done when:

- A dummy or existing-run fixture demonstrates a stall, failure, and successful finish
  with timings. Missing usage stays visibly unavailable.
- A restore drill has recorded evidence, and backup/snapshot responsibilities are clear.

## Delivery rules

- Implement one batch at a time; split a batch further if it cannot be reviewed cleanly.
- Each batch reports changes, targeted verification, and remaining limitations. Include
  screenshots for visible changes. Broaden tests only for changes that warrant it.
- Preserve unrelated working-tree edits. Plan writing does not authorize API spending,
  launching experiments, stopping active seats, or publishing implementation changes.
- No framework migration, product rename, leaderboard identity changes, new matchmaking,
  tutor feature, or wholesale refactor is part of this maintenance pass.
