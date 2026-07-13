"""Read calibration ELO for spectator ladder and live session API."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .opponents import Opponent, OpponentCatalog, get_catalog
from .paths import project_root

def _continuous_mgr():
    from .continuous_calibration import get_continuous_calibration

    return get_continuous_calibration()


def _results_root() -> Path:
    return project_root() / "elo_calibration" / "results"


_MERGE_CACHE: Optional[Tuple[float, Dict[str, Dict[str, Any]]]] = None
MERGE_CACHE_TTL_SEC = 2.0
_STATUS_CACHE: Optional[Tuple[float, Dict[str, Any]]] = None
STATUS_CACHE_TTL_SEC = 1.0


def invalidate_merge_cache() -> None:
    global _MERGE_CACHE, _STATUS_CACHE
    _MERGE_CACHE = None
    _STATUS_CACHE = None


def merge_calibration_ratings(*, max_age_sec: Optional[float] = MERGE_CACHE_TTL_SEC) -> Dict[str, Dict[str, Any]]:
    """Best-known calibrated row per engine across all suite ratings.json files."""
    global _MERGE_CACHE
    now = time.monotonic()
    if max_age_sec is not None and _MERGE_CACHE is not None:
        cached_at, cached = _MERGE_CACHE
        if now - cached_at < max_age_sec:
            return cached

    root = _results_root()
    merged: Dict[str, Dict[str, Any]] = {}
    catalog = get_catalog()
    if root.exists():
        for ratings_file in root.glob("*/ratings.json"):
            try:
                data = json.loads(ratings_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            games_played = data.get("games_played", {})
            suite = ratings_file.parent.name
            for oid, elo in data.get("ratings", {}).items():
                games = int(games_played.get(oid, 0))
                prev = merged.get(oid)
                if prev is None or games > prev.get("games", 0):
                    try:
                        anchor = catalog.get(oid).type == "stockfish"
                    except ValueError:
                        anchor = False
                    merged[oid] = {
                        "id": oid,
                        "elo": round(float(elo)),
                        "elo_exact": round(float(elo), 2),
                        "games": games,
                        "suite": suite,
                        "anchor": anchor,
                    }
    if max_age_sec is not None:
        _MERGE_CACHE = (now, merged)
    return merged


def rebuild_merged_ratings_file() -> Dict[str, Dict[str, Any]]:
    """Rewrite merged_ratings.json cache from all suite ratings files."""
    merged = merge_calibration_ratings(max_age_sec=None)
    path = _results_root() / "merged_ratings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"ratings": merged}, indent=2), encoding="utf-8")
    global _MERGE_CACHE
    _MERGE_CACHE = (time.monotonic(), merged)
    _STATUS_CACHE = None
    return merged


DEFAULT_FLOATING_ELO = 500


def calibrated_elo_for(opp: Opponent, calibration: Dict[str, Dict[str, Any]]) -> Optional[int]:
    if opp.type == "stockfish":
        return opp.elo
    row = calibration.get(opp.id)
    if row and row.get("games", 0) > 0:
        return int(row["elo"])
    return None


def ladder_elo_for_opponent(
    opp: Opponent,
    calibration: Optional[Dict[str, Dict[str, Any]]] = None,
) -> int:
    """ELO for agent ladder pairing, display, and rating updates (never catalog for floaters)."""
    cal = calibration if calibration is not None else merge_calibration_ratings()
    display = calibrated_elo_for(opp, cal)
    if display is not None:
        return display
    if opp.type == "stockfish":
        return opp.elo
    return DEFAULT_FLOATING_ELO


def ladder_elo_for_opponent_id(
    opponent_id: str,
    catalog: Optional[OpponentCatalog] = None,
    calibration: Optional[Dict[str, Dict[str, Any]]] = None,
) -> int:
    cat = catalog or get_catalog()
    return ladder_elo_for_opponent(cat.get(opponent_id), calibration)


def build_ladder_rating_table(
    catalog: OpponentCatalog,
    calibration: Optional[Dict[str, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Full ladder for APIs: anchors, engines, and harnessed Stockfish (skill 0)."""
    cal = calibration if calibration is not None else merge_calibration_ratings()
    rows: List[Dict[str, Any]] = []
    for opp in catalog.list_opponents():
        if not opp.enabled:
            continue
        if opp.type == "stockfish":
            rows.append(
                {
                    "id": opp.id,
                    "elo": opp.elo,
                    "games": 0,
                    "anchor": True,
                    "catalog_elo": opp.elo,
                }
            )
        elif opp.type in ("uci", "uci_elo", "uci_harness", "stockfish_harness", "inverse_sf", "random"):
            row = cal.get(opp.id, {})
            games = int(row.get("games", 0)) if row else 0
            display = calibrated_elo_for(opp, cal)
            rows.append(
                {
                    "id": opp.id,
                    "elo": display if display is not None else DEFAULT_FLOATING_ELO,
                    "games": games,
                    "anchor": False,
                    "catalog_elo": opp.elo,
                    "uncalibrated": games == 0,
                    "enabled": opp.enabled,
                }
            )
    rows.sort(key=lambda r: (r.get("anchor", False), -r.get("elo", 0)))
    return rows


def enrich_rating_table_activity(
    rows: List[Dict[str, Any]],
    *,
    active: bool,
    in_flight_by_engine: Optional[Dict[str, int]] = None,
) -> List[Dict[str, Any]]:
    """Attach per-engine live game counts for the calibration spectator table."""
    in_flight = in_flight_by_engine or {}
    enriched: List[Dict[str, Any]] = []
    for row in rows:
        copy = dict(row)
        if copy.get("anchor"):
            copy["playing"] = 0
            copy["activity"] = "anchor"
        elif not copy.get("enabled", True):
            copy["playing"] = 0
            copy["activity"] = "disabled"
        else:
            playing = int(in_flight.get(copy["id"], 0)) if active else 0
            copy["playing"] = playing
            copy["activity"] = "playing" if playing else "idle"
        enriched.append(copy)
    return enriched


def get_calibration_status() -> Dict[str, Any]:
    global _STATUS_CACHE
    now = time.monotonic()
    mgr = _continuous_mgr()
    running = mgr.running_engines()
    if _STATUS_CACHE is not None and running:
        cached_at, cached = _STATUS_CACHE
        if now - cached_at < STATUS_CACHE_TTL_SEC:
            cont = mgr.status_payload()
            return {
                **cached,
                "continuous_engines": sorted(running),
                "parallel_by_engine": cont.get("parallel_by_engine", {}),
                "skipped_games": cont.get("skipped_games", 0),
                "in_progress": sum(cont.get("in_flight_by_engine", {}).values()),
                "in_flight_by_engine": cont.get("in_flight_by_engine", {}),
                "recent_games": cont.get("recent_games", [])[-30:],
                "updated_at": cont.get("updated_at"),
                "process_pool_workers": cont.get("process_pool_workers"),
                "pairing_mode": cont.get("pairing_mode"),
                "fixed_opponent_id": cont.get("fixed_opponent_id"),
            }

    cont = mgr.status_payload()
    root = _results_root()
    merge_ttl = 0.5 if running else MERGE_CACHE_TTL_SEC
    calibration = merge_calibration_ratings(max_age_sec=merge_ttl)
    catalog = get_catalog()

    recent: List[Dict[str, Any]] = list(cont.get("recent_games", []))
    if not recent:
        games_path: Optional[Path] = None
        latest_mtime = -1.0
        for candidate in root.glob("*/games.jsonl"):
            try:
                mtime = candidate.stat().st_mtime
            except OSError:
                continue
            if mtime > latest_mtime:
                latest_mtime = mtime
                games_path = candidate
        if games_path and games_path.exists():
            lines = games_path.read_text(encoding="utf-8").splitlines()
            for line in lines[-20:]:
                if line.strip():
                    recent.append(json.loads(line))

    rating_table = build_ladder_rating_table(catalog, calibration)
    rating_table = mgr.enrich_rating_rows([r for r in rating_table if not r.get("anchor")])

    payload = {
        "mode": "continuous" if running else "idle",
        "active": bool(running),
        "continuous_engines": sorted(running),
        "parallel_by_engine": cont.get("parallel_by_engine", {}),
        "skipped_games": cont.get("skipped_games", 0),
        "suite": "continuous" if running else None,
        "workers": len(running),
        "process_pool_workers": cont.get("process_pool_workers"),
        "scheduled": 0,
        "completed": 0,
        "in_progress": sum(cont.get("in_flight_by_engine", {}).values()),
        "in_flight_by_engine": cont.get("in_flight_by_engine", {}),
        "rating_table": rating_table,
        "recent_games": recent[-30:],
        "updated_at": cont.get("updated_at"),
        "pairing_mode": cont.get("pairing_mode"),
        "fixed_opponent_id": cont.get("fixed_opponent_id"),
        "pairing_opponents": cont.get("pairing_opponents", []),
        "calibratable_engines": cont.get("calibratable_engines", []),
    }
    if running:
        _STATUS_CACHE = (now, payload)
    else:
        _STATUS_CACHE = None
    return payload


def split_opponent_ladder_calibrated(
    catalog: OpponentCatalog,
    calibration: Optional[Dict[str, Dict[str, Any]]] = None,
) -> tuple[
    List[tuple[Opponent, Optional[int], int]],
    List[tuple[Opponent, Optional[int], int]],
    List[tuple[Opponent, int, int]],
]:
    """Returns (engines, stockfish harness, stockfish anchors)."""
    cal = calibration if calibration is not None else merge_calibration_ratings()
    engine_types = ("uci", "uci_elo", "uci_harness", "random")
    harness_types = ("stockfish_harness", "inverse_sf")
    engines: List[tuple[Opponent, Optional[int], int]] = []
    harness: List[tuple[Opponent, Optional[int], int]] = []
    for opp in catalog.list_opponents():
        if not opp.enabled:
            continue
        row = cal.get(opp.id, {})
        games = int(row.get("games", 0)) if row else 0
        entry = (opp, ladder_elo_for_opponent(opp, cal), games)
        if opp.type in engine_types:
            engines.append(entry)
        elif opp.type in harness_types:
            harness.append(entry)
    sort_floating = lambda t: (t[1] is None, -(t[1] or 0))
    engines.sort(key=sort_floating)
    harness.sort(key=sort_floating)

    anchors: List[tuple[Opponent, int, int]] = []
    for opp in catalog.list_opponents():
        if opp.type != "stockfish":
            continue
        anchors.append((opp, opp.elo, 0))
    anchors.sort(key=lambda t: t[1])
    return engines, harness, anchors
