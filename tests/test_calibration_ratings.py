"""Calibration ladder: per-game ELO updates."""

import os
import sys

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..", "elo_calibration")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from calibration.ratings import CalibrationLadder, is_anchor  # noqa: E402
from calibration.runner import build_schedule  # noqa: E402
from chess_harness.opponents import OpponentCatalog, get_catalog, reload_catalog  # noqa: E402

from conftest import LOW_OPPONENT, MID_OPPONENT  # noqa: E402

LOW = LOW_OPPONENT
MID = MID_OPPONENT


def test_non_stockfish_starts_at_500():
    ladder = CalibrationLadder()
    assert ladder.initial_rating(LOW) == 500.0
    assert ladder.initial_rating("random") == 500.0


def test_stockfish_anchor_uses_catalog_elo():
    ladder = CalibrationLadder()
    assert ladder.initial_rating("stockfish:0") == 1320.0
    assert ladder.initial_rating("stockfish:5") == 1788.0


def test_harness_gains_elo_beating_stockfish_anchor():
    ladder = CalibrationLadder()
    ladder.ensure_player(MID)
    ladder.ensure_player("stockfish:0")
    before = ladder.get_rating(MID)
    record = ladder.record_game(MID, "stockfish:0", "1-0")
    after = ladder.get_rating(MID)
    assert after > before
    assert ladder.get_rating("stockfish:0") == 1320.0
    assert len(record.updates) == 1
    assert record.updates[0].opponent_id == MID
    assert record.updates[0].elo_delta > 0


def test_both_harness_tiers_update_when_they_play():
    ladder = CalibrationLadder()
    ladder.record_game(LOW, MID, "1-0")
    assert ladder.get_rating(LOW) > 500.0
    assert ladder.get_rating(MID) < 500.0


def test_build_schedule_no_engines():
    suite = {
        "defaults": {"movetime_ms": 100, "max_plies": 200},
        "pairs": [
            {"white": LOW, "black": "stockfish:0", "games": 2, "colors": "alternate"},
        ],
    }
    schedule = build_schedule(suite, seed=1)
    assert len(schedule) == 2
    assert schedule[0].white_id == LOW
    assert schedule[1].white_id == "stockfish:0"


def test_stockfish_handicap_is_floating_not_anchor():
    catalog = get_catalog()
    assert not is_anchor(catalog.get("stockfish-handicap:depth4"))
    assert is_anchor(catalog.get("stockfish:0"))


def test_build_schedule_skips_disabled_opponents(tmp_path, monkeypatch):
    dest = tmp_path / "opponents.json"
    dest.write_text(get_catalog().path.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setenv("OPPONENTS_FILE", str(dest))
    reload_catalog()
    catalog = get_catalog()
    catalog.set_enabled(LOW, False)
    try:
        suite = {
            "defaults": {"movetime_ms": 100, "max_plies": 200},
            "round_robin": {
                "opponents": [LOW, "random"],
                "games_per_pair": 1,
            },
        }
        assert build_schedule(suite, seed=1) == []
    finally:
        reload_catalog()


def test_stockfish_handicap_starts_at_500_in_calibration():
    ladder = CalibrationLadder()
    assert ladder.initial_rating(LOW) == 500.0


def test_depth_harness_in_catalog():
    catalog = get_catalog()
    depth = catalog.get("stockfish-handicap:depth4")
    assert depth.type == "stockfish_harness"
    assert depth.harness["depth"] == 2


def test_calibration_first_game_uses_sliding_k():
    from chess_harness.rating_math import expected_score, k_factor

    ladder = CalibrationLadder()
    ladder.record_game(LOW, MID, "1-0")
    exp = expected_score(500.0, 500.0)
    expected_delta = k_factor(0) * (1.0 - exp)
    actual_delta = ladder.get_rating(LOW) - 500.0
    assert abs(actual_delta - expected_delta) < 0.01
