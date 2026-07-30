"""Tests for static accuracy→Elo map (Phase 3)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from chess_harness.accuracy_elo_map import (  # noqa: E402
    collect_engine_pairs,
    est_elo_from_accuracy,
    fit_accuracy_elo_knots,
    interpolate_accuracy_elo,
    map_path,
    map_warm,
    rebuild_accuracy_elo_map,
)
from chess_harness.play_rating import append_play_rating_sample, process_calibration_game_quality  # noqa: E402


def test_fit_accuracy_elo_knots_monotone():
    pairs = [
        {"accuracy": 60.0, "elo": 900},
        {"accuracy": 70.0, "elo": 850},
        {"accuracy": 80.0, "elo": 880},
        {"accuracy": 90.0, "elo": 1100},
    ]
    knots = fit_accuracy_elo_knots(pairs)
    assert len(knots) >= 2
    for i in range(len(knots) - 1):
        assert knots[i]["accuracy"] <= knots[i + 1]["accuracy"]
        assert knots[i]["elo"] <= knots[i + 1]["elo"]


def test_interpolate_accuracy_elo_clamps_and_linear():
    knots = [
        {"accuracy": 50.0, "elo": 800.0},
        {"accuracy": 90.0, "elo": 1200.0},
    ]
    assert interpolate_accuracy_elo(knots, 30.0) == pytest.approx(800.0)
    assert interpolate_accuracy_elo(knots, 95.0) == pytest.approx(1200.0)
    assert interpolate_accuracy_elo(knots, 70.0) == pytest.approx(1000.0)


def test_rebuild_and_lookup(tmp_path: Path):
    root = tmp_path / "results"
    calibration = {
        "engine-a": {"id": "engine-a", "elo": 900, "games": 120, "anchor": False},
        "engine-b": {"id": "engine-b", "elo": 1100, "games": 150, "anchor": False},
        "stockfish:0": {"id": "stockfish:0", "elo": 1350, "games": 0, "anchor": True},
    }

    for i in range(5):
        append_play_rating_sample(
            {
                "engine_id": "engine-a",
                "accuracy": 70.0 + i,
                "calibration_elo_before": 900.0,
                "q": 60.0,
            },
            root=root,
        )
        append_play_rating_sample(
            {
                "engine_id": "engine-b",
                "accuracy": 80.0 + i,
                "calibration_elo_before": 1100.0,
                "q": 70.0,
            },
            root=root,
        )
        append_play_rating_sample(
            {
                "engine_id": "stockfish:0",
                "accuracy": 95.0 + i * 0.2,
                "calibration_elo_before": 1350.0,
                "q": 90.0,
            },
            root=root,
        )

    with patch(
        "chess_harness.accuracy_elo_map._calibration_ratings",
        return_value=calibration,
    ):
        pairs = collect_engine_pairs(root=root)
        assert len(pairs) == 3
        assert any(p["engine_id"] == "stockfish:0" and p["elo"] == 1350 for p in pairs)
        payload = rebuild_accuracy_elo_map(root=root)

    assert payload["engine_count"] == 3
    assert map_path(root).exists()
    saved = json.loads(map_path(root).read_text())
    assert saved["knots"]
    assert map_warm(saved)

    est = est_elo_from_accuracy(72.0, root=root)
    assert est is not None
    assert 850 <= est <= 1150
    high = est_elo_from_accuracy(96.0, root=root)
    assert high is not None
    assert high > 1100


def test_lookup_cold_when_few_engines(tmp_path: Path):
    root = tmp_path / "results"
    calibration = {
        "engine-a": {"id": "engine-a", "elo": 900, "games": 120, "anchor": False},
    }
    append_play_rating_sample(
        {"engine_id": "engine-a", "accuracy": 75.0, "calibration_elo_before": 900.0, "q": 60.0},
        root=root,
    )
    with patch(
        "chess_harness.accuracy_elo_map._calibration_ratings",
        return_value=calibration,
    ):
        payload = rebuild_accuracy_elo_map(root=root)
    assert payload["engine_count"] == 1
    assert not map_warm(payload)
    assert est_elo_from_accuracy(75.0, root=root) is None


def test_continuous_play_does_not_rewrite_map(tmp_path: Path, monkeypatch):
    root = tmp_path / "results"
    monkeypatch.setattr("chess_harness.play_rating.samples_path", lambda r=None: root / "continuous" / "play_rating_samples.jsonl")
    monkeypatch.setattr("chess_harness.play_rating.map_path", lambda r=None: root / "continuous" / "play_rating_map.json")

    record = type("R", (), {"updates": [], "game_index": 1})()
    with patch("chess_harness.play_rating.build_samples_for_calibration_game", return_value=[{"q": 1.0}]):
        process_calibration_game_quality(record, "a", "b", ["e2e4"], root=root)

    assert not map_path(root).exists()
