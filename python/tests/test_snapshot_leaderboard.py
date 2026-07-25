"""Tests for public-site leaderboard snapshot export."""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chess_harness.models import ModelRegistry
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

    snapshot = build_snapshot(registry, game_counts, generated_at="2026-07-25T12:00:00.000Z")

    assert snapshot["generated_at"] == "2026-07-25T12:00:00.000Z"
    assert [a["id"] for a in snapshot["agents"]] == ["high-elo", "low-elo"]
    assert snapshot["agents"][0] == {
        "id": "high-elo",
        "name": "High Elo",
        "elo": 812,
        "games": 42,
        "provisional": True,
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
        }
    ]
    assert data["generated_at"].endswith("Z")
