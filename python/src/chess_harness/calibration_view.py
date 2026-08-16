"""Spectator calibration read path: engine Elo, quality samples, and accuracy map.

Calibration layers (never folded into agent ladder Elo):

- **A** Calibrated engine Elo — ``elo_calibration/results/*/ratings.json`` via
  :func:`merge_calibration_ratings` (continuous ``ratings.json`` included).
- **B** Quality samples — ``continuous/play_rating_samples.jsonl`` (aggregates via
  precomputed summary when present).
- **C** Accuracy→Elo map — ``accuracy_elo_map.json`` (Performance column).
- **D** Agent ladder — ``CHESS_HARNESS_DIR`` models/results (unchanged; see ladder APIs).

Serve builds layers A–C from disk on every full status GET. Live activity (continuous
engines, in-flight counts, recent games) overlays from the worker ``status.json`` snapshot
or the in-process manager during tests — not per-request enrich HTTP to the worker.

``merged_ratings.json`` is publish-only (written for exports/commits); runtime reads merge
suite files directly and never treat the merged file as SSOT.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

from .opponents import Opponent, OpponentCatalog, get_catalog
from .paths import project_root


def _results_root() -> Path:
    return project_root() / "elo_calibration" / "results"


_MERGE_CACHE: Optional[Tuple[float, Dict[str, Dict[str, Any]]]] = None
MERGE_CACHE_TTL_SEC = 2.0
_STATUS_CACHE: Optional[Tuple[float, Dict[str, Any]]] = None
STATUS_CACHE_TTL_SEC = 10.0


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


def _recent_games_from_jsonl(games_path: Path, *, tail: int = 20) -> List[Dict[str, Any]]:
    """Parse trailing games.jsonl rows; skip corrupt lines without failing status."""
    try:
        lines = games_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    recent: List[Dict[str, Any]] = []
    skipped = 0
    for line in lines[-tail:]:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            recent.append(json.loads(stripped))
        except json.JSONDecodeError:
            skipped += 1
    if skipped:
        logger.debug("Skipped %d corrupt games.jsonl line(s) in %s", skipped, games_path)
    return recent


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


def enrich_rating_rows_from_snapshot(
    rows: List[Dict[str, Any]],
    snapshot: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Pure enrich: continuous / activity flags from a worker status snapshot."""
    pairing_mode = str(snapshot.get("pairing_mode") or "floaters")
    running = set(snapshot.get("continuous_engines") or [])
    in_flight = snapshot.get("in_flight_by_engine") or {}
    parallel_by = snapshot.get("parallel_by_engine") or {}
    enriched: List[Dict[str, Any]] = []
    for row in rows:
        copy = dict(row)
        if copy.get("anchor") and pairing_mode != "anchors-self":
            copy["continuous"] = False
            copy["can_calibrate"] = False
            copy["playing"] = 0
            copy["activity"] = "anchor"
            enriched.append(copy)
            continue
        eid = copy["id"]
        copy["can_calibrate"] = bool(copy.get("enabled", True))
        copy["continuous"] = eid in running
        copy["parallel"] = int(parallel_by.get(eid, 1))
        playing = int(in_flight.get(eid, 0))
        copy["playing"] = playing
        if playing > 0:
            copy["activity"] = "playing"
        elif copy["continuous"]:
            copy["activity"] = "continuous"
        elif not copy.get("enabled", True):
            copy["activity"] = "disabled"
        else:
            copy["activity"] = "idle"
        enriched.append(copy)
    return enriched


def _read_live_snapshot() -> Dict[str, Any]:
    from .calibration_worker_ipc import calibration_in_process, read_worker_status_snapshot
    from .continuous_calibration import get_continuous_calibration

    if calibration_in_process():
        return get_continuous_calibration().status_payload()
    return read_worker_status_snapshot()


def _live_status_overlay(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    running = set(snapshot.get("continuous_engines") or [])
    in_flight = snapshot.get("in_flight_by_engine") or {}
    recent = list(snapshot.get("recent_games") or [])
    overlay: Dict[str, Any] = {
        "mode": "continuous" if running else "idle",
        "active": bool(running),
        "continuous_engines": sorted(running),
        "parallel_by_engine": dict(snapshot.get("parallel_by_engine") or {}),
        "skipped_games": int(snapshot.get("skipped_games") or 0),
        "workers": len(running),
        "in_progress": sum(int(v) for v in in_flight.values()),
        "in_flight_by_engine": dict(in_flight),
        "updated_at": snapshot.get("updated_at"),
        "process_pool_workers": snapshot.get("process_pool_workers"),
        "pairing_mode": snapshot.get("pairing_mode"),
        "fixed_opponent_id": snapshot.get("fixed_opponent_id"),
        "pairing_opponents": snapshot.get("pairing_opponents") or [],
        "calibratable_engines": snapshot.get("calibratable_engines") or [],
        "pairing_locked": bool(running),
        "parallel_hard_cap": snapshot.get("parallel_hard_cap"),
        "parallel_confirm_above": snapshot.get("parallel_confirm_above"),
        "fleet_parallel_in_use": snapshot.get("fleet_parallel_in_use", 0),
        "fleet_parallel_hard_cap": snapshot.get("fleet_parallel_hard_cap"),
        "fleet_parallel_confirm_above": snapshot.get("fleet_parallel_confirm_above"),
        "suite": "continuous" if running else None,
    }
    if recent:
        overlay["recent_games"] = recent[-30:]
    return overlay


def _attach_worker_health(payload: Dict[str, Any]) -> None:
    from .calibration_worker_ipc import calibration_in_process

    if calibration_in_process():
        return
    from .calibration_supervisor import calibration_worker_error, calibration_worker_healthy

    payload["calibration_worker_ok"] = calibration_worker_healthy()
    worker_err = calibration_worker_error()
    if worker_err:
        payload["calibration_worker_error"] = worker_err


def _recent_games_for_status(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    recent: List[Dict[str, Any]] = list(snapshot.get("recent_games") or [])
    if recent:
        return recent
    root = _results_root()
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
        recent.extend(_recent_games_from_jsonl(games_path))
    return recent


def _build_file_calibration_status(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    running = set(snapshot.get("continuous_engines") or [])
    merge_ttl = 0.5 if running else MERGE_CACHE_TTL_SEC
    calibration = merge_calibration_ratings(max_age_sec=merge_ttl)
    catalog = get_catalog()

    rating_table = build_ladder_rating_table(catalog, calibration)
    rating_table = enrich_rating_rows_from_snapshot(rating_table, snapshot)

    from .accuracy_elo_map import MIN_ENGINE_PAIRS, status_summary as accuracy_map_status
    from .play_rating import play_rating_status_summary

    cal_root = project_root() / "elo_calibration" / "results"
    try:
        play_rating = play_rating_status_summary(root=cal_root)
    except Exception:
        play_rating = {
            "sample_count": 0,
            "min_samples": 30,
        }
    try:
        accuracy_map = accuracy_map_status(root=cal_root)
    except Exception:
        accuracy_map = {}
    by_engine = {row["engine_id"]: row for row in play_rating.get("engines", [])}
    for row in rating_table:
        info = by_engine.get(row["id"])
        if not info:
            row["mean_accuracy"] = None
            row["accuracy_std"] = None
            row["quality_samples"] = 0
            row["play_rating"] = None
            continue
        row["mean_accuracy"] = info.get("mean_accuracy")
        row["accuracy_std"] = info.get("accuracy_std")
        row["quality_samples"] = int(info.get("sample_count") or 0)
        row["play_rating"] = info.get("mean_play_rating")

    recent = _recent_games_for_status(snapshot)
    return {
        "scheduled": 0,
        "completed": 0,
        "rating_table": rating_table,
        "recent_games": recent[-30:],
        "play_rating": {
            "sample_count": play_rating["sample_count"],
            "min_samples": play_rating["min_samples"],
        },
        "accuracy_map": {
            "sample_count": int(accuracy_map.get("engine_count") or 0),
            "min_samples": int(accuracy_map.get("min_engines") or MIN_ENGINE_PAIRS),
            "fitted_at": accuracy_map.get("fitted_at"),
            "warm": bool(accuracy_map.get("warm")),
        },
    }


def get_calibration_status_live() -> Dict[str, Any]:
    """Lightweight poll payload — live activity only (no rating table or quality maps)."""
    from .continuous_calibration import (
        PARALLEL_CONFIRM_ABOVE,
        fleet_parallel_confirm_above,
        fleet_parallel_hard_cap,
        parallel_hard_cap,
    )

    snapshot = _read_live_snapshot()
    payload: Dict[str, Any] = {
        **_live_status_overlay(snapshot),
        "parallel_hard_cap": snapshot.get("parallel_hard_cap") or parallel_hard_cap(),
        "parallel_confirm_above": snapshot.get("parallel_confirm_above")
        or PARALLEL_CONFIRM_ABOVE,
        "fleet_parallel_in_use": snapshot.get("fleet_parallel_in_use", 0),
        "fleet_parallel_hard_cap": snapshot.get("fleet_parallel_hard_cap")
        or fleet_parallel_hard_cap(),
        "fleet_parallel_confirm_above": snapshot.get(
            "fleet_parallel_confirm_above", fleet_parallel_confirm_above()
        ),
    }
    payload.setdefault("recent_games", [])
    _attach_worker_health(payload)
    return payload


def get_calibration_status() -> Dict[str, Any]:
    global _STATUS_CACHE
    now = time.monotonic()
    snapshot = _read_live_snapshot()

    if _STATUS_CACHE is not None:
        cached_at, cached = _STATUS_CACHE
        if now - cached_at < STATUS_CACHE_TTL_SEC:
            payload = {**cached, **_live_status_overlay(snapshot)}
            _attach_worker_health(payload)
            return payload

    file_payload = _build_file_calibration_status(snapshot)
    payload = {**file_payload, **_live_status_overlay(snapshot)}
    _attach_worker_health(payload)
    _STATUS_CACHE = (now, file_payload)
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
