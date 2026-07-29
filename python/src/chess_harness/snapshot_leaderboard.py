"""Export public-site leaderboard snapshot from harness models and results."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import AGENT_START_ELO, ModelRegistry
from .paths import project_root, resolve_base_dir
from .results import ResultsManager

# Matches rating_math.k_factor stable threshold and public-site provisional display.
PROVISIONAL_GAMES_THRESHOLD = 100


def default_output_path() -> Path:
    return project_root() / "public-site" / "data" / "leaderboard.json"


def is_provisional(games: int) -> bool:
    return games < PROVISIONAL_GAMES_THRESHOLD


def build_opponent_snapshot_rows() -> List[Dict[str, Any]]:
    """Anchors + calibrated floaters for the public ladder snapshot."""
    from .calibration_view import build_ladder_rating_table
    from .opponents import OpponentCatalog

    catalog = OpponentCatalog()
    rows: List[Dict[str, Any]] = []
    for row in build_ladder_rating_table(catalog):
        oid = str(row.get("id") or "")
        opp = catalog.get(oid) if oid else None
        if opp and opp.type == "stockfish":
            name = f"{opp.display_name} ({oid})"
        elif opp:
            name = opp.display_name
        else:
            name = oid
        rows.append(
            {
                "id": oid,
                "name": name,
                "elo": round(float(row.get("elo") or 0)),
                "games": int(row.get("games") or 0),
                "anchor": bool(row.get("anchor")),
                "uncalibrated": bool(row.get("uncalibrated")),
            }
        )
    rows.sort(key=lambda r: (-r["elo"], str(r["name"]).lower()))
    return rows


def _quality_snapshot_fields(
    quality_stats: Dict[str, Dict[str, Any]], model_id: str
) -> Dict[str, Any]:
    stats = quality_stats.get(model_id, {})
    return {
        "mean_accuracy": stats.get("mean_accuracy"),
        "mean_play_rating": stats.get("mean_play_rating"),
        "quality_games": int(stats.get("quality_games", 0)),
    }


def build_snapshot(
    registry: ModelRegistry,
    game_counts: Dict[str, int],
    *,
    quality_stats: Optional[Dict[str, Dict[str, Any]]] = None,
    generated_at: Optional[str] = None,
    include_opponents: bool = True,
) -> Dict[str, Any]:
    quality_stats = quality_stats or {}
    agents: List[Dict[str, Any]] = []
    for model in registry.list_models():
        model_id = model["id"]
        games = int(game_counts.get(model_id, 0))
        agents.append(
            {
                "id": model_id,
                "name": model.get("name", model_id),
                "elo": round(float(model.get("elo", AGENT_START_ELO))),
                "games": games,
                "provisional": is_provisional(games),
                **_quality_snapshot_fields(quality_stats, model_id),
            }
        )
    agents.sort(key=lambda a: (-a["elo"], str(a["name"]).lower()))

    if generated_at is None:
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    snapshot: Dict[str, Any] = {"generated_at": generated_at, "agents": agents}
    if include_opponents:
        snapshot["opponents"] = build_opponent_snapshot_rows()
    return snapshot


def export_leaderboard_snapshot(
    output_path: Optional[Path | str] = None,
    *,
    base_dir: Optional[str] = None,
    registry: Optional[ModelRegistry] = None,
) -> Path:
    """Write leaderboard JSON for the public site."""
    base = Path(base_dir) if base_dir else resolve_base_dir()
    reg = registry or ModelRegistry()
    results = ResultsManager(base_dir=str(base))
    game_counts = results.count_by_model()
    quality_stats = results.aggregate_quality_by_model()
    snapshot = build_snapshot(reg, game_counts, quality_stats=quality_stats)

    out = Path(output_path) if output_path else default_output_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    return out
