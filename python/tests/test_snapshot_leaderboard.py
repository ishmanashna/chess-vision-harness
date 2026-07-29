"""Tests for public-site leaderboard snapshot export."""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chess_harness.models import ModelRegistry
from chess_harness.results import ResultsManager
from chess_harness.snapshot_leaderboard import (
    PROVISIONAL_GAMES_THRESHOLD,
    build_snapshot,
    export_leaderboard_snapshot,
    is_provisional,
)


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

    rm = ResultsManager(base_dir=str(harness))
    assert rm.count_by_model()["agent-a"] == 4  # Elo count: includes * and AvA dupes, excludes AvH
    agg = rm.aggregate_quality_by_model()
    assert agg["agent-a"] == {
        "quality_games": 3,
        "mean_accuracy": round((80.0 + 70.0 + 60.0) / 3, 2),
        "mean_play_rating": round((600.0 + 500.0) / 2, 2),
    }
    assert agg["agent-b"] == {
        "quality_games": 1,
        "mean_accuracy": 88.0,
        "mean_play_rating": 720.0,
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

    registry = ModelRegistry(models_file)
    rm = ResultsManager(base_dir=str(harness))
    snapshot = build_snapshot(
        registry,
        rm.count_by_model(),
        quality_stats=rm.aggregate_quality_by_model(),
    )
    agent = snapshot["agents"][0]
    assert agent["mean_accuracy"] == 90.0
    assert agent["mean_play_rating"] == 800.0
    assert agent["quality_games"] == 1
