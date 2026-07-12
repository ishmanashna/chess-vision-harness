"""Markdown + JSON report generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def write_report(results_dir: Path, summary: Dict[str, Any]) -> None:
    results_dir.mkdir(parents=True, exist_ok=True)
    (results_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = [
        "# Calibration summary",
        "",
        f"- **Suite:** {summary.get('suite')}",
        f"- **Mode:** {summary.get('mode')}",
        f"- **Scheduled games:** {summary.get('scheduled_games')}",
        f"- **Games played:** {summary.get('games_played')}",
        f"- **Floating start ELO:** {summary.get('floating_start_elo')}",
        f"- **K-factor:** {summary.get('k_factor')}",
        "",
        "## Ratings",
        "",
        "| Engine | ELO | Games | Anchor | Catalog |",
        "|--------|-----|-------|--------|---------|",
    ]
    for row in summary.get("rating_table", []):
        anchor = "yes" if row.get("anchor") else "no"
        lines.append(
            f"| {row['id']} | {row['elo']} | {row['games']} | {anchor} | {row.get('catalog_elo', '')} |"
        )

    stab = summary.get("stabilization", {}).get("players", {})
    if stab:
        lines.extend(["", "## Stabilization (recent window)", ""])
        for oid, info in stab.items():
            lines.append(
                f"- **{oid}**: latest {info.get('latest')}, "
                f"swing {info.get('delta_range')} over {info.get('games_in_window')} games"
            )

    preview = summary.get("schedule_preview", [])
    if preview:
        lines.extend(["", "## Schedule preview", ""])
        for i, game in enumerate(preview, 1):
            lines.append(
                f"{i}. {game['white']} vs {game['black']} "
                f"(W: {game['white_harness']}, B: {game['black_harness']})"
            )
        if summary.get("schedule_preview_note"):
            lines.append(f"\n_{summary['schedule_preview_note']}_")

    (results_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
