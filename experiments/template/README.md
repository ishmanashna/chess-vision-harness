# Future experiment template

Copy this directory to `experiments/<experiment-id>/`, excluding `runs/`. Fill in
`brief.md`, `config.json`, and `prompt.txt`; replace the synthetic body of `run.py`
with a small provider-specific launcher when an actual experiment is authorized.

The demo uses only Python's standard library and the sibling `run_record.py` helper.
It never starts chess games or contacts a provider. The helper does not schedule,
retry, resume, or manage processes; those choices belong to the experiment.

Before a real run, specify a bounded sample/budget, fixed opponent/color policy,
identity/effort/observation mode, and completion criteria in the brief. Keep the
provider and model declared in config aligned with the launcher actually used.
Do not place credentials in config or prompt files that will be committed.

Run `python experiments/<experiment-id>/run.py --run-id <unique-id>` from the repo
root. An optional `--output-root` selects the parent of the run-ID directory.
The default is this experiment's ignored `runs/` directory.

Use `RunRecord.event(...)` around meaningful transitions and `finish(...)` with a
terminal status and reason. Successful no-op/dry runs must remain labeled synthetic.
For real games, carry the harness game ID in events and link to its existing record;
never duplicate credentials or mutate Elo from an experiment report.

Use `report.template.md` for the reviewed research conclusion. The generated report
is a minimal operational summary, not a substitute for the experiment's analysis.
