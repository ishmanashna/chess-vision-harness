"""Tests for public-site leaderboard snapshot export."""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chess_harness.accuracy_elo_map import est_elo_from_accuracy, map_path
from chess_harness.models import ModelRegistry
from chess_harness.results import ResultsManager
from chess_harness.snapshot_leaderboard import (
    PROVISIONAL_GAMES_THRESHOLD,
    build_snapshot,
    export_leaderboard_snapshot,
    is_provisional,
)


def _write_warm_map(cal_root, knots, *, engine_count=2):
    cal_root.mkdir(parents=True, exist_ok=True)
    map_path(cal_root).write_text(
        json.dumps(
            {
                "engine_count": engine_count,
                "knots": knots,
                "fitted_at": "2026-01-01T00:00:00.000Z",
            }
        ),
        encoding="utf-8",
    )


def _clear_map_cache():
    import chess_harness.accuracy_elo_map as accuracy_elo_map

    accuracy_elo_map._map_cache = None
    accuracy_elo_map._map_cache_path = None


def test_is_provisional_matches_site_threshold():
    assert is_provisional(0) is True
    assert is_provisional(99) is True
    assert is_provisional(100) is False
    assert PROVISIONAL_GAMES_THRESHOLD == 100


def test_build_snapshot_sorts_and_flags_provisional(tmp_path):
    models_file = tmp_path / "models.json"
    models_file.write_text(
        json.dumps(
            {
                "models": [
                    {"id": "low-elo", "name": "Low Elo", "elo": 520.0},
                    {"id": "high-elo", "name": "High Elo", "elo": 812.4},
                ]
            }
        ),
        encoding="utf-8",
    )
    registry = ModelRegistry(models_file)
    game_counts = {"low-elo": 100, "high-elo": 42}

    snapshot = build_snapshot(
        registry, game_counts, generated_at="2026-07-25T12:00:00.000Z"
    )

    assert snapshot["generated_at"] == "2026-07-25T12:00:00.000Z"
    assert [a["id"] for a in snapshot["agents"]] == ["high-elo", "low-elo"]
    assert snapshot["agents"][0] == {
        "id": "high-elo",
        "name": "High Elo",
        "elo": 812,
        "games": 42,
        "provisional": True,
        "mean_accuracy": None,
        "mean_play_rating": None,
        "quality_games": 0,
    }
    assert snapshot["agents"][1]["provisional"] is False


def test_export_leaderboard_snapshot_writes_file(tmp_path, monkeypatch):
    harness_dir = tmp_path / "harness"
    harness_dir.mkdir()
    models_file = harness_dir / "models.json"
    models_file.write_text(
        json.dumps({"models": [{"id": "solo", "name": "Solo Agent", "elo": 650.0}]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness_dir))

    out = tmp_path / "out" / "leaderboard.json"
    written = export_leaderboard_snapshot(out, registry=ModelRegistry(models_file))

    assert written == out
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["agents"] == [
        {
            "id": "solo",
            "name": "Solo Agent",
            "elo": 650,
            "games": 0,
            "provisional": True,
            "mean_accuracy": None,
            "mean_play_rating": None,
            "quality_games": 0,
        }
    ]
    assert data["generated_at"].endswith("Z")


def _write_results(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def test_aggregate_quality_by_model_rules(tmp_path):
    from chess_harness.game_types import (
        GAME_TYPE_AGENT_VS_AGENT,
        GAME_TYPE_HUMAN_VS_AGENT,
    )

    harness = tmp_path / "harness"
    harness.mkdir()
    models_file = harness / "models.json"
    models_file.write_text(
        json.dumps(
            {
                "models": [
                    {"id": "agent-a", "name": "Agent A", "elo": 700.0},
                    {"id": "agent-b", "name": "Agent B", "elo": 680.0},
                ]
            }
        ),
        encoding="utf-8",
    )
    results_file = harness / "results.jsonl"
    rows = [
        {
            "game_id": "g1",
            "model_name": "agent-a",
            "result": "1-0",
            "accuracy": 80.0,
            "play_rating": 600.0,
        },
        {
            "game_id": "g2",
            "model_name": "agent-a",
            "result": "*",
            "accuracy": 90.0,
        },
        {
            "game_id": "g3",
            "model_name": "agent-a",
            "game_type": GAME_TYPE_HUMAN_VS_AGENT,
            "result": "0-1",
            "accuracy": 70.0,
            "play_rating": None,
        },
        {
            "game_id": "avaa-1",
            "model_name": "agent-a",
            "game_type": GAME_TYPE_AGENT_VS_AGENT,
            "result": "1-0",
            "accuracy": 60.0,
            "play_rating": 500.0,
        },
        {
            "game_id": "avaa-1",
            "model_name": "agent-a",
            "game_type": GAME_TYPE_AGENT_VS_AGENT,
            "result": "1-0",
            "accuracy": 99.0,
            "play_rating": 900.0,
        },
        {
            "game_id": "avaa-1",
            "model_name": "agent-b",
            "game_type": GAME_TYPE_AGENT_VS_AGENT,
            "result": "0-1",
            "accuracy": 88.0,
            "play_rating": 720.0,
        },
    ]
    _write_results(results_file, rows)

    cal_root = tmp_path / "cal"
    knots = [
        {"accuracy": 50.0, "elo": 800.0},
        {"accuracy": 90.0, "elo": 1200.0},
    ]
    _write_warm_map(cal_root, knots)

    rm = ResultsManager(base_dir=str(harness))
    assert rm.count_by_model()["agent-a"] == 3  # Elo count: excludes * and AvH; AvA dupes still count
    agg = rm.aggregate_quality_by_model(cal_root=cal_root)
    mean_a = round((80.0 + 70.0 + 60.0) / 3, 2)
    assert agg["agent-a"] == {
        "quality_games": 3,
        "mean_accuracy": mean_a,
        "mean_play_rating": est_elo_from_accuracy(mean_a, root=cal_root),
    }
    assert agg["agent-b"] == {
        "quality_games": 1,
        "mean_accuracy": 88.0,
        "mean_play_rating": est_elo_from_accuracy(88.0, root=cal_root),
    }


def test_build_snapshot_includes_quality_stats(tmp_path):
    harness = tmp_path / "harness"
    harness.mkdir()
    models_file = harness / "models.json"
    models_file.write_text(
        json.dumps({"models": [{"id": "agent-a", "name": "Agent A", "elo": 700.0}]}),
        encoding="utf-8",
    )
    _write_results(
        harness / "results.jsonl",
        [
            {
                "game_id": "g1",
                "model_name": "agent-a",
                "result": "1-0",
                "accuracy": 90.0,
                "play_rating": 800.0,
            }
        ],
    )

    cal_root = tmp_path / "cal"
    _write_warm_map(
        cal_root,
        [
            {"accuracy": 50.0, "elo": 800.0},
            {"accuracy": 90.0, "elo": 1200.0},
        ],
    )

    registry = ModelRegistry(models_file)
    rm = ResultsManager(base_dir=str(harness))
    snapshot = build_snapshot(
        registry,
        rm.count_by_model(),
        quality_stats=rm.aggregate_quality_by_model(cal_root=cal_root),
    )
    agent = snapshot["agents"][0]
    assert agent["mean_accuracy"] == 90.0
    assert agent["mean_play_rating"] == est_elo_from_accuracy(90.0, root=cal_root)
    assert agent["quality_games"] == 1


def test_estimated_elo_from_current_map_not_frozen_play_rating(tmp_path):
    """Estimated Elo follows the live accuracy→Elo map, not stored play_rating."""
    harness = tmp_path / "harness"
    harness.mkdir()
    models_file = harness / "models.json"
    models_file.write_text(
        json.dumps({"models": [{"id": "agent-a", "name": "Agent A", "elo": 700.0}]}),
        encoding="utf-8",
    )
    _write_results(
        harness / "results.jsonl",
        [
            {
                "game_id": "g1",
                "model_name": "agent-a",
                "result": "1-0",
                "accuracy": 70.0,
                "play_rating": 999.0,
            },
            {
                "game_id": "g2",
                "model_name": "agent-a",
                "result": "0-1",
                "accuracy": 90.0,
                "play_rating": 111.0,
            },
        ],
    )

    cal_root = tmp_path / "cal"
    map_v1 = [
        {"accuracy": 50.0, "elo": 800.0},
        {"accuracy": 90.0, "elo": 1200.0},
    ]
    _write_warm_map(cal_root, map_v1)

    rm = ResultsManager(base_dir=str(harness))
    mean_accuracy = 80.0
    agg_v1 = rm.aggregate_quality_by_model(cal_root=cal_root)
    expected_v1 = est_elo_from_accuracy(mean_accuracy, root=cal_root)
    assert agg_v1["agent-a"]["mean_accuracy"] == mean_accuracy
    assert agg_v1["agent-a"]["mean_play_rating"] == expected_v1
    assert expected_v1 != 555.0  # not average of frozen play_rating fields

    map_v2 = [
        {"accuracy": 50.0, "elo": 900.0},
        {"accuracy": 90.0, "elo": 1500.0},
    ]
    _write_warm_map(cal_root, map_v2)
    _clear_map_cache()

    agg_v2 = rm.aggregate_quality_by_model(cal_root=cal_root)
    expected_v2 = est_elo_from_accuracy(mean_accuracy, root=cal_root)
    assert expected_v2 != expected_v1
    assert agg_v2["agent-a"]["mean_play_rating"] == expected_v2

    registry = ModelRegistry(models_file)
    snapshot = build_snapshot(
        registry,
        rm.count_by_model(),
        quality_stats=agg_v2,
        include_opponents=False,
    )
    assert snapshot["agents"][0]["mean_play_rating"] == expected_v2
