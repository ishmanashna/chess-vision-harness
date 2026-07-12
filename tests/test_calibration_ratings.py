"""Calibration ladder: per-game ELO updates."""

import os
import sys

import pytest

ROOT = os.path.join(os.path.dirname(__file__), "..", "elo_calibration")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from calibration.ratings import CalibrationLadder, is_anchor  # noqa: E402
from calibration.runner import build_schedule  # noqa: E402
from chess_harness.opponents import get_catalog  # noqa: E402


def test_non_stockfish_starts_at_500():
    ladder = CalibrationLadder()
    assert ladder.initial_rating("patricia:500") == 500.0
    assert ladder.initial_rating("minimalchess-0.2") == 500.0


def test_stockfish_anchor_uses_catalog_elo():
    ladder = CalibrationLadder()
    assert ladder.initial_rating("stockfish:0") == 1320.0
    assert ladder.initial_rating("stockfish:5") == 1788.0


def test_patricia_gains_elo_beating_stockfish_anchor():
    ladder = CalibrationLadder()
    ladder.ensure_player("patricia:800")
    ladder.ensure_player("stockfish:0")
    before = ladder.get_rating("patricia:800")
    record = ladder.record_game("patricia:800", "stockfish:0", "1-0")
    after = ladder.get_rating("patricia:800")
    assert after > before
    assert ladder.get_rating("stockfish:0") == 1320.0
    assert len(record.updates) == 1
    assert record.updates[0].opponent_id == "patricia:800"
    assert record.updates[0].elo_delta > 0


def test_both_patricia_tiers_update_when_they_play():
    ladder = CalibrationLadder()
    ladder.record_game("patricia:500", "patricia:800", "1-0")
    assert ladder.get_rating("patricia:500") > 500.0
    assert ladder.get_rating("patricia:800") < 500.0


def test_build_schedule_no_engines():
    suite = {
        "defaults": {"movetime_ms": 100, "max_plies": 200},
        "pairs": [
            {"white": "patricia:800", "black": "stockfish:0", "games": 2, "colors": "alternate"},
        ],
    }
    schedule = build_schedule(suite, seed=1)
    assert len(schedule) == 2
    assert schedule[0].white_id == "patricia:800"
    assert schedule[1].white_id == "stockfish:0"


def test_stockfish_handicap_is_floating_not_anchor():
    catalog = get_catalog()
    assert not is_anchor(catalog.get("stockfish-handicap:depth6"))
    assert is_anchor(catalog.get("stockfish:0"))


def test_stockfish_handicap_starts_at_500_in_calibration():
    ladder = CalibrationLadder()
    assert ladder.initial_rating("stockfish-handicap:blitz50") == 500.0
