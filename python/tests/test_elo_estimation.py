"""Tests for Phase 4 Elo estimation bake-off."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from chess_harness.elo_estimation import (  # noqa: E402
    ESTIMATOR_IDS,
    champion_id,
    engine_elo_estimations,
    estimation_maps_path,
    fit_all_estimators,
    fit_estimator_knots,
    load_estimation_maps,
    set_champion,
    train_holdout_split,
)
from chess_harness.play_rating import (  # noqa: E402
    MIN_MAP_SAMPLES,
    append_play_rating_sample,
    fit_play_rating_map,
    rewrite_play_rating_samples,
)


def _synthetic_sample(
    i: int,
    *,
    q: float,
    elo: float,
    accuracy: float | None = None,
    acpl: float | None = None,
    q_midgame: float | None = None,
    q_trimmed: float | None = None,
) -> dict:
    return {
        "engine_id": f"engine-{i % 3}",
        "game_index": i,
        "ts": f"2026-01-{(i % 28) + 1:02d}T00:00:00+00:00",
        "q": q,
        "q_midgame": q_midgame if q_midgame is not None else q - 1.0,
        "q_trimmed": q_trimmed if q_trimmed is not None else q + 0.5,
        "calibration_elo_before": elo,
        "accuracy": accuracy if accuracy is not None else 50.0 + q * 0.4,
        "acpl": acpl if acpl is not None else max(10.0, 200.0 - q * 2),
        "blunder_rate": 0.05,
    }


def _write_synthetic_samples(root: Path, n: int = 50) -> None:
    samples = [
        _synthetic_sample(
            i,
            q=10.0 + i * 1.5,
            elo=400.0 + i * 15.0,
        )
        for i in range(n)
    ]
    rewrite_play_rating_samples(samples, root=root)


def test_train_holdout_split_deterministic():
    samples = [_synthetic_sample(i, q=float(i), elo=500.0 + i) for i in range(10)]
    train, holdout = train_holdout_split(samples)
    assert len(train) + len(holdout) == 10
    assert len(holdout) == 2  # 20% of 10
    train2, holdout2 = train_holdout_split(samples)
    assert [s["game_index"] for s in train] == [s["game_index"] for s in train2]
    assert [s["game_index"] for s in holdout] == [s["game_index"] for s in holdout2]


def test_all_estimators_produce_knots(tmp_path: Path):
    root = tmp_path / "results"
    _write_synthetic_samples(root, n=40)
    samples = [
        json.loads(line)
        for line in (root / "continuous" / "play_rating_samples.jsonl").read_text().splitlines()
    ]
    for eid in ESTIMATOR_IDS:
        knots = fit_estimator_knots(samples, eid)
        assert knots, f"{eid} produced no knots"
        ratings = [k["play_rating"] for k in knots]
        assert ratings == sorted(ratings)


def test_fit_all_estimators_writes_maps_no_auto_champion(tmp_path: Path):
    root = tmp_path / "results"
    _write_synthetic_samples(root, n=50)
    payload = fit_all_estimators(root=root)

    maps_path = estimation_maps_path(root)
    assert maps_path.exists()
    loaded = load_estimation_maps(root=root)
    assert loaded is not None
    assert loaded.get("champion") is None
    assert champion_id(root=root) is None

    for eid in ESTIMATOR_IDS:
        est = payload["estimators"][eid]
        if eid == "accuracy_scale":
            assert est["params"]["slope"] is not None
            assert est["params"]["intercept"] is not None
        else:
            assert est["knots"]
        assert est["holdout_n"] > 0
        assert est["holdout_mae"] is not None


def test_fit_all_preserves_explicit_champion(tmp_path: Path):
    root = tmp_path / "results"
    _write_synthetic_samples(root, n=50)
    fit_all_estimators(root=root)
    set_champion("accuracy_only", root=root)
    refit = fit_all_estimators(root=root)
    assert refit["champion"] == "accuracy_only"
    assert champion_id(root=root) == "accuracy_only"


def test_fit_play_rating_map_writes_play_rating_map(tmp_path: Path):
    root = tmp_path / "results"
    for i in range(35):
        append_play_rating_sample(
            _synthetic_sample(i, q=float(i), elo=500.0 + i * 10),
            root=root,
        )
    fit_play_rating_map(root=root)
    assert (root / "continuous" / "play_rating_map.json").exists()


def test_fit_all_deterministic(tmp_path: Path):
    root = tmp_path / "results"
    _write_synthetic_samples(root, n=45)
    first = fit_all_estimators(root=root)
    second = fit_all_estimators(root=root)
    assert first.get("champion") is None
    assert second.get("champion") is None
    for eid in ESTIMATOR_IDS:
        assert first["estimators"][eid]["knots"] == second["estimators"][eid]["knots"]
        assert (
            first["estimators"][eid]["holdout_mae"]
            == second["estimators"][eid]["holdout_mae"]
        )


def test_engine_elo_estimations_shape_and_delta(tmp_path: Path):
    root = tmp_path / "results"
    samples = [
        _synthetic_sample(
            i,
            q=20.0 + i,
            elo=800.0 + i,
            accuracy=70.0 + (i % 5),
            acpl=40.0 + (i % 3),
        )
        for i in range(MIN_MAP_SAMPLES)
    ]
    for s in samples:
        s["engine_id"] = "engine-a"
    rewrite_play_rating_samples(samples, root=root)
    fit_all_estimators(root=root)

    out = engine_elo_estimations(samples, 900, root=root)
    assert set(out) == set(ESTIMATOR_IDS)
    for eid in ESTIMATOR_IDS:
        cell = out[eid]
        assert set(cell) == {"estimate", "delta", "elo_miss"}
        assert cell["estimate"] is not None
        assert cell["elo_miss"] == pytest.approx(cell["estimate"] - 900, abs=0.2)
        # consistency: scatter of single-game preds around mean (not vs Elo)
        assert cell["delta"] is not None
        assert cell["delta"] >= 0


def test_engine_elo_estimations_cold_maps(tmp_path: Path):
    samples = [_synthetic_sample(0, q=10.0, elo=700.0)]
    out = engine_elo_estimations(samples, 800, root=tmp_path / "results")
    for eid in ESTIMATOR_IDS:
        assert out[eid] == {"estimate": None, "delta": None, "elo_miss": None}
