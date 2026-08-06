"""Self-contained Glicko-2 rating system (greenfield, no external ratings).

Implements the canonical Glicko-2 algorithm from Mark Glickman's paper, in
the rating period it is Lichess's documented approach for rated puzzle
attempts: every attempt is a single "game" between the solver and the
puzzle, and both sides' ratings, deviations and volatilities are updated.

This module is pure math: no filesystem access, no stores, no Elo ladder.
Persistence and attempt semantics live in ``puzzle_ratings``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = [
    "GlickoRating",
    "DEFAULT_RATING",
    "DEFAULT_DEVIATION",
    "DEFAULT_VOLATILITY",
    "MIN_DEVIATION",
    "MAX_DEVIATION",
    "RATING_SCALE",
    "update_rating",
    "rating_to_mu",
    "deviation_to_phi",
]

# Glicko-2 scale: mu = (rating - 1500) / SCALE, phi = deviation / SCALE.
# SCALE = 400 / ln(10); q = ln(10)/400 = 1/SCALE.
RATING_SCALE = 400.0 / math.log(10.0)

DEFAULT_RATING = 1500.0
DEFAULT_DEVIATION = 350.0
DEFAULT_VOLATILITY = 0.06
MIN_DEVIATION = 30.0
MAX_DEVIATION = 350.0
TAU = 0.5  # volatility convergence constraint (Glickman's recommended default)
_EPSILON = 0.000001


def rating_to_mu(rating: float) -> float:
    return (rating - DEFAULT_RATING) / RATING_SCALE


def deviation_to_phi(deviation: float) -> float:
    return deviation / RATING_SCALE


def _from_glicko(mu: float, phi: float) -> tuple[float, float]:
    return DEFAULT_RATING + RATING_SCALE * mu, RATING_SCALE * phi


def _g(phi: float) -> float:
    return 1.0 / math.sqrt(1.0 + 3.0 * phi * phi / (math.pi * math.pi))


def _expected(mu: float, mu_j: float, phi_j: float) -> float:
    return 1.0 / (1.0 + math.exp(-_g(phi_j) * (mu - mu_j)))


def _f(x: float, a: float, delta: float, phi_sq: float, v: float) -> float:
    exp_x = math.exp(x)
    numerator = exp_x * (delta * delta - phi_sq - v - exp_x)
    denominator = 2.0 * (phi_sq + v + exp_x) ** 2
    return numerator / denominator - (x - a) / (TAU * TAU)


def _new_volatility(sigma: float, delta: float, phi_sq: float, v: float) -> float:
    """Find the new volatility sigma' by the Illinois algorithm.

    Converges on the root of f(x); returns exp(A/2) at termination.
    """
    a = math.log(sigma * sigma)

    if delta * delta > phi_sq + v:
        b = math.log(delta * delta - phi_sq - v)
    else:
        k = 1
        b = a - k * TAU
        while _f(b, a, delta, phi_sq, v) < 0.0:
            k += 1
            b = a - k * TAU

    f_a = _f(a, a, delta, phi_sq, v)
    f_b = _f(b, a, delta, phi_sq, v)
    a_lo, a_hi = a, b
    f_lo, f_hi = f_a, f_b

    while abs(a_hi - a_lo) > _EPSILON:
        c = a_lo + (a_lo - a_hi) * f_lo / (f_hi - f_lo)
        f_c = _f(c, a, delta, phi_sq, v)
        if f_c == 0.0:
            a_lo = a_hi = c
            break
        if f_c * f_hi < 0.0:
            a_lo, f_lo = a_hi, f_hi
            a_hi, f_hi = c, f_c
        else:
            f_lo = f_lo / 2.0
            a_hi, f_hi = c, f_c

    return math.exp(a_lo / 2.0)


@dataclass
class GlickoRating:
    """One player's Glicko-2 state (rating, deviation, volatility)."""

    rating: float = DEFAULT_RATING
    deviation: float = DEFAULT_DEVIATION
    volatility: float = DEFAULT_VOLATILITY

    def to_dict(self) -> dict[str, float]:
        return {
            "rating": round(self.rating, 1),
            "deviation": round(self.deviation, 1),
            "volatility": round(self.volatility, 6),
        }


def update_rating(
    player: GlickoRating,
    opponent_rating: float,
    opponent_deviation: float,
    score: float,
) -> GlickoRating:
    """Update one player's rating against a single opponent.

    ``score`` is 1.0 for a win, 0.0 for a loss (Glicko-2 supports halves for
    draws; puzzle attempts never draw). Returns the updated rating.
    """
    mu = rating_to_mu(player.rating)
    phi = deviation_to_phi(player.deviation)
    mu_j = rating_to_mu(opponent_rating)
    phi_j = deviation_to_phi(opponent_deviation)

    g_j = _g(phi_j)
    e_j = _expected(mu, mu_j, phi_j)
    v = 1.0 / (g_j * g_j * e_j * (1.0 - e_j))
    delta = v * g_j * (score - e_j)

    phi_sq = phi * phi
    sigma = _new_volatility(player.volatility, delta, phi_sq, v)

    phi_star = math.sqrt(phi_sq + sigma * sigma)
    phi_new = 1.0 / math.sqrt(1.0 / (phi_star * phi_star) + 1.0 / v)
    mu_new = mu + phi_new * phi_new * g_j * (score - e_j)

    rating, deviation = _from_glicko(mu_new, phi_new)
    deviation = max(MIN_DEVIATION, min(MAX_DEVIATION, deviation))
    return GlickoRating(rating=rating, deviation=deviation, volatility=sigma)