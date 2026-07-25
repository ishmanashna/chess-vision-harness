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


def build_snapshot(
    registry: ModelRegistry,
    game_counts: Dict[str, int],
    *,
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
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
            }
        )
    agents.sort(key=lambda a: (-a["elo"], str(a["name"]).lower()))

    if generated_at is None:
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    return {"generated_at": generated_at, "agents": agents}


def export_leaderboard_snapshot(
    output_path: Optional[Path | str] = None,
    *,
    base_dir: Optional[str] = None,
    registry: Optional[ModelRegistry] = None,
) -> Path:
    """Write leaderboard JSON for the public site."""
    base = Path(base_dir) if base_dir else resolve_base_dir()
    reg = registry or ModelRegistry()
    game_counts = ResultsManager(base_dir=str(base)).count_by_model()
    snapshot = build_snapshot(reg, game_counts)

    out = Path(output_path) if output_path else default_output_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    return out
