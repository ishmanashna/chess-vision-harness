"""Statistical helpers for calibration gates."""

from __future__ import annotations


def wilson_ci(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = wins / n
    denom = 1 + z**2 / n
    centre = p + z**2 / (2 * n)
    margin = z * ((p * (1 - p) + z**2 / (4 * n)) / n) ** 0.5
    return (centre - margin) / denom, (centre + margin) / denom
