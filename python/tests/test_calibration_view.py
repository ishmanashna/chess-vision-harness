"""Spectator calibration view: merged ratings and status API payload."""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chess_harness.calibration_view import (  # noqa: E402
    calibrated_elo_for,
    enrich_rating_table_activity,
    get_calibration_status,
    ladder_elo_for_opponent,
    merge_calibration_ratings,
    _recent_games_from_jsonl,
)
from chess_harness.opponents import get_catalog  # noqa: E402


@pytest.fixture
def cal_results(tmp_path, monkeypatch):
    from chess_harness.calibration_view import invalidate_merge_cache
    import chess_harness.continuous_calibration as cc

    invalidate_merge_cache()
    cc._manager = None
    root = tmp_path / "elo_calibration" / "results"
    suite_a = root / "suite-a"
    suite_a.mkdir(parents=True)
    (suite_a / "ratings.json").write_text(
        json.dumps(
            {
                "ratings": {"stockfish-handicap:noise10": 956.2, "stockfish-handicap:noise70": 520.0},
                "games_played": {"stockfish-handicap:noise10": 20, "stockfish-handicap:noise70": 2},
            }
        ),
        encoding="utf-8",
    )
    suite_b = root / "suite-b"
    suite_b.mkdir(parents=True)
    (suite_b / "ratings.json").write_text(
        json.dumps(
            {
                "ratings": {"stockfish-handicap:noise10": 980.0, "stockfish-handicap:noise70": 510.0},
                "games_played": {"stockfish-handicap:noise10": 5, "stockfish-handicap:noise70": 10},
            }
        ),
        encoding="utf-8",
    )

    def _project_root():
        return tmp_path

    monkeypatch.setattr(
        "chess_harness.calibration_view.project_root",
        _project_root,
    )
    yield root
    invalidate_merge_cache()
    cc._manager = None


def test_merge_picks_suite_with_most_games(cal_results):
    merged = merge_calibration_ratings(max_age_sec=None)
    assert merged["stockfish-handicap:noise10"]["elo"] == 956
    assert merged["stockfish-handicap:noise10"]["games"] == 20
    assert merged["stockfish-handicap:noise70"]["elo"] == 510
    assert merged["stockfish-handicap:noise70"]["games"] == 10


def test_merge_prefers_suite_with_most_games(cal_results):
    merged_path = cal_results / "merged_ratings.json"
    merged_path.write_text(
        json.dumps(
            {
                "ratings": {
                    "stockfish-handicap:noise10": {
                        "id": "stockfish-handicap:noise10",
                        "elo": 500,
                        "games": 1,
                        "anchor": False,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    merged = merge_calibration_ratings(max_age_sec=None)
    assert merged["stockfish-handicap:noise10"]["elo"] == 956
    assert merged["stockfish-handicap:noise10"]["games"] == 20


def test_stale_merged_file_does_not_hide_suite_data(cal_results):
    """merged_ratings.json cache is ignored; suite files with more games win."""
    merged_path = cal_results / "merged_ratings.json"
    merged_path.write_text(
        json.dumps(
            {
                "ratings": {
                    "stockfish-handicap:noise10": {
                        "id": "stockfish-handicap:noise10",
                        "elo": 1000,
                        "games": 99,
                        "anchor": False,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    merged = merge_calibration_ratings(max_age_sec=None)
    assert merged["stockfish-handicap:noise10"]["elo"] == 956
    assert merged["stockfish-handicap:noise10"]["games"] == 20


def test_calibrated_elo_stockfish_uses_catalog():
    catalog = get_catalog()
    opp = catalog.get("stockfish:0")
    assert calibrated_elo_for(opp, {}) == opp.elo


def test_ladder_elo_prefers_calibration_over_catalog(cal_results):
    catalog = get_catalog()
    opp = catalog.get("stockfish-handicap:noise10")
    assert opp.elo != 956
    assert ladder_elo_for_opponent(opp) == 956


def test_ladder_elo_uncalibrated_floater_uses_default(cal_results):
    catalog = get_catalog()
    opp = catalog.get("stockfish-handicap:noise7")
    assert ladder_elo_for_opponent(opp, {}) == 500


def test_get_calibration_status_idle(cal_results):
    status = get_calibration_status()
    assert status["active"] is False
    assert status["workers"] == 0
    assert any(r["id"] == "stockfish-handicap:noise10" for r in status["rating_table"])
    assert any(r["id"] == "stockfish-handicap:noise7" for r in status["rating_table"])
    harness = next(r for r in status["rating_table"] if r["id"] == "stockfish-handicap:noise7")
    assert harness["uncalibrated"] is True
    assert harness["playing"] == 0
    assert harness["activity"] == "idle"
    assert "play_rating" in status
    assert status["play_rating"]["sample_count"] == 0
    assert "play_rating_map" in status
    assert status["play_rating_map"]["warm"] is False
    assert harness.get("mean_accuracy") is None
    assert harness.get("accuracy_std") is None
    assert "champion" not in status["play_rating"]
    assert "estimators" not in status["play_rating"]
    assert "reliability" not in status["play_rating"]
    assert "warm" not in status["play_rating"]


def test_get_calibration_status_keeps_anchor_rows(cal_results):
    status = get_calibration_status()
    anchors = [r for r in status["rating_table"] if r.get("anchor") is True]
    assert anchors, "anchored engines must appear in the calibration rating table"
    row = anchors[0]
    assert row.get("activity") == "anchor"
    assert row.get("continuous") is False
    assert row.get("can_calibrate") is False


def test_get_calibration_status_anchors_can_calibrate_in_anchors_self(cal_results):
    from chess_harness.calibration_view import invalidate_merge_cache
    from chess_harness.continuous_calibration import get_continuous_calibration

    mgr = get_continuous_calibration()
    mgr.set_pairing_mode("anchors-self")
    try:
        invalidate_merge_cache()
        status = get_calibration_status()
        anchors = [r for r in status["rating_table"] if r.get("anchor") is True]
        assert anchors
        for row in anchors:
            assert row.get("can_calibrate") is True
            assert row.get("activity") == "idle"
            assert row.get("continuous") is False
    finally:
        mgr.set_pairing_mode("floaters")
        invalidate_merge_cache()


def test_get_calibration_status_includes_play_rating_means(cal_results):
    continuous = cal_results / "continuous"
    continuous.mkdir(parents=True)
    samples = continuous / "play_rating_samples.jsonl"
    lines = [
        {
            "engine_id": "stockfish-handicap:noise10",
            "q": 70.0,
            "q_midgame": 69.0,
            "q_trimmed": 71.0,
            "accuracy": 88.0,
            "acpl": 40.0,
            "calibration_elo_before": 900.0,
        },
        {
            "engine_id": "stockfish-handicap:noise10",
            "q": 74.0,
            "q_midgame": 73.0,
            "q_trimmed": 75.0,
            "accuracy": 92.0,
            "acpl": 35.0,
            "calibration_elo_before": 910.0,
        },
    ]
    samples.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    from chess_harness.calibration_view import invalidate_merge_cache

    invalidate_merge_cache()
    status = get_calibration_status()
    row = next(r for r in status["rating_table"] if r["id"] == "stockfish-handicap:noise10")
    assert row["mean_accuracy"] == 90.0
    assert row["quality_samples"] == 2
    assert row.get("accuracy_std") == 2.0
    assert status["play_rating"]["sample_count"] == 2
    assert status["play_rating_map"]["warm"] is False


def test_get_calibration_status_play_rating_map_warm(cal_results):
    from chess_harness.accuracy_elo_map import rebuild_accuracy_elo_map

    continuous = cal_results / "continuous"
    continuous.mkdir(parents=True)
    rows = []
    for i in range(101):
        rows.append(
            {
                "engine_id": "stockfish-handicap:noise10",
                "game_index": i,
                "ts": f"2026-01-01T00:00:{i % 60:02d}+00:00",
                "q": 50.0 + (i % 20),
                "q_midgame": 49.0 + (i % 20),
                "q_trimmed": 51.0 + (i % 20),
                "accuracy": 80.0 + (i % 5),
                "acpl": 30.0 + (i % 3),
                "blunder_rate": 0.05,
                "calibration_elo_before": 900.0 + i,
            }
        )
        rows.append(
            {
                "engine_id": "stockfish-handicap:noise7",
                "game_index": i,
                "ts": f"2026-01-01T00:01:{i % 60:02d}+00:00",
                "q": 40.0 + (i % 20),
                "accuracy": 60.0 + (i % 4),
                "calibration_elo_before": 520.0 + i,
            }
        )
    (continuous / "play_rating_samples.jsonl").write_text(
        "\n".join(json.dumps(x) for x in rows) + "\n",
        encoding="utf-8",
    )
    ratings = {
        "ratings": {
            "stockfish-handicap:noise10": 950.0,
            "stockfish-handicap:noise7": 520.0,
        },
        "games_played": {
            "stockfish-handicap:noise10": 120,
            "stockfish-handicap:noise7": 120,
        },
    }
    (cal_results / "suite-a" / "ratings.json").write_text(
        json.dumps(ratings), encoding="utf-8"
    )
    rebuild_accuracy_elo_map(root=cal_results)
    from chess_harness.calibration_view import invalidate_merge_cache

    invalidate_merge_cache()
    status = get_calibration_status()
    row = next(r for r in status["rating_table"] if r["id"] == "stockfish-handicap:noise10")
    assert row["mean_accuracy"] is not None
    assert row["quality_samples"] == 101
    assert row["play_rating"] is not None
    assert status["play_rating_map"]["warm"] is True
    assert status["play_rating_map"]["sample_count"] == 2
    assert "elo_estimations" not in row
    assert "estimators" not in status["play_rating"]


def test_enrich_rating_table_activity_playing():
    rows = enrich_rating_table_activity(
        [{"id": "stockfish-handicap:noise22", "elo": 720, "games": 5, "anchor": False}],
        active=True,
        in_flight_by_engine={"stockfish-handicap:noise22": 2},
    )
    assert rows[0]["playing"] == 2
    assert rows[0]["activity"] == "playing"


def test_recent_games_from_jsonl_skips_corrupt_lines(tmp_path):
    games = tmp_path / "games.jsonl"
    games.write_text(
        '{"game_index": 1, "white": "a", "black": "b", "result": "1-0"}\n'
        "NOT VALID JSON\n"
        '{"game_index": 2, "white": "c", "black": "d", "result": "0-1"}\n',
        encoding="utf-8",
    )
    recent = _recent_games_from_jsonl(games)
    assert len(recent) == 2
    assert recent[0]["game_index"] == 1
    assert recent[1]["game_index"] == 2


def test_get_calibration_status_skips_corrupt_games_jsonl(cal_results):
    continuous = cal_results / "continuous"
    continuous.mkdir(parents=True)
    (continuous / "games.jsonl").write_text(
        '{"game_index": 1, "white": "a", "black": "b", "result": "1-0"}\n'
        "corrupt tail line\n"
        '{"game_index": 3, "white": "e", "black": "f", "result": "1/2-1/2"}\n',
        encoding="utf-8",
    )
    from chess_harness.calibration_view import invalidate_merge_cache

    invalidate_merge_cache()
    status = get_calibration_status()
    assert len(status["recent_games"]) == 2
    assert any(r["id"] == "stockfish-handicap:noise10" for r in status["rating_table"])
    assert "play_rating" in status
    assert "play_rating_map" in status


def test_get_calibration_status_all_corrupt_games_jsonl_still_builds_ratings(cal_results):
    continuous = cal_results / "continuous"
    continuous.mkdir(parents=True)
    (continuous / "games.jsonl").write_text("garbage\n{broken json\n", encoding="utf-8")
    from chess_harness.calibration_view import invalidate_merge_cache

    invalidate_merge_cache()
    status = get_calibration_status()
    assert status["recent_games"] == []
    assert any(r["id"] == "stockfish-handicap:noise10" for r in status["rating_table"])


def test_get_calibration_status_live(cal_results):
    live = {
        "active": True,
        "suite": "suite-a",
        "workers": 4,
        "scheduled": 20,
        "completed": 3,
        "in_progress": 4,
        "in_flight_by_engine": {"stockfish-handicap:noise10": 1, "stockfish:0": 1},
        "rating_table": [{"id": "stockfish-handicap:noise10", "elo": 900, "games": 3, "anchor": False}],
        "recent_games": [{"game_index": 1, "white": "a", "black": "b", "result": "1-0"}],
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    (cal_results / "live_session.json").write_text("{}", encoding="utf-8")
    status = get_calibration_status()
    assert "rating_table" in status
    assert "continuous_engines" in status
