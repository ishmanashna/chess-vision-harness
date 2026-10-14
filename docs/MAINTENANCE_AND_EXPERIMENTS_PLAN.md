# Maintenance, Ops, and future experiments

Status: Batches 1–5 implemented (2026-10-13); Batches 6–8 planned. Frontend deployment evidence is recorded per batch below; Batches 3–5 backend activation still pending localhost restart.
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
screenshots were saved with this chat's artifacts. Public deployment succeeded on
2026-10-13: GitHub Actions run 38403378869 deployed source commit 232da64. Public
Home was checked in the browser and localhost/tunnel/Pages health probes passed.

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

Status: implemented and verified in an isolated read-only preview, 2026-10-13.
Automatic approval review blocked restarting the serving process ("blocked by policy");
the running server remains unchanged. Restart localhost to activate the new backend.
The restart was attempted again after Jordi explicitly authorized it on 2026-10-13;
automatic approval review again returned only "blocked by policy". All four maintenance
commits were pushed to origin/main and the public frontend deployment succeeded.

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

Verification: 85 targeted Python tests (including proxy protection) and 17 JavaScript
tests passed. The preview's Composer selection contains 75 games; Jeff contains 135
with explicit 100-game pagination. Selecting J1 produces one pack and 15 matching
games, including 14 analysed finishes; summary and game selections agree. Tests cover
deduplication, stale live states, exclusions/missing metrics, filtering, pagination,
safe artifact fields, loopback locks, and overlapping/hung requests. A/B, audience,
and full inbox load on demand; snapshot updates independently. New run links expose
allowlisted operational reports/events only, not raw report.md or private logs.
The A/B UI detects the old running backend and explains the required restart.

## Batch 4 — Ops health and shared Go Online status

Status: implemented and verified in an isolated read-only preview, 2026-10-13.
Backend activation still requires the localhost restart already noted in Batch 3.
Public frontend deployment succeeded: GitHub Actions run 38430379130 (4470b0e).


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

Verification: 42 targeted Python tests and five Ops JavaScript tests passed, along
with the existing offline GitHub retry regression script. Windows PowerShell and
Python exercised the same exclusive lock, live desktop record, interrupted operation,
launcher success and GitHub failure, and persistence across fresh Ops instances.
No real recovery, Sleep, server restart, or paid provider call was used in validation.
Health checks cover bounded reads/timeouts, offline payloads, invalid saved URLs,
stale PIDs, cached/single-flight refresh, and loopback access. Sleep checks verify
process identity, preserve tracking on a failed stop, and clear stale URL files.
The Machine preview was checked at 1440px and 390px with no page-wide overflow;
a screenshot shows a clearly labeled offline desktop failure fixture. Actual localhost
and public Pages edge-health both reported healthy during read-only checks.

Desktop and panel operations now share logs/go-online-status.json and an OS-held
logs/go-online.lock; a crashed process releases the lock automatically. The bounded
log view reads the last 16 KiB / 40 lines of go-online-transcript.log. Operations
respect CHESS_HARNESS_DIR, and Ops reports runtime/log paths. Actual reachability
probes have four-second socket timeouts, refresh independently in the background,
and expose unknown/stale results without blocking the main snapshot. The probe
identifies itself as ChessVisionHarness-Ops/1.0; the default Python user agent was
rejected by the public edge during validation. Operational POSTs and status polling
now use the bounded request helper, and desktop operations are discovered on every
normal Ops refresh. The shared operation card stays visible across sections.

## Batch 5 — Spectator move annotations

Status: implemented and verified in an isolated finished-game preview, 2026-10-13.
The localhost backend restart remains pending under the existing approval-review block.
Public frontend deployment succeeded: GitHub Actions run 38434166644 (4575101).


Dependency boundary: implement versioned annotation storage and a bounded finished-game
example here. Batch 8 owns analysis-budget validation, broad historical reanalysis,
and migration of published Accuracy/Performance. Avoid an unversioned bulk backfill
here that would have to be repeated after the analysis profile changes.

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

Verification: 52 targeted Python tests passed and one pre-existing Stockfish test
was skipped because its test-specific binary path was absent. Six JavaScript tests
passed, including hung response-body timeout and missing-data handling. The actual
repository Stockfish 17.1 binary analysed a seven-ply offline Scholar's Mate example
in an isolated temporary directory; no production game, calibration map, or ladder
was reanalysed or updated. Browser checks covered replay selection, typed mate scores,
text/color labels, 1768px desktop and 390px narrow layouts. Narrow-screen grid overflow
was corrected within the game view. The preview produced no browser runtime errors.

The existing quality pass now captures before/after scores and mover win-chance loss
without another engine search. Finished-game jobs atomically save move-analysis.json
with schema/formula/label versions, a move-sequence fingerprint, engine identity and
binary hash, network identifier, configured depth, default threads/hash settings,
strength-limit flag, timestamp and completion status. Per-move labels use mover
win-chance loss: Good below 5 pp, Inaccuracy from 5 pp, Mistake from 10 pp, Blunder
above 30 pp. These are estimated labels under an explicitly unvalidated analysis
budget; changing the evaluator or formula remains Batch 8 work.

The spectator-only annotations endpoint validates the schema, exact move alignment,
starting position and completion, and projects allowlisted fields without engine PVs
or candidate moves. Live games receive no annotations. Packed-game visibility is
preserved. Saved analysis stays outside agent state/payloads. The move list uses
explicit ply identifiers, including black-to-move setup positions; scrubbing uses the
saved evaluations locally and cancels stale network-evaluation updates. Annotation
loading is independent of board loading with a four-second deadline. Missing or
incomplete analysis is reported honestly; legacy games await the later backfill.
Existing right-click board arrows remain separate and unchanged. Follow-up presentation
correction: use conventional inline ?!, ?, and ?? suffixes for inaccuracies, mistakes,
and blunders. Ordinary good moves are unmarked. Remove the visible annotation legend;
keep classification/provenance in hover text. On the next follow-up, replace the
selected-move evaluation paragraph with a small after-move number beside each move
(White's perspective). Implement positive annotations now using the explicit policy
below; broader analysis/calibration migration remains Batch 8.

Positive annotations follow-up (2026-10-13): use the publicly documented concepts
from [Chess.com's move classifications](https://support.chess.com/en/articles/8572705-how-are-moves-classified-what-is-a-blunder-or-brilliant-etc):
critical continuations for !, and sound piece sacrifices for !!. Its complete
classification algorithm is not published. The following thresholds are our own
conservative, rating-independent policy, not a reproduction of proprietary code.

- Inspect legal captures and recaptures on the offered piece's square. A bounded
  material-exchange tree (pawn 100, minor 300, rook 500, queen 900) must find a net
  offer of at least 150 cp for !!. Pawn offers, equal trades and illegal pinned
  captures do not qualify; an exhausted exchange-tree budget is unknown.
- Compare the engine's two strongest continuations privately, in two bounded passes:
  target depth 18 / 0.2s and depth 22 / 0.8s per candidate. Require actual depths at
  least 14 and 18 respectively, no bound-only scores, and the played move must remain
  first in both passes. Lower-depth/time-limited or unstable evidence produces no
  positive symbol. No candidate moves or variations are published.
- Both passes must leave the mover at least 45% on the documented evaluation-to-chance
  scale, while the second continuation is below 85%. This rejects unsound sacrifices
  and positions where alternatives already clearly win. For !, also require a gap
  of at least 10 percentage points, with the alternative below 70%. For !!, require
  the verified material sacrifice instead. Both passes must agree on the category.
  Positions with only one legal move are excluded. These chance values are analysis
  heuristics, not claims about a particular human player's actual winning probability.
- Positive review runs only in finished-game jobs, after the complete legacy quality
  evaluation pass. It cannot warm engine hashes during Accuracy computation; existing
  Accuracy/Performance formulas and map inputs stay unchanged. Calibration and live
  provisional analysis do not request the extra searches. Additional work is bounded
  per candidate; CPU cost still belongs in Batch 8's resource/stability benchmark.
- Persist detector version, search budgets and actual verification depths, score-gap
  evidence and estimated sacrifice value. Publish only projected numeric evidence;
  preserve old analysis artifacts and wait for explicit historical backfill.

Verification of this follow-up: 54 targeted Python tests passed, one existing test
skipped, and seven JavaScript tests passed. Tests include both colors, sound/unsound
criteria, equal trades, pinned captures, forced moves, insufficient depths, unstable
choices, engine timeouts, no variation disclosure, and separation from quality
calculation. A real Stockfish smothered-mate position confirmed that a queen offer is
not automatically brilliant when another continuation is also a forced win. The
seven-ply offline game also completed the full real-engine positive-review path while
retaining the same 93.98% / 96.32% Accuracy values. Finished games with provisional
quality remain pending until their saved final annotations arrive; polling stays
bounded and replay loading remains independent.

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

## Batch 8 — Spectator speed, analysis reliability, and historical reanalysis

Status: planned, added at Jordi's request on 2026-10-13. Treat depth 8 as a legacy
unvalidated analysis profile; stronger-model comparisons require a stronger reference
benchmark and a reviewed replacement budget, rather than assuming depth 8 is sufficient. Investigation and migration
work are deferred; adding this batch does not start reanalysis or change ratings.

Problem and evidence:

- Completed Spectator currently requests `/api/games?status=finished&limit=100`.
  It does not download the entire archive in that response. However,
  `_build_games_list` calls `game_manager.list_games()`, which reads every game
  state and sorts the entire collection before filtering and slicing. List discovery
  also calls idle-game pruning. These are confirmed scaling risks, not a measured
  attribution of all the reported latency to one cause.
- Quality analysis uses unrestricted-strength Stockfish with a default depth of 8,
  configurable through `QUALITY_STOCKFISH_DEPTH`. `evaluate` uses a depth limit,
  rather than a configured per-position search-time budget. A stronger playing model
  does not itself prove the evaluator is inadequate, but shallow search reliability
  and resolution among high-accuracy games need validation.
- The current Accuracy formula skips moves whose centipawn loss crosses the
  mate-miss sentinel threshold. Batch 5's isolated Scholar's Mate example therefore
  gave Black roughly 96% Accuracy despite a correctly labelled mating blunder.
  Audit mate transitions and excluded-move coverage as part of formula validation;
  increasing search depth alone does not resolve this scoring behavior. Any formula
  change needs its own version and the same calibration/backfill comparison.
- `analyse_game` requests before/after evaluations for every ply, including adjacent
  repeated positions. Provisional and final jobs share an in-process queue with up
  to four concurrent quality slots. Reanalysis cost and contention with live play,
  calibration, public requests, and storage must be measured before increasing work.
- Accuracy-to-Performance is a separately rebuilt monotone calibration map. Quality
  recomputation can change saved Accuracy and Performance; rebuilding the map alone
  must not be assumed to refresh every stored game, result, and published aggregate.
  The map is distinct from outcome-based game Elo and engine calibration Elo.

Work:

- Profile completed-list discovery and opening an individual completed game
  separately: browser waterfall, tunnel/Pages overhead, origin latency, disk reads,
  enrichment, payload size, rendering, cold/warm caches, and concurrent requests.
  Record median/p95 latency on the current archive and a larger offline fixture;
  choose explicit acceptance targets from that baseline.
- Implement bounded, indexed discovery using the existing durable game store where
  practical. Filter/order/page before loading full states or enriching rows. Preserve
  public-versus-packed visibility, ordering, accurate counts, filters, and access to
  games beyond the first 100. Add real navigation rather than silently truncating.
- Audit repeated scans and result/rating reads, idle-pruning on reads, browser polling
  and overlapping requests, replay/evaluation fetches while scrubbing, immutable
  finished-game caching, engine startup costs, and full-history aggregate rebuilds.
  Fix measured bottlenecks; do not assume every suspected issue is an outage.
- Benchmark evaluation stability on a frozen representative sample, including strong
  models, tactical positions, quiet play, long games, mates and endgames, plus the
  engine games used to calibrate the Performance map. Compare increasing budgets
  against a substantially stronger reference pass. Measure evaluation, label,
  Accuracy, and ranking changes alongside runtime, CPU/RAM, and queue age. Do not
  choose a new depth solely because it sounds stronger or promises a human Elo.
- Define a reproducible analysis profile: engine binary/version/hash and network
  identity where applicable, settings, threads/hash, search limits and actual depth/
  nodes/time, score perspective and mate handling, quality-formula version, and
  annotation thresholds. Distinguish a quick provisional profile from authoritative
  final analysis; keep the agents' play/observation contract free of analysis data.
- Persist per-position/per-ply results once and reuse them for Accuracy, move labels,
  replay evaluations, and reports. Evaluate reuse of adjacent/shared positions with
  cache keys covering the complete position/history requirements and analysis profile.
  Record incomplete/failed searches honestly, rather than accepting partial analysis
  as a full authoritative game. Do not analyse again on every spectator request.
- Use a durable, resumable, deduplicated backfill queue with progress, last activity,
  failures/retries, cancellation, and configurable CPU/RAM/concurrency limits. Protect
  live play responsiveness, limit provisional recomputation, and avoid spawning an
  unbounded number of waiting workers. Estimate the whole backfill cost from a pilot.
- Inventory historical PGNs, current analysis settings/coverage, and missing artifacts.
  Select a consistent eligible cohort for agent games and calibration reference games;
  annotate old games using Batch 5's schema without alternative moves or lines.
  Keep original results and analysis available for comparison and rollback.
- Reanalyse the calibration reference cohort with the same authoritative profile as
  the agent cohort, then fit a new version of the Accuracy-to-Performance map using
  frozen, documented reference Elo labels. Validate coverage near the strong-model
  end, held-out calibration behavior, uncertainty, and mapping sensitivity. Do not
  fit the conversion to make selected models obtain desired scores.
- Produce an old/new comparison of per-game metrics, per-model aggregates/rankings,
  annotations, and map knots. Separate effects of stronger analysis from effects of
  refitting the map. Accuracy and Performance may rise or fall; rankings may change.
  Preserve game outcomes, outcome-based ladder Elo, and calibrated engine Elo.
- Stage the migration separately from production. Carry analysis/profile/map versions
  through saved states, result records, leaderboards, reports and public snapshots;
  avoid silently mixing old/new samples or comparing unlike versions. Recompute all
  dependent aggregates, validate counts/links, then publish a coherent release with
  a change note and rollback path. Reanalysis alone must not replay Elo updates.

Done when:

- Completed lists and game opening meet the recorded latency targets as history grows;
  accessing a page does not read all historical states or trigger engine analysis.
- The chosen authoritative profile has measured stability and resource-cost evidence,
  with visible pending/unavailable states and bounded background work.
- A pilot backfill survives interruption/restart, produces historical annotations, and
  demonstrates complete propagation into a separately versioned candidate map and
  model aggregates. Broad migration follows only after reviewing that evidence.
- Published data identifies its analysis and map versions, original values can be
  recovered, and no outcome-based Elo or agent-facing payload changes occur.

## Follow-up: Ops restart and historical annotations (2026-10-13)

- Added **Restart server** beside Go Online / Sleep public. The managed CLI requests
  graceful Uvicorn shutdown only after a detached helper acknowledges the handoff.
  The helper waits for the old process to exit, refuses an occupied port, starts
  the updated server without `--force`, and verifies both the replacement PID and
  health before declaring success. The browser reconnects across downtime.
- Restart is local and same-origin only. Active games, puzzle/identification
  attempts, calibration, post-game analysis, historical annotation backfill,
  concurrent mutations, and Go Online / Sleep operations prevent restart.
  New mutations are refused while the handoff is pending. A backend already running
  older code needs one manual restart to activate this new endpoint.
- User explicitly requested annotation backfill for **all agent games**. Inventory
  includes finished filesystem games plus archive-only records in the permanent
  SQLite store; filesystem state takes precedence for duplicate game IDs.
- `python -m chess_harness.annotation_backfill --workers 4` performs an annotation-only
  pass. It retains the existing v1 depth-8 evaluation profile and the separate
  deeper exceptional-move verification from Batch 5. This is not Batch 8's stronger
  authoritative evaluation or Performance-map migration.
- Saves validated `move-analysis.json` atomically, skips already complete matching
  artifacts on rerun, and preserves replaced artifacts under `analysis-history/`.
  Archive-only annotations live under runtime `archived-move-analysis/<game_id>/`;
  deleted game directories are not restored. Empty games receive an empty artifact.
  Invalid saved moves fail explicitly without replacing existing artifacts.
- Does not write state, PGNs, results, permanent SQLite records, model ratings, maps,
  or leaderboards. A SHA-256 preservation baseline is stored in runtime logs.
  Progress and per-game failures: `logs/annotation-backfill.json`; single-job lock
  prevents duplicate backfills, and four workers bound CPU use.
- Initial inventory: **686 games = 369 local + 317 archive-only** (including historical
  test records). The original backfill completed all 686 without failures, covering
  39,887 plies. Initial counts: 138 `!`, one `!!`, 3,823 `?!`, 3,931 `?`, and 4,126 `??`.
  Archive-only records keep their existing visibility behavior.
- Verification: Python restart/backfill/quality checks and JavaScript request,
  restart-reconnection/refusal, and annotation checks pass. The real server was
  not restarted by the agent; replacement-process behavior is covered with fakes.
- CI follow-up: the new Python tests pass on Windows and Ubuntu. Full CI retains
  the preceding commit's failures (Home/leaderboard assertions, prompt-pack fixture,
  move-row assertions, invalid game-ID handling, puzzle UI assertions, runner event
  naming, calibration confirmation on Windows, and MCP idle-pruning parity).
  Fix or update these in the maintenance work; do not treat this release as a
  fully green repository-wide test run.

### Annotation presentation and discovery follow-up

- User requested no evaluations beside moves, larger/more separated symbols, and
  `ELO` with just the before/after values. Published in `1f5eaa8`; verified the public
  GPT-6.1 Sol game displays `GPT-6.1 Sol 500 → 537` and no move-evaluation spans.
- Narrowed `?!` to 8–10 percentage points of estimated mover win-chance loss;
  `?` starts at 10 and `??` remains above 30. This changes annotation labels only.
- `!` does not require a sacrifice. The existing critical-only-move rule remains.
  `!!` now also supports quiet discoveries, rather than relying exclusively on
  material offers. Sacrifices may be nearly best (within 3 percentage points),
  provided the position remains sound and other choices are not already winning.
- Discovery is a benchmark heuristic, not a measure of human difficulty. Clear the
  Stockfish hash before tracing the first search; record its best root at every
  reported depth. Depth 8 must prefer another move. The played move must become
  best at depth 10+ for `!`, or 14+ for `!!`, stay best for at least three consecutive
  reported depths, and reveal at least a 5/8 percentage-point evaluation gain over
  the shallow best score. Require a meaningful deep gap to the runner-up and both
  subsequent depth checks to agree. A jump without a late, stable move discovery
  does not qualify. Bounded/shallow/incomplete evidence produces no discovery label.
- Evidence format remains backward compatible; policy version, discovery depths,
  evaluation gains, and actual verification depths are saved separately. The updated
  API projects numeric discovery evidence without alternative moves or variations.
- `--refresh-labels` reuses saved scores, preserves the previous artifact, changes
  negative thresholds, and checks shallow-discounted moves (loss >=3 points) plus
  material offers for positive labels. Existing verified positive labels are retained.
  Accuracy, Performance, outcome-based Elo, states and SQLite rows remain untouched.
- Fixed atomic file replacement to retry transient Windows reader-sharing collisions.
  A regression test covers progress-file retry. The first refresh worker continued
  processing after its progress writer failed with WinError 5; a resumable pass
  reconciled all 686 existing current-version artifacts and completed without failures.
- Final verification: **686/686** artifacts valid in a fresh Python process,
  **369/369** local game annotation endpoints return complete, and SHA-256 checks
  confirm all **742** protected state/PGN/results/model/database files unchanged.
- Final labels across 39,887 plies: **207 `!`, 4 `!!`, 1,134 `?!`, 3,931 `?`,
  4,059 `??`**. Agent moves account for **53 `!` and all four `!!`**. The archive
  produced no qualifying late-search discovery under the conservative new thresholds;
  tests cover quiet/non-sacrifice discoveries, unstable search and missing evidence.
  Do not fabricate extra brilliant moves to meet a target count.
- Public frontend changes are deployed and verified. Saved finished-game labels are
  already served by the existing backend. Activating new analysis criteria for future
  games, discovery-detail projection, and the new Ops restart endpoint still requires
  one manual restart: automatic approval review had rejected the agent restarting the
  live server. The prior manually started process predates these backend changes.

### Replay layout, model metadata, and annotation audit (policies v4/v5)

- Published `04d1bfa` and `1d8f7d2`: smaller shared header spacing, a larger
  centered replay board, matching move-panel height, and fixed dark-mode evaluation
  colors (black above white). Responsive checks cover desktop and narrow screens.
- Home puts the token joke first, merges the benchmark explanation, removes the
  obsolete Playground reference and trims the rating discussion. Benchmark freshness
  is now heading hover text. Historical model display names omit reasoning effort;
  stored identities and ratings remain intact.
- GPT-6.1 Sol uses AA index 52 and the existing estimated cost convention ($0.89
  per typical game), not metered billing. Sources:
  https://artificialanalysis.ai/models/releases/gpt-6-1-sol/ and
  https://developers.openai.com/api/docs/models/gpt-6.1-sol .
- Policy v4 supersedes the preceding v3 refresh rules: all moves, including old
  positive labels, are reverified. Verification gets 0.35/1.0 seconds with target
  depths 18/22 and minimum completed depths 14/18. Cold depth-4 discovery traces
  can identify stable later choices or substantial deeper value refinement.
  Quiet exceptional moves need no sacrifice. Routine captures need a genuinely
  changed, later engine choice; simply taking a hung piece is insufficient.
  Material disposal that merely preserves an already drawn position is rejected.
- Review during the full refresh found an additional false positive: an ordinary
  bishop check block received `!` solely from the gap to inferior alternatives.
  Policy v5 excludes routine check evasions unless both saved verification passes
  show deeper difficulty evidence or a sound material offer. This exclusion can
  be applied directly to v4's saved evidence without repeating engine searches.
- An 811-position pilot included every old positive plus sampled quiet moves and
  captures. It exposed many old critical-gap capture false positives, including
  11...dxe4 in `game-5c-eqcCF2tSm_lDiSlPxlw`. Desired 2x/4x positive counts are
  diagnostic goals, never quotas. Reviewed evidence takes precedence over counts.
- Negative annotation hover text uses the engine's preferred SAN move instead of
  percentage loss. When deeper verification prefers the played move, a conflicting
  shallow error label is suppressed; its original score and label remain recorded.
  Neither this nor positive-label refresh changes Accuracy, Performance or Elo.
- The cited game's final zero score is reproducible with full move history:
  White could claim a threefold draw but resigned instead. Display a contextual
  `=` with that explanation rather than a misleading winning-side `??`. Preserve
  the engine score and the actual result. Apply the same history-based rule to
  future analysis and historical refreshes; never replace a real draw score merely
  because the game ended with a decisive result.
- Full refresh completed for all 686 games without failures, prioritizing the cited game and the two
  GPT-6.1 Sol games. Runtime progress and backups follow the existing backfill
  contract. The stronger authoritative evaluation and Performance-map migration
  remain Batch 8 work.
- Final v5 artifact verification: **686/686** complete, **369/369** local completed-game
  annotation endpoints complete, and every negative annotation has a saved preferred
  move. All **39,887** before/after evaluations and saved losses match their pre-refresh
  artifacts; all **742** protected state/PGN/results/model/database files are unchanged.
  The evidence-only refinement removed 55 routine check-evasion positives.
- Final counts: **49 `!`, 12 `!!`, 1,121 `?!`, 3,910 `?`, 4,011 `??`** and
  30,784 unmarked moves. Agents account for **12 `!` and 7 `!!`**. Positive labels
  include quiet discoveries and value refinements, such as 102...Be4 in
  `game-JJXR5SOc41jXTLsAnlLrzA` (stable deeper choice from depth 16).
  The requested approximate 2x/4x multipliers were not met: removing the preceding
  policy's false positives reduced the `!` count significantly. Do not undo those
  exclusions merely to hit counts. Revisit budget sufficiency and heuristic
  calibration with Batch 8's stronger authoritative analysis.
- Validation: 64 targeted Python tests passed, one environment-specific test skipped;
  nine annotation UI tests and seven Home benchmark tests passed. Public-site
  deployment runs succeeded. New best-move and terminal-context API fields still
  need one manual activation restart under the existing approval-review block.

### Less restrictive exceptional-move policy (v6, 2026-10-14)

- User explicitly requested substantially less restrictive `!`/`!!` criteria.
  Critical gap changes from 7.5 to 3 percentage points. Quiet deeper refinements
  require 2.5 points for `!` and 5 for `!!`, previously 6/10. Late discoveries
  require depth 5 with 1.5-point gain for `!`, or depth 8 with 3-point gain for `!!`.
  Quiet discovery needs two consecutive depths and a 3-point runner-up gap.
  Resourceful moves can qualify from 15% estimated mover chance (`!!`: 30%).
- Engine verification remains unchanged: target depths 18/22, completed depths
  at least 14/18, and two agreeing passes. Routine captures and check evasions
  retain the stronger previous discovery, gap and three-depth stability guards.
  Forced moves and pointless sacrifices in drawn positions remain excluded.
- A 1,009-move pilot includes all 61 current positives, prior positive candidates,
  sampled engine-preferred quiet moves/captures, and three explicit negative
  controls. New rules add 8 previously unmarked `!`, one previously unmarked `!!`,
  one shallow-discounted `!!`, and upgrade five `!` to `!!` in this sample.
  All three known false-positive controls remain unmarked. Counts are not quotas.
- Optional `--reuse-preferences` avoids repeating searches for non-positive,
  non-sacrificial moves when a legal alternative was already preferred at depth
  14+. Current preferred moves, material offers, prior positives and missing or
  shallow preferences still receive fresh verification. The artifact records
  which scope was reused. State, stored evaluations, losses and ratings are retained.
- Full annotation-only v6 refresh completed for **686/686** games without failures.
  Final counts: **55 `!`, 31 `!!`, 1,123 `?!`, 3,912 `?`, 4,019 `??`**, and
  30,747 unmarked moves. Agents account for **16 `!` and 21 `!!`**, previously
  12/7: positive agent annotations rise from 19 to 37, with triple the `!!` count.
  All 369 local completed-game annotation endpoints return complete; every negative
  annotation has a saved best move. All 39,887 saved evaluations/losses and all
  742 protected files remain unchanged. The public API serves the v6 criteria,
  and known ordinary-capture, check-block and pointless-sacrifice controls stay
  unmarked. Future-game v6 activation requires restarting the backend;
  the existing Ops restart button is now available after the user's activation.
- Avoid cold difficulty searches when the first verified scores already exclude
  both symbols (drawn/too-losing positions, already-winning alternatives, or an
  insufficient gap without a sacrifice). This preserves the grading conditions
  and preferred-move audit while removing redundant engine work. The owned
  annotation job was resumed with this optimization; valid completed artifacts
  are retained. Targeted Python verification: 78 passed, one environment skip.
- Batch 8 follow-up: persist private verification/rejection evidence for screened
  candidates so future threshold changes can reuse searches instead of repeating
  the archive pass. Continue excluding private variations from public responses.

### Broader strong-move annotations (v7, 2026-10-14)

- User requested roughly ten times the current 16 agent `!` labels, with `!!`
  considered separately. This is a calibration target, not a quota. The definition
  of `!` now includes strong practical quiet choices as well as exceptional moves.
- A deterministic study covered all 16 agent `!` plus 700 of 933 eligible agent
  quiet moves previously preferred by a deep engine. A separate hash-cleared,
  forced depth-4 score exposed hidden choices that preserve the position's best
  evaluation while improving the evaluation of the played move itself. Root
  changes caused only by equal shallow choices are insufficient evidence.
- New quiet routes exclude the first eight plies, captures, check evasions,
  terminal positions and available draw claims. Both deep verification passes
  must prefer the played move. Existing routine-capture and check-evasion guards
  remain; `!!` uses the preceding v6 criteria.
- Private numeric search audits are saved with the actual root scores, depths,
  bounds, shallow search evidence and a digest of the position's full history.
  They never publish engine variations. Optional `--reuse-evidence` checks the
  Stockfish binary hash and compatible search evidence before regrading; missing
  or insufficient evidence triggers fresh analysis. This reduces repeated engine
  work when calibrating thresholds.
- Final thresholds, historical counts and verification are recorded after the
  implementation and archive refresh below.

## Delivery rules

- Implement one batch at a time; split a batch further if it cannot be reviewed cleanly.
- Each batch reports changes, targeted verification, and remaining limitations. Include
  screenshots for visible changes. Broaden tests only for changes that warrant it.
- Preserve unrelated working-tree edits. Plan writing does not authorize API spending,
  launching experiments, stopping active seats, or publishing implementation changes.
- No framework migration, product rename, leaderboard identity changes, new matchmaking,
  tutor feature, or wholesale refactor is part of this maintenance pass.
