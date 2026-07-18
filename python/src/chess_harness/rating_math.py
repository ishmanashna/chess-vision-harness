"""Shared ELO update math for agents and engine calibration."""

from __future__ import annotations

import math


def k_factor(games_played: int) -> int:
    """Sliding K by games completed before the current game (tuned for faster convergence)."""
    if games_played < 20:
        return 64
    if games_played < 100:
        return 48
    return 24


def expected_score(rating: float, opponent_rating: float) -> float:
    return 1.0 / (1.0 + math.pow(10, (opponent_rating - rating) / 400.0))


def update_elo(
    rating: float,
    opponent_rating: float,
    score: float,
    *,
    games_played: int = 32,
    k: int | None = None,
) -> float:
    """Update rating after one game. `games_played` is count before this game."""
    factor = k if k is not None else k_factor(games_played)
    exp = expected_score(rating, opponent_rating)
    return rating + factor * (score - exp)
