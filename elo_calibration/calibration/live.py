"""Live calibration session state for the spectator UI."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _results_root(project_root: Path) -> Path:
    return project_root / "elo_calibration" / "results"


def live_session_path(project_root: Path) -> Path:
    return _results_root(project_root) / "live_session.json"


def merged_ratings_path(project_root: Path) -> Path:
    return _results_root(project_root) / "merged_ratings.json"


def write_live_session(project_root: Path, data: Dict[str, Any]) -> None:
    path = live_session_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def clear_live_session(project_root: Path, *, active: bool = False) -> None:
    path = live_session_path(project_root)
    if path.exists():
        path.unlink()


def read_live_session(project_root: Path) -> Optional[Dict[str, Any]]:
    path = live_session_path(project_root)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def write_merged_ratings(project_root: Path, rating_table: List[Dict[str, Any]]) -> None:
    """Rebuild merged cache from all suite ratings.json (rating_table is ignored)."""
    del rating_table
    path = merged_ratings_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    merged = merge_ratings_from_results(project_root)
    path.write_text(json.dumps({"ratings": merged}, indent=2), encoding="utf-8")


def read_merged_ratings(project_root: Path) -> Dict[str, Dict[str, Any]]:
    path = merged_ratings_path(project_root)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("ratings", {})
        except (OSError, json.JSONDecodeError):
            pass
    return merge_ratings_from_results(project_root)


def merge_ratings_from_results(project_root: Path) -> Dict[str, Dict[str, Any]]:
    """Pick best-known calibration row per opponent from all suite ratings.json files."""
    root = _results_root(project_root)
    if not root.exists():
        return {}
    merged: Dict[str, Dict[str, Any]] = {}
    for ratings_file in root.glob("*/ratings.json"):
        try:
            data = json.loads(ratings_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        games_played = data.get("games_played", {})
        for oid, elo in data.get("ratings", {}).items():
            games = int(games_played.get(oid, 0))
            prev = merged.get(oid)
            if prev is None or games > prev.get("games", 0):
                merged[oid] = {
                    "id": oid,
                    "elo": round(float(elo)),
                    "elo_exact": round(float(elo), 2),
                    "games": games,
                    "suite": ratings_file.parent.name,
                }
    return merged
