# Offline scaffold demonstration

Hypothesis: the shared record format can preserve one synthetic seat's progress and
completion without contacting a provider or changing harness data.

- Sample: one synthetic seat lifecycle with a heartbeat, zero chess games.
- Budget: zero provider calls and zero monetary cost; usage is unavailable, not measured.
- Success: a manifest, parseable event stream, and report with a matching run ID.
- Failure: invalid metadata, missing artifacts, or accidental network/game creation.
- Exclusions: this demonstrates bookkeeping only and provides no model-quality evidence.

Replace these decisions before a real experiment.
