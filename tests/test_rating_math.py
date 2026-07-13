"""Tests for shared ELO rating math."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chess_harness.rating_math import expected_score, k_factor, update_elo


def test_k_factor_sliding():
    assert k_factor(0) == 64
    assert k_factor(19) == 64
    assert k_factor(20) == 48
    assert k_factor(99) == 48
    assert k_factor(100) == 24


def test_update_elo_new_player_moves_more():
    delta_new = update_elo(500.0, 500.0, 1.0, games_played=0) - 500.0
    delta_veteran = update_elo(500.0, 500.0, 1.0, games_played=100) - 500.0
    assert delta_new > delta_veteran
    assert abs(delta_new - k_factor(0) * (1.0 - expected_score(500.0, 500.0))) < 0.01
