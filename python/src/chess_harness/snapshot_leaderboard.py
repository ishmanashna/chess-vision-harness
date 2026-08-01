"""Export public-site leaderboard snapshot from harness models and results."""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .models import AGENT_START_ELO, ModelRegistry
from .paths import project_root, resolve_base_dir
from .results import ResultsManager

# Matches rating_math.k_factor stable threshold and public-site provisional display.
PROVISIONAL_GAMES_THRESHOLD = 100

SNAPSHOT_REFRESH_MIN_INTERVAL_SEC = 30.0
_snapshot_refresh_lock = threading.Lock()
_last_snapshot_refresh_mono = 0.0


def default_output_path() -> Path:
    return project_root() / "public-site" / "data" / "leaderboard.json"


def is_provisional(games: int) -> bool:
    return games < PROVISIONAL_GAMES_THRESHOLD


def build_opponent_snapshot_rows() -> List[Dict[str, Any]]:
    """Anchors + calibrated floaters for the public ladder snapshot."""
    from .accuracy_elo_map import est_elo_from_accuracy
    from .calibration_view import build_ladder_rating_table
    from .opponents import OpponentCatalog
    from .play_rating import play_rating_status_summary
    from .paths import project_root

    catalog = OpponentCatalog()
    cal_root = project_root() / "elo_calibration" / "results"
    try:
        quality = play_rating_status_summary(root=cal_root)
    except Exception:
        quality = {"engines": []}
    by_engine = {e["engine_id"]: e for e in quality.get("engines", [])}

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
        info = by_engine.get(oid) or {}
        mean_accuracy = info.get("mean_accuracy")
        mean_play_rating = None
        if mean_accuracy is not None:
            mean_play_rating = est_elo_from_accuracy(float(mean_accuracy), root=cal_root)
        rows.append(
            {
                "id": oid,
                "name": name,
                "elo": round(float(row.get("elo") or 0)),
                "games": int(row.get("games") or 0),
                "anchor": bool(row.get("anchor")),
                "uncalibrated": bool(row.get("uncalibrated")),
                "mean_accuracy": mean_accuracy,
                "mean_play_rating": mean_play_rating,
                "quality_games": int(info.get("sample_count") or 0),
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
    rated_counts: Optional[Dict[str, int]] = None,
    quality_stats: Optional[Dict[str, Dict[str, Any]]] = None,
    generated_at: Optional[str] = None,
    include_opponents: bool = True,
) -> Dict[str, Any]:
    """Build leaderboard snapshot.

    ``game_counts`` is the display Games column (scored: real results including AvH).
    ``rated_counts`` drives provisional ``*`` (Elo ladder games only). When omitted,
    provisional uses ``game_counts`` (legacy call sites / tests).
    Always emits boolean ``provisional`` so clients never derive it from display Games.
    """
    quality_stats = quality_stats or {}
    provisional_counts = rated_counts if rated_counts is not None else game_counts
    agents: List[Dict[str, Any]] = []
    for model in registry.list_models():
        model_id = model["id"]
        games = int(game_counts.get(model_id, 0))
        rated = int(provisional_counts.get(model_id, 0))
        agents.append(
            {
                "id": model_id,
                "name": model.get("name", model_id),
                "elo": round(float(model.get("elo", AGENT_START_ELO))),
                "games": games,
                "provisional": is_provisional(rated),
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


def load_live_leaderboard(
    *,
    base_dir: Optional[str] = None,
    registry: Optional[ModelRegistry] = None,
) -> Dict[str, Any]:
    """Build public-site leaderboard JSON from current harness state (no disk write)."""
    reg = registry or ModelRegistry()
    harness_base = str(base_dir) if base_dir else str(resolve_base_dir())
    results = ResultsManager(base_dir=harness_base)
    return build_snapshot(
        reg,
        results.count_scored_by_model(),
        rated_counts=results.count_by_model(),
        quality_stats=results.aggregate_quality_by_model(),
    )


def export_leaderboard_snapshot(
    output_path: Optional[Path | str] = None,
    *,
    base_dir: Optional[str] = None,
    registry: Optional[ModelRegistry] = None,
) -> Path:
    """Write leaderboard JSON for the public site offline fallback."""
    snapshot = load_live_leaderboard(base_dir=base_dir, registry=registry)
    out = Path(output_path) if output_path else default_output_path()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    return out


def request_leaderboard_snapshot_refresh() -> None:
    """Debounced background write of public-site/data/leaderboard.json."""
    global _last_snapshot_refresh_mono
    now = time.monotonic()
    with _snapshot_refresh_lock:
        if now - _last_snapshot_refresh_mono < SNAPSHOT_REFRESH_MIN_INTERVAL_SEC:
            return
        try:
            export_leaderboard_snapshot()
            _last_snapshot_refresh_mono = now
        except Exception:
            pass
