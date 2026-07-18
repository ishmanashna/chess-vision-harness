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


def test_enrich_rating_table_activity_playing():
    rows = enrich_rating_table_activity(
        [{"id": "stockfish-handicap:noise22", "elo": 720, "games": 5, "anchor": False}],
        active=True,
        in_flight_by_engine={"stockfish-handicap:noise22": 2},
    )
    assert rows[0]["playing"] == 2
    assert rows[0]["activity"] == "playing"


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
