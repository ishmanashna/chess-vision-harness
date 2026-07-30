"""
Elo estimation bake-off: five monotone PWL estimators on continuous floater samples.

Holdout split (deterministic): samples sorted by (game_index, ts); the last 20% are
holdout. Metrics (MAE/RMSE) are written for operator comparison. Champion is **not**
auto-selected — use ``set_champion`` / ``clear_champion`` after calibration review.
Until set, runtime scoring uses baseline A ``q_composite`` / ``play_rating_map.json``.

Estimator C uses negated normalized ACPL (-acpl/100) so higher feature → stronger play.

Never writes ladder Elo / ratings.json.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from .game_quality import ACPL_NORMALIZER
from .play_rating import (
    MIN_MAP_SAMPLES,
    _atomic_write_json,
    _play_rating_lock,
    _read_json_object,
    continuous_fit_lock_path,
    continuous_results_dir,
    fit_map_knots,
    interpolate_map,
    load_samples,
)

ESTIMATOR_IDS: Tuple[str, ...] = (
    "q_composite",
    "accuracy_only",
    "acpl_only",
    "midgame_focus",
    "trimmed_moves",
    "accuracy_scale",
)

ESTIMATOR_SHORT_LABELS: Dict[str, str] = {
    "q_composite": "A",
    "accuracy_only": "B",
    "acpl_only": "C",
    "midgame_focus": "D",
    "trimmed_moves": "E",
    "accuracy_scale": "F",
}

HOLDOUT_FRACTION = 0.20

_estimation_maps_cache: Optional[Dict[str, Any]] = None
_estimation_maps_cache_path: Optional[str] = None

FeatureFn = Callable[[Dict[str, Any]], Optional[float]]


def estimation_maps_path(root: Optional[Path] = None) -> Path:
    return continuous_results_dir(root) / "elo_estimation_maps.json"


def _negated_normalized_acpl(sample: Dict[str, Any]) -> Optional[float]:
    acpl = sample.get("acpl")
    if acpl is None:
        return None
    return -float(acpl) / ACPL_NORMALIZER


ESTIMATOR_FEATURES: Dict[str, FeatureFn] = {
    "q_composite": lambda s: _float_or_none(s.get("q")),
    "accuracy_only": lambda s: _float_or_none(s.get("accuracy")),
    "acpl_only": _negated_normalized_acpl,
    "midgame_focus": lambda s: _float_or_none(s.get("q_midgame")),
    "trimmed_moves": lambda s: _float_or_none(s.get("q_trimmed")),
    "accuracy_scale": lambda s: _float_or_none(s.get("accuracy")),
}

ESTIMATOR_DESCRIPTIONS: Dict[str, str] = {
    "q_composite": "Q = acc − α·nacpl − β·blunder_rate (baseline)",
    "accuracy_only": "accuracy only (PWL map)",
    "acpl_only": "negated normalized ACPL (-acpl/100)",
    "midgame_focus": "composite Q with quiet low-material endings down-weighted",
    "trimmed_moves": "composite Q after dropping top 10% win%-swing plies",
    "accuracy_scale": "accuracy → Elo via fitted linear scale (adapts to samples)",
}


def _float_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    return float(value)


def maps_warm(maps: Optional[Dict[str, Any]]) -> bool:
    return bool(
        maps
        and maps.get("sample_count", 0) >= MIN_MAP_SAMPLES
        and maps.get("fitted_at")
    )


def sample_sort_key(sample: Dict[str, Any]) -> Tuple[Any, ...]:
    return (sample.get("game_index", 0), sample.get("ts", ""))


def train_holdout_split(
    samples: Sequence[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    ordered = sorted(samples, key=sample_sort_key)
    n = len(ordered)
    if n == 0:
        return [], []
    holdout_n = max(1, int(n * HOLDOUT_FRACTION))
    if holdout_n >= n:
        holdout_n = max(1, n // 5)
    split_at = max(1, n - holdout_n)
    return list(ordered[:split_at]), list(ordered[split_at:])


def feature_rows(
    samples: Sequence[Dict[str, Any]], feature_fn: FeatureFn
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for sample in samples:
        x = feature_fn(sample)
        if x is None:
            continue
        rows.append({"q": x, "calibration_elo_before": sample["calibration_elo_before"]})
    return rows


def _mean_feature(samples: Sequence[Dict[str, Any]], feature_fn: FeatureFn) -> Optional[float]:
    vals = [feature_fn(s) for s in samples]
    nums = [v for v in vals if v is not None]
    if not nums:
        return None
    return sum(nums) / len(nums)


def fit_estimator_knots(
    samples: Sequence[Dict[str, Any]], estimator_id: str
) -> List[Dict[str, float]]:
    feature_fn = ESTIMATOR_FEATURES[estimator_id]
    return fit_map_knots(feature_rows(samples, feature_fn))


def holdout_errors(
    knots: Sequence[Dict[str, float]],
    holdout: Sequence[Dict[str, Any]],
    feature_fn: FeatureFn,
) -> List[float]:
    errors: List[float] = []
    for sample in holdout:
        x = feature_fn(sample)
        if x is None:
            continue
        pred = interpolate_map(knots, x)
        if pred is None:
            continue
        errors.append(abs(pred - float(sample["calibration_elo_before"])))
    return errors


def _error_stats(errors: Sequence[float]) -> Dict[str, Optional[float]]:
    if not errors:
        return {"holdout_mae": None, "holdout_rmse": None, "holdout_n": 0}
    mae = sum(errors) / len(errors)
    rmse = (sum(e * e for e in errors) / len(errors)) ** 0.5
    return {
        "holdout_mae": round(mae, 2),
        "holdout_rmse": round(rmse, 2),
        "holdout_n": len(errors),
    }


def fit_linear_accuracy_scale(
    samples: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """OLS: calibration_elo_before ≈ slope * accuracy + intercept (adapts to data)."""
    xs: List[float] = []
    ys: List[float] = []
    for sample in samples:
        acc = sample.get("accuracy")
        elo = sample.get("calibration_elo_before")
        if acc is None or elo is None:
            continue
        xs.append(float(acc))
        ys.append(float(elo))
    if len(xs) < 2:
        return {"kind": "linear", "slope": None, "intercept": None, "n": len(xs)}
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    var_x = sum((x - mean_x) ** 2 for x in xs)
    if var_x <= 0:
        return {"kind": "linear", "slope": 0.0, "intercept": mean_y, "n": n}
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    slope = cov / var_x
    intercept = mean_y - slope * mean_x
    return {
        "kind": "linear",
        "slope": round(slope, 6),
        "intercept": round(intercept, 4),
        "n": n,
    }


def predict_accuracy_scale(accuracy: float, params: Dict[str, Any]) -> Optional[float]:
    slope = params.get("slope")
    intercept = params.get("intercept")
    if slope is None or intercept is None:
        return None
    return float(slope) * float(accuracy) + float(intercept)


def estimator_panel_metrics(
    maps: Optional[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Per-estimator holdout metrics for the calibration status panel."""
    out: Dict[str, Dict[str, Any]] = {}
    estimators = (maps or {}).get("estimators", {})
    for eid in ESTIMATOR_IDS:
        est = estimators.get(eid, {})
        out[eid] = {
            "label": ESTIMATOR_SHORT_LABELS[eid],
            "description": ESTIMATOR_DESCRIPTIONS[eid],
            "holdout_mae": est.get("holdout_mae"),
            "holdout_rmse": est.get("holdout_rmse"),
            "holdout_n": est.get("holdout_n", 0),
        }
    return out


def engine_elo_estimations(
    engine_samples: Sequence[Dict[str, Any]],
    calibrated_elo: int,
    *,
    root: Optional[Path] = None,
) -> Dict[str, Dict[str, Optional[float]]]:
    """Per-estimator mean estimate, consistency (±), and miss vs calibrated Elo.

    For each estimator, predict each sample, then:
    - ``estimate`` — mean of those single-game predictions
    - ``delta`` — population stdev of single-game predictions vs that mean
      (plusminus / consistency; null if fewer than 2 predictions)
    - ``elo_miss`` — ``estimate − calibrated_elo`` (closeness; separate from delta)

    ``delta`` is **not** miss vs Elo. Nulls when maps are cold or features missing.
    """
    import statistics

    empty = {
        eid: {"estimate": None, "delta": None, "elo_miss": None} for eid in ESTIMATOR_IDS
    }
    if not engine_samples:
        return empty

    maps = load_estimation_maps(root=root)
    if not maps_warm(maps):
        return empty

    estimators = maps.get("estimators", {})
    out: Dict[str, Dict[str, Optional[float]]] = {}
    for eid in ESTIMATOR_IDS:
        preds: List[float] = []
        if eid == "accuracy_scale":
            params = estimators.get(eid, {}).get("params") or {}
            for sample in engine_samples:
                acc = sample.get("accuracy")
                if acc is None:
                    continue
                pred = predict_accuracy_scale(float(acc), params)
                if pred is not None:
                    preds.append(float(pred))
        else:
            feature_fn = ESTIMATOR_FEATURES[eid]
            knots = estimators.get(eid, {}).get("knots", [])
            if not knots:
                out[eid] = {"estimate": None, "delta": None, "elo_miss": None}
                continue
            for sample in engine_samples:
                x = feature_fn(sample)
                if x is None:
                    continue
                pred = interpolate_map(knots, x)
                if pred is not None:
                    preds.append(float(pred))
        if not preds:
            out[eid] = {"estimate": None, "delta": None, "elo_miss": None}
            continue
        mean_est = sum(preds) / len(preds)
        consistency = statistics.pstdev(preds) if len(preds) >= 2 else None
        out[eid] = {
            "estimate": round(mean_est, 1),
            "delta": round(consistency, 1) if consistency is not None else None,
            "elo_miss": round(mean_est - calibrated_elo, 1),
        }
    return out


def _write_maps(
    payload: Dict[str, Any], *, root: Optional[Path] = None, _already_locked: bool = False
) -> None:
    out_path = estimation_maps_path(root)

    def _do_write() -> None:
        _atomic_write_json(out_path, payload)

    if _already_locked:
        _do_write()
        return
    with _play_rating_lock(continuous_fit_lock_path(root)):
        _do_write()


def fit_all_estimators(
    *, root: Optional[Path] = None, _already_locked: bool = False
) -> Dict[str, Any]:
    """Fit A–E, evaluate holdout metrics, write elo_estimation_maps.json."""
    existing = load_estimation_maps(root=root)
    prior_champion = existing.get("champion") if existing else None
    if prior_champion is not None and prior_champion not in ESTIMATOR_IDS:
        prior_champion = None

    samples = load_samples(root)
    train, holdout = train_holdout_split(samples)
    estimators: Dict[str, Any] = {}

    for eid in ESTIMATOR_IDS:
        if eid == "accuracy_scale":
            params = fit_linear_accuracy_scale(train)
            errors: List[float] = []
            for sample in holdout:
                acc = sample.get("accuracy")
                elo = sample.get("calibration_elo_before")
                if acc is None or elo is None:
                    continue
                pred = predict_accuracy_scale(float(acc), params)
                if pred is None:
                    continue
                errors.append(abs(pred - float(elo)))
            stats = _error_stats(errors)
            estimators[eid] = {
                "description": ESTIMATOR_DESCRIPTIONS[eid],
                "feature": "accuracy",
                "kind": "linear_scale",
                "params": params,
                "train_count": int(params.get("n") or 0),
                "knots": [],
                **stats,
            }
            continue
        feature_fn = ESTIMATOR_FEATURES[eid]
        train_rows = feature_rows(train, feature_fn)
        knots = fit_map_knots(train_rows) if train_rows else []
        errors = holdout_errors(knots, holdout, feature_fn)
        stats = _error_stats(errors)
        estimators[eid] = {
            "description": ESTIMATOR_DESCRIPTIONS[eid],
            "feature": {
                "q_composite": "q",
                "accuracy_only": "accuracy",
                "acpl_only": "negated_normalized_acpl",
                "midgame_focus": "q_midgame",
                "trimmed_moves": "q_trimmed",
            }[eid],
            "train_count": len(train_rows),
            "knots": knots,
            **stats,
        }

    payload: Dict[str, Any] = {
        "holdout_fraction": HOLDOUT_FRACTION,
        "holdout_split": "sorted by (game_index, ts); last 20%",
        "min_samples": MIN_MAP_SAMPLES,
        "sample_count": len(samples),
        "fitted_at": datetime.now(timezone.utc).isoformat(),
        "champion": prior_champion,
        "estimators": estimators,
    }
    _write_maps(payload, root=root, _already_locked=_already_locked)
    global _estimation_maps_cache, _estimation_maps_cache_path
    _estimation_maps_cache = payload
    _estimation_maps_cache_path = str(estimation_maps_path(root).resolve())
    return payload


def load_estimation_maps(*, root: Optional[Path] = None, force: bool = False) -> Optional[Dict[str, Any]]:
    global _estimation_maps_cache, _estimation_maps_cache_path
    path = estimation_maps_path(root)
    path_key = str(path.resolve()) if path.parent.exists() else str(path)
    if (
        not force
        and _estimation_maps_cache is not None
        and _estimation_maps_cache_path == path_key
    ):
        return _estimation_maps_cache
    data = _read_json_object(path)
    _estimation_maps_cache = data
    _estimation_maps_cache_path = path_key
    return data


def champion_id(*, root: Optional[Path] = None) -> Optional[str]:
    maps = load_estimation_maps(root=root)
    if not maps:
        return None
    champion = maps.get("champion")
    if champion in ESTIMATOR_IDS:
        return champion
    return None


def set_champion(estimator_id: str, *, root: Optional[Path] = None) -> Dict[str, Any]:
    """Operator sets active estimator after reviewing calibration compare."""
    if estimator_id not in ESTIMATOR_IDS:
        raise ValueError(f"Unknown estimator: {estimator_id}")
    maps = load_estimation_maps(root=root)
    if not maps:
        raise RuntimeError("No estimation maps file; fit estimators first")
    maps["champion"] = estimator_id
    maps["champion_set_at"] = datetime.now(timezone.utc).isoformat()
    with _play_rating_lock(continuous_fit_lock_path(root)):
        _write_maps(maps, root=root, _already_locked=True)
    return maps


def clear_champion(*, root: Optional[Path] = None) -> Dict[str, Any]:
    """Revert to baseline A / legacy play-rating map for scoring."""
    maps = load_estimation_maps(root=root)
    if not maps:
        raise RuntimeError("No estimation maps file")
    maps.pop("champion", None)
    maps.pop("champion_set_at", None)
    with _play_rating_lock(continuous_fit_lock_path(root)):
        _write_maps(maps, root=root, _already_locked=True)
    return maps


def estimate_from_maps(
    estimator_id: str,
    feature_value: float,
    *,
    root: Optional[Path] = None,
) -> Optional[float]:
    maps = load_estimation_maps(root=root)
    if not maps_warm(maps):
        return None
    est = maps.get("estimators", {}).get(estimator_id, {})
    knots = est.get("knots", [])
    rating = interpolate_map(knots, feature_value)
    return round(rating, 1) if rating is not None else None
