"""Tests for public-site leaderboard snapshot export."""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chess_harness.accuracy_elo_map import map_path
from chess_harness.models import ModelRegistry
from chess_harness.results import ResultsManager
from chess_harness.snapshot_leaderboard import (
    PROVISIONAL_GAMES_THRESHOLD,
    build_snapshot,
    export_leaderboard_snapshot,
    is_provisional,
)


def _write_warm_map(cal_root, knots):
    cal_root.mkdir(parents=True, exist_ok=True)
    map_path(cal_root).parent.mkdir(parents=True, exist_ok=True)
    map_path(cal_root).write_text(
        json.dumps(
            {
                "engine_count": 2,
                "min_engines": 2,
                "knots": knots,
                "fitted_at": "2026-01-01T00:00:00.000Z",
            }
        ),
        encoding="utf-8",
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
        "puzzle_rating": None,
        "puzzle_deviation": None,
        "puzzle_attempts": 0,
        "puzzle_solves": 0,
        "identify_attempts": 0,
        "identify_mean_accuracy": None,
        "identify_full_position_rate": None,
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
            "puzzle_rating": None,
            "puzzle_deviation": None,
            "puzzle_attempts": 0,
            "puzzle_solves": 0,
            "identify_attempts": 0,
            "identify_mean_accuracy": None,
            "identify_full_position_rate": None,
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
        "mean_play_rating": 550.0,
    }
    assert agg["agent-b"] == {
        "quality_games": 1,
        "mean_accuracy": 88.0,
        "mean_play_rating": 720.0,
    }


def test_snapshot_games_scored_provisional_rated_only(tmp_path, monkeypatch):
    """Display Games includes AvH / same-model AvA; provisional uses rated count only."""
    from chess_harness.game_types import (
        GAME_TYPE_AGENT_VS_AGENT,
        GAME_TYPE_HUMAN_VS_AGENT,
    )
    from chess_harness.snapshot_leaderboard import load_live_leaderboard

    harness = tmp_path / "harness"
    harness.mkdir()
    models_file = harness / "models.json"
    models_file.write_text(
        json.dumps({"models": [{"id": "agent-a", "name": "Agent A", "elo": 700.0}]}),
        encoding="utf-8",
    )
    monkeypatch.setenv("CHESS_HARNESS_DIR", str(harness))

    rows = [
        {
            "game_id": "rated-1",
            "model_name": "agent-a",
            "result": "1-0",
            "skill": 1,
            "agent_color": "WHITE",
        },
        {
            "game_id": "avh-1",
            "model_name": "agent-a",
            "game_type": GAME_TYPE_HUMAN_VS_AGENT,
            "result": "0-1",
            "agent_color": "BLACK",
        },
        {
            "game_id": "same-avaa",
            "model_name": "agent-a",
            "opponent_model": "agent-a",
            "game_type": GAME_TYPE_AGENT_VS_AGENT,
            "result": "1-0",
            "agent_color": "WHITE",
            "rated": False,
        },
        {
            "game_id": "same-avaa",
            "model_name": "agent-a",
            "opponent_model": "agent-a",
            "game_type": GAME_TYPE_AGENT_VS_AGENT,
            "result": "0-1",
            "agent_color": "BLACK",
            "rated": False,
        },
    ]
    _write_results(harness / "results.jsonl", rows)

    rm = ResultsManager(base_dir=str(harness))
    assert rm.count_by_model()["agent-a"] == 1
    assert rm.count_scored_by_model()["agent-a"] == 4

    snap = load_live_leaderboard(
        base_dir=str(harness), registry=ModelRegistry(models_file)
    )
    agent = snap["agents"][0]
    assert agent["games"] == 4
    assert agent["provisional"] is True
    assert isinstance(agent["provisional"], bool)

    # More AvH / same-model AvA must not clear provisional.
    rows.append(
        {
            "game_id": "avh-2",
            "model_name": "agent-a",
            "game_type": GAME_TYPE_HUMAN_VS_AGENT,
            "result": "1-0",
            "agent_color": "WHITE",
        }
    )
    _write_results(harness / "results.jsonl", rows)
    snap2 = load_live_leaderboard(
        base_dir=str(harness), registry=ModelRegistry(models_file)
    )
    assert snap2["agents"][0]["games"] == 5
    assert snap2["agents"][0]["provisional"] is True


def test_build_snapshot_rated_counts_drive_provisional(tmp_path):
    models_file = tmp_path / "models.json"
    models_file.write_text(
        json.dumps({"models": [{"id": "solo", "name": "Solo", "elo": 600.0}]}),
        encoding="utf-8",
    )
    registry = ModelRegistry(models_file)
    snap = build_snapshot(
        registry,
        {"solo": 150},
        rated_counts={"solo": 50},
        include_opponents=False,
    )
    assert snap["agents"][0]["games"] == 150
    assert snap["agents"][0]["provisional"] is True


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
    assert agent["mean_play_rating"] == 800.0
    assert agent["quality_games"] == 1


def test_build_snapshot_merges_puzzle_and_identify_stats(tmp_path):
    models_file = tmp_path / "models.json"
    models_file.write_text(
        json.dumps(
            {
                "models": [
                    {"id": "agent-a", "name": "Agent A", "elo": 700.0},
                    {"id": "agent-b", "name": "Agent B", "elo": 680.0},
                    {"id": "puzzle-only", "name": "Puzzle Only", "elo": 500.0},
                ]
            }
        ),
        encoding="utf-8",
    )
    registry = ModelRegistry(models_file)
    snapshot = build_snapshot(
        registry,
        {"agent-a": 10, "agent-b": 5},
        include_opponents=False,
        puzzle_agents=[
            {"id": "agent-a", "name": "Agent A", "rating": 1650.0, "deviation": 80.0,
             "attempts": 3, "solves": 2, "solve_rate": 0.6667},
            {"id": "puzzle-only", "name": "Puzzle Only", "rating": 1400.0, "deviation": 90.0,
             "attempts": 1, "solves": 1, "solve_rate": 1.0},
        ],
        identify_agents=[
            {"id": "agent-a", "name": "Agent A", "attempts": 4,
             "mean_accuracy": 0.75, "full_position_rate": 0.5},
        ],
    )
    by_id = {a["id"]: a for a in snapshot["agents"]}
    aa = by_id["agent-a"]
    assert aa["puzzle_rating"] == 1650.0
    assert "puzzle_solve_rate" not in aa, "agent rows no longer carry a solve rate"
    assert aa["puzzle_attempts"] == 3 and aa["puzzle_solves"] == 2
    assert aa["identify_attempts"] == 4
    assert aa["identify_mean_accuracy"] == pytest.approx(0.75)
    assert aa["identify_full_position_rate"] == pytest.approx(0.5)
    ab = by_id["agent-b"]
    assert ab["puzzle_rating"] is None and ab["puzzle_attempts"] == 0
    assert ab["identify_attempts"] == 0 and ab["identify_mean_accuracy"] is None
    po = by_id["puzzle-only"]
    assert po["games"] == 0 and po["puzzle_rating"] == 1400.0 and po["elo"] == 500


def test_aggregate_quality_uses_stored_play_rating(tmp_path):
    """Quality aggregation uses canonical stored Q-map ratings, not accuracy-only remapping."""
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
            {"game_id": "g1", "model_name": "agent-a", "result": "1-0", "accuracy": 70.0, "play_rating": 999.0},
            {"game_id": "g2", "model_name": "agent-a", "result": "0-1", "accuracy": 90.0, "play_rating": 111.0},
        ],
    )

    rm = ResultsManager(base_dir=str(harness))
    agg = rm.aggregate_quality_by_model(cal_root=tmp_path / "unused")
    assert agg["agent-a"]["mean_accuracy"] == 80.0
    assert agg["agent-a"]["mean_play_rating"] == 555.0
