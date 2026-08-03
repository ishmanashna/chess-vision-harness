"""
Legacy compatibility map for older operator data. Runtime quality scoring uses play_rating.py.

Each eligible engine contributes one (mean_accuracy, Elo) pair from quality
samples. Floaters use calibrated ladder Elo; anchors use fixed catalog Elo.
Monotone piecewise-linear knots are fitted for lookup at game finish.

Never writes ladder Elo / ratings.json. The map changes only via rebuild_accuracy_elo_map.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .paths import project_root
from .play_rating import (
    _atomic_write_json,
    _play_rating_lock,
    _read_json_object,
    fit_map_knots,
    interpolate_map,
    load_samples,
)

MIN_ENGINE_PAIRS = 2

_map_cache: Optional[Dict[str, Any]] = None
_map_cache_path: Optional[str] = None


def results_root(root: Optional[Path] = None) -> Path:
    return root if root is not None else project_root() / "elo_calibration" / "results"


def map_path(root: Optional[Path] = None) -> Path:
    return results_root(root) / "accuracy_elo_map.json"


def fit_lock_path(root: Optional[Path] = None) -> Path:
    return results_root(root) / "accuracy_elo_map.fit"


def _calibration_ratings() -> Dict[str, Dict[str, Any]]:
    from .calibration_view import merge_calibration_ratings

    return merge_calibration_ratings(max_age_sec=None)


def _pair_elo(
    engine_id: str, calibration: Dict[str, Dict[str, Any]]
) -> Optional[int]:
    """Elo Y for the map: calibrated floater Elo, or fixed catalog Elo for anchors."""
    row = calibration.get(engine_id)
    if row and bool(row.get("anchor")):
        return int(row["elo"])
    if row and int(row.get("games", 0)) > 0 and not bool(row.get("anchor")):
        return int(row["elo"])

    from .opponents import get_catalog

    opp = get_catalog().get(engine_id)
    if opp is not None and opp.type == "stockfish":
        return int(opp.elo)
    return None


def collect_engine_pairs(*, root: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Mean move accuracy per eligible engine paired with reference Elo."""
    samples = load_samples(results_root(root))
    calibration = _calibration_ratings()

    buckets: Dict[str, List[float]] = {}
    for sample in samples:
        eid = sample.get("engine_id")
        acc = sample.get("accuracy")
        if not eid or acc is None:
            continue
        buckets.setdefault(str(eid), []).append(float(acc))

    pairs: List[Dict[str, Any]] = []
    for eid, accs in sorted(buckets.items()):
        elo = _pair_elo(eid, calibration)
        if elo is None:
            continue
        mean_accuracy = sum(accs) / len(accs)
        pairs.append(
            {
                "engine_id": eid,
                "accuracy": round(mean_accuracy, 2),
                "elo": elo,
                "sample_count": len(accs),
            }
        )
    return pairs


def fit_accuracy_elo_knots(pairs: Sequence[Dict[str, Any]]) -> List[Dict[str, float]]:
    if not pairs:
        return []
    rows = [
        {"q": float(p["accuracy"]), "calibration_elo_before": float(p["elo"])} for p in pairs
    ]
    return [
        {"accuracy": knot["q"], "elo": knot["play_rating"]}
        for knot in fit_map_knots(rows)
    ]


def interpolate_accuracy_elo(
    knots: Sequence[Dict[str, float]], accuracy: float
) -> Optional[float]:
    if not knots:
        return None
    adapted = [{"q": k["accuracy"], "play_rating": k["elo"]} for k in knots]
    return interpolate_map(adapted, accuracy)


def map_warm(m: Optional[Dict[str, Any]]) -> bool:
    return bool(
        m
        and int(m.get("engine_count", 0)) >= MIN_ENGINE_PAIRS
        and m.get("fitted_at")
        and m.get("knots")
    )


def rebuild_accuracy_elo_map(*, root: Optional[Path] = None) -> Dict[str, Any]:
    """Fit monotone PWL from calibrated floaters and persist accuracy_elo_map.json."""
    global _map_cache, _map_cache_path

    from .calibration_view import invalidate_merge_cache

    out_path = map_path(root)
    pairs = collect_engine_pairs(root=root)
    payload: Dict[str, Any] = {
        "engine_count": len(pairs),
        "min_engines": MIN_ENGINE_PAIRS,
        "fitted_at": datetime.now(timezone.utc).isoformat(),
        "pairs": pairs,
        "knots": fit_accuracy_elo_knots(pairs) if pairs else [],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with _play_rating_lock(fit_lock_path(root)):
        _atomic_write_json(out_path, payload)
    _map_cache = payload
    _map_cache_path = str(out_path.resolve())
    invalidate_merge_cache()
    return payload


def load_accuracy_elo_map(
    *, root: Optional[Path] = None, force: bool = False
) -> Optional[Dict[str, Any]]:
    global _map_cache, _map_cache_path
    path = map_path(root)
    path_key = str(path.resolve()) if path.parent.exists() else str(path)
    if not force and _map_cache is not None and _map_cache_path == path_key:
        return _map_cache
    data = _read_json_object(path)
    _map_cache = data
    _map_cache_path = path_key
    return data


def est_elo_from_accuracy(accuracy: float, *, root: Optional[Path] = None) -> Optional[int]:
    """Lookup estimated Elo for a move-accuracy percentage via the static map."""
    m = load_accuracy_elo_map(root=root)
    if not map_warm(m):
        return None
    rating = interpolate_accuracy_elo(m.get("knots", []), float(accuracy))
    return int(round(rating)) if rating is not None else None


def status_summary(*, root: Optional[Path] = None) -> Dict[str, Any]:
    m = load_accuracy_elo_map(root=root)
    return {
        "engine_count": int(m.get("engine_count", 0)) if m else 0,
        "min_engines": MIN_ENGINE_PAIRS,
        "fitted_at": m.get("fitted_at") if m else None,
        "warm": map_warm(m),
    }
